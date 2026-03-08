from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from gpu_alerts.engine import AlertEngine
from gpu_alerts.matcher import ProductMatcher
from gpu_alerts.models import AlertEvent, OfferObservation
from gpu_alerts.storage import Storage


class DummyNotifierManager:
    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    async def send(self, event: AlertEvent) -> None:
        self.events.append(event)


def make_observation(
    *,
    title: str,
    price: str,
    observed_at: datetime,
    shop: str = "caseking",
    url: str = "https://example.com/item",
    product_hint: str | None = None,
    include_title_terms: list[str] | None = None,
    exclude_title_terms: list[str] | None = None,
    price_ceiling: str | None = None,
    new_listing_price_below: str | None = None,
) -> OfferObservation:
    return OfferObservation(
        shop=shop,
        source="shop",
        scope="shop_product",
        title=title,
        url=url,
        price=Decimal(price),
        in_stock=True,
        observed_at=observed_at,
        product_hint=product_hint,
        include_title_terms=list(include_title_terms or []),
        exclude_title_terms=list(exclude_title_terms or []),
        price_ceiling=Decimal(price_ceiling) if price_ceiling else None,
        new_listing_price_below=Decimal(new_listing_price_below) if new_listing_price_below else None,
    )


async def _process_sequence(engine: AlertEngine, observations: list[OfferObservation]) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    for observation in observations:
        event = await engine.process(observation)
        if event:
            events.append(event)
    return events


