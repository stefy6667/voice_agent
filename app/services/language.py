import re
from dataclasses import dataclass


@dataclass
class LanguageDetection:
    language: str
    confidence: float


class LanguageDetector:
    RO_MARKERS = {
        "buna", "bună", "salut", "factura", "comanda", "comandă", "livrare", "multumesc", "mulțumesc", "romana", "română", "vreau", "am", "problema", "problemă"
    }
    EN_MARKERS = {
        "hello", "invoice", "order", "delivery", "thanks", "english", "want", "problem", "please"
    }

    def detect(self, text: str, previous_language: str | None = None) -> LanguageDetection:
        tokens = set(re.findall(r"[a-zA-ZăâîșțĂÂÎȘȚ]+", text.lower()))
        ro_score = len(tokens.intersection(self.RO_MARKERS))
        en_score = len(tokens.intersection(self.EN_MARKERS))

        if ro_score > en_score:
            return LanguageDetection(language="ro", confidence=min(0.99, 0.6 + ro_score * 0.1))
        if en_score > ro_score:
            return LanguageDetection(language="en", confidence=min(0.99, 0.6 + en_score * 0.1))
        if previous_language:
            return LanguageDetection(language=previous_language, confidence=0.55)

        return LanguageDetection(language="en", confidence=0.51)
