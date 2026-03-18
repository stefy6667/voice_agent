import hashlib

import httpx

from app.config import settings


class ElevenLabsTTSClient:
    def configured(self) -> bool:
        return bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id_ro)

    def enabled_for_language(self, language: str) -> bool:
        return (
            language == "ro"
            and settings.tts_provider_ro.lower().strip() == "elevenlabs"
            and self.configured()
        )

    async def synthesize(self, text: str, language: str) -> tuple[bytes, str] | None:
        if not self.enabled_for_language(language):
            return None

        voice_id = settings.elevenlabs_voice_id_ro
        output_format = settings.elevenlabs_output_format
        model_id = settings.elevenlabs_model_id
        cache_key = hashlib.sha256(
            f"{voice_id}:{model_id}:{output_format}:{language}:{text}".encode("utf-8")
        ).hexdigest()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Accept": "audio/mpeg",
                },
                params={"output_format": output_format},
                json={
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": 0.35,
                        "similarity_boost": 0.8,
                    },
                },
            )
            response.raise_for_status()
            return response.content, cache_key
