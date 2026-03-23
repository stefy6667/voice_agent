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
    twilio_record_calls: bool = False
    twilio_recording_status_callback: str = ""
    tts_provider_ro: str = "elevenlabs"  # twilio | elevenlabs
    elevenlabs_api_key: str = ""
    # Voice ID - "EXAVITQu4vr4xnSDxMaL" is Sarah (good for Romanian)
    # Alternative Romanian-friendly voices: 
    # - "pNInz6obpgDQGcFmaJgB" (Adam - warm male)
    # - "21m00Tcm4TlvDq8ikWAM" (Rachel - natural female)
    elevenlabs_voice_id_ro: str = "EXAVITQu4vr4xnSDxMaL"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "mp3_44100_128"
    
    # Voice tuning parameters for natural human-like speech
    # stability: 0.5-0.7 for consistent, clear Romanian pronunciation (higher = more stable)
    elevenlabs_stability: float = 0.6
    # similarity_boost: Controls voice matching (0.7-0.8 for natural sound)
    elevenlabs_similarity_boost: float = 0.75
    # style: Expressiveness level (0.3-0.5 for natural emotion without over-acting)
    elevenlabs_style: float = 0.4
    # use_speaker_boost: Enhances clarity and presence
    elevenlabs_use_speaker_boost: bool = True

    # Conversation behavior - optimized for natural, human-like speech
    behavior_style_en: str = "Warm, friendly, and conversational. Speak naturally with varied intonation. Use short sentences. Show genuine empathy. Avoid robotic patterns."
    behavior_style_ro: str = "Cald, prietenos și conversațional. Vorbește natural cu intonație variată. Folosește propoziții scurte. Arată empatie sinceră. Evită tiparele robotice."

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
    website_context_url: str = ""
    website_context_mode: str = "faq_only"  # faq_only | on_demand | always

    # Operations
    human_handoff_number: str = ""
    admin_alert_email: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
