import httpx

from app.config import settings


class CalendarClient:
    def __init__(self) -> None:
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.refresh_token = settings.google_refresh_token
        self.calendar_id = settings.google_calendar_id
        self.token_url = settings.google_oauth_token_url
        self.base_url = settings.google_calendar_base_url.rstrip("/")
        self.timezone = settings.google_calendar_timezone

    def configured(self) -> bool:
        return all([self.client_id, self.client_secret, self.refresh_token, self.calendar_id])

    async def _access_token(self) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def schedule_meeting(
        self,
        attendee_email: str,
        start_iso: str,
        end_iso: str,
        summary: str,
        description: str,
    ) -> dict:
        if not self.configured():
            return {
                "provider": "google_calendar",
                "configured": False,
                "status": "dry_run",
                "attendee_email": attendee_email,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "summary": summary,
                "description": description,
                "timezone": self.timezone,
                "meet_link": "https://meet.google.com/dry-run-demo",
            }

        token = await self._access_token()
        payload = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": self.timezone},
            "end": {"dateTime": end_iso, "timeZone": self.timezone},
            "attendees": [{"email": attendee_email}],
            "conferenceData": {
                "createRequest": {
                    "requestId": f"{attendee_email}-{start_iso}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/calendars/{self.calendar_id}/events",
                params={"conferenceDataVersion": 1, "sendUpdates": "all"},
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        entry_points = body.get("conferenceData", {}).get("entryPoints", [])
        meet_link = next((entry.get("uri") for entry in entry_points if entry.get("entryPointType") == "video"), body.get("hangoutLink"))
        return {
            "provider": "google_calendar",
            "configured": True,
            "status": body.get("status", "confirmed"),
            "event_id": body.get("id"),
            "event_link": body.get("htmlLink"),
            "meet_link": meet_link,
            "attendee_email": attendee_email,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "summary": summary,
            "description": description,
            "timezone": self.timezone,
        }
