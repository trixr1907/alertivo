from __future__ import annotations

import aiohttp

from gpu_alerts.config import SourceConfig
from gpu_alerts.models import OfferObservation

from .parser import ParsedHtmlCollectorMixin

class HttpCollector(ParsedHtmlCollectorMixin):
    def __init__(self, session: aiohttp.ClientSession, config: SourceConfig, user_agent: str):
        if not config.parser:
            raise ValueError(f"Source {config.name} requires a parser config.")

        self.name = config.name
        self._session = session
        self._config = config
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            **config.headers,
        }

    async def collect(self) -> list[OfferObservation]:
        if not self._config.url:
            return []

        timeout = aiohttp.ClientTimeout(total=self._config.timeout_seconds)
        async with self._session.get(self._config.url, headers=self._headers, timeout=timeout) as response:
            response.raise_for_status()
            html = await response.text()

        return self.parse_html(html)
