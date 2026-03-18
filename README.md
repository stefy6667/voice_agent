# Bilingual AI Customer Support Voice Agent

Deploy-ready FastAPI service for a customer support voice agent that:
- receives inbound calls (Twilio webhook);
- places outbound calls (Twilio API);
- responds dynamically (knowledge + LLM, not static scripts);
- switches automatically between Romanian and English;
- supports plug-and-play skills (sales/support/retention/scheduling/research);
- can trigger production actions such as Google Meet scheduling, Twilio SMS sending, and natural web research.

## Features

- **Language auto-switch** (`ro`/`en`) per turn.
- **Business customization** (`BUSINESS_NAME`, `AGENT_NAME`, greetings).
- **Skill router** (`sales`, `support`, `retention`, `scheduling`, `research`).
- **Knowledge lookup** (`knowledge/faq.json`) for grounded answers.
- **Research actions** for URL inspection and optional web search.
- **Sales-oriented prompting** for discovery, value framing, and next-step closing.
- **DB integration ready** with a default **SQLite** implementation that works out-of-the-box.
- **CRM API connector** for external software.
- **Twilio inbound/outbound voice** and **Twilio SMS action endpoint**.
- **Google Calendar / Google Meet scheduling endpoint** with dry-run fallback when credentials are missing.
- **Docker deployment** included.

---

## 1) Local run

```bash
cd voice_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## 2) Deploy with Docker

```bash
cd voice_agent
docker build -t voice-agent .
docker run -p 8000:8000 --env-file .env voice-agent
```

If you deploy to Render, a basic `render.yaml` is included.

---

## 3) Required environment variables

Copy `.env.example` and set values:

- App/runtime:
  - `APP_NAME`, `ENVIRONMENT`, `HOST`, `PORT`, `PUBLIC_BASE_URL`
- Business:
  - `BUSINESS_NAME`, `BUSINESS_DOMAIN`, `AGENT_NAME`, `GREETING_RO`, `GREETING_EN`, `INTRO_ONLY_MODE`
- LLM:
  - `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`
- Behavior style:
  - `BEHAVIOR_STYLE_EN`, `BEHAVIOR_STYLE_RO`
- Twilio:
  - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_SMS_FROM_NUMBER`, `TWILIO_VOICE_EN`, `TWILIO_VOICE_RO`, `TWILIO_DEFAULT_LANGUAGE`
  - `TTS_PROVIDER_RO`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID_RO`, `ELEVENLABS_MODEL_ID`, `ELEVENLABS_OUTPUT_FORMAT`
- Integrations:
  - `DATABASE_URL`, `CRM_API_BASE_URL`, `CRM_API_KEY`
- Google Calendar / Meet:
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`, `GOOGLE_CALENDAR_TIMEZONE`
- Web research:
  - `TAVILY_API_KEY`, `TAVILY_BASE_URL`, `WEB_SEARCH_MAX_RESULTS`
- Operations:
  - `HUMAN_HANDOFF_NUMBER`, `ADMIN_ALERT_EMAIL`

---

## Human-like behavior & Romanian voice tuning

```env
TWILIO_VOICE_EN=Polly.Amy-Neural
TWILIO_VOICE_RO=Google.ro-RO-Wavenet-B
TWILIO_DEFAULT_LANGUAGE=ro-RO
TTS_PROVIDER_RO=elevenlabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID_RO=EXAVITQu4vr4xnSDxMaL
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
BEHAVIOR_STYLE_EN=Warm, friendly, concise, and natural. Use short sentences and empathy.
BEHAVIOR_STYLE_RO=Cald, prietenos, concis și natural. Folosește propoziții scurte și empatie.
GREETING_RO=Bună! Sunt Ana de la Compania X. Cu ce te pot ajuta astăzi?
```

When `TTS_PROVIDER_RO=elevenlabs` and `ELEVENLABS_API_KEY` is configured, Romanian Twilio responses are rendered as generated audio clips served from this app and played back to callers via Twilio `<Play>`. If ElevenLabs is not configured, the app falls back to Twilio `<Say>`.

---

## 4) API endpoints

- `GET /health`
- `GET /api/skills`
- `POST /api/simulate-turn`
- `POST /api/actions/send-sms`
- `POST /api/actions/schedule-call`
- `POST /api/actions/research`
- `POST /twilio/voice`
- `POST /twilio/outbound`
- `GET /api/tts/{token}`

### Example simulate turn

```bash
curl -X POST http://localhost:8000/api/simulate-turn \
  -H "Content-Type: application/json" \
  -d '{"session_id":"abc","user_text":"Buna, vreau factura"}'
```

### Example send SMS

```bash
curl -X POST http://localhost:8000/api/actions/send-sms \
  -H "Content-Type: application/json" \
  -d '{"to_number":"+40123456789","message":"Programarea ta a fost confirmată."}'
```

### Example schedule Google Meet / callback

