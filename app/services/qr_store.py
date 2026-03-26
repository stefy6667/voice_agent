import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import ContentPayload, QRCodeRecord


class QRStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.sqlite_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        settings.storage_path.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS qr_codes (
                    qr_id TEXT PRIMARY KEY,
                    edit_code TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            conn.commit()

    def create(self) -> QRCodeRecord:
        now = datetime.now(timezone.utc).isoformat()
        qr_id = secrets.token_hex(5)
        edit_code = secrets.token_urlsafe(6).replace("-", "")[:8].upper()
        slug = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10]
        content = ContentPayload()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO qr_codes (qr_id, edit_code, slug, content_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (qr_id, edit_code, slug, content.model_dump_json(), now, now),
            )
            conn.commit()
        return QRCodeRecord(qr_id=qr_id, edit_code=edit_code, slug=slug, created_at=now, updated_at=now, content=content)

    def _row_to_record(self, row: sqlite3.Row | None) -> QRCodeRecord | None:
        if row is None:
            return None
        return QRCodeRecord(
            qr_id=row["qr_id"],
            edit_code=row["edit_code"],
            slug=row["slug"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            content=ContentPayload(**json.loads(row["content_json"])),
        )

    def list_all(self) -> list[QRCodeRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM qr_codes ORDER BY created_at DESC").fetchall()
        return [self._row_to_record(row) for row in rows if row is not None]

    def get_by_slug(self, slug: str) -> QRCodeRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM qr_codes WHERE slug = ?", (slug,)).fetchone()
        return self._row_to_record(row)

    def update(self, slug: str, edit_code: str, payload: dict[str, Any]) -> QRCodeRecord | None:
        existing = self.get_by_slug(slug)
        if existing is None or existing.edit_code != edit_code:
            return None
        content = existing.content.model_copy(update=payload)
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE qr_codes SET content_json = ?, updated_at = ? WHERE slug = ?",
                (content.model_dump_json(), updated_at, slug),
            )
            conn.commit()
        return self.get_by_slug(slug)
