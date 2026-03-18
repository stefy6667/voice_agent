import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

from app.config import settings


class UnsafeResearchTargetError(ValueError):
    pass


class ResearchClient:
    def __init__(self) -> None:
        self.api_key = settings.tavily_api_key
        self.base_url = settings.tavily_base_url.rstrip("/")
        self.max_results = settings.web_search_max_results

    def configured(self) -> bool:
        return bool(self.api_key)

    def _validate_public_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeResearchTargetError("Only public http(s) URLs are supported.")

        host = parsed.hostname.lower()
        if host in {"localhost"} or host.endswith(".localhost"):
            raise UnsafeResearchTargetError("Localhost URLs are not allowed.")

        try:
            addresses = {
                info[4][0]
                for info in socket.getaddrinfo(
                    parsed.hostname,
                    parsed.port or None,
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise UnsafeResearchTargetError("Unable to resolve the target host.") from exc

        for address in addresses:
            ip = ipaddress.ip_address(address)
            if any(
                [
                    ip.is_private,
                    ip.is_loopback,
                    ip.is_link_local,
                    ip.is_multicast,
                    ip.is_reserved,
                    ip.is_unspecified,
                ]
            ):
                raise UnsafeResearchTargetError("Private or non-public network targets are not allowed.")

        return url

    async def search_web(self, query: str) -> dict:
        if not self.configured():
            return {
                "provider": "tavily",
                "configured": False,
                "status": "dry_run",
                "query": query,
                "results": [],
                "summary": "Web search is not configured yet.",
            }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": self.max_results,
                    "include_answer": True,
                },
            )
            response.raise_for_status()
            body = response.json()

        return {
            "provider": "tavily",
            "configured": True,
            "status": "ok",
            "query": query,
            "summary": body.get("answer") or "",
            "results": body.get("results", [])[: self.max_results],
        }

    async def inspect_url(self, url: str) -> dict:
        safe_url = self._validate_public_url(url)
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(safe_url)
            response.raise_for_status()
            html = response.text

        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else url
        clean_text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        excerpt = clean_text[:600]
        return {
            "provider": "url_fetch",
            "configured": True,
            "status": "ok",
            "url": url,
            "title": title,
            "summary": excerpt,
        }
