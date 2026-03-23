import hashlib
import re

import httpx

from app.config import settings


class ElevenLabsTTSClient:
    """
    ElevenLabs TTS client optimized for natural, human-like Romanian voice.
    
    Key optimizations for natural speech:
    - Higher stability (0.5-0.7) for consistent, clear pronunciation
    - Balanced similarity_boost (0.75) for natural timbre
    - Style parameter for expressiveness
    - Speaker boost for clarity
    - Text preprocessing for natural pauses and emphasis
    """
    
    def configured(self) -> bool:
        return bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id_ro)

    def enabled_for_language(self, language: str) -> bool:
        return (
            language == "ro"
            and settings.tts_provider_ro.lower().strip() == "elevenlabs"
            and self.configured()
        )

    def _preprocess_text_for_natural_speech(self, text: str, language: str) -> str:
        """
        Preprocess text for more natural TTS output.
        - Add slight pauses after punctuation
        - Handle Romanian-specific patterns
        - Normalize spacing for better rhythm
        """
        # Add natural breath pauses after sentences
        text = re.sub(r'([.!?])\s+', r'\1 ... ', text)
        
        # Add slight pauses after commas for natural rhythm
        text = re.sub(r',\s*', ', ', text)
        
        # Handle Romanian greeting patterns for warmth
        if language == "ro":
            # Add slight emphasis pause after greetings
            text = re.sub(r'^(Bună|Salut|Bună ziua)([!,.]?)\s*', r'\1\2 ... ', text, flags=re.IGNORECASE)
            
            # Natural pause before questions
            text = re.sub(r'\s+(Cu ce|Cum|Ce|Când|Unde)\s+', r' ... \1 ', text, flags=re.IGNORECASE)
        
        # Remove excessive ellipses that might have been added
        text = re.sub(r'\.{4,}', '...', text)
        text = re.sub(r'\s+\.\.\.', ' ...', text)
        text = re.sub(r'\.\.\.\s+\.\.\.', '...', text)
        
        return text.strip()

    async def synthesize(self, text: str, language: str) -> tuple[bytes, str] | None:
        if not self.enabled_for_language(language):
            return None

        voice_id = settings.elevenlabs_voice_id_ro
        output_format = settings.elevenlabs_output_format
        model_id = settings.elevenlabs_model_id
        
        # Preprocess text for natural speech patterns
        processed_text = self._preprocess_text_for_natural_speech(text, language)
        
        cache_key = hashlib.sha256(
            f"{voice_id}:{model_id}:{output_format}:{language}:{processed_text}".encode("utf-8")
        ).hexdigest()

        # Optimized voice settings for natural, human-like Romanian speech
        voice_settings = {
            # Higher stability (0.5-0.7) for clearer, more consistent pronunciation
            # Lower values cause too much variation, making it sound unstable
            "stability": settings.elevenlabs_stability,
            
            # Similarity boost controls how closely the voice matches the original
            # 0.75 is a good balance - not too artificial, not too different
            "similarity_boost": settings.elevenlabs_similarity_boost,
            
            # Style controls expressiveness (0 = neutral, 1 = very expressive)
            # 0.3-0.5 adds natural emotion without over-acting
            "style": settings.elevenlabs_style,
            
            # Speaker boost enhances clarity and presence
            "use_speaker_boost": settings.elevenlabs_use_speaker_boost,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Accept": "audio/mpeg",
                },
                params={"output_format": output_format},
                json={
                    "text": processed_text,
                    "model_id": model_id,
                    "voice_settings": voice_settings,
                },
            )
            response.raise_for_status()
            return response.content, cache_key
