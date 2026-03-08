from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MatchResult:
    product_family: str
    canonical_model: str
    normalized_title: str


@dataclass(slots=True)
class OfferObservation:
    shop: str
    source: str
    scope: str
    title: str
    url: str
    price: Decimal | None
    in_stock: bool | None
    currency: str = "EUR"
    observed_at: datetime = field(default_factory=utc_now)
    product_hint: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    include_title_terms: list[str] = field(default_factory=list)
    exclude_title_terms: list[str] = field(default_factory=list)
    price_ceiling: Decimal | None = None
    new_listing_price_below: Decimal | None = None
    product_family: str | None = None
    canonical_model: str | None = None
    normalized_title: str | None = None

    @property
    def offer_key(self) -> tuple[str, str, str]:
        canonical = self.canonical_model or "unknown"
        url = self.url or f"title:{self.title}"
        return self.shop, canonical, url


@dataclass(slots=True)
class AlertEvent:
    event_type: str
    shop: str
    source: str
    product_family: str
    canonical_model: str
    title: str
    url: str
    old_price: Decimal | None
    new_price: Decimal | None
    currency: str
    in_stock: bool | None
    dedupe_key: str
    threshold_price: Decimal | None = None
    observed_at: datetime = field(default_factory=utc_now)

    @property
    def delta(self) -> Decimal | None:
        if self.old_price is None or self.new_price is None:
            return None
        return self.old_price - self.new_price

    @property
    def delta_percent(self) -> Decimal | None:
        if not self.delta or not self.old_price:
            return None
        return (self.delta / self.old_price) * Decimal("100")
