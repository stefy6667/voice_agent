from fastapi.testclient import TestClient

from app.main import app


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


def test_skills_endpoint_lists_sales():
    res = client.get("/api/skills")
    assert res.status_code == 200
    names = [item["name"] for item in res.json()["skills"]]
    assert "sales" in names


def test_skill_selection_sales():
    res = client.post("/api/simulate-turn", json={"session_id": "3", "user_text": "What is your pricing?"})
    assert res.status_code == 200
    assert res.json()["skill"] == "sales"


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
