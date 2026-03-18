from app.services.integrations import CRMClient, DatabaseClient


class ToolClient:
    def __init__(self, db: DatabaseClient, crm: CRMClient) -> None:
        self.db = db
        self.crm = crm

    async def get_customer_context(self, session_id: str) -> dict:
        profile = await self.db.fetch_customer_profile(session_id)
        tickets = await self.crm.fetch_open_tickets(profile.get("customer_id"))

        return {
            "session_id": session_id,
            "customer_id": profile.get("customer_id"),
            "tier": profile.get("tier", "standard"),
            "open_tickets": tickets.get("open_tickets", 0),
            "database_connected": profile.get("database_connected", False),
            "crm_connected": tickets.get("crm_connected", False),
        }