```bash
curl -X POST http://localhost:8000/api/actions/schedule-call \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"abc",
    "attendee_email":"client@example.com",
    "start_iso":"2026-03-20T10:00:00+02:00",
    "end_iso":"2026-03-20T10:30:00+02:00",
    "summary":"Demo call",
    "description":"Google Meet onboarding",
    "language":"ro"
  }'
```

### Example web research

```bash
curl -X POST http://localhost:8000/api/actions/research \
  -H "Content-Type: application/json" \
  -d '{"query":"latest ecommerce pricing trends"}'
```

### Example URL inspection

```bash
curl -X POST http://localhost:8000/api/actions/research \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

If Google credentials are missing, the scheduling endpoint returns a **dry-run** payload with a demo Meet link so you can test the integration flow before wiring production secrets.
If `TAVILY_API_KEY` is missing, search requests return a **dry-run** response, but direct URL inspection still works.

Direct URL inspection accepts only public `http`/`https` targets and blocks `localhost` or private-network addresses to avoid accidental internal fetches.

---

## 5) Twilio setup

1. Deploy this service publicly (HTTPS).
2. In Twilio Phone Number Voice webhook, set URL to `https://your-domain.com/twilio/voice`.
3. Set method `POST`.
4. Fill Twilio credentials in `.env` for outbound calls.
5. Fill `TWILIO_SMS_FROM_NUMBER` if you want SMS actions.
6. For Romanian ElevenLabs playback, set `PUBLIC_BASE_URL` to your public HTTPS hostname and configure `ELEVENLABS_API_KEY`.

---

## 6) Where to “train” the agent

This project does **not** fine-tune a model. In the current implementation, “training” means configuring the agent’s:

1. **Knowledge**:
   - edit `knowledge/faq.json`;
   - replace the simple FAQ matcher with real RAG/vector search for production.
2. **Behavior**:
   - tune `BEHAVIOR_STYLE_RO` / `BEHAVIOR_STYLE_EN`;
   - update the orchestrator prompt and escalation policy.
3. **Actions**:
   - connect real CRM endpoints;
   - provide Google Calendar credentials for Meet scheduling;
   - provide Twilio credentials for voice/SMS;
   - provide Tavily credentials if you want external web search.

For enterprise rollout, move from FAQ JSON to vector search over policy, pricing, contracts, internal support docs, and product content.

---

## 7) Plug-and-play skills

Defined in `app/services/agent_skills.py`:
- `sales`
- `support`
- `retention`
- `scheduling`
- `research`

To add a new skill:
1. Add class with `can_handle()` + `prompt_instruction()`.
2. Register in `SkillRegistry`.
3. Add tests.

---

## 8) Production actions included now

### Send SMS
- Endpoint: `POST /api/actions/send-sms`
- Uses Twilio Messages API when credentials are configured.
- Returns `dry_run` when Twilio SMS credentials are missing.

### Web research / URL verification
- Endpoint: `POST /api/actions/research`
- Uses Tavily search when `TAVILY_API_KEY` is configured.
- Can inspect a URL directly without a Tavily key.

### Schedule Google Meet / calendar callback
- Endpoint: `POST /api/actions/schedule-call`
- Uses Google OAuth refresh-token flow and Calendar Events API.
- Requests a Meet link via `conferenceData.createRequest`.
- Returns `dry_run` when Google credentials are missing.

---

## 9) Database + client software integration

- `DatabaseClient` uses SQLite by default (`voice_agent.db`) so deployment works immediately.
- `CRMClient` integrates external software APIs (HubSpot/Salesforce/Zoho/custom).
- `ToolClient` merges DB + CRM context and now also exposes SMS, calendar, and research actions.

For enterprise rollout, replace SQLite implementation with your production DB driver and schema.

---

## 10) Tests

```bash
cd voice_agent
pytest -q
```

If dependencies are unavailable in your environment, run at least syntax validation:

```bash
python -m compileall app tests
```

---

## 11) Troubleshooting: Romanian flow

If the bot repeats the intro or doesn’t seem Romanian-first:

1. Set `INTRO_ONLY_MODE=false`.
2. Set `TWILIO_DEFAULT_LANGUAGE=ro-RO`.
3. Set `TTS_PROVIDER_RO=elevenlabs` and configure `ELEVENLABS_API_KEY`.
4. Optionally keep `TWILIO_VOICE_RO=Google.ro-RO-Wavenet-B` as the fallback voice.
5. Make sure `PUBLIC_BASE_URL` points to your public HTTPS app URL.
6. Make sure `OPENAI_API_KEY` is set if you want AI-generated answers.

---

## 12) Next production upgrades I recommend

- Replace FAQ-only retrieval with pgvector/Pinecone/Weaviate RAG.
- Add CRM write actions (create ticket, update lead, change booking state).
- Add authenticated admin endpoints and audit logs.
- Add real-time STT/TTS streaming beyond simple Twilio gather loops.
- Add human handoff workflows and notification automations.
