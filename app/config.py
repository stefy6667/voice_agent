from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "voice-agent"
    environment: str = "production"
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"

    # Business customization
    business_name: str = "Your Company"
    business_domain: str = "general support"
    agent_name: str = "Alex"
    greeting_ro: str = "Bună! Sunt {agent_name} de la {business_name}. Cu ce te pot ajuta astăzi?"
    greeting_en: str = "Hello! I'm {agent_name} from {business_name}. How can I help you today?"
    intro_only_mode: bool = False

    # LLM config
    llm_provider: str = "openai"  # openai | groq
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1/chat/completions"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions"

    # Telephony
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_sms_from_number: str = ""
    twilio_voice_en: str = "Polly.Amy-Neural"
    twilio_voice_ro: str = "Google.ro-RO-Wavenet-B"
    tts_provider_ro: str = "elevenlabs"  # twilio | elevenlabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id_ro: str = "EXAVITQu4vr4xnSDxMaL"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "mp3_44100_128"

    # Conversation behavior
    behavior_style_en: str = "Warm, friendly, concise, and natural. Use short sentences and empathy."
    behavior_style_ro: str = "Cald, prietenos, concis și natural. Folosește propoziții scurte și empatie."

    # Speech recognition behavior
    twilio_default_language: str = "ro-RO"

    # Data integrations
    database_url: str = "sqlite:///./voice_agent.db"
    crm_api_base_url: str = ""
    crm_api_key: str = ""

    # Google Calendar / Google Meet
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = "primary"
    google_calendar_timezone: str = "Europe/Bucharest"
    google_calendar_base_url: str = "https://www.googleapis.com/calendar/v3"
    google_oauth_token_url: str = "https://oauth2.googleapis.com/token"

    # Web research
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    web_search_max_results: int = 3

    # Operations
    human_handoff_number: str = ""
    admin_alert_email: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
