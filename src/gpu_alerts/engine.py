from __future__ import annotations

import asyncio
import hashlib
from datetime import timezone, timedelta
from decimal import Decimal

from gpu_alerts.matcher import ProductMatcher, normalize_title
from gpu_alerts.models import AlertEvent, OfferObservation
from gpu_alerts.notifiers import NotifierManager
from gpu_alerts.storage import Storage


class AlertEngine:
    def __init__(
        self,
        storage: Storage,
        matcher: ProductMatcher,
        notifiers: NotifierManager,
        *,
        enable_restock_alerts: bool,
        new_listing_reference_min_age_seconds: int = 60,
        rtx_5070_ti_exclude_complete_pc_terms: list[str] | None = None,
        rtx_5070_ti_exclude_notebook_terms: list[str] | None = None,
        rtx_5070_ti_exclude_bundle_terms: list[str] | None = None,
        rtx_5070_ti_exclude_defect_terms: list[str] | None = None,
    ):
        self._storage = storage
        self._matcher = matcher
        self._notifiers = notifiers
        self._enable_restock_alerts = enable_restock_alerts
        self._new_listing_reference_min_age_seconds = new_listing_reference_min_age_seconds
        self._rtx_5070_ti_exclude_groups = {
            "complete_pc": list(rtx_5070_ti_exclude_complete_pc_terms or []),
            "notebook": list(rtx_5070_ti_exclude_notebook_terms or []),
            "bundle": list(rtx_5070_ti_exclude_bundle_terms or []),
            "defect": list(rtx_5070_ti_exclude_defect_terms or []),
        }
        self._lock = asyncio.Lock()

    @property
    def enable_restock_alerts(self) -> bool:
        return self._enable_restock_alerts

    @enable_restock_alerts.setter
    def enable_restock_alerts(self, value: bool) -> None:
        self._enable_restock_alerts = bool(value)

    @property
    def new_listing_reference_min_age_seconds(self) -> int:
        return self._new_listing_reference_min_age_seconds

    @new_listing_reference_min_age_seconds.setter
    def new_listing_reference_min_age_seconds(self, value: int) -> None:
        self._new_listing_reference_min_age_seconds = int(value)

    @property
    def rtx_5070_ti_exclude_complete_pc_terms(self) -> list[str]:
        return list(self._rtx_5070_ti_exclude_groups["complete_pc"])

    @rtx_5070_ti_exclude_complete_pc_terms.setter
    def rtx_5070_ti_exclude_complete_pc_terms(self, values: list[str]) -> None:
        self._rtx_5070_ti_exclude_groups["complete_pc"] = list(values)

    @property
    def rtx_5070_ti_exclude_notebook_terms(self) -> list[str]:
        return list(self._rtx_5070_ti_exclude_groups["notebook"])

    @rtx_5070_ti_exclude_notebook_terms.setter
    def rtx_5070_ti_exclude_notebook_terms(self, values: list[str]) -> None:
        self._rtx_5070_ti_exclude_groups["notebook"] = list(values)

    @property
    def rtx_5070_ti_exclude_bundle_terms(self) -> list[str]:
        return list(self._rtx_5070_ti_exclude_groups["bundle"])

    @rtx_5070_ti_exclude_bundle_terms.setter
    def rtx_5070_ti_exclude_bundle_terms(self, values: list[str]) -> None:
        self._rtx_5070_ti_exclude_groups["bundle"] = list(values)

    @property
    def rtx_5070_ti_exclude_defect_terms(self) -> list[str]:
        return list(self._rtx_5070_ti_exclude_groups["defect"])

    @rtx_5070_ti_exclude_defect_terms.setter
    def rtx_5070_ti_exclude_defect_terms(self, values: list[str]) -> None:
        self._rtx_5070_ti_exclude_groups["defect"] = list(values)

    async def process(self, observation: OfferObservation) -> AlertEvent | None:
        async with self._lock:
            normalized_title = normalize_title(observation.title)
            if self._should_exclude(observation, normalized_title):
                return None

            match = self._matcher.match(observation.title, observation.product_hint)
            if not match:
                return None

            observation.product_family = match.product_family
            observation.canonical_model = match.canonical_model
            observation.normalized_title = match.normalized_title
            if self._should_exclude_family(observation.product_family, normalized_title):
                return None

            status_hash = self._status_hash(observation)
            existing = self._storage.get_offer(*observation.offer_key)
            event = self._decide_event(observation, existing)

            clear_alerted = False
            alert_price = None
            if existing and observation.price is not None and existing.last_seen_price != observation.price:
                clear_alerted = True
            if event and event.event_type in {"price_drop", "new_listing_below_last_seen", "new_listing_under_threshold"}:
                clear_alerted = False
                alert_price = observation.price

            self._storage.upsert_offer(
                observation,
                status_hash=status_hash,
                last_alerted_price=alert_price,
                clear_last_alerted_price=clear_alerted,
            )

            if event:
                self._storage.record_event(event)
                await self._notifiers.send(event)
            return event

    def _decide_event(self, observation: OfferObservation, existing) -> AlertEvent | None:
        if existing:
            if self._enable_restock_alerts and existing.last_seen_stock is False and observation.in_stock is True and observation.price is not None:
                return self._build_event("restock", observation, existing.last_seen_price)

            if observation.price is None or existing.last_seen_price is None:
                return None

            if observation.price < existing.last_seen_price and observation.price != existing.last_alerted_price:
                return self._build_event("price_drop", observation, existing.last_seen_price)
            return None

        if (
            observation.new_listing_price_below is not None
            and observation.price is not None
            and observation.price < observation.new_listing_price_below
        ):
            return self._build_event(
                "new_listing_under_threshold",
                observation,
                old_price=None,
                threshold_price=observation.new_listing_price_below,
            )

        reference_price = self._storage.get_reference_price(
            observation.shop,
            observation.product_family or "",
            observation.canonical_model or "",
            older_than=(
                observation.observed_at - timedelta(seconds=self._new_listing_reference_min_age_seconds)
            ).astimezone(timezone.utc).isoformat(),
        )
        if observation.price is None or reference_price is None:
            return None
        if observation.price < reference_price:
            return self._build_event("new_listing_below_last_seen", observation, reference_price)
        return None

    def _build_event(
        self,
        event_type: str,
        observation: OfferObservation,
        old_price: Decimal | None,
        *,
        threshold_price: Decimal | None = None,
    ) -> AlertEvent:
        dedupe_key = f"{observation.shop}|{observation.canonical_model}|{observation.price}"
        return AlertEvent(
            event_type=event_type,
            shop=observation.shop,
            source=observation.source,
            product_family=observation.product_family or "unknown",
            canonical_model=observation.canonical_model or "unknown",
            title=observation.title,
            url=observation.url,
            old_price=old_price,
            new_price=observation.price,
            currency=observation.currency,
            in_stock=observation.in_stock,
            dedupe_key=dedupe_key,
            threshold_price=threshold_price,
            observed_at=observation.observed_at,
        )

    @staticmethod
    def _should_exclude(observation: OfferObservation, normalized_title: str) -> bool:
        for term in observation.exclude_title_terms:
            if normalize_title(term) in normalized_title:
                return True
        return False

    def _should_exclude_family(self, product_family: str | None, normalized_title: str) -> bool:
        if product_family == "rtx-5070-ti":
            for terms in self._rtx_5070_ti_exclude_groups.values():
                for term in terms:
                    if normalize_title(term) in normalized_title:
                        return True
        return False

    @staticmethod
    def _status_hash(observation: OfferObservation) -> str:
        raw = f"{observation.title}|{observation.price}|{observation.in_stock}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
