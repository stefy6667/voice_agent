import json
from pathlib import Path
from typing import Optional


class KnowledgeBase:
    def __init__(self, path: str = "knowledge/faq.json") -> None:
        self.path = Path(path)
        self.items = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def search(self, user_text: str, language: str) -> Optional[str]:
        text = user_text.lower()
        best = None
        score = 0
        for item in self.items:
            if item.get("language") != language:
                continue
            question = item.get("question", "").lower()
            local_score = sum(1 for token in text.split() if token in question)
            if local_score > score:
                best = item
                score = local_score
        if best and score > 0:
            return best["answer"]
        return None
