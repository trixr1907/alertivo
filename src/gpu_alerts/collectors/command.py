from __future__ import annotations

import asyncio

from gpu_alerts.config import SourceConfig
from gpu_alerts.models import OfferObservation

from .parser import ParsedHtmlCollectorMixin


class CommandCollector(ParsedHtmlCollectorMixin):
    def __init__(self, config: SourceConfig):
        if not config.parser:
            raise ValueError(f"Source {config.name} requires a parser config.")
        if not config.command:
            raise ValueError(f"Source {config.name} requires a command.")
        self.name = config.name
        self._config = config

    async def collect(self) -> list[OfferObservation]:
        process = await asyncio.create_subprocess_exec(
            *self._config.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self._config.timeout_seconds)
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="ignore").strip() or f"Command failed: {self._config.command}")

        encoding = self._config.encoding or "utf-8"
        html = stdout.decode(encoding, errors="ignore")
        return self.parse_html(html)
