from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _is_real_secret(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    if not lowered:
        return False
    if "replace-me" in lowered:
        return False
    return True


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
    exclude_title_terms: list[str] = field(default_factory=list)
    new_listing_price_below: Decimal | None = None
    parser: ParserConfig | None = None


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
class AppConfig:
    config_path: Path
    database_path: Path
    log_level: str
    user_agent: str
    enable_restock_alerts: bool
    new_listing_reference_min_age_seconds: int
    rtx_5070_ti_exclude_complete_pc_terms: list[str]
    rtx_5070_ti_exclude_notebook_terms: list[str]
    rtx_5070_ti_exclude_bundle_terms: list[str]
    rtx_5070_ti_exclude_defect_terms: list[str]
    sources: list[SourceConfig]
    telegram: TelegramConfig | None = None
    discord: DiscordConfig | None = None
    windows: WindowsConfig = field(default_factory=WindowsConfig)
    sound: SoundConfig = field(default_factory=SoundConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda match: os.environ.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _load_parser(raw: dict[str, Any] | None) -> ParserConfig | None:
    if not raw:
        return None
    return ParserConfig(
        mode=raw["mode"],
        item_selector=raw.get("item_selector"),
        title_selector=raw.get("title_selector"),
        price_selector=raw.get("price_selector"),
        link_selector=raw.get("link_selector"),
        stock_selector=raw.get("stock_selector"),
        remove_selectors=list(raw.get("remove_selectors", [])),
        price_regex=raw.get("price_regex"),
        stock_in_texts=list(raw.get("stock_in_texts", [])),
        stock_out_texts=list(raw.get("stock_out_texts", [])),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw = _expand_env(raw)

    database_path = Path(raw.get("database_path", "data/alerts.sqlite"))
    if not database_path.is_absolute():
        database_path = (config_path.parent / database_path).resolve()
    sources = [
        SourceConfig(
            name=source["name"],
            type=source["type"],
            enabled=bool(source.get("enabled", True)),
            url=source.get("url"),
            command=list(source.get("command", [])),
            encoding=source.get("encoding"),
            interval_seconds=int(source.get("interval_seconds", 60)),
            timeout_seconds=int(source.get("timeout_seconds", 20)),
            shop=source["shop"],
            source=source.get("source", "shop"),
            scope=source.get("scope", "shop_search"),
            product_hint=source.get("product_hint"),
            headers=dict(source.get("headers", {})),
            exclude_title_terms=list(source.get("exclude_title_terms", [])),
            new_listing_price_below=(
                Decimal(str(source["new_listing_price_below"]))
                if source.get("new_listing_price_below") is not None
                else None
            ),
            parser=_load_parser(source.get("parser")),
        )
        for source in raw.get("sources", [])
    ]

    telegram = None
    if _is_real_secret(raw.get("telegram", {}).get("bot_token")) and _is_real_secret(str(raw.get("telegram", {}).get("chat_id", ""))):
        telegram = TelegramConfig(
            bot_token=raw["telegram"]["bot_token"],
            chat_id=str(raw["telegram"]["chat_id"]),
        )

    discord = None
    if _is_real_secret(raw.get("discord", {}).get("webhook_url")):
        discord = DiscordConfig(webhook_url=raw["discord"]["webhook_url"])

    webhook_raw = raw.get("webhook", {})
    windows_raw = raw.get("windows", {})
    sound_raw = raw.get("sound", {})

    return AppConfig(
        config_path=config_path,
        database_path=database_path,
        log_level=raw.get("log_level", "INFO"),
        user_agent=raw.get("user_agent", "Alertivo/0.1"),
        enable_restock_alerts=bool(raw.get("enable_restock_alerts", False)),
        new_listing_reference_min_age_seconds=int(raw.get("new_listing_reference_min_age_seconds", 60)),
        rtx_5070_ti_exclude_complete_pc_terms=list(
            raw.get("rtx_5070_ti_exclude_complete_pc_terms", raw.get("rtx_5070_ti_exclude_title_terms", []))
        ),
        rtx_5070_ti_exclude_notebook_terms=list(raw.get("rtx_5070_ti_exclude_notebook_terms", [])),
        rtx_5070_ti_exclude_bundle_terms=list(raw.get("rtx_5070_ti_exclude_bundle_terms", [])),
        rtx_5070_ti_exclude_defect_terms=list(raw.get("rtx_5070_ti_exclude_defect_terms", [])),
        sources=sources,
        telegram=telegram,
        discord=discord,
        windows=WindowsConfig(
            enabled=bool(windows_raw.get("enabled", True)),
            app_id=windows_raw.get("app_id", "Alertivo"),
        ),
        sound=SoundConfig(
            enabled=bool(sound_raw.get("enabled", True)),
            sound_file=sound_raw.get("sound_file"),
        ),
        webhook=WebhookConfig(
            enabled=bool(webhook_raw.get("enabled", False)),
            host=webhook_raw.get("host", "127.0.0.1"),
            port=int(webhook_raw.get("port", 8787)),
            path=webhook_raw.get("path", "/webhook/distill"),
            token=webhook_raw.get("token") if _is_real_secret(webhook_raw.get("token")) else None,
        ),
    )
