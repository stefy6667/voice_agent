import base64
from html import escape

import httpx

from app.config import settings
from app.services.audio_store import AudioStore
from app.services.tts import ElevenLabsTTSClient


class TelephonyService:
    def __init__(
        self,
        audio_store: AudioStore | None = None,
        tts_client: ElevenLabsTTSClient | None = None,
    ) -> None:
        self.audio_store = audio_store or AudioStore()
        self.tts_client = tts_client or ElevenLabsTTSClient()

    def _basic_auth(self) -> str:
        return base64.b64encode(
            f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode("utf-8")
        ).decode("utf-8")

    async def twiml_verb(self, message: str, language: str) -> str:
        audio_result = await self.tts_client.synthesize(message, language)
        if audio_result is None:
            voice = settings.twilio_voice_ro if language == "ro" else settings.twilio_voice_en
            lang_code = "ro-RO" if language == "ro" else "en-US"
            return (
                f'<Say voice="{voice}" language="{lang_code}">'
                f"{escape(message, quote=False)}</Say>"
            )

        audio_bytes, cache_key = audio_result
        token = self.audio_store.put(audio_bytes)
        return (
            f"<Play>{settings.public_base_url.rstrip('/')}/api/tts/{token}"
            f"?v={cache_key[:12]}</Play>"
        )

    async def create_outbound_call(self, to_number: str, message: str, language: str) -> dict:
        intro = (settings.greeting_ro if language == "ro" else settings.greeting_en).format(
            agent_name=settings.agent_name,
            business_name=settings.business_name,
        )
        full_message = f"{intro} {message}".strip()

        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            return {
                "provider": "twilio",
                "account_configured": False,
                "to": to_number,
                "language": language,
                "business": settings.business_name,
                "preview_message": full_message,
                "status": "dry_run",
            }

        speech_verb = await self.twiml_verb(full_message, language)
        twiml = f"<Response>{speech_verb}<Pause length=\"1\"/></Response>"
        auth = self._basic_auth()

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json",
                headers={"Authorization": f"Basic {auth}"},
                data={
                    "To": to_number,
                    "From": settings.twilio_from_number,
                    "Twiml": twiml,
                },
            )
            response.raise_for_status()
            body = response.json()

        return {
            "provider": "twilio",
            "account_configured": True,
            "to": to_number,
            "language": language,
            "business": settings.business_name,
            "status": body.get("status", "queued"),
            "sid": body.get("sid"),
        }

    async def send_sms(self, to_number: str, message: str) -> dict:
        from_number = settings.twilio_sms_from_number or settings.twilio_from_number
        if not (settings.twilio_account_sid and settings.twilio_auth_token and from_number):
            return {
                "provider": "twilio",
                "account_configured": False,
                "to": to_number,
                "from": from_number,
                "preview_message": message,
                "status": "dry_run",
            }

        auth = self._basic_auth()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                headers={"Authorization": f"Basic {auth}"},
                data={
                    "To": to_number,
                    "From": from_number,
                    "Body": message,
                },
            )
            response.raise_for_status()
            body = response.json()

        return {
            "provider": "twilio",
            "account_configured": True,
            "to": to_number,
            "from": from_number,
            "status": body.get("status", "queued"),
            "sid": body.get("sid"),
        }
