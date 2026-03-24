import re

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import PlainTextResponse, Response
import json

from app.config import settings
from app.models import (
    ResearchRequest,
    ScheduleMeetingRequest,
    SimulateTurnRequest,
    SimulateTurnResponse,
    SmsRequest,
    TwilioOutboundRequest,
)
from app.services.agent_skills import SkillRegistry
from app.services.calendar import CalendarClient
from app.services.event_catalog import EventCatalogClient
from app.services.integrations import build_integration_clients
from app.services.knowledge_base import KnowledgeBase, KnowledgeMatch
from app.services.language import LanguageDetector
from app.services.orchestrator import OpenAILLMProvider
from app.services.research import ResearchClient, UnsafeResearchTargetError
from app.services.session_store import SessionStore
from app.services.telephony import TelephonyService
from app.services.tools import ToolClient

app = FastAPI(title="Bilingual Voice Agent")

language_detector = LanguageDetector()
skill_registry = SkillRegistry()
kb = KnowledgeBase()
llm = OpenAILLMProvider()
sessions = SessionStore()
db_client, crm_client = build_integration_clients()
telephony = TelephonyService()
calendar = CalendarClient()
research = ResearchClient()
event_catalog = EventCatalogClient(settings.events_source_url, settings.events_max_results)
tools = ToolClient(db_client, crm_client, telephony, calendar, research, event_catalog)


def build_intro(language: str) -> str:
    template = settings.greeting_ro if language == "ro" else settings.greeting_en
    return template.format(agent_name=settings.agent_name, business_name=settings.business_name)


def gather_loop(language_code: str) -> str:
    return (
        f'<Gather input="speech" language="{language_code}" action="/twilio/voice" method="POST" timeout="5" speechTimeout="auto" />'
        '<Pause length="1"/>'
        '<Redirect method="POST">/twilio/voice</Redirect>'
    )


def intro_only_response(language: str, session_id: str) -> SimulateTurnResponse:
    intro = build_intro(language)
    sessions.upsert_language(session_id, language)
    return SimulateTurnResponse(
        session_id=session_id,
        language=language,
        answer=intro,
        source="intro_only",
        skill=None,
    )


def needs_handoff(user_text: str, kb_match: KnowledgeMatch | None, history: list[dict[str, str]]) -> bool:
    lower_text = user_text.lower()
    urgent_markers = [
        "lawyer", "legal", "gdpr", "security", "fraud", "complaint", "supervisor", "manager",
        "human", "operator", "chargeback", "refund",
    ]
    repeated_failures = sum(
        1 for turn in history[-4:] if turn["role"] == "assistant" and "detail" in turn["text"].lower()
    ) >= 2
    return any(marker in lower_text for marker in urgent_markers) or (kb_match is None and repeated_failures)


def extract_url(text: str) -> str | None:
    match = re.search(r"https?://\S+", text)
    return match.group(0) if match else None


def wants_web_research(text: str) -> bool:
    lowered = text.lower()
    markers = ["search", "internet", "online", "verify", "check this", "cauta", "caută", "verifica", "verifică", "site", "link"]
    return any(marker in lowered for marker in markers) or bool(extract_url(text))


