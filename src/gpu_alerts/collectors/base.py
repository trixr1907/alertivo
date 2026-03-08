from __future__ import annotations

from typing import Protocol

from gpu_alerts.models import OfferObservation


class Collector(Protocol):
    name: str

    async def collect(self) -> list[OfferObservation]:
        ...
