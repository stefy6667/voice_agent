import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class DatabaseClient:
    """
    Deploy-ready DB adapter with SQLite default for zero-config startup.
    For production, point DATABASE_URL to PostgreSQL/MySQL and replace implementation.
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.sqlite_path = self._sqlite_path_from_url(database_url)
        self._init_sqlite()

    @staticmethod
    def _sqlite_path_from_url(database_url: str) -> str:
        if database_url.startswith("sqlite:///"):
            return database_url.replace("sqlite:///", "", 1)
        return "voice_agent.db"

    def _init_sqlite(self) -> None:
        db_file = Path(self.sqlite_path)
        db_file.parent.mkdir(parents=True, exist_ok=True) if db_file.parent != Path(".") else None
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_profiles (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    tier TEXT DEFAULT 'standard'
                )
                """
            )
            conn.commit()

    async def fetch_customer_profile(self, session_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.sqlite_path) as conn:
            row = conn.execute(
                "SELECT session_id, customer_id, tier FROM customer_profiles WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if row is None:
                conn.execute(
                    "INSERT INTO customer_profiles (session_id, customer_id, tier) VALUES (?, ?, ?)",
                    (session_id, f"cust-{session_id}", "standard"),
                )
                conn.commit()
                row = (session_id, f"cust-{session_id}", "standard")

        return {
            "session_id": row[0],
            "customer_id": row[1],
            "tier": row[2],
            "database_connected": True,
        }


class CRMClient:
    """
    Generic CRM software connector.
    Can be reused for HubSpot, Salesforce, Zoho, custom ERP/CRM APIs.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch_open_tickets(self, customer_id: str | None) -> dict[str, Any]:
        if not self.base_url or not self.api_key or not customer_id:
            return {
                "crm_connected": bool(self.base_url and self.api_key),
                "open_tickets": 0,
            }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/customers/{customer_id}/tickets",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        return {
            "crm_connected": True,
            "open_tickets": len(data.get("tickets", [])),
        }


def build_integration_clients() -> tuple[DatabaseClient, CRMClient]:
    return (
        DatabaseClient(settings.database_url),
        CRMClient(settings.crm_api_base_url, settings.crm_api_key),
    )
