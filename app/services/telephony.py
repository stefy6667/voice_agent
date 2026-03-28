"""
telephony.py — TelephonyService complet

FIX-URI:
1. ElevenLabs eroare silentioasa -> fallback la <Say> cu log clar
2. PUBLIC_BASE_URL gresit -> eroare explicita
3. send_sms metoda adaugata (lipsea)
4. Cifre si date pronuntate corect in romana (pentru <Say> fallback)
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


_UNITS = ["", "unu", "doi", "trei", "patru", "cinci", "sase", "sapte", "opt", "noua",
          "zece", "unsprezece", "doisprezece", "treisprezece", "paisprezece", "cincisprezece",
          "saisprezece", "saptesprezece", "optsprezece", "nouasprezece"]
_TENS = ["", "", "douazeci", "treizeci", "patruzeci", "cincizeci",
         "saizeci", "saptezeci", "optzeci", "nouazeci"]


def _int_to_ro(n: int) -> str:
    if n < 0:
        return "minus " + _int_to_ro(-n)
    if n == 0:
        return "zero"
    if n < 20:
        return _UNITS[n]
    if n < 100:
        tens = _TENS[n // 10]
        unit = _UNITS[n % 10]
        return tens + (" si " + unit if unit else "")
    if n < 1000:
        hundreds = n // 100
        rest = n % 100
        h = ("o suta" if hundreds == 1 else _UNITS[hundreds] + " sute")
        return h + (" " + _int_to_ro(rest) if rest else "")
    if n < 1_000_000:
        thousands = n // 1000
        rest = n % 1000
        t = ("o mie" if thousands == 1 else _int_to_ro(thousands) + " mii")
        return t + (" " + _int_to_ro(rest) if rest else "")
    return str(n)


def _replace_numbers_ro(text: str) -> str:
    months_ro = ["", "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
                 "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie"]

    def replace_date(m: re.Match) -> str:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            month_name = months_ro[month] if 1 <= month <= 12 else str(month)
            return f"{_int_to_ro(day)} {month_name} {_int_to_ro(year)}"
        except Exception:
            return m.group(0)

    def replace_time(m: re.Match) -> str:
        try:
            h, mi = int(m.group(1)), int(m.group(2))
            result = _int_to_ro(h)
            if mi:
                result += " si " + _int_to_ro(mi)
            return result
        except Exception:
            return m.group(0)

    def replace_number(m: re.Match) -> str:
        try:
            return _int_to_ro(int(m.group(0)))
        except Exception:
            return m.group(0)

    text = re.sub(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", replace_date, text)
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", replace_time, text)
    text = re.sub(r"\b\d{1,6}\b", replace_number, text)
    return text


class AudioStore:
    TTL_SECONDS = 300

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def put(self, content: bytes, media_type: str) -> str:
        token = secrets.token_urlsafe(24)
        self._store[token] = {
            "content": content,
            "media_type": media_type,
            "created_at": time.monotonic(),
        }
        self._evict_expired()
        return token

    def get(self, token: str) -> dict[str, Any] | None:
        item = self._store.get(token)
        if item is None:
            return None
        if time.monotonic() - item["created_at"] > self.TTL_SECONDS:
            del self._store[token]
            return None
        return item

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now - v["created_at"] > self.TTL_SECONDS]
        for k in expired:
            del self._store[k]


class TelephonyService:
    def __init__(self) -> None:
        from app.config import settings
        self._settings = settings
        self.audio_store = AudioStore()

    async def twiml_verb(self, text: str, language: str) -> str:
        if language == "ro" and self._settings.tts_provider_ro == "elevenlabs":
            play_verb = await self._elevenlabs_play_verb(text)
            if play_verb:
                return play_verb
            logger.warning(
                "[TTS] ElevenLabs ESUAT -> folosesc Twilio <Say> ca fallback. "
                "Verifica ELEVENLABS_API_KEY, PUBLIC_BASE_URL si logs."
            )
        return self._twilio_say_verb(text, language)

    async def _elevenlabs_play_verb(self, text: str) -> str | None:
        if not self._settings.elevenlabs_api_key:
            logger.error("[ElevenLabs] ELEVENLABS_API_KEY lipsa din .env")
            return None
        if not self._settings.elevenlabs_voice_id_ro:
            logger.error("[ElevenLabs] ELEVENLABS_VOICE_ID_RO lipsa din .env")
            return None

        public_url = self._settings.public_base_url.rstrip("/")
        if not public_url or "localhost" in public_url or "127.0.0.1" in public_url:
            logger.error("[ElevenLabs] PUBLIC_BASE_URL='%s' nu e accesibil public!", public_url)
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{self._settings.elevenlabs_voice_id_ro}",
                    headers={
                        "xi-api-key": self._settings.elevenlabs_api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text,
                        "model_id": self._settings.elevenlabs_model_id or "eleven_multilingual_v2",
                        "output_format": self._settings.elevenlabs_output_format or "mp3_44100_128",
                        "voice_settings": {
                            "stability": 0.45,
                            "similarity_boost": 0.80,
                            "style": 0.35,
                            "use_speaker_boost": True,
                        },
                    },
                )

            if resp.status_code != 200:
                logger.error("[ElevenLabs] HTTP %s: %s", resp.status_code, resp.text[:300])
                return None

            audio_bytes = resp.content
            if not audio_bytes:
                logger.error("[ElevenLabs] Raspuns gol (0 bytes)")
                return None

            logger.info("[ElevenLabs] Audio generat: %d bytes", len(audio_bytes))

        except httpx.TimeoutException:
            logger.error("[ElevenLabs] Timeout dupa 15s")
            return None
        except Exception as exc:
            logger.error("[ElevenLabs] Eroare neasteptata: %s", exc)
            return None

        token = self.audio_store.put(audio_bytes, "audio/mpeg")
        audio_url = f"{public_url}/api/tts/{token}"
        logger.info("[ElevenLabs] <Play> URL: %s", audio_url)
        return f"<Play>{audio_url}</Play>"

    def _twilio_say_verb(self, text: str, language: str) -> str:
        if language == "ro":
            voice = self._settings.twilio_voice_ro or "Google.ro-RO-Wavenet-B"
            lang_code = "ro-RO"
            text = _replace_numbers_ro(text)
        else:
            voice = self._settings.twilio_voice_en or "Polly.Amy-Neural"
            lang_code = "en-US"

        safe_text = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )
        return f'<Say voice="{voice}" language="{lang_code}">{safe_text}</Say>'

    async def send_sms(self, to_number: str, message: str) -> dict[str, Any]:
        sid = self._settings.twilio_account_sid
        token = self._settings.twilio_auth_token
        from_number = self._settings.twilio_sms_from_number or self._settings.twilio_from_number

        if not all([sid, token, from_number]):
            logger.warning("[Twilio SMS] Credentiale lipsa -> dry_run")
            return {
                "status": "dry_run",
                "provider": "twilio",
                "to": to_number,
                "preview_message": message,
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, token),
                    data={"To": to_number, "From": from_number, "Body": message},
                )
            data = resp.json()
            return {
                "status": data.get("status", "queued"),
                "provider": "twilio",
                "sid": data.get("sid"),
                "to": to_number,
                "preview_message": message,
            }
        except Exception as exc:
            logger.error("[Twilio SMS] Eroare: %s", exc)
            return {"status": "error", "provider": "twilio", "message": str(exc)}

    async def create_outbound_call(
        self, to_number: str, message: str, language: str = "en"
    ) -> dict[str, Any]:
        sid = self._settings.twilio_account_sid
        token = self._settings.twilio_auth_token
        from_number = self._settings.twilio_from_number

        if not all([sid, token, from_number]):
            logger.warning("[Twilio Outbound] Credentiale lipsa -> dry_run")
            return {
                "status": "dry_run",
                "provider": "twilio",
                "to": to_number,
                "message": message,
            }

        lang_code = "ro-RO" if language == "ro" else "en-US"
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Say language="{lang_code}">{message}</Say></Response>'
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
                    auth=(sid, token),
                    data={"To": to_number, "From": from_number, "Twiml": twiml},
                )
            data = resp.json()
            return {
                "status": data.get("status", "queued"),
                "provider": "twilio",
                "call_sid": data.get("sid"),
                "to": to_number,
            }
        except Exception as exc:
            logger.error("[Twilio Outbound] Eroare: %s", exc)
            return {"status": "error", "provider": "twilio", "message": str(exc)}