def extract_phone_number(text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", text)
    if not match:
        return None
    return re.sub(r"[\s\-]", "", match.group(1))


def wants_outbound_call(text: str) -> bool:
    lowered = text.lower()
    markers = ["call me", "call me back", "callback", "sună-mă", "suna-ma", "sunati-ma", "sunăți-mă", "apelati-ma", "apelează-mă", "demo call"]
    return any(marker in lowered for marker in markers)


def wants_event_info(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "event",
        "events",
        "concert",
        "concerte",
        "show",
        "festival",
        "upcoming",
        "ce evenimente",
        "what events",
        "tickets",
        "bilete",
    ]
    return any(marker in lowered for marker in markers)


def should_fetch_events(user_text: str) -> bool:
    if not settings.events_source_url:
        return False
    mode = settings.events_context_mode.lower().strip()
    if mode == "off":
        return False
    if mode == "always":
        return True
    return wants_event_info(user_text)


def wants_ticket_link_sms(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "ticket link",
        "buy ticket",
        "buy tickets",
        "link by sms",
        "send link",
        "trimite link",
        "trimite-mi link",
        "link de bilete",
        "bilet",
        "tickets by sms",
    ]
    return any(marker in lowered for marker in markers)


def build_outbound_message(language: str, skill_name: str | None) -> str:
    if language == "ro":
        if skill_name == "sales":
            return "Revin cu un apel scurt pentru a-ți prezenta oferta potrivită și următorii pași."
        return "Revin cu un apel scurt pentru a continua discuția și a te ajuta mai departe."
    if skill_name == "sales":
        return "I’m calling back with the best-fit offer and the next steps."
    return "I’m calling back shortly so we can continue the conversation."


def build_events_reply(language: str, events_result: dict) -> str:
    events = events_result.get("events", [])
    if not events:
        if language == "ro":
            return "Suntem un business de evenimente și momentan nu am găsit evenimente disponibile pe site. Dacă vrei, verific din nou sau îți pot trimite direct linkul principal de bilete."
        return "We are an event business and I couldn't find available events on the website right now. If you want, I can check again or send you the main ticket link."

    top_events = events[:3]
    if language == "ro":
        parts = []
        for item in top_events:
            date_label = f" — {item['date']}" if item.get("date") else ""
            parts.append(f"{item['title']}{date_label}")
        return (
            "Suntem un business de evenimente și în prezent găzduim următoarele evenimente, ordonate după dată: "
            + "; ".join(parts)
            + ". Dacă vrei, îți trimit imediat pe SMS linkul de cumpărare pentru unul dintre ele."
        )

    parts = []
    for item in top_events:
        date_label = f" — {item['date']}" if item.get("date") else ""
        parts.append(f"{item['title']}{date_label}")
    return (
        "We are an event business and we currently host these events, sorted by date: "
        + "; ".join(parts)
        + ". If you want, I can send you the ticket purchase link by SMS right away."
    )


def build_ticket_link_sms(language: str, event_title: str, event_url: str) -> str:
    if language == "ro":
        return f"Link bilete pentru {event_title}: {event_url}"
    return f"Ticket link for {event_title}: {event_url}"


def wants_sms(text: str) -> bool:
    lowered = text.lower()
    markers = ["sms", "text me", "message me", "trimite-mi sms", "trimite sms", "mesaj", "send me a text"]
    return any(marker in lowered for marker in markers)


def build_sms_message(language: str, skill_name: str | None) -> str:
    if language == "ro":
        if skill_name == "sales":
            return "Salut! Îți trimit pe SMS un rezumat al ofertei și următorii pași pentru demo."
        return "Salut! Îți trimit pe SMS rezumatul discuției și următorii pași."
    if skill_name == "sales":
        return "Hi! I'm sending you an SMS with the offer summary and the next demo steps."
    return "Hi! I'm sending you an SMS with a summary of our discussion and the next steps."


def _recent_user_messages(history: list[dict[str, str]], limit: int = 4) -> list[str]:
    return [turn["text"] for turn in history if turn["role"] == "user"][-limit:]


def _extract_first_match(patterns: list[str], text: str, flags: int = 0) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def extract_reservation_details(history: list[dict[str, str]]) -> dict[str, str]:
    combined = " | ".join(_recent_user_messages(history, limit=6))
    lowered = combined.lower()

    date_value = _extract_first_match(
        [
            r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
            r"\b(?:pe\s+)?(luni|marti|marți|miercuri|joi|vineri|sambata|sâmbătă|duminica|duminică|mâine|maine|today|tomorrow)\b",
        ],
        lowered,
        flags=re.IGNORECASE,
    )
    time_value = _extract_first_match(
        [
            r"\b(?:la|ora)\s+(\d{1,2}[:.]\d{2})\b",
            r"\b(\d{1,2}[:.]\d{2})\b",
        ],
        lowered,
        flags=re.IGNORECASE,
    )
    guests_value = _extract_first_match(
        [
            r"\b(\d+)\s*(?:persoane|persons|people|guests|locuri)\b",
            r"\bmasa\s+pentru\s+(\d+)\b",
            r"\btable for\s+(\d+)\b",
        ],
        lowered,
        flags=re.IGNORECASE,
    )
    name_value = _extract_first_match(
        [
            r"\b(?:numele meu este|ma numesc|mă numesc)\s+([a-zăâîșț\- ]{2,40})\b",
            r"\b(?:my name is|name is)\s+([a-z\- ]{2,40})\b",
        ],
        combined,
        flags=re.IGNORECASE,
    )

    details: dict[str, str] = {"note": " | ".join(_recent_user_messages(history, limit=3))}
    if date_value:
        details["date"] = date_value
    if time_value:
        details["time"] = time_value.replace(".", ":")
    if guests_value:
        details["guests"] = guests_value
    if name_value:
        details["name"] = " ".join(name_value.split())
    return details


def build_dynamic_sms_message(language: str, skill_name: str | None, history: list[dict[str, str]]) -> str:
    details = extract_reservation_details(history)
    note = details.get("note", "")
    reservation_markers = ["rezerv", "restaurant", "masa", "booking", "reservation", "table"]
    is_reservation = any(marker in note.lower() for marker in reservation_markers) or skill_name == "scheduling"

    if is_reservation:
        segments: list[str] = []
        if details.get("date"):
            segments.append(f"data {details['date']}" if language == "ro" else f"date {details['date']}")
        if details.get("time"):
            segments.append(f"ora {details['time']}" if language == "ro" else f"time {details['time']}")
        if details.get("guests"):
            segments.append(
                f"{details['guests']} {'persoane' if language == 'ro' else 'guests'}"
            )
        if details.get("name"):
            segments.append(f"{'numele' if language == 'ro' else 'name'} {details['name']}")

        summary = ", ".join(segments) if segments else note
        if language == "ro":
            return (
                "Confirmare rezervare: "
                f"{summary}. "
                "Dacă vrei să modifici ora sau numărul de persoane, răspunde la acest mesaj."
            )
        return (
            "Reservation confirmation: "
            f"{summary}. "
            "If you want to change the time or party size, reply to this message."
        )

    if note:
        compact_note = note[:220]
        if language == "ro":
            return f"Rezumat conversație: {compact_note}"
        return f"Conversation summary: {compact_note}"

    return build_sms_message(language, skill_name)


def should_fetch_website_context(
    user_text: str,
    kb_match: KnowledgeMatch | None,
    active_skill_name: str | None,
) -> bool:
    if not settings.website_context_url:
        return False
    mode = settings.website_context_mode.lower().strip()
    if mode == "faq_only":
        return False
    lowered = user_text.lower()
    markers = [
        "site",
        "website",
        "menu",
        "pricing",
        "price",
        "product",
        "products",
        "restaurant",
        "reservation",
        "rezervare",
        "detalii",
        "details",
    ]
    explicit_request = wants_web_research(user_text) or any(marker in lowered for marker in markers)
    if mode == "always":
        return kb_match is None
    return kb_match is None and (
        explicit_request
        or active_skill_name in {"sales", "scheduling"}
    )


def build_sms_confirmation(language: str, phone_number: str, status: str) -> str:
    if language == "ro":
        if status == "dry_run":
            return f"Perfect, am pregătit SMS-ul pentru {phone_number}. După ce activezi Twilio, mesajul va pleca automat către numărul de pe care ai sunat."
        return f"Perfect, tocmai am trimis SMS-ul către {phone_number}."
    if status == "dry_run":
        return f"Perfect, I prepared the SMS for {phone_number}. Once Twilio is enabled, it will be sent automatically to the number you called from."
    return f"Perfect, I just sent the SMS to {phone_number}."


def build_outbound_confirmation(language: str, phone_number: str, status: str) -> str:
    if language == "ro":
        if status == "dry_run":
            return f"Perfect, am pregătit un apel de revenire către {phone_number}. După ce activezi credențialele Twilio, apelul va porni automat."
        return f"Perfect, am programat un apel de revenire către {phone_number}. Vei fi contactat în scurt timp."
    if status == "dry_run":
        return f"Perfect, I prepared a callback to {phone_number}. Once Twilio credentials are enabled, the outbound call will run automatically."
    return f"Perfect, I scheduled a callback to {phone_number}. You should receive the call shortly."


def should_use_kb_match(user_text: str, kb_match: KnowledgeMatch | None) -> bool:
    if kb_match is None:
        return False
    lowered = user_text.lower()
    request_markers = [
        "?", "cum", "când", "cand", "unde", "ce", "vreau", "aș vrea", "as vrea", "poți", "poti",
        "help", "how", "when", "where", "can you", "i need", "i want", "please",
    ]
    if kb_match.confidence >= 0.75:
        return True
    return any(marker in lowered for marker in request_markers)


async def build_turn_response(session_id: str, user_text: str) -> SimulateTurnResponse:
    previous_language = sessions.get_language(session_id)
    caller_number = sessions.get_value(session_id, "caller_number")
    detection = language_detector.detect(user_text, previous_language=previous_language)
    sessions.upsert_language(session_id, detection.language)
    sessions.append_turn(session_id, "user", user_text)

    if settings.intro_only_mode:
        result = intro_only_response(detection.language, session_id)
        sessions.append_turn(session_id, "assistant", result.answer)
        return result

    context = await tools.get_customer_context(session_id)
    actions: list[dict] = []
    event_result = None
    if should_fetch_events(user_text):
        event_result = await tools.list_events()
        context["events"] = event_result
        actions.append(event_result)
        top_event = next((item for item in event_result.get("events", []) if item.get("url")), None)
        if top_event:
            sessions.set_value(session_id, "last_event_title", top_event.get("title", "event"))
            sessions.set_value(session_id, "last_event_link", top_event["url"])

    if wants_web_research(user_text):
        url = extract_url(user_text)
        try:
            research_result = await (tools.inspect_url(url) if url else tools.search_web(user_text))
        except UnsafeResearchTargetError as exc:
            research_result = {
                "provider": "url_fetch",
                "configured": True,
                "status": "blocked",
                "message": str(exc),
            }
        context["research"] = research_result
        actions.append(research_result)

    raw_kb_match = kb.search(user_text, detection.language)
    kb_match = raw_kb_match if should_use_kb_match(user_text, raw_kb_match) else None
    active_skill = skill_registry.resolve(detection.language, user_text)
    skill_instruction = active_skill.prompt_instruction(detection.language) if active_skill else None
    history = sessions.get_recent_turns(session_id)

    if should_fetch_website_context(user_text, kb_match, active_skill.name if active_skill else None):
        try:
            website_result = await tools.inspect_url(settings.website_context_url)
        except UnsafeResearchTargetError as exc:
            website_result = {
                "provider": "url_fetch",
                "configured": True,
                "status": "blocked",
                "message": str(exc),
                "url": settings.website_context_url,
            }
        context["website_context"] = website_result
        actions.append(website_result)

    handoff = needs_handoff(user_text, kb_match, history)

    phone_number = extract_phone_number(user_text)
    sms_target = phone_number or caller_number
    sms_action = None
    if sms_target and wants_sms(user_text):
        last_event_link = sessions.get_value(session_id, "last_event_link")
        last_event_title = sessions.get_value(session_id, "last_event_title") or "event"
        sms_message = build_dynamic_sms_message(
            detection.language,
            active_skill.name if active_skill else None,
            history,
        )
        if wants_ticket_link_sms(user_text) and last_event_link:
            sms_message = build_ticket_link_sms(detection.language, last_event_title, last_event_link)
        sms_action = await tools.send_sms(
            sms_target,
            sms_message,
        )
        actions.append(sms_action)

    outbound_action = None
    if phone_number and wants_outbound_call(user_text):
        outbound_action = await telephony.create_outbound_call(
            phone_number,
            build_outbound_message(detection.language, active_skill.name if active_skill else None),
            detection.language,
        )
        actions.append(outbound_action)

    if handoff:
        answer = (
            "Te conectez cu un coleg uman care poate verifica în siguranță acest caz."
            if detection.language == "ro"
            else "I’m routing you to a human teammate who can review this safely."
        )
        source = "handoff"
        citations: list[str] = []
    else:
        if sms_action is not None:
            answer = build_sms_confirmation(detection.language, sms_target, sms_action.get("status", "queued"))
        elif outbound_action is not None:
            answer = build_outbound_confirmation(detection.language, phone_number, outbound_action.get("status", "queued"))
        elif event_result is not None:
            answer = build_events_reply(detection.language, event_result)
        else:
            answer = await llm.generate(
                user_text,
                detection.language,
                kb_match,
                context,
                skill_instruction,
                history,
            )
        source = "knowledge_base" if kb_match else ("action" if (sms_action or outbound_action) else ("events" if event_result is not None else ("research" if actions else "llm")))
        citations = [kb_match.source] if kb_match else []

    sessions.append_turn(session_id, "assistant", answer)
    return SimulateTurnResponse(
        session_id=session_id,
        language=detection.language,
        answer=answer,
        source=source,
        skill=active_skill.name if active_skill else None,
        handoff_recommended=handoff,
        citations=citations,
        actions=actions,
    )


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "app": settings.app_name,
        "environment": settings.environment,
        "business": settings.business_name,
        "skills": len(skill_registry.list_skills()),
        "intro_only_mode": settings.intro_only_mode,
        "google_calendar_configured": calendar.configured(),
        "twilio_sms_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token and (settings.twilio_sms_from_number or settings.twilio_from_number)),
        "web_search_configured": research.configured(),
    }


