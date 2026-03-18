import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class KnowledgeMatch:
    answer: str
    source: str
    confidence: float


class KnowledgeBase:
    def __init__(self, path: str = "knowledge/faq.json") -> None:
        base_dir = Path(__file__).resolve().parents[2]
        candidate = Path(path)
        self.path = candidate if candidate.is_absolute() else base_dir / candidate
        self.items = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def search(self, user_text: str, language: str) -> KnowledgeMatch | None:
        text = user_text.lower()
        tokens = {token.strip('.,!?') for token in text.split() if token.strip('.,!?')}
        best = None
        score = 0
        for item in self.items:
            if item.get("language") != language:
                continue
            question_tokens = set(item.get("question", "").lower().split())
            local_score = len(tokens.intersection(question_tokens))
            if local_score > score:
                best = item
                score = local_score
        if best and score > 0:
            confidence = min(0.95, 0.45 + (score * 0.15))
            source = best.get("source") or best.get("question") or "faq"
            return KnowledgeMatch(answer=best["answer"], source=source, confidence=confidence)
        return None
