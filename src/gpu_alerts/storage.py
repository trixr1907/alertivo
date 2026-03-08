from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from gpu_alerts.models import AlertEvent, OfferObservation


def _utc_iso(dt: datetime | None = None) -> str:
    current = dt or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


@dataclass(slots=True)
class OfferRecord:
    shop: str
    product_family: str
    canonical_model: str
    offer_url: str
    last_seen_price: Decimal | None
    last_seen_stock: bool | None
    last_seen_title: str
    first_seen_at: str
    last_seen_at: str
    last_alerted_price: Decimal | None
    status_hash: str


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS offers (
                    shop TEXT NOT NULL,
                    product_family TEXT NOT NULL,
                    canonical_model TEXT NOT NULL,
                    offer_url TEXT NOT NULL,
                    last_seen_price TEXT,
                    last_seen_stock INTEGER,
                    last_seen_title TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_alerted_price TEXT,
                    status_hash TEXT NOT NULL,
                    PRIMARY KEY (shop, canonical_model, offer_url)
                );

                CREATE TABLE IF NOT EXISTS events (
                    timestamp TEXT NOT NULL,
                    shop TEXT NOT NULL,
                    source TEXT NOT NULL,
                    product_family TEXT NOT NULL,
                    canonical_model TEXT NOT NULL,
                    title TEXT NOT NULL,
                    offer_url TEXT NOT NULL,
                    old_price TEXT,
                    new_price TEXT,
                    currency TEXT NOT NULL,
                    in_stock INTEGER,
                    event_type TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_offers_shop_family ON offers(shop, product_family);
                CREATE INDEX IF NOT EXISTS idx_events_dedupe ON events(dedupe_key, timestamp);
                """
            )

    def get_offer(self, shop: str, canonical_model: str, offer_url: str) -> OfferRecord | None:
        with self._lock, self._conn:
            row = self._conn.execute(
                """
                SELECT * FROM offers
                WHERE shop = ? AND canonical_model = ? AND offer_url = ?
                """,
                (shop, canonical_model, offer_url),
            ).fetchone()

        if not row:
            return None
        return self._row_to_offer(row)

    def get_reference_price(
        self,
        shop: str,
        product_family: str,
        canonical_model: str,
        *,
        older_than: str | None = None,
    ) -> Decimal | None:
        with self._lock, self._conn:
            base_model_query = """
                SELECT last_seen_price
                FROM offers
                WHERE shop = ? AND canonical_model = ? AND last_seen_price IS NOT NULL
            """
            base_family_query = """
                SELECT MIN(CAST(last_seen_price AS REAL)) AS ref_price
                FROM offers
                WHERE shop = ? AND product_family = ? AND last_seen_price IS NOT NULL
            """
            model_params: list[str] = [shop, canonical_model]
            family_params: list[str] = [shop, product_family]
            if older_than:
                base_model_query += " AND first_seen_at < ?"
                base_family_query += " AND first_seen_at < ?"
                model_params.append(older_than)
                family_params.append(older_than)

            row = self._conn.execute(
                base_model_query + " ORDER BY last_seen_at DESC LIMIT 1",
                tuple(model_params),
            ).fetchone()
            if row and row["last_seen_price"]:
                return Decimal(row["last_seen_price"])

            row = self._conn.execute(
                base_family_query,
                tuple(family_params),
            ).fetchone()

        if not row or row["ref_price"] is None:
            return None
        return Decimal(str(row["ref_price"]))

    def upsert_offer(
        self,
        observation: OfferObservation,
        *,
        status_hash: str,
        first_seen_at: str | None = None,
        last_alerted_price: Decimal | None = None,
        clear_last_alerted_price: bool = False,
    ) -> None:
        with self._lock, self._conn:
            existing = self._conn.execute(
                """
                SELECT first_seen_at, last_alerted_price
                FROM offers
                WHERE shop = ? AND canonical_model = ? AND offer_url = ?
                """,
                observation.offer_key,
            ).fetchone()

            created_at = first_seen_at or (existing["first_seen_at"] if existing else _utc_iso(observation.observed_at))
            alerted_price = (
                None if clear_last_alerted_price else
                str(last_alerted_price) if last_alerted_price is not None else
                (existing["last_alerted_price"] if existing else None)
            )

            self._conn.execute(
                """
                INSERT INTO offers (
                    shop, product_family, canonical_model, offer_url,
                    last_seen_price, last_seen_stock, last_seen_title,
                    first_seen_at, last_seen_at, last_alerted_price, status_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shop, canonical_model, offer_url)
                DO UPDATE SET
                    product_family = excluded.product_family,
                    last_seen_price = excluded.last_seen_price,
                    last_seen_stock = excluded.last_seen_stock,
                    last_seen_title = excluded.last_seen_title,
                    last_seen_at = excluded.last_seen_at,
                    last_alerted_price = excluded.last_alerted_price,
                    status_hash = excluded.status_hash
                """,
                (
                    observation.shop,
                    observation.product_family,
                    observation.canonical_model,
                    observation.url or f"title:{observation.title}",
                    str(observation.price) if observation.price is not None else None,
                    self._bool_to_int(observation.in_stock),
                    observation.title,
                    created_at,
                    _utc_iso(observation.observed_at),
                    alerted_price,
                    status_hash,
                ),
            )

    def record_event(self, event: AlertEvent) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO events (
                    timestamp, shop, source, product_family, canonical_model, title, offer_url,
                    old_price, new_price, currency, in_stock, event_type, dedupe_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_iso(event.observed_at),
                    event.shop,
                    event.source,
                    event.product_family,
                    event.canonical_model,
                    event.title,
                    event.url,
                    str(event.old_price) if event.old_price is not None else None,
                    str(event.new_price) if event.new_price is not None else None,
                    event.currency,
                    self._bool_to_int(event.in_stock),
                    event.event_type,
                    event.dedupe_key,
                ),
            )

    def get_summary(self) -> dict[str, Any]:
        with self._lock, self._conn:
            offers_count = self._conn.execute("SELECT COUNT(*) AS count FROM offers").fetchone()["count"]
            events_count = self._conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"]
            last_event_row = self._conn.execute(
                "SELECT timestamp FROM events ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            shop_count = self._conn.execute(
                "SELECT COUNT(DISTINCT shop) AS count FROM offers"
            ).fetchone()["count"]
        return {
            "offers_count": int(offers_count or 0),
            "events_count": int(events_count or 0),
            "shop_count": int(shop_count or 0),
            "last_event_at": last_event_row["timestamp"] if last_event_row else None,
        }

    def list_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT timestamp, shop, source, product_family, canonical_model, title, offer_url,
                       old_price, new_price, currency, in_stock, event_type, dedupe_key
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "shop": row["shop"],
                "source": row["source"],
                "product_family": row["product_family"],
                "canonical_model": row["canonical_model"],
                "title": row["title"],
                "offer_url": row["offer_url"],
                "old_price": row["old_price"],
                "new_price": row["new_price"],
                "currency": row["currency"],
                "in_stock": None if row["in_stock"] is None else bool(row["in_stock"]),
                "event_type": row["event_type"],
                "dedupe_key": row["dedupe_key"],
            }
            for row in rows
        ]

    def list_recent_offers(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT shop, product_family, canonical_model, offer_url, last_seen_price, last_seen_stock,
                       last_seen_title, first_seen_at, last_seen_at, last_alerted_price
                FROM offers
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "shop": row["shop"],
                "product_family": row["product_family"],
                "canonical_model": row["canonical_model"],
                "offer_url": row["offer_url"],
                "last_seen_price": row["last_seen_price"],
                "last_seen_stock": None if row["last_seen_stock"] is None else bool(row["last_seen_stock"]),
                "last_seen_title": row["last_seen_title"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "last_alerted_price": row["last_alerted_price"],
            }
            for row in rows
        ]

    @staticmethod
    def _bool_to_int(value: bool | None) -> int | None:
        if value is None:
            return None
        return int(bool(value))

    @staticmethod
    def _row_to_offer(row: sqlite3.Row) -> OfferRecord:
        return OfferRecord(
            shop=row["shop"],
            product_family=row["product_family"],
            canonical_model=row["canonical_model"],
            offer_url=row["offer_url"],
            last_seen_price=Decimal(row["last_seen_price"]) if row["last_seen_price"] else None,
            last_seen_stock=bool(row["last_seen_stock"]) if row["last_seen_stock"] is not None else None,
            last_seen_title=row["last_seen_title"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            last_alerted_price=Decimal(row["last_alerted_price"]) if row["last_alerted_price"] else None,
            status_hash=row["status_hash"],
        )
