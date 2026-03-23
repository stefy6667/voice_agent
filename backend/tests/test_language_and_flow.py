from fastapi.testclient import TestClient
from pathlib import Path
import tempfile

from app.main import app, kb, research, telephony


client = TestClient(app)


def test_language_switch_romanian():
    res = client.post("/api/simulate-turn", json={"session_id": "1", "user_text": "Buna, vreau factura"})
    assert res.status_code == 200
    body = res.json()
    assert body["language"] == "ro"


def test_language_switch_english():
    res = client.post("/api/simulate-turn", json={"session_id": "2", "user_text": "Hello, I need my invoice"})
    assert res.status_code == 200
    body = res.json()
    assert body["language"] == "en"


def test_skills_endpoint_lists_research():
    res = client.get("/api/skills")
    assert res.status_code == 200
    names = [item["name"] for item in res.json()["skills"]]
    assert "research" in names


def test_skill_selection_sales():
    res = client.post("/api/simulate-turn", json={"session_id": "3", "user_text": "What is your pricing?"})
    assert res.status_code == 200
    assert res.json()["skill"] == "sales"


def test_skill_selection_scheduling():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "meet-1", "user_text": "Te rog programează un apel mâine"},
    )
    assert res.status_code == 200
    assert res.json()["skill"] == "scheduling"


def test_twilio_webhook_xml():
    res = client.post("/twilio/voice", data={"CallSid": "CA123", "SpeechResult": "Buna"})
    assert res.status_code == 200
    assert "<Response><Say" in res.text
    assert "voice=" in res.text
    assert "language=" in res.text
    assert "<Gather" in res.text
    assert "<Redirect" in res.text


def test_health_payload():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "business" in body
    assert "skills" in body
    assert "intro_only_mode" in body
    assert "google_calendar_configured" in body
    assert "twilio_sms_configured" in body
    assert "web_search_configured" in body


def test_intro_only_mode_returns_intro():
    from app.config import settings

    old = settings.intro_only_mode
    settings.intro_only_mode = True
    try:
        res = client.post("/api/simulate-turn", json={"session_id": "99", "user_text": "Ce pret aveti?"})
        assert res.status_code == 200
        body = res.json()
        assert body["source"] == "intro_only"
    finally:
        settings.intro_only_mode = old


def test_kb_answers_include_source_citation():
    assert kb.items, "Knowledge base should be loaded from the project path"
    res = client.post("/api/simulate-turn", json={"session_id": "kb-1", "user_text": "Buna, vreau factura"})
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "knowledge_base"
    assert body["citations"]


def test_ambiguous_language_uses_previous_session_language():
    client.post("/api/simulate-turn", json={"session_id": "sticky", "user_text": "Buna"})
    res = client.post("/api/simulate-turn", json={"session_id": "sticky", "user_text": "invoice"})
    assert res.status_code == 200
    assert res.json()["language"] == "ro"


def test_handoff_for_sensitive_request():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "handoff", "user_text": "I need a human agent for a fraud complaint"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["handoff_recommended"] is True
    assert body["source"] == "handoff"


