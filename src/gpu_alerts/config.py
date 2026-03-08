from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml


PLACEHOLDER_MARKERS = ("replace-me", "123456789:replace-me")
IDENTIFIER_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class ParserConfig:
    mode: str
    item_selector: str | None = None
    title_selector: str | None = None
    price_selector: str | None = None
    link_selector: str | None = None
    stock_selector: str | None = None
    remove_selectors: list[str] = field(default_factory=list)
    price_regex: str | None = None
    stock_in_texts: list[str] = field(default_factory=list)
    stock_out_texts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourceConfig:
    name: str
    type: str
    enabled: bool
    url: str | None
    interval_seconds: int
    timeout_seconds: int
    shop: str
    source: str
    scope: str
    command: list[str] = field(default_factory=list)
    encoding: str | None = None
    product_hint: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    include_title_terms: list[str] = field(default_factory=list)
    exclude_title_terms: list[str] = field(default_factory=list)
    price_ceiling: Decimal | None = None
    new_listing_price_below: Decimal | None = None
    parser: ParserConfig | None = None
    tracker_id: str | None = None
    tracker_name: str | None = None
    shop_id: str | None = None
    mode: str = "auto"


@dataclass(slots=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass(slots=True)
class DiscordConfig:
    webhook_url: str


@dataclass(slots=True)
class WindowsConfig:
    enabled: bool = True
    app_id: str = "Alertivo"


@dataclass(slots=True)
class SoundConfig:
    enabled: bool = True
    sound_file: str | None = None


@dataclass(slots=True)
class WebhookConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8787
    path: str = "/webhook/distill"
    token: str | None = None


@dataclass(slots=True)
class AppInfo:
    name: str = "Alertivo"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppInfo":
        return cls(name=str(payload.get("name") or "Alertivo"))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name}


@dataclass(slots=True)
class ControlCenterConfig:
    host: str = "127.0.0.1"
    port: int = 8787

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ControlCenterConfig":
        return cls(
            host=str(payload.get("host") or "127.0.0.1"),
            port=int(payload.get("port", 8787)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"host": self.host, "port": self.port}


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LoggingConfig":
        return cls(level=str(payload.get("level") or "INFO"))

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level}


@dataclass(slots=True)
class MonitoringConfig:
    enable_restock_alerts: bool = True
    new_listing_reference_min_age_seconds: int = 60
    default_timeout_seconds: int = 20
    default_interval_seconds: int = 60
    user_agent: str = "Alertivo/1.0"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MonitoringConfig":
        return cls(
            enable_restock_alerts=bool(payload.get("enable_restock_alerts", True)),
            new_listing_reference_min_age_seconds=int(payload.get("new_listing_reference_min_age_seconds", 60)),
            default_timeout_seconds=int(payload.get("default_timeout_seconds", 20)),
            default_interval_seconds=int(payload.get("default_interval_seconds", 60)),
            user_agent=str(payload.get("user_agent") or "Alertivo/1.0"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable_restock_alerts": self.enable_restock_alerts,
            "new_listing_reference_min_age_seconds": self.new_listing_reference_min_age_seconds,
            "default_timeout_seconds": self.default_timeout_seconds,
            "default_interval_seconds": self.default_interval_seconds,
            "user_agent": self.user_agent,
        }


@dataclass(slots=True)
class StorageConfig:
    appdata_subdir: str = "Alertivo"
    database_filename: str = "alerts.sqlite"
    logs_dirname: str = "logs"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StorageConfig":
        return cls(
            appdata_subdir=str(payload.get("appdata_subdir") or "Alertivo"),
            database_filename=str(payload.get("database_filename") or "alerts.sqlite"),
            logs_dirname=str(payload.get("logs_dirname") or "logs"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "appdata_subdir": self.appdata_subdir,
            "database_filename": self.database_filename,
            "logs_dirname": self.logs_dirname,
        }


@dataclass(slots=True)
class SystemConfig:
    schema_version: int = 1
    app: AppInfo = field(default_factory=AppInfo)
    control_center: ControlCenterConfig = field(default_factory=ControlCenterConfig)
    webhook_path: str = "/webhook/distill"
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    path: Path | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, path: Path | None = None) -> "SystemConfig":
        webhook = payload.get("webhook", {})
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            app=AppInfo.from_dict(payload.get("app", {})),
            control_center=ControlCenterConfig.from_dict(payload.get("control_center", {})),
            webhook_path=str(webhook.get("path") or "/webhook/distill"),
            logging=LoggingConfig.from_dict(payload.get("logging", {})),
            monitoring=MonitoringConfig.from_dict(payload.get("monitoring", {})),
            storage=StorageConfig.from_dict(payload.get("storage", {})),
            path=path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app": self.app.to_dict(),
            "control_center": self.control_center.to_dict(),
            "webhook": {"path": self.webhook_path},
            "logging": self.logging.to_dict(),
            "monitoring": self.monitoring.to_dict(),
            "storage": self.storage.to_dict(),
        }


