# Bilingual AI Customer Support Voice Agent

Deploy-ready FastAPI service for a customer support voice agent that:
- receives inbound calls (Twilio webhook);
- places outbound calls (Twilio API);
- responds dynamically (knowledge + LLM, not static scripts);
- switches automatically between Romanian and English;
- supports plug-and-play skills (sales/support/retention);
- supports business-specific branding + integrations.

## Features

- **Language auto-switch** (`ro`/`en`) per turn.
- **Business customization** (`BUSINESS_NAME`, `AGENT_NAME`, greetings).
- **Skill router** (`sales`, `support`, `retention`) with easy extension.
- **Knowledge lookup** (`knowledge/faq.json`) for grounded answers.
- **DB integration ready** with a default **SQLite** implementation that works out-of-the-box.
- **CRM API connector** for external software.
- **Twilio inbound/outbound endpoints**.
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
  - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_VOICE_EN`, `TWILIO_VOICE_RO`, `TWILIO_DEFAULT_LANGUAGE`
- Integrations:
  - `DATABASE_URL` (defaults to SQLite)
  - `CRM_API_BASE_URL`, `CRM_API_KEY`

---

## Human-like behavior & voice tuning

To make the assistant sound more natural:

```env
TWILIO_VOICE_EN=Polly.Amy-Neural
TWILIO_VOICE_RO=Google.ro-RO-Standard-A
TWILIO_DEFAULT_LANGUAGE=ro-RO
BEHAVIOR_STYLE_EN=Warm, friendly, concise, and natural. Use short sentences and empathy.
BEHAVIOR_STYLE_RO=Cald, prietenos, concis și natural. Folosește propoziții scurte și empatie.
```

Also customize introductions:

```env
GREETING_RO=Bună! Sunt Ana de la Compania X. Mă bucur să te ajut astăzi.
GREETING_EN=Hello! I'm Ana from Company X. Happy to help you today.
```

## Use Groq as AI provider

You can switch from OpenAI to Groq (OpenAI-compatible API):

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1/chat/completions
```

Keep `OPENAI_API_KEY` empty when using Groq.

## Intro-only mode (no Q&A)

If you want the bot to only greet and never answer questions, set:

```env
INTRO_ONLY_MODE=true
```

In this mode, every turn returns only your configured intro (`GREETING_RO` / `GREETING_EN`).

---

## 4) API endpoints

- `GET /health`
- `GET /api/skills`
- `POST /api/simulate-turn`
- `POST /twilio/voice`
- `POST /twilio/outbound`

Example simulate turn:

```bash
curl -X POST http://localhost:8000/api/simulate-turn \
  -H "Content-Type: application/json" \
  -d '{"session_id":"abc","user_text":"Buna, vreau factura"}'
```

---

## 5) Twilio setup

1. Deploy this service publicly (HTTPS).
2. In Twilio Phone Number Voice webhook, set URL to:
   - `https://your-domain.com/twilio/voice`
3. Set method `POST`.
4. Fill Twilio credentials in `.env` for outbound calls.

---

## 6) Plug-and-play skills

Defined in `app/services/agent_skills.py`:
- `sales`
- `support`
- `retention`

To add a new skill:
1. Add class with `can_handle()` + `prompt_instruction()`.
2. Register in `SkillRegistry`.
3. Add tests.

---

## 7) Database + client software integration

- `DatabaseClient` uses SQLite by default (`voice_agent.db`) so deployment works immediately.
- `CRMClient` integrates external software APIs (HubSpot/Salesforce/Zoho/custom).
- `ToolClient` merges DB + CRM context and passes it to the LLM.

For enterprise rollout, replace SQLite implementation with your production DB driver and schema.

---

## 8) Tests

```bash
cd voice_agent
pytest -q
```

If dependencies are unavailable in your environment, run at least syntax validation:

```bash
python -m compileall app
```


## Troubleshooting: Call closes after hello

If the call closes after the first phrase, ensure:

1. Twilio webhook is `POST` to `/twilio/voice`.
2. You redeployed latest version (which includes a Gather+Redirect loop).
3. Trial limitations are handled (verified caller ID).

The new call loop keeps the session open:
- `<Gather ... />`
- fallback `<Redirect ...>/twilio/voice</Redirect>`

Also use more natural voices:

```env
TWILIO_VOICE_EN=Polly.Amy-Neural
TWILIO_VOICE_RO=Google.ro-RO-Standard-A
```


## Troubleshooting: doesn't respond to question (RO)

If user speaks Romanian and agent repeats intro or misses intent:

1. Set `INTRO_ONLY_MODE=false`.
2. Set `TWILIO_DEFAULT_LANGUAGE=ro-RO`.
3. Keep Twilio webhook method as `POST` to `/twilio/voice`.
4. Ensure `OPENAI_API_KEY` is set for AI responses.

The call loop now uses language-aware speech gather to improve recognition.


## Troubleshooting: Twilio says system error after question

This usually happens when generated text contains XML-breaking characters (`&`, `<`, `>`).
The app now escapes TwiML speech text automatically to prevent call drops.

If issue persists:
1. Check Twilio debugger for exact error code.
2. Confirm webhook method is `POST`.
3. Confirm speech gather language is set (`TWILIO_DEFAULT_LANGUAGE=ro-RO` for Romanian-first flows).