def test_send_sms_endpoint_dry_run_without_credentials():
    res = client.post(
        "/api/actions/send-sms",
        json={"to_number": "+40123456789", "message": "Confirmare programare"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dry_run"
    assert body["provider"] == "twilio"


def test_schedule_call_endpoint_dry_run_without_google_credentials():
    res = client.post(
        "/api/actions/schedule-call",
        json={
            "session_id": "meet-2",
            "attendee_email": "client@example.com",
            "start_iso": "2026-03-20T10:00:00+02:00",
            "end_iso": "2026-03-20T10:30:00+02:00",
            "summary": "Demo call",
            "description": "Google Meet onboarding",
            "language": "ro",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dry_run"
    assert body["provider"] == "google_calendar"
    assert body["meet_link"]


def test_invoice_follow_up_does_not_repeat_same_kb_answer():
    first = client.post(
        "/api/simulate-turn",
        json={"session_id": "invoice-loop", "user_text": "Buna, vreau factura"},
    )
    second = client.post(
        "/api/simulate-turn",
        json={"session_id": "invoice-loop", "user_text": "Da, dar am nevoie de ajutor cu factura"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["answer"] != first.json()["answer"]
    assert "email" in second.json()["answer"].lower() or "factura" in second.json()["answer"].lower()


def test_research_endpoint_returns_dry_run_without_api_key():
    res = client.post(
        "/api/actions/research",
        json={"query": "latest ecommerce pricing trends"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dry_run"
    assert body["provider"] == "tavily"


def test_simulate_turn_can_trigger_research_skill_naturally():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "research-1", "user_text": "Verifică pe internet https://example.com"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["skill"] == "research"
    assert body["actions"]


def test_twilio_initial_prompt_does_not_include_could_not_hear_reprompt():
    res = client.post("/twilio/voice", data={"CallSid": "CA999", "SpeechResult": ""})
    assert res.status_code == 200
    assert "Nu te-am auzit clar" not in res.text
    assert "I couldn't hear you clearly" not in res.text


def test_mock_chatbot_reply_feels_conversational_when_no_kb_match():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "chatbot-1", "user_text": "Am nevoie de ceva mai bun pentru echipa mea"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "Ai spus" in body["answer"] or "te ajut" in body["answer"]


def test_outbound_endpoint_dry_run_without_credentials():
    res = client.post(
        "/twilio/outbound",
        json={"to_number": "+40123456789", "message": "Te sunam pentru demo", "language": "ro"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dry_run"
    assert body["provider"] == "twilio"


def test_sales_callback_request_creates_outbound_action():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "sales-call", "user_text": "Vreau să cumpăr, sună-mă la +40 712 345 678"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["skill"] == "sales"
    assert body["actions"]
    assert body["actions"][0]["provider"] == "twilio"
    assert "apel" in body["answer"].lower() or "call" in body["answer"].lower()


def test_kb_answer_is_conversational_not_raw_faq_playback():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "kb-chat", "user_text": "Buna, vreau factura"},
    )
    assert res.status_code == 200
    answer = res.json()["answer"]
    assert "Din informațiile pe care le am" in answer or "te pot ajuta" in answer
    assert not answer.startswith("Poți primi factura pe email")


def test_kb_is_not_used_for_non_questional_fact_mention():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "kb-gate", "user_text": "Am plătit factura ieri"},
    )
    assert res.status_code == 200
    assert res.json()["source"] != "knowledge_base"


def test_sms_request_uses_caller_number_from_twilio_context():
    client.post("/twilio/voice", data={"CallSid": "CA-SMS", "From": "+40111222333", "SpeechResult": ""})
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "CA-SMS", "user_text": "Trimite-mi un SMS cu detaliile"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["actions"]
    assert body["actions"][0]["provider"] == "twilio"
    assert body["actions"][0]["to"] == "+40111222333"


def test_demo_reply_is_natural_for_business_niche():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "demo-1", "user_text": "Arată-mi un demo pentru restaurant"},
    )
    assert res.status_code == 200
    answer = res.json()["answer"].lower()
    assert "demo" in answer
    assert "restaurant" in answer


def test_research_endpoint_blocks_localhost_urls():
    res = client.post(
        "/api/actions/research",
        json={"url": "http://localhost/admin"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "blocked"
    assert body["provider"] == "url_fetch"


def test_simulate_turn_blocks_private_url_inspection_cleanly():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "research-blocked", "user_text": "Verifică linkul http://127.0.0.1/test"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["actions"]
    assert body["actions"][0]["status"] == "blocked"


def test_default_romanian_twilio_voice_uses_wavenet():
    from app.config import settings

    assert settings.twilio_voice_ro == "Google.ro-RO-Wavenet-B"


def test_twilio_initial_prompt_uses_elevenlabs_play_for_romanian_when_configured():
    from app.config import settings

    original_api_key = settings.elevenlabs_api_key
    original_provider = settings.tts_provider_ro
    original_method = telephony.tts_client.synthesize

    async def fake_synthesize(text: str, language: str):
        return b"fake-mp3", "cache-key"

    settings.elevenlabs_api_key = "test-key"
    settings.tts_provider_ro = "elevenlabs"
    telephony.tts_client.synthesize = fake_synthesize
    try:
        res = client.post("/twilio/voice", data={"CallSid": "CA-EL-1", "SpeechResult": ""})
        assert res.status_code == 200
        assert "<Play>" in res.text
        assert "/api/tts/" in res.text
    finally:
        telephony.tts_client.synthesize = original_method
        settings.elevenlabs_api_key = original_api_key
        settings.tts_provider_ro = original_provider


def test_tts_audio_endpoint_returns_cached_audio():
    token = telephony.audio_store.put(b"audio-bytes")
    res = client.get(f"/api/tts/{token}")
    assert res.status_code == 200
    assert res.content == b"audio-bytes"
    assert res.headers["content-type"].startswith("audio/mpeg")


def test_sms_request_uses_dynamic_reservation_summary():
    client.post(
        "/twilio/voice",
        data={"CallSid": "CA-RESTO", "From": "+40123456789", "SpeechResult": ""},
    )
    client.post(
        "/api/simulate-turn",
        json={"session_id": "CA-RESTO", "user_text": "Vreau rezervare la restaurant pe 21/03 la 19:30 pentru 4 persoane"},
    )
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "CA-RESTO", "user_text": "Trimite-mi un SMS de confirmare"},
    )
    assert res.status_code == 200
    action = res.json()["actions"][0]
    assert action["provider"] == "twilio"
    assert "21/03" in action["preview_message"]
    assert "19:30" in action["preview_message"]
    assert "4 persoane" in action["preview_message"]


def test_website_context_url_is_used_when_needed():
    from app.config import settings

    original_url = settings.website_context_url
    original_mode = settings.website_context_mode
    original_method = research.inspect_url

    async def fake_inspect(url: str):
        return {
            "provider": "url_fetch",
            "configured": True,
            "status": "ok",
            "url": url,
            "title": "Restaurant menu",
            "summary": "Meniul zilei include paste, pizza și opțiuni vegane.",
        }

    settings.website_context_url = "https://example.com/menu"
    settings.website_context_mode = "on_demand"
    research.inspect_url = fake_inspect
    try:
        res = client.post(
            "/api/simulate-turn",
            json={"session_id": "web-context", "user_text": "Ce opțiuni aveți în meniu pentru restaurant?"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["actions"]
        assert body["actions"][0]["url"] == "https://example.com/menu"
    finally:
        research.inspect_url = original_method
        settings.website_context_url = original_url
        settings.website_context_mode = original_mode


def test_restaurant_demo_reply_is_concrete_and_actionable():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "demo-restaurant", "user_text": "Fă-mi un demo pentru rezervare la restaurant"},
    )
    assert res.status_code == 200
    answer = res.json()["answer"].lower()
    assert "4 persoane" in answer or "4 guests" in answer
    assert "19:30" in answer or "7:30" in answer
    assert "sms" in answer


def test_sales_pricing_question_uses_english_kb_and_mentions_price():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "pricing-en", "user_text": "How much does a personalized AI agent bot cost?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["language"] == "en"
    assert body["source"] == "knowledge_base"
    assert "5000" in body["answer"]
    assert "25" in body["answer"]


def test_sales_demo_question_uses_english_kb_and_stays_natural():
    res = client.post(
        "/api/simulate-turn",
        json={"session_id": "demo-en", "user_text": "How would the demo work for my business?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "knowledge_base"
    assert "demo" in body["answer"].lower()
    assert "business" in body["answer"].lower()


def test_transcript_endpoint_returns_recent_turns():
    client.post(
        "/api/simulate-turn",
        json={"session_id": "transcript-1", "user_text": "Hello, I want a demo"},
    )
    res = client.get("/api/transcript/transcript-1")
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"] == "transcript-1"
    assert body["turns"]
    assert "user:" in body["transcript"]


def test_recording_status_webhook_saves_metadata():
    res = client.post(
        "/twilio/recording-status",
        data={
            "CallSid": "CA-REC-1",
            "RecordingSid": "RE123",
            "RecordingUrl": "https://api.twilio.com/recordings/RE123",
            "RecordingStatus": "completed",
            "RecordingDuration": "42",
        },
    )
    assert res.status_code == 200

    transcript = client.get("/api/transcript/CA-REC-1")
    assert transcript.status_code == 200
    recordings = transcript.json()["recordings"]
    assert recordings
    assert recordings[0]["recording_sid"] == "RE123"


def test_website_context_mode_faq_only_does_not_fetch_site():
    from app.config import settings

    original_url = settings.website_context_url
    original_mode = settings.website_context_mode
    original_method = research.inspect_url

    async def fail_if_called(url: str):
        raise AssertionError(f"inspect_url should not be called in faq_only mode: {url}")

    settings.website_context_url = "https://example.com/menu"
    settings.website_context_mode = "faq_only"
    research.inspect_url = fail_if_called
    try:
        res = client.post(
            "/api/simulate-turn",
            json={"session_id": "faq-only", "user_text": "What products do you sell?"},
        )
        assert res.status_code == 200
    finally:
        research.inspect_url = original_method
        settings.website_context_url = original_url
        settings.website_context_mode = original_mode


def test_import_website_faq_generates_extra_faq_file():
    from app.config import settings

    original_url = settings.website_context_url
    original_generated_path = kb.generated_path
    original_method = research.inspect_url

    async def fake_inspect(url: str):
        return {
            "provider": "url_fetch",
            "configured": True,
            "status": "ok",
            "url": url,
            "title": "AI Agents Website",
            "summary": "We build AI agents and bots for lead generation, support, and booking.",
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        kb.generated_path = Path(tmpdir) / "website_faq.json"
        settings.website_context_url = "https://example.com"
        research.inspect_url = fake_inspect
        try:
            res = client.post("/api/actions/import-website-faq")
            assert res.status_code == 200
            body = res.json()
            assert body["status"] == "ok"
            assert body["generated_items"] == 3
            assert kb.generated_path.exists()
        finally:
            research.inspect_url = original_method
            settings.website_context_url = original_url
            kb.generated_path = original_generated_path
            kb.reload()
