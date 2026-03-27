from html import escape
import re

from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse

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
from app.services.integrations import build_integration_clients
from app.services.knowledge_base import KnowledgeBase, KnowledgeMatch
from app.services.language import LanguageDetector
from app.services.orchestrator import OpenAILLMProvider
from app.services.research import ResearchClient
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
tools = ToolClient(db_client, crm_client, telephony, calendar, research)


def build_intro(language: str) -> str:
    template = settings.greeting_ro if language == "ro" else settings.greeting_en
    return template.format(agent_name=settings.agent_name, business_name=settings.business_name)


def twilio_voice_for_language(language: str) -> str:
    return settings.twilio_voice_ro if language == "ro" else settings.twilio_voice_en


def xml_safe(text: str) -> str:
    return escape(text, quote=False)


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


def build_outbound_message(language: str, skill_name: str | None) -> str:
    if language == "ro":
        if skill_name == "sales":
            return "Revin cu un apel scurt pentru a-ți prezenta oferta potrivită și următorii pași."
        return "Revin cu un apel scurt pentru a continua discuția și a te ajuta mai departe."
    if skill_name == "sales":
        return "I’m calling back with the best-fit offer and the next steps."
    return "I’m calling back shortly so we can continue the conversation."


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
    detection = language_detector.detect(user_text, previous_language=previous_language)
    sessions.upsert_language(session_id, detection.language)
    sessions.append_turn(session_id, "user", user_text)

    if settings.intro_only_mode:
        result = intro_only_response(detection.language, session_id)
        sessions.append_turn(session_id, "assistant", result.answer)
        return result

    context = await tools.get_customer_context(session_id)
    actions: list[dict] = []
    if wants_web_research(user_text):
        url = extract_url(user_text)
        research_result = await (tools.inspect_url(url) if url else tools.search_web(user_text))
        context["research"] = research_result
        actions.append(research_result)

    raw_kb_match = kb.search(user_text, detection.language)
    kb_match = raw_kb_match if should_use_kb_match(user_text, raw_kb_match) else None
    active_skill = skill_registry.resolve(detection.language, user_text)
    skill_instruction = active_skill.prompt_instruction(detection.language) if active_skill else None
    history = sessions.get_recent_turns(session_id)
    handoff = needs_handoff(user_text, kb_match, history)

    phone_number = extract_phone_number(user_text)
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
        if outbound_action is not None:
            answer = build_outbound_confirmation(detection.language, phone_number, outbound_action.get("status", "queued"))
        else:
            answer = await llm.generate(
                user_text,
                detection.language,
                kb_match,
                context,
                skill_instruction,
                history,
            )
        source = "knowledge_base" if kb_match else ("action" if outbound_action else ("research" if actions else "llm"))
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
        return await tools.inspect_url(payload.url)
    if payload.query:
        return await tools.search_web(payload.query)
    return {"status": "error", "message": "Provide either query or url."}


@app.post("/twilio/voice", response_class=PlainTextResponse)
async def twilio_voice(
    CallSid: str = Form(default=""),
    SpeechResult: str = Form(default=""),
) -> str:
    session_id = CallSid or "unknown-call"

    if not SpeechResult:
        lang_code = settings.twilio_default_language
        lang = "ro" if lang_code.startswith("ro") else "en"
        intro = build_intro(lang)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Say voice="{twilio_voice_for_language(lang)}" language="{lang_code}">{xml_safe(intro)}</Say>'
            f"{gather_loop(lang_code)}"
            "</Response>"
        )

    result = await build_turn_response(session_id, SpeechResult)
    lang_code = "ro-RO" if result.language == "ro" else "en-US"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Say voice="{twilio_voice_for_language(result.language)}" language="{lang_code}">'
        f"{xml_safe(result.answer)}</Say>"
        f"{gather_loop(lang_code)}"
        "</Response>"
    )


@app.post("/twilio/outbound")
async def outbound_call(payload: TwilioOutboundRequest) -> dict:
    return await telephony.create_outbound_call(payload.to_number, payload.message, payload.language)