@app.get("/api/skills")
async def list_skills() -> dict:
    return {"skills": skill_registry.list_skills()}


@app.get("/api/transcript/{session_id}")
async def get_transcript(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "turns": sessions.get_recent_turns(session_id),
        "recordings": sessions.get_recordings(session_id),
        "transcript": sessions.build_transcript_text(session_id),
    }


@app.get("/api/events")
async def get_events() -> dict:
    return await tools.list_events()


@app.post("/api/simulate-turn", response_model=SimulateTurnResponse)
async def simulate_turn(payload: SimulateTurnRequest) -> SimulateTurnResponse:
    return await build_turn_response(payload.session_id, payload.user_text)


@app.post("/api/actions/send-sms")
async def send_sms(payload: SmsRequest) -> dict:
    return await tools.send_sms(payload.to_number, payload.message)


@app.post("/api/actions/schedule-call")
async def schedule_call(payload: ScheduleMeetingRequest) -> dict:
    result = await tools.schedule_meeting(
        attendee_email=payload.attendee_email,
        start_iso=payload.start_iso,
        end_iso=payload.end_iso,
        summary=payload.summary,
        description=payload.description,
    )
    sessions.append_turn(
        payload.session_id,
        "system",
        f"Scheduled meeting for {payload.attendee_email} at {payload.start_iso} with status {result.get('status')}",
    )
    return result


