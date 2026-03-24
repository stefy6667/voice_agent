from datetime import date, datetime
import re
from urllib.parse import urljoin

import httpx


class EventCatalogClient:
    RO_MONTHS = {
        "ianuarie": 1,
        "februarie": 2,
        "martie": 3,
        "aprilie": 4,
        "mai": 5,
        "iunie": 6,
        "iulie": 7,
        "august": 8,
        "septembrie": 9,
        "octombrie": 10,
        "noiembrie": 11,
        "decembrie": 12,
    }

    def __init__(self, source_url: str, max_results: int = 5) -> None:
        self.source_url = source_url.rstrip("/")
        self.max_results = max_results

    async def list_events(self) -> dict:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            html = response.text

        events = self.parse_events_from_html(html, self.source_url)[: self.max_results]
        return {
            "provider": "event_catalog",
            "status": "ok",
            "source_url": self.source_url,
            "events": events,
        }

    @classmethod
    def parse_events_from_html(cls, html: str, base_url: str) -> list[dict]:
        anchors = re.findall(
            r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        events: list[dict] = []
        seen: set[str] = set()

        for href, raw_text in anchors:
            clean_text = re.sub(r"<[^>]+>", " ", raw_text)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            if len(clean_text) < 8:
                continue
            absolute_url = urljoin(base_url + "/", href)
            lowered = clean_text.lower()
            if "iabilet.ro" not in absolute_url and not absolute_url.startswith("https://www.iabilet.ro"):
                continue
            if any(marker in lowered for marker in ["login", "contul", "newsletter", "facebook", "instagram"]):
                continue
            event_date = cls.extract_date(clean_text)
            key = f"{clean_text}|{absolute_url}"
            if key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    "title": clean_text,
                    "url": absolute_url,
                    "date": event_date.isoformat() if event_date else None,
                }
            )

        events.sort(
            key=lambda item: (
                item["date"] is None,
                item["date"] or "9999-12-31",
                item["title"].lower(),
            )
        )
        return events

    @classmethod
    def extract_date(cls, text: str) -> date | None:
        lowered = text.lower()
        match = re.search(
            r"\b(\d{1,2})\s+("
            + "|".join(cls.RO_MONTHS.keys())
            + r")(?:\s+(\d{4}))?\b",
            lowered,
        )
        if not match:
            return None
        day = int(match.group(1))
        month = cls.RO_MONTHS[match.group(2)]
        year = int(match.group(3)) if match.group(3) else datetime.utcnow().year
        try:
            return date(year, month, day)
        except ValueError:
            return None
