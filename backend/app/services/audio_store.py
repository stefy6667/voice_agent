import secrets
import time


class AudioStore:
    def __init__(self) -> None:
        self._items: dict[str, dict] = {}

    def put(self, content: bytes, media_type: str = "audio/mpeg", ttl_seconds: int = 900) -> str:
        token = secrets.token_urlsafe(24)
        self._items[token] = {
            "content": content,
            "media_type": media_type,
            "expires_at": time.time() + ttl_seconds,
        }
        self._purge_expired()
        return token

    def get(self, token: str) -> dict | None:
        item = self._items.get(token)
        if item is None:
            return None
        if item["expires_at"] <= time.time():
            self._items.pop(token, None)
            return None
        return item

    def _purge_expired(self) -> None:
        now = time.time()
        expired_tokens = [
            token for token, item in self._items.items() if item["expires_at"] <= now
        ]
        for token in expired_tokens:
            self._items.pop(token, None)