@dataclass(slots=True)
class UserSettings:
    display_name: str = "Alertivo User"
    onboarding_completed: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UserSettings":
        return cls(
            display_name=str(payload.get("display_name") or "Alertivo User"),
            onboarding_completed=bool(payload.get("onboarding_completed", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "onboarding_completed": self.onboarding_completed,
        }


@dataclass(slots=True)
class UISettings:
    simple_mode: bool = True
    close_to_tray: bool = False
    intro_enabled: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UISettings":
        return cls(
            simple_mode=bool(payload.get("simple_mode", True)),
            close_to_tray=bool(payload.get("close_to_tray", False)),
            intro_enabled=bool(payload.get("intro_enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "simple_mode": self.simple_mode,
            "close_to_tray": self.close_to_tray,
            "intro_enabled": self.intro_enabled,
        }


@dataclass(slots=True)
class DesktopSettings:
    autostart_enabled: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DesktopSettings":
        return cls(autostart_enabled=bool(payload.get("autostart_enabled", False)))

    def to_dict(self) -> dict[str, Any]:
        return {"autostart_enabled": self.autostart_enabled}


@dataclass(slots=True)
class TelegramSettings:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TelegramSettings":
        return cls(
            enabled=bool(payload.get("enabled", False)),
            bot_token=str(payload.get("bot_token") or ""),
            chat_id=str(payload.get("chat_id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bot_token": self.bot_token,
            "chat_id": self.chat_id,
        }


@dataclass(slots=True)
class DiscordSettings:
    enabled: bool = False
    webhook_url: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DiscordSettings":
        return cls(
            enabled=bool(payload.get("enabled", False)),
            webhook_url=str(payload.get("webhook_url") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "webhook_url": self.webhook_url,
        }


@dataclass(slots=True)
class WindowsNotificationSettings:
    enabled: bool = True
    app_id: str = "Alertivo"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WindowsNotificationSettings":
        return cls(
            enabled=bool(payload.get("enabled", True)),
            app_id=str(payload.get("app_id") or "Alertivo"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "app_id": self.app_id,
        }


@dataclass(slots=True)
class SoundSettings:
    enabled: bool = True
    sound_file: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SoundSettings":
        sound_file = payload.get("sound_file")
        return cls(
            enabled=bool(payload.get("enabled", True)),
            sound_file=str(sound_file) if sound_file not in (None, "") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "sound_file": self.sound_file,
        }


@dataclass(slots=True)
class NotificationSettings:
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    discord: DiscordSettings = field(default_factory=DiscordSettings)
    windows: WindowsNotificationSettings = field(default_factory=WindowsNotificationSettings)
    sound: SoundSettings = field(default_factory=SoundSettings)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NotificationSettings":
        return cls(
            telegram=TelegramSettings.from_dict(payload.get("telegram", {})),
            discord=DiscordSettings.from_dict(payload.get("discord", {})),
            windows=WindowsNotificationSettings.from_dict(payload.get("windows", {})),
            sound=SoundSettings.from_dict(payload.get("sound", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "telegram": self.telegram.to_dict(),
            "discord": self.discord.to_dict(),
            "windows": self.windows.to_dict(),
            "sound": self.sound.to_dict(),
        }


@dataclass(slots=True)
class DistillIntegrationSettings:
    enabled: bool = False
    token: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DistillIntegrationSettings":
        return cls(
            enabled=bool(payload.get("enabled", False)),
            token=str(payload.get("token") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "token": self.token,
        }


@dataclass(slots=True)
class IntegrationSettings:
    distill: DistillIntegrationSettings = field(default_factory=DistillIntegrationSettings)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntegrationSettings":
        return cls(distill=DistillIntegrationSettings.from_dict(payload.get("distill", {})))

    def to_dict(self) -> dict[str, Any]:
        return {"distill": self.distill.to_dict()}


@dataclass(slots=True)
class MetaSettings:
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MetaSettings":
        return cls(
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def touch(self) -> None:
        now = _utc_now_iso()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class SettingsConfig:
    schema_version: int = 1
    user: UserSettings = field(default_factory=UserSettings)
    ui: UISettings = field(default_factory=UISettings)
    desktop: DesktopSettings = field(default_factory=DesktopSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    integrations: IntegrationSettings = field(default_factory=IntegrationSettings)
    meta: MetaSettings = field(default_factory=MetaSettings)
    path: Path | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, path: Path | None = None) -> "SettingsConfig":
        settings = cls(
            schema_version=int(payload.get("schema_version", 1)),
            user=UserSettings.from_dict(payload.get("user", {})),
            ui=UISettings.from_dict(payload.get("ui", {})),
            desktop=DesktopSettings.from_dict(payload.get("desktop", {})),
            notifications=NotificationSettings.from_dict(payload.get("notifications", {})),
            integrations=IntegrationSettings.from_dict(payload.get("integrations", {})),
            meta=MetaSettings.from_dict(payload.get("meta", {})),
            path=path,
        )
        settings.meta.touch()
        return settings

    def to_dict(self) -> dict[str, Any]:
        self.meta.touch()
        return {
            "schema_version": self.schema_version,
            "user": self.user.to_dict(),
            "ui": self.ui.to_dict(),
            "desktop": self.desktop.to_dict(),
            "notifications": self.notifications.to_dict(),
            "integrations": self.integrations.to_dict(),
            "meta": self.meta.to_dict(),
        }


@dataclass(slots=True)
class TrackerFilterConfig:
    include_terms: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    price_ceiling: Decimal | None = None
    new_listing_price_below: Decimal | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrackerFilterConfig":
        return cls(
            include_terms=_clean_terms(payload.get("include_terms", [])),
            exclude_terms=_clean_terms(payload.get("exclude_terms", [])),
            price_ceiling=_to_decimal(payload.get("price_ceiling")),
            new_listing_price_below=_to_decimal(payload.get("new_listing_price_below")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_terms": list(self.include_terms),
            "exclude_terms": list(self.exclude_terms),
            "price_ceiling": _decimal_to_json(self.price_ceiling),
            "new_listing_price_below": _decimal_to_json(self.new_listing_price_below),
        }


@dataclass(slots=True)
class TrackerProductConfig:
    title: str = ""
    brand: str = ""
    image_url: str = ""
    identifier_type: str = ""
    identifier_value: str = ""
    source: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TrackerProductConfig | None":
        if not isinstance(payload, dict):
            return None
        product = cls(
            title=str(payload.get("title") or "").strip(),
            brand=str(payload.get("brand") or "").strip(),
            image_url=str(payload.get("image_url") or "").strip(),
            identifier_type=str(payload.get("identifier_type") or "").strip(),
            identifier_value=str(payload.get("identifier_value") or "").strip(),
            source=str(payload.get("source") or "").strip(),
        )
        if not any(
            (
                product.title,
                product.brand,
                product.image_url,
                product.identifier_type,
                product.identifier_value,
                product.source,
            )
        ):
            return None
        return product

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "brand": self.brand,
            "image_url": self.image_url,
            "identifier_type": self.identifier_type,
            "identifier_value": self.identifier_value,
            "source": self.source,
        }


@dataclass(slots=True)
class TrackerShopConfig:
    shop_id: str
    enabled: bool = True
    mode: str = "auto"
    url: str | None = None
    interval_seconds: int | None = None
    timeout_seconds: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrackerShopConfig":
        return cls(
            shop_id=str(payload.get("shop_id") or "").strip(),
            enabled=bool(payload.get("enabled", True)),
            mode=str(payload.get("mode") or "auto").strip().lower(),
            url=str(payload.get("url") or "").strip() or None,
            interval_seconds=int(payload["interval_seconds"]) if payload.get("interval_seconds") is not None else None,
            timeout_seconds=int(payload["timeout_seconds"]) if payload.get("timeout_seconds") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "shop_id": self.shop_id,
            "enabled": self.enabled,
            "mode": self.mode,
            "url": self.url,
        }
        if self.interval_seconds is not None:
            payload["interval_seconds"] = self.interval_seconds
        if self.timeout_seconds is not None:
            payload["timeout_seconds"] = self.timeout_seconds
        return payload


@dataclass(slots=True)
class TrackerMeta:
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrackerMeta":
        meta = cls(
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )
        meta.touch()
        return meta

    def touch(self) -> None:
        now = _utc_now_iso()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        self.touch()
        return {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class TrackerConfig:
    schema_version: int
    id: str
    name: str
    enabled: bool
    query: str
    filters: TrackerFilterConfig = field(default_factory=TrackerFilterConfig)
    product: TrackerProductConfig | None = None
    shops: list[TrackerShopConfig] = field(default_factory=list)
    meta: TrackerMeta = field(default_factory=TrackerMeta)
    path: Path | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, path: Path | None = None) -> "TrackerConfig":
        tracker = cls(
            schema_version=int(payload.get("schema_version", 1)),
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            enabled=bool(payload.get("enabled", True)),
            query=str(payload.get("query") or "").strip(),
            filters=TrackerFilterConfig.from_dict(payload.get("filters", {})),
            product=TrackerProductConfig.from_dict(payload.get("product")),
            shops=[
                TrackerShopConfig.from_dict(item)
                for item in payload.get("shops", [])
                if str(item.get("shop_id") or "").strip()
            ],
            meta=TrackerMeta.from_dict(payload.get("meta", {})),
            path=path,
        )
        if not tracker.id:
            tracker.id = slugify_identifier(tracker.name or tracker.query or "tracker")
        if not tracker.name:
            tracker.name = tracker.query or tracker.id
        if not tracker.query:
            tracker.query = tracker.name
        return tracker

    def to_dict(self) -> dict[str, Any]:
        self.meta.touch()
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "query": self.query,
            "filters": self.filters.to_dict(),
            "product": self.product.to_dict() if self.product else None,
            "shops": [shop.to_dict() for shop in self.shops],
            "meta": self.meta.to_dict(),
        }


@dataclass(slots=True)
class AppConfig:
    config_path: Path
    install_dir: Path
    appdata_dir: Path
    settings_path: Path
    trackers_dir: Path
    logs_dir: Path
    state_dir: Path
    migration_state_path: Path
    database_path: Path
    log_level: str
    user_agent: str
    enable_restock_alerts: bool
    new_listing_reference_min_age_seconds: int
    sources: list[SourceConfig]
    trackers: list[TrackerConfig]
    settings: SettingsConfig
    system: SystemConfig
    telegram: TelegramConfig | None = None
    discord: DiscordConfig | None = None
    windows: WindowsConfig = field(default_factory=WindowsConfig)
    sound: SoundConfig = field(default_factory=SoundConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass(slots=True)
class ShopCatalogEntry:
    shop_id: str
    label: str
    collector_type: str
    shop: str
    source: str
    scope: str
    parser: ParserConfig | None = None
    headers: dict[str, str] = field(default_factory=dict)
    command_template: list[str] = field(default_factory=list)
    encoding: str | None = None
    url_template: str | None = None
    interval_seconds: int | None = None
    timeout_seconds: int | None = None
    supports_distill: bool = False
    distill_note: str = ""


SHOP_ID_ALIASES: dict[str, str] = {
    "amazon": "amazon-search",
    "alternate": "alternate-search",
    "billiger": "billiger-search",
    "caseking": "caseking-search",
    "geizhals": "geizhals-search",
    "kleinanzeigen": "kleinanzeigen-search",
    "mediamarkt": "mediamarkt-search",
    "mindfactory": "mindfactory-search",
    "saturn": "saturn-search",
}

SHOP_CATALOG: dict[str, ShopCatalogEntry] = {
    "amazon-search": ShopCatalogEntry(
        shop_id="amazon-search",
        label="Amazon",
        collector_type="distill",
        shop="amazon",
        source="shop",
        scope="shop_search",
        url_template="https://www.amazon.de/s?k={query_plus}",
        supports_distill=True,
        distill_note="Lokal im Browser mit Distill oder ähnlicher Erweiterung überwachen.",
    ),
    "alternate-search": ShopCatalogEntry(
        shop_id="alternate-search",
        label="Alternate",
        collector_type="http",
        shop="alternate",
        source="shop",
        scope="shop_search",
        parser=ParserConfig(
            mode="list",
            item_selector="a.card.productBox",
            title_selector=".product-name",
            price_selector=".price",
            link_selector="__self__",
            stock_selector=".delivery-info",
            stock_in_texts=["Auf Lager", "lieferbar", "sofort"],
            stock_out_texts=["nicht lieferbar", "ausverkauft", "derzeit nicht"],
        ),
        interval_seconds=25,
        timeout_seconds=20,
        url_template="https://www.alternate.de/listing.xhtml?q={query_plus}",
        supports_distill=True,
        distill_note="Wenn die Suchseite JS-lastig wird, Distill im eingeloggten Browser verwenden.",
    ),
    "billiger-search": ShopCatalogEntry(
        shop_id="billiger-search",
        label="billiger.de",
        collector_type="http",
        shop="billiger",
        source="billiger",
        scope="aggregator",
        parser=ParserConfig(
            mode="list",
            item_selector="[data-test-item-view-tile]",
            title_selector="a[title]",
            price_selector="[data-bde-price]",
            link_selector="a[title]",
        ),
        interval_seconds=90,
        timeout_seconds=20,
        url_template="https://www.billiger.de/search?searchstring={query_plus}",
    ),
    "caseking-search": ShopCatalogEntry(
        shop_id="caseking-search",
        label="Caseking",
        collector_type="distill",
        shop="caseking",
        source="shop",
        scope="shop_search",
        url_template="https://www.caseking.de/search?search={query_plus}",
        supports_distill=True,
        distill_note="Caseking liefert häufig Cloudflare-Challenges; Distill ist die robuste Option.",
    ),
    "geizhals-product": ShopCatalogEntry(
        shop_id="geizhals-product",
        label="Geizhals Produktseite",
        collector_type="http",
        shop="geizhals",
        source="geizhals",
        scope="aggregator",
        parser=ParserConfig(
            mode="single",
            title_selector="h1.variant__header__headline",
            price_selector="#pricerange-min .gh_price, .offer__price .gh_price",
            stock_selector=".offer__delivery-time, #pricerange-no-offers",
            stock_in_texts=["Auf Lager", "lagernd", "verfügbar"],
            stock_out_texts=["Derzeit keine Angebote", "ausverkauft", "nicht verfügbar"],
        ),
        interval_seconds=90,
        timeout_seconds=20,
    ),
    "geizhals-search": ShopCatalogEntry(
        shop_id="geizhals-search",
        label="Geizhals Suche",
        collector_type="http",
        shop="geizhals",
        source="geizhals",
        scope="aggregator",
        parser=ParserConfig(
            mode="list",
            item_selector="article",
            title_selector="h3 a, h3",
            price_selector="__self__",
            price_regex=r"ab\s*€\s*([0-9\.\,]+)",
            link_selector="h3 a",
            stock_selector="__self__",
            stock_in_texts=["lagernd beim Händler", "lagernd", "verfügbar"],
            stock_out_texts=["derzeit keine angebote", "ausverkauft", "nicht verfügbar"],
        ),
        interval_seconds=90,
        timeout_seconds=20,
        url_template="https://geizhals.de/?fs={query_plus}&hloc=at&hloc=de",
    ),
    "kleinanzeigen-search": ShopCatalogEntry(
        shop_id="kleinanzeigen-search",
        label="Kleinanzeigen",
        collector_type="command",
        shop="kleinanzeigen",
        source="classifieds",
        scope="shop_search",
        parser=ParserConfig(
            mode="list",
            item_selector="article.aditem",
            title_selector="h2 a",
            price_selector=".aditem-main--middle--price-shipping--price",
            link_selector="h2 a",
            stock_selector="__self__",
            stock_in_texts=["Direkt kaufen", "VB", "€"],
        ),
        command_template=["curl", "-L", "--silent", "{url}"],
        interval_seconds=45,
        timeout_seconds=20,
        url_template="https://www.kleinanzeigen.de/s-{query_plus}/k0",
        supports_distill=True,
        distill_note="Für JS-lastige Kategorien kann alternativ Distill genutzt werden.",
    ),
    "mediamarkt-search": ShopCatalogEntry(
        shop_id="mediamarkt-search",
        label="MediaMarkt",
        collector_type="distill",
        shop="mediamarkt",
        source="shop",
        scope="shop_search",
        url_template="https://www.mediamarkt.de/de/search.html?query={query_plus}",
        supports_distill=True,
        distill_note="Schnelle Suchseite, aber zuverlässig über Distill.",
    ),
    "mindfactory-search": ShopCatalogEntry(
        shop_id="mindfactory-search",
        label="Mindfactory",
        collector_type="command",
        shop="mindfactory",
        source="shop",
        scope="shop_search",
        parser=ParserConfig(
            mode="list",
            item_selector="div.p",
            title_selector=".pname",
            price_selector=".pprice",
            link_selector="a.phover-complete-link, a.p-complete-link",
            stock_selector=".pshipping span",
            stock_in_texts=["Lagernd", "lagernd", "Sofort"],
            stock_out_texts=["nicht lagernd", "nicht verfügbar", "ausverkauft"],
        ),
        command_template=["curl", "-L", "--silent", "{url}"],
        encoding="iso-8859-15",
        interval_seconds=25,
        timeout_seconds=20,
        url_template="https://www.mindfactory.de/search_result.php?search_query={query_plus}",
        supports_distill=True,
        distill_note="HTTP funktioniert meist direkt; Distill ist die schnellere Alternative bei Bedarf.",
    ),
    "saturn-search": ShopCatalogEntry(
        shop_id="saturn-search",
        label="Saturn",
        collector_type="distill",
        shop="saturn",
        source="shop",
        scope="shop_search",
        url_template="https://www.saturn.de/de/search.html?query={query_plus}",
        supports_distill=True,
        distill_note="Schneller Suchseiten-Monitor per Distill.",
    ),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_real_secret(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return lowered != "" and not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _clean_terms(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("\r", "\n")
    parts = text.replace(",", "\n").split("\n")
    return [part.strip() for part in parts if part.strip()]


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "null"):
        return None
    try:
        return Decimal(str(value).strip())
    except Exception:
        return None


def _decimal_to_json(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral():
        return int(value)
    return float(value)


def _read_json_file(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def slugify_identifier(value: str) -> str:
    lowered = value.strip().lower()
    slug = IDENTIFIER_PATTERN.sub("-", lowered).strip("-")
    return slug or "tracker"


def default_system_config() -> SystemConfig:
    return SystemConfig()


def default_settings_config(*, path: Path | None = None) -> SettingsConfig:
    settings = SettingsConfig(path=path)
    settings.meta.touch()
    return settings


def load_system_config(path: str | Path) -> SystemConfig:
    system_path = Path(path).resolve()
    if not system_path.exists():
        system = default_system_config()
        system.path = system_path
        save_system_config(system)
        return system
    return SystemConfig.from_dict(_read_json_file(system_path), path=system_path)


def save_system_config(system: SystemConfig) -> None:
    if not system.path:
        raise ValueError("SystemConfig.path is required for persistence")
    _write_json_file(system.path, system.to_dict())


def load_settings_config(path: str | Path) -> SettingsConfig:
    settings_path = Path(path).resolve()
    if not settings_path.exists():
        settings = default_settings_config(path=settings_path)
        save_settings_config(settings)
        return settings
    return SettingsConfig.from_dict(_read_json_file(settings_path), path=settings_path)


def save_settings_config(settings: SettingsConfig) -> None:
    if not settings.path:
        raise ValueError("SettingsConfig.path is required for persistence")
    _write_json_file(settings.path, settings.to_dict())


def load_tracker_config(path: str | Path) -> TrackerConfig:
    tracker_path = Path(path).resolve()
    return TrackerConfig.from_dict(_read_json_file(tracker_path), path=tracker_path)


def load_trackers(trackers_dir: str | Path) -> list[TrackerConfig]:
    directory = Path(trackers_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    trackers: list[TrackerConfig] = []
    for tracker_path in sorted(directory.glob("*.json")):
        payload = _read_json_file(tracker_path)
        trackers.append(TrackerConfig.from_dict(payload, path=tracker_path))
    return trackers


def save_tracker_config(tracker: TrackerConfig) -> None:
    if tracker.path is None:
        raise ValueError("TrackerConfig.path is required for persistence")
    tracker.meta.touch()
    _write_json_file(tracker.path, tracker.to_dict())


def create_tracker_config(*, trackers_dir: str | Path, payload: dict[str, Any]) -> TrackerConfig:
    trackers_path = Path(trackers_dir).resolve()
    trackers_path.mkdir(parents=True, exist_ok=True)
    tracker = TrackerConfig.from_dict(payload)
    tracker.path = trackers_path / f"{tracker.id}.json"
    save_tracker_config(tracker)
    return tracker


def delete_tracker_config(tracker: TrackerConfig) -> None:
    if tracker.path and tracker.path.exists():
        tracker.path.unlink()


def load_config(path: str | Path) -> AppConfig:
    system = load_system_config(path)
    if system.path is None:
        raise ValueError("System config path missing")

    install_dir = system.path.parent
    appdata_root = resolve_appdata_dir(system.storage.appdata_subdir)
    settings_path = appdata_root / "settings.json"
    trackers_dir = appdata_root / "trackers"
    data_dir = appdata_root / "data"
    logs_dir = appdata_root / system.storage.logs_dirname
    state_dir = appdata_root / "state"
    migration_state_path = state_dir / "migration.json"
    database_path = data_dir / system.storage.database_filename

    trackers_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    _bootstrap_runtime_storage(
        system=system,
        settings_path=settings_path,
        trackers_dir=trackers_dir,
        migration_state_path=migration_state_path,
    )

    settings = load_settings_config(settings_path)
    trackers = load_trackers(trackers_dir)
    sources = build_sources_from_trackers(trackers, system)

    telegram = None
    if settings.notifications.telegram.enabled and _is_real_secret(settings.notifications.telegram.bot_token) and _is_real_secret(settings.notifications.telegram.chat_id):
        telegram = TelegramConfig(
            bot_token=settings.notifications.telegram.bot_token,
            chat_id=settings.notifications.telegram.chat_id,
        )

    discord = None
    if settings.notifications.discord.enabled and _is_real_secret(settings.notifications.discord.webhook_url):
        discord = DiscordConfig(webhook_url=settings.notifications.discord.webhook_url)

    webhook = WebhookConfig(
        enabled=bool(settings.integrations.distill.enabled),
        host=system.control_center.host,
        port=system.control_center.port,
        path=system.webhook_path,
        token=settings.integrations.distill.token if _is_real_secret(settings.integrations.distill.token) else None,
    )

    return AppConfig(
        config_path=system.path,
        install_dir=install_dir,
        appdata_dir=appdata_root,
        settings_path=settings_path,
        trackers_dir=trackers_dir,
        logs_dir=logs_dir,
        state_dir=state_dir,
        migration_state_path=migration_state_path,
        database_path=database_path,
        log_level=system.logging.level,
        user_agent=system.monitoring.user_agent,
        enable_restock_alerts=system.monitoring.enable_restock_alerts,
        new_listing_reference_min_age_seconds=system.monitoring.new_listing_reference_min_age_seconds,
        sources=sources,
        trackers=trackers,
        settings=settings,
        system=system,
        telegram=telegram,
        discord=discord,
        windows=WindowsConfig(
            enabled=settings.notifications.windows.enabled,
            app_id=settings.notifications.windows.app_id,
        ),
        sound=SoundConfig(
            enabled=settings.notifications.sound.enabled,
            sound_file=settings.notifications.sound.sound_file,
        ),
        webhook=webhook,
    )


def resolve_appdata_dir(appdata_subdir: str) -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata).expanduser().resolve() / appdata_subdir
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config).expanduser().resolve() / appdata_subdir
    return Path.home().resolve() / ".config" / appdata_subdir


def build_sources_from_trackers(trackers: list[TrackerConfig], system: SystemConfig) -> list[SourceConfig]:
    sources: list[SourceConfig] = []
    seen_names: set[str] = set()
    for tracker in trackers:
        for shop in tracker.shops:
            source = build_source_config(tracker, shop, system)
            if not source:
                continue
            base_name = source.name
            if base_name in seen_names:
                suffix = 2
                while f"{base_name}-{suffix}" in seen_names:
                    suffix += 1
                source.name = f"{base_name}-{suffix}"
            seen_names.add(source.name)
            sources.append(source)
    return sources


def build_source_config(tracker: TrackerConfig, shop: TrackerShopConfig, system: SystemConfig) -> SourceConfig | None:
    entry = get_shop_catalog_entry(shop.shop_id)
    if entry is None:
        return None

    requested_mode = shop.mode or "auto"
    collector_type = resolve_collector_type(entry, requested_mode)
    url = shop.url or build_default_shop_url(entry, tracker.query)
    interval_seconds = shop.interval_seconds or entry.interval_seconds or system.monitoring.default_interval_seconds
    timeout_seconds = shop.timeout_seconds or entry.timeout_seconds or system.monitoring.default_timeout_seconds
    name = f"{tracker.id}__{slugify_identifier(entry.shop_id)}"
    parser = clone_parser(entry.parser)
    command = []
    if collector_type == "command":
        command = [part.format(url=url or "", query=tracker.query, query_plus=quote_plus(tracker.query)) for part in entry.command_template]

    return SourceConfig(
        name=name,
        type=collector_type,
        enabled=bool(tracker.enabled and shop.enabled),
        url=url,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        shop=entry.shop,
        source=entry.source,
        scope=entry.scope,
        command=command,
        encoding=entry.encoding,
        product_hint=tracker.id,
        headers=dict(entry.headers),
        include_title_terms=list(tracker.filters.include_terms),
        exclude_title_terms=list(tracker.filters.exclude_terms),
        price_ceiling=tracker.filters.price_ceiling,
        new_listing_price_below=tracker.filters.new_listing_price_below,
        parser=parser,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        shop_id=entry.shop_id,
        mode=requested_mode,
    )


def clone_parser(parser: ParserConfig | None) -> ParserConfig | None:
    if parser is None:
        return None
    return ParserConfig(
        mode=parser.mode,
        item_selector=parser.item_selector,
        title_selector=parser.title_selector,
        price_selector=parser.price_selector,
        link_selector=parser.link_selector,
        stock_selector=parser.stock_selector,
        remove_selectors=list(parser.remove_selectors),
        price_regex=parser.price_regex,
        stock_in_texts=list(parser.stock_in_texts),
        stock_out_texts=list(parser.stock_out_texts),
    )


def get_shop_catalog_entry(shop_id: str) -> ShopCatalogEntry | None:
    resolved_id = SHOP_ID_ALIASES.get(shop_id, shop_id)
    return SHOP_CATALOG.get(resolved_id)


def list_available_shops() -> list[dict[str, Any]]:
    items = []
    for shop_id in sorted(SHOP_CATALOG):
        entry = SHOP_CATALOG[shop_id]
        items.append(
            {
                "shop_id": entry.shop_id,
                "label": entry.label,
                "supports_distill": entry.supports_distill,
                "collector_type": entry.collector_type,
            }
        )
    return items


def resolve_collector_type(entry: ShopCatalogEntry, requested_mode: str) -> str:
    mode = requested_mode.lower().strip()
    if mode == "distill":
        return "distill"
    if mode == "http" and entry.collector_type == "http":
        return "http"
    if mode == "command" and entry.collector_type == "command":
        return "command"
    if mode == "auto":
        return entry.collector_type
    return entry.collector_type if entry.collector_type != "distill" else "distill"


def build_default_shop_url(entry: ShopCatalogEntry, query: str) -> str | None:
    if not entry.url_template:
        return None
    return entry.url_template.format(query=query, query_plus=quote_plus(query))


def build_distill_targets_for_tracker(
    tracker: TrackerConfig,
    *,
    system: SystemConfig,
    host: str,
    port: int,
    path: str,
    token: str | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for shop in tracker.shops:
        entry = get_shop_catalog_entry(shop.shop_id)
        if entry is None or not entry.supports_distill:
            continue
        url = shop.url or build_default_shop_url(entry, tracker.query)
        source = build_source_config(tracker, shop, system)
        if source is None:
            continue
        snippet = {
            "url": f"http://{host}:{port}{path}",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
            },
            "body": {
                "shop": source.shop,
                "source": source.source,
                "scope": source.scope,
                "product_hint": tracker.id,
                "include_title_terms": list(tracker.filters.include_terms),
                "exclude_title_terms": list(tracker.filters.exclude_terms),
                "price_ceiling": _decimal_to_json(tracker.filters.price_ceiling),
                "new_listing_price_below": _decimal_to_json(tracker.filters.new_listing_price_below),
            },
        }
        if token:
            snippet["headers"]["X-Webhook-Token"] = token
        targets.append(
            {
                "tracker_id": tracker.id,
                "tracker_name": tracker.name,
                "shop_id": entry.shop_id,
                "shop_label": entry.label,
                "url": url,
                "mode": shop.mode,
                "note": entry.distill_note,
                "snippet": json.dumps(snippet, ensure_ascii=True, indent=2),
            }
        )
    return targets


def build_distill_targets(config: AppConfig) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for tracker in config.trackers:
        targets.extend(
            build_distill_targets_for_tracker(
                tracker,
                system=config.system,
                host=config.webhook.host,
                port=config.webhook.port,
                path=config.webhook.path,
                token=config.webhook.token,
            )
        )
    return targets


def upsert_system_monitoring(system: SystemConfig, *, enable_restock_alerts: bool | None = None, new_listing_reference_min_age_seconds: int | None = None) -> None:
    if enable_restock_alerts is not None:
        system.monitoring.enable_restock_alerts = bool(enable_restock_alerts)
    if new_listing_reference_min_age_seconds is not None:
        system.monitoring.new_listing_reference_min_age_seconds = max(0, int(new_listing_reference_min_age_seconds))
    save_system_config(system)


def _bootstrap_runtime_storage(
    *,
    system: SystemConfig,
    settings_path: Path,
    trackers_dir: Path,
    migration_state_path: Path,
) -> None:
    has_trackers = any(trackers_dir.glob("*.json"))
    if settings_path.exists() or has_trackers:
        if not settings_path.exists():
            save_settings_config(default_settings_config(path=settings_path))
        return

    install_dir = system.path.parent if system.path else Path.cwd()
    legacy_paths = discover_legacy_paths(install_dir)
    if _should_import_legacy_configuration(install_dir=install_dir, legacy_paths=legacy_paths):
        import_legacy_configuration(
            system=system,
            settings_path=settings_path,
            trackers_dir=trackers_dir,
            migration_state_path=migration_state_path,
            legacy_paths=legacy_paths,
        )
        return

    save_settings_config(default_settings_config(path=settings_path))


def discover_legacy_paths(install_dir: Path) -> dict[str, Path]:
    config_dir = install_dir / "config"
    return {
        "monitor": config_dir / "monitor.yaml",
        "env": config_dir / "alerts.env.ps1",
        "profile": config_dir / "user-profile.json",
    }


def _should_import_legacy_configuration(*, install_dir: Path, legacy_paths: dict[str, Path]) -> bool:
    if not any(path.exists() for path in legacy_paths.values()):
        return False

    force_import = str(os.getenv("ALERTIVO_IMPORT_LEGACY_FROM_REPO") or "").strip().lower()
    if force_import in {"1", "true", "yes", "on"}:
        return True

    # Source checkouts often carry repo-local legacy examples or ignored dev files.
    # A clean first run should stay blank unless migration is explicitly requested.
    return not (install_dir / ".git").exists()


def import_legacy_configuration(
    *,
    system: SystemConfig,
    settings_path: Path,
    trackers_dir: Path,
    migration_state_path: Path,
    legacy_paths: dict[str, Path],
) -> None:
    raw_monitor = _load_legacy_monitor(legacy_paths["monitor"])
    env_values = _load_legacy_env(legacy_paths["env"])
    legacy_profile = _read_json_file(legacy_paths["profile"], default={}) if legacy_paths["profile"].exists() else {}

    settings = default_settings_config(path=settings_path)
    settings.user.display_name = str(legacy_profile.get("display_name") or settings.user.display_name)
    settings.user.onboarding_completed = bool(legacy_profile.get("onboarding_completed", False))
    settings.ui.simple_mode = bool(legacy_profile.get("simple_mode", True))
    settings.ui.close_to_tray = bool(legacy_profile.get("close_to_tray", False))
    settings.ui.intro_enabled = bool(legacy_profile.get("intro_enabled", True))
    settings.desktop.autostart_enabled = bool(legacy_profile.get("autostart_enabled", False))
    settings.meta.created_at = str(legacy_profile.get("created_at") or "")
    settings.meta.updated_at = str(legacy_profile.get("updated_at") or "")

    telegram = raw_monitor.get("telegram", {}) if isinstance(raw_monitor.get("telegram"), dict) else {}
    discord = raw_monitor.get("discord", {}) if isinstance(raw_monitor.get("discord"), dict) else {}
    windows = raw_monitor.get("windows", {}) if isinstance(raw_monitor.get("windows"), dict) else {}
    sound = raw_monitor.get("sound", {}) if isinstance(raw_monitor.get("sound"), dict) else {}
    webhook = raw_monitor.get("webhook", {}) if isinstance(raw_monitor.get("webhook"), dict) else {}

    telegram_bot_token = _normalize_legacy_secret(env_values.get("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id = _normalize_legacy_secret(env_values.get("TELEGRAM_CHAT_ID"))
    discord_webhook_url = _normalize_legacy_secret(env_values.get("DISCORD_WEBHOOK_URL"))
    distill_token = _normalize_legacy_secret(env_values.get("WEBHOOK_TOKEN"))

    settings.notifications.telegram.enabled = bool(telegram_bot_token and telegram_chat_id)
    settings.notifications.telegram.bot_token = telegram_bot_token
    settings.notifications.telegram.chat_id = telegram_chat_id
    settings.notifications.discord.enabled = bool(discord_webhook_url)
    settings.notifications.discord.webhook_url = discord_webhook_url
    settings.notifications.windows.enabled = bool(windows.get("enabled", True))
    settings.notifications.windows.app_id = str(windows.get("app_id") or "Alertivo")
    settings.notifications.sound.enabled = bool(sound.get("enabled", True))
    settings.notifications.sound.sound_file = _normalize_legacy_sound_file(
        env_values.get("ALERT_SOUND_FILE") or sound.get("sound_file")
    )
    settings.integrations.distill.enabled = bool(webhook.get("enabled", False))
    settings.integrations.distill.token = distill_token
    save_settings_config(settings)

    trackers_dir.mkdir(parents=True, exist_ok=True)
    imported_trackers: list[str] = []
    unmapped_sources: list[str] = []
    for tracker in _convert_legacy_sources_to_trackers(raw_monitor.get("sources", []), raw_monitor):
        tracker.path = trackers_dir / f"{tracker.id}.json"
        save_tracker_config(tracker)
        imported_trackers.append(tracker.id)

    for source in raw_monitor.get("sources", []):
        if not _map_legacy_source_to_shop_id(source):
            unmapped_sources.append(str(source.get("name") or source.get("shop") or "unknown"))

    migration_payload = {
        "version": 2,
        "migrated": True,
        "migrated_at": _utc_now_iso(),
        "legacy_paths": {key: str(value) for key, value in legacy_paths.items() if value.exists()},
        "settings_path": str(settings_path),
        "trackers_dir": str(trackers_dir),
        "imported_trackers": imported_trackers,
        "unmapped_sources": sorted(set(unmapped_sources)),
    }
    _write_json_file(migration_state_path, migration_payload)


def _load_legacy_monitor(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_legacy_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("$env:") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        env_key = key.split(":", 1)[1].strip()
        value = raw_value.strip().strip('"').strip("'")
        values[env_key] = value
    return values


def _normalize_legacy_secret(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip()
    if not _is_real_secret(normalized):
        return ""
    return normalized


def _normalize_legacy_sound_file(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.startswith("${") and normalized.endswith("}"):
        return None
    return normalized


def _convert_legacy_sources_to_trackers(sources: list[dict[str, Any]], raw_monitor: dict[str, Any]) -> list[TrackerConfig]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        hint = str(source.get("product_hint") or source.get("shop") or source.get("name") or "tracker")
        grouped.setdefault(hint, []).append(source)

    trackers: list[TrackerConfig] = []
    for hint, items in grouped.items():
        tracker = _legacy_tracker_from_group(hint, items, raw_monitor)
        trackers.append(tracker)
    return trackers


def _legacy_tracker_from_group(hint: str, items: list[dict[str, Any]], raw_monitor: dict[str, Any]) -> TrackerConfig:
    tracker_id = slugify_identifier(hint)
    fallback_name = str(items[0].get("product_hint") or items[0].get("name") or hint)
    name = _humanize_identifier(fallback_name)
    query = name
    include_terms = _clean_terms(fallback_name)
    exclude_terms = _collect_legacy_tracker_terms(raw_monitor, hint, kind="exclude")

    shops: list[TrackerShopConfig] = []
    new_listing_price_below: Decimal | None = None
    for item in items:
        shop_id = _map_legacy_source_to_shop_id(item)
        if not shop_id:
            continue
        shops.append(
            TrackerShopConfig(
                shop_id=shop_id,
                enabled=bool(item.get("enabled", True)),
                mode="auto",
                url=str(item.get("url") or "").strip() or None,
                interval_seconds=int(item["interval_seconds"]) if item.get("interval_seconds") is not None else None,
                timeout_seconds=int(item["timeout_seconds"]) if item.get("timeout_seconds") is not None else None,
            )
        )
        exclude_terms.extend(_clean_terms(item.get("exclude_title_terms", [])))
        threshold = _to_decimal(item.get("new_listing_price_below"))
        if threshold is not None and new_listing_price_below is None:
            new_listing_price_below = threshold

    return TrackerConfig(
        schema_version=1,
        id=tracker_id,
        name=name,
        enabled=any(shop.enabled for shop in shops) if shops else True,
        query=query,
        filters=TrackerFilterConfig(
            include_terms=list(dict.fromkeys(include_terms)),
            exclude_terms=list(dict.fromkeys(exclude_terms)),
            price_ceiling=None,
            new_listing_price_below=new_listing_price_below,
        ),
        shops=shops,
        meta=TrackerMeta(),
    )


def _map_legacy_source_to_shop_id(source: dict[str, Any]) -> str | None:
    shop = str(source.get("shop") or "")
    if shop == "geizhals":
        parser_payload = source.get("parser", {})
        parser_mode = ""
        if isinstance(parser_payload, dict):
            parser_mode = str(parser_payload.get("mode") or "").strip().lower()
        return "geizhals-product" if parser_mode == "single" else "geizhals-search"
    return SHOP_ID_ALIASES.get(shop)


def _humanize_identifier(value: str) -> str:
    parts = [part for part in IDENTIFIER_PATTERN.split(value.strip()) if part]
    humanized: list[str] = []
    for part in parts:
        if part.isdigit():
            humanized.append(part)
            continue
        if any(char.isdigit() for char in part) or part.lower() in {"cpu", "gpu", "oled", "pc", "ps", "ram", "rtx", "ssd", "usb", "wifi"}:
            humanized.append(part.upper())
            continue
        humanized.append(part.capitalize())
    return " ".join(humanized) or "Tracker"


def _collect_legacy_tracker_terms(raw_monitor: dict[str, Any], hint: str, *, kind: str) -> list[str]:
    prefix = slugify_identifier(hint).replace("-", "_")
    terms: list[str] = []
    for key, value in raw_monitor.items():
        normalized_key = slugify_identifier(str(key)).replace("-", "_")
        if not normalized_key.endswith("_terms"):
            continue
        if normalized_key == f"{prefix}_{kind}_terms" or normalized_key.startswith(f"{prefix}_{kind}_"):
            terms.extend(_clean_terms(value))
    return terms