@app.post("/api/actions/research")
async def research_action(payload: ResearchRequest) -> dict:
    if payload.url:
        try:
            return await tools.inspect_url(payload.url)
        except UnsafeResearchTargetError as exc:
            return {"status": "blocked", "provider": "url_fetch", "message": str(exc)}
    if payload.query:
        return await tools.search_web(payload.query)
    return {"status": "error", "message": "Provide either query or url."}


@app.post("/api/actions/import-website-faq")
async def import_website_faq() -> dict:
    if not settings.website_context_url:
        return {"status": "error", "message": "Set WEBSITE_CONTEXT_URL before importing website FAQ content."}

    try:
        website_result = await tools.inspect_url(settings.website_context_url)
    except UnsafeResearchTargetError as exc:
        return {"status": "blocked", "provider": "url_fetch", "message": str(exc)}

    summary = website_result.get("summary") or website_result.get("title") or ""
    title = website_result.get("title") or settings.website_context_url
    generated_items = [
        {
            "id": "website_context_overview_en",
            "language": "en",
            "question": "What does your website say?",
            "answer": summary,
            "source": "website_context",
        },
        {
            "id": "website_services_en",
            "language": "en",
            "question": "What services do you offer?",
            "answer": summary,
            "source": "website_context",
        },
        {
            "id": "website_products_en",
            "language": "en",
            "question": "What do you sell on your website?",
            "answer": summary,
            "source": "website_context",
        },
    ]
    kb.generated_path.write_text(
        json.dumps(generated_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    kb.reload()
    return {
        "status": "ok",
        "provider": "url_fetch",
        "url": settings.website_context_url,
        "title": title,
        "generated_items": len(generated_items),
        "output_path": str(kb.generated_path.relative_to(kb.base_dir)),
    }


@app.post("/twilio/voice", response_class=PlainTextResponse)
async def twilio_voice(
    CallSid: str = Form(default=""),
    SpeechResult: str = Form(default=""),
    From: str = Form(default=""),
) -> str:
    session_id = CallSid or "unknown-call"
    if From:
        sessions.set_value(session_id, "caller_number", From)

    if not SpeechResult:
        lang_code = settings.twilio_default_language
        lang = "ro" if lang_code.startswith("ro") else "en"
        intro = build_intro(lang)
        speech_verb = await telephony.twiml_verb(intro, lang)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response>{speech_verb}"
            f"{gather_loop(lang_code)}"
            "</Response>"
        )

    result = await build_turn_response(session_id, SpeechResult)
    lang_code = "ro-RO" if result.language == "ro" else "en-US"
    speech_verb = await telephony.twiml_verb(result.answer, result.language)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{speech_verb}"
        f"{gather_loop(lang_code)}"
        "</Response>"
    )


@app.post("/twilio/outbound")
async def outbound_call(payload: TwilioOutboundRequest) -> dict:
    return await telephony.create_outbound_call(payload.to_number, payload.message, payload.language)


@app.post("/twilio/recording-status")
async def recording_status(
    CallSid: str = Form(default=""),
    RecordingSid: str = Form(default=""),
    RecordingUrl: str = Form(default=""),
    RecordingStatus: str = Form(default=""),
    RecordingDuration: str = Form(default=""),
) -> dict:
    session_id = CallSid or "unknown-call"
    recording = {
        "recording_sid": RecordingSid,
        "recording_url": RecordingUrl,
        "status": RecordingStatus,
        "duration": RecordingDuration,
    }
    sessions.append_recording(session_id, recording)
    return {"ok": True, "session_id": session_id, "recording": recording}


@app.get("/api/tts/{token}")
async def get_tts_audio(token: str) -> Response:
    item = telephony.audio_store.get(token)
    if item is None:
        raise HTTPException(status_code=404, detail="Audio clip not found or expired.")
    return Response(content=item["content"], media_type=item["media_type"])
