class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def upsert_language(self, session_id: str, language: str) -> None:
        self._sessions.setdefault(session_id, {})["language"] = language

    def get_language(self, session_id: str) -> str | None:
        session = self._sessions.get(session_id, {})
        return session.get("language")

    def append_turn(self, session_id: str, role: str, text: str) -> None:
        session = self._sessions.setdefault(session_id, {})
        turns = session.setdefault("turns", [])
        turns.append({"role": role, "text": text})
        if len(turns) > 8:
            session["turns"] = turns[-8:]

    def get_recent_turns(self, session_id: str) -> list[dict[str, str]]:
        session = self._sessions.get(session_id, {})
        return list(session.get("turns", []))
