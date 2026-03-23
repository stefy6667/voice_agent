class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def upsert_language(self, session_id: str, language: str) -> None:
        self._sessions.setdefault(session_id, {})["language"] = language

    def get_language(self, session_id: str) -> str | None:
        session = self._sessions.get(session_id, {})
        return session.get("language")

    def set_value(self, session_id: str, key: str, value: str) -> None:
        self._sessions.setdefault(session_id, {})[key] = value

    def get_value(self, session_id: str, key: str) -> str | None:
        session = self._sessions.get(session_id, {})
        return session.get(key)

    def append_turn(self, session_id: str, role: str, text: str) -> None:
        session = self._sessions.setdefault(session_id, {})
        turns = session.setdefault("turns", [])
        turns.append({"role": role, "text": text})
        if len(turns) > 8:
            session["turns"] = turns[-8:]

    def get_recent_turns(self, session_id: str) -> list[dict[str, str]]:
        session = self._sessions.get(session_id, {})
        return list(session.get("turns", []))

    def append_recording(self, session_id: str, recording: dict) -> None:
        session = self._sessions.setdefault(session_id, {})
        recordings = session.setdefault("recordings", [])
        recordings.append(recording)

    def get_recordings(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id, {})
        return list(session.get("recordings", []))

    def build_transcript_text(self, session_id: str) -> str:
        turns = self.get_recent_turns(session_id)
        return "\n".join(f"{turn['role']}: {turn['text']}" for turn in turns)
