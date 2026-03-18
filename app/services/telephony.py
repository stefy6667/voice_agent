import base64
from html import escape
import httpx

from app.config import settings


class TelephonyService:
    def _basic_auth(self) -> str:
        return base64.b64encode(
            f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode("utf-8")
        ).decode("utf-8")

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

        voice = settings.twilio_voice_ro if language == "ro" else settings.twilio_voice_en
        twiml = (
            f"<Response><Say voice=\"{voice}\" language=\"{'ro-RO' if language == 'ro' else 'en-US'}\">{escape(full_message, quote=False)}</Say>"
            "<Pause length=\"1\"/>"
            "</Response>"
        )
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
