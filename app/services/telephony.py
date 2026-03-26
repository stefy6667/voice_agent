"""
telephony.py — TelephonyService cu ElevenLabs fix robust

PROBLEME REZOLVATE:
1. PUBLIC_BASE_URL lipsă sau greșit → URL invalid pentru Twilio <Play>
2. ElevenLabs eroare silențioasă → fallback la <Say> fără log vizibil
3. Content-Type greșit pentru audio stream
4. Token expirat / audio_store gol
5. Twilio nu poate reda MP3 dacă nu e servit cu header corect
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AudioStore:
    """Store temporar pentru clipuri audio ElevenLabs (TTL 5 minute)."""

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
        age = time.monotonic() - item["created_at"]
        if age > self.TTL_SECONDS:
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

    # ------------------------------------------------------------------
    # PUBLIC: metoda principală folosită din main.py
    # ------------------------------------------------------------------

    async def twiml_verb(self, text: str, language: str) -> str:
        """
        Returnează un verb TwiML (<Play> sau <Say>) pentru textul dat.

        Logica:
        1. Dacă language == 'ro' și TTS_PROVIDER_RO == 'elevenlabs' → încearcă ElevenLabs
        2. Dacă ElevenLabs reușește → returnează <Play url="..."/>
        3. Dacă ElevenLabs eșuează (orice motiv) → fallback <Say> cu log clar
        4. Pentru engleză sau fallback → <Say> Twilio direct
        """
        if language == "ro" and self._settings.tts_provider_ro == "elevenlabs":
            play_verb = await self._elevenlabs_play_verb(text)
            if play_verb:
                return play_verb
            # Fallback cu log clar — acesta era motivul problemei tale
            logger.warning(
                "[TTS] ElevenLabs EȘUAT → folosesc Twilio <Say> ca fallback. "
                "Verifică ELEVENLABS_API_KEY, PUBLIC_BASE_URL și logs de mai sus."
            )

        return self._twilio_say_verb(text, language)

    # ------------------------------------------------------------------
    # ELEVENLABS
    # ------------------------------------------------------------------

    async def _elevenlabs_play_verb(self, text: str) -> str | None:
        """
        Generează audio prin ElevenLabs și returnează <Play url="..."/>.
        Returnează None dacă ceva eșuează (cu log detaliat).
        """
        # 1. Verificare configurație
        if not self._settings.elevenlabs_api_key:
            logger.error("[ElevenLabs] ELEVENLABS_API_KEY lipsă din .env")
            return None

        if not self._settings.elevenlabs_voice_id_ro:
            logger.error("[ElevenLabs] ELEVENLABS_VOICE_ID_RO lipsă din .env")
            return None

        public_url = self._settings.public_base_url.rstrip("/")
        if not public_url or "localhost" in public_url or "127.0.0.1" in public_url:
            logger.error(
                "[ElevenLabs] PUBLIC_BASE_URL este '%s'. "
                "Twilio nu poate accesa localhost! Setează URL-ul public HTTPS al serverului tău.",
                public_url,
            )
            return None

        # 2. Apel API ElevenLabs
        voice_id = self._settings.elevenlabs_voice_id_ro
        model_id = self._settings.elevenlabs_model_id or "eleven_multilingual_v2"
        output_format = self._settings.elevenlabs_output_format or "mp3_44100_128"

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self._settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "output_format": output_format,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.80,
                "style": 0.35,
                "use_speaker_boost": True,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code != 200:
                logger.error(
                    "[ElevenLabs] HTTP %s: %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return None

            audio_bytes = resp.content
            if not audio_bytes:
                logger.error("[ElevenLabs] Răspuns gol (0 bytes)")
                return None

            logger.info("[ElevenLabs] Audio generat: %d bytes", len(audio_bytes))

        except httpx.TimeoutException:
            logger.error("[ElevenLabs] Timeout după 15s — ElevenLabs nu a răspuns")
            return None
        except Exception as exc:
            logger.error("[ElevenLabs] Eroare neașteptată: %s", exc)
            return None

        # 3. Stochează audio și generează URL public
        media_type = "audio/mpeg"
        token = self.audio_store.put(audio_bytes, media_type)
        audio_url = f"{public_url}/api/tts/{token}"

        logger.info("[ElevenLabs] <Play> URL: %s", audio_url)
        return f'<Play>{audio_url}</Play>'

    # ------------------------------------------------------------------
    # TWILIO SAY (fallback)
    # ------------------------------------------------------------------

    def _twilio_say_verb(self, text: str, language: str) -> str:
        if language == "ro":
            voice = self._settings.twilio_voice_ro or "Google.ro-RO-Wavenet-B"
            lang_code = "ro-RO"
        else:
            voice = self._settings.twilio_voice_en or "Polly.Amy-Neural"
            lang_code = "en-US"

        # Escape XML special chars
        safe_text = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )
        return f'<Say voice="{voice}" language="{lang_code}">{safe_text}</Say>'

    # ------------------------------------------------------------------
    # OUTBOUND CALL
    # ------------------------------------------------------------------

    async def create_outbound_call(
        self, to_number: str, message: str, language: str = "en"
    ) -> dict[str, Any]:
        sid = self._settings.twilio_account_sid
        token = self._settings.twilio_auth_token
        from_number = self._settings.twilio_from_number
        public_url = self._settings.public_base_url.rstrip("/")

        if not all([sid, token, from_number]):
            logger.warning("[Twilio Outbound] Credențiale lipsă → dry_run")
            return {
                "status": "dry_run",
                "provider": "twilio",
                "to": to_number,
                "message": message,
            }

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Say language=\"{'ro-RO' if language == 'ro' else 'en-US'}\">{message}</Say></Response>"
        )
        twiml_url = f"{public_url}/api/tts/outbound-twiml"  # sau un TwiML Bin

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
                    auth=(sid, token),
                    data={
                        "To": to_number,
                        "From": from_number,
                        "Twiml": twiml,
                    },
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