def test_price_drop_alert_and_dedupe(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    title = "ASUS GeForce RTX 5070 Ti TUF OC 16GB"
    observations = [
        make_observation(title=title, price="899", observed_at=base, product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
        make_observation(title=title, price="879", observed_at=base + timedelta(seconds=20), product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
        make_observation(title=title, price="879", observed_at=base + timedelta(seconds=40), product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
    ]

    events = asyncio.run(_process_sequence(engine, observations))

    assert [event.event_type for event in events] == ["price_drop"]
    assert events[0].old_price == Decimal("899")
    assert events[0].new_price == Decimal("879")
    assert len(notifier.events) == 1


def test_realert_after_price_changed_in_between(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    title = "ASUS GeForce RTX 5070 Ti TUF OC 16GB"
    observations = [
        make_observation(title=title, price="899", observed_at=base, product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
        make_observation(title=title, price="879", observed_at=base + timedelta(seconds=20), product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
        make_observation(title=title, price="899", observed_at=base + timedelta(seconds=40), product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
        make_observation(title=title, price="879", observed_at=base + timedelta(seconds=60), product_hint="rtx-5070-ti", include_title_terms=["rtx", "5070", "ti"]),
    ]

    events = asyncio.run(_process_sequence(engine, observations))

    assert [event.event_type for event in events] == ["price_drop", "price_drop"]
    assert len(notifier.events) == 2


def test_new_listing_below_shop_reference(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(
        storage,
        ProductMatcher(),
        notifier,
        enable_restock_alerts=False,
        new_listing_reference_min_age_seconds=0,
    )

    base = datetime.now(timezone.utc)
    title = "GL.iNet GL-MT6000 (Flint 2)"
    observations = [
        make_observation(
            title=title,
            price="199",
            observed_at=base,
            shop="amazon",
            url="https://example.com/flint-old",
            product_hint="glinet-flint-2",
        ),
        make_observation(
            title=title,
            price="189",
            observed_at=base + timedelta(seconds=30),
            shop="amazon",
            url="https://example.com/flint-new",
            product_hint="glinet-flint-2",
        ),
    ]

    events = asyncio.run(_process_sequence(engine, observations))

    assert [event.event_type for event in events] == ["new_listing_below_last_seen"]
    assert events[0].old_price == Decimal("199.0")
    assert events[0].new_price == Decimal("189")


def test_initial_batch_does_not_alert_against_same_scan_baseline(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(
        storage,
        ProductMatcher(),
        notifier,
        enable_restock_alerts=False,
        new_listing_reference_min_age_seconds=60,
    )

    base = datetime.now(timezone.utc)
    observations = [
        make_observation(
            title="MSI GeForce RTX 5070 Ti Gaming Trio OC 16GB",
            price="1039",
            observed_at=base,
            shop="alternate",
            url="https://example.com/one",
            product_hint="rtx-5070-ti",
            include_title_terms=["rtx", "5070", "ti"],
        ),
        make_observation(
            title="Gainward GeForce RTX 5070 Ti Phoenix 16GB",
            price="899",
            observed_at=base,
            shop="alternate",
            url="https://example.com/two",
            product_hint="rtx-5070-ti",
            include_title_terms=["rtx", "5070", "ti"],
        ),
    ]

    events = asyncio.run(_process_sequence(engine, observations))

    assert events == []


def test_new_listing_under_fixed_threshold(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    observation = make_observation(
        title="GL.iNet Flint 2 Router (GL-MT6000)",
        price="140",
        observed_at=base,
        shop="kleinanzeigen",
        url="https://example.com/kleinanzeigen/flint",
        product_hint="glinet-flint-2",
        new_listing_price_below="150",
    )

    event = asyncio.run(engine.process(observation))

    assert event is not None
    assert event.event_type == "new_listing_under_threshold"
    assert event.threshold_price == Decimal("150")
    assert len(notifier.events) == 1


def test_excluded_title_terms_skip_observation(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    observation = make_observation(
        title="MSI GeForce RTX 5070 Ti defekt fuer Bastler",
        price="450",
        observed_at=base,
        shop="ebay",
        url="https://example.com/ebay/defekt",
        product_hint="rtx-5070-ti",
        include_title_terms=["rtx", "5070", "ti"],
        exclude_title_terms=["defekt", "bastler"],
    )

    event = asyncio.run(engine.process(observation))

    assert event is None
    assert notifier.events == []
    row = storage._conn.execute("SELECT COUNT(*) AS count FROM offers").fetchone()
    assert row["count"] == 0


def test_complete_pc_listing_with_rtx_5070_ti_is_ignored(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    observation = make_observation(
        title="Gaming PC Ryzen 7 7800X3D RTX 5070 Ti 32GB RAM 2TB SSD",
        price="1899",
        observed_at=base,
        shop="ebay",
        url="https://example.com/ebay/system",
        product_hint="rtx-5070-ti",
        include_title_terms=["rtx", "5070", "ti"],
        exclude_title_terms=["gaming pc", "komplettsystem", "zbox"],
    )

    event = asyncio.run(engine.process(observation))

    assert event is None
    assert notifier.events == []
    row = storage._conn.execute("SELECT COUNT(*) AS count FROM offers").fetchone()
    assert row["count"] == 0


def test_include_terms_require_all_tokens_for_generic_tracker(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    observation = make_observation(
        title="PlayStation 5 Slim Konsole",
        price="499",
        observed_at=base,
        shop="amazon",
        product_hint="ps5-pro",
        include_title_terms=["ps5", "pro"],
        url="https://example.com/ps5-slim",
    )

    event = asyncio.run(engine.process(observation))

    assert event is None
    assert notifier.events == []


def test_price_ceiling_skips_expensive_generic_tracker_listing(tmp_path) -> None:
    storage = Storage(tmp_path / "alerts.sqlite")
    notifier = DummyNotifierManager()
    engine = AlertEngine(storage, ProductMatcher(), notifier, enable_restock_alerts=False)

    base = datetime.now(timezone.utc)
    observation = make_observation(
        title="Sony PlayStation 5 Pro Konsole",
        price="899",
        observed_at=base,
        shop="amazon",
        product_hint="ps5-pro",
        include_title_terms=["ps5", "pro"],
        price_ceiling="799",
        url="https://example.com/ps5-pro",
    )

    event = asyncio.run(engine.process(observation))

    assert event is None
    assert notifier.events == []
