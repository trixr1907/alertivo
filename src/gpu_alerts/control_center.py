from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from gpu_alerts.autostart import is_autostart_enabled, set_autostart
from gpu_alerts.config import (
    AppConfig,
    DiscordConfig,
    SourceConfig,
    SoundConfig,
    TelegramConfig,
    TrackerConfig,
    TrackerFilterConfig,
    TrackerMeta,
    TrackerShopConfig,
    WindowsConfig,
    build_distill_targets,
    build_distill_targets_for_tracker,
    build_sources_from_trackers,
    create_tracker_config,
    delete_tracker_config,
    list_available_shops,
    load_config,
    save_settings_config,
    save_tracker_config,
    slugify_identifier,
    upsert_system_monitoring,
)
from gpu_alerts.engine import AlertEngine
from gpu_alerts.migration import rollback_monitor_config
from gpu_alerts.models import AlertEvent
from gpu_alerts.notifiers import NotifierManager, format_event_message, send_test_notifications
from gpu_alerts.profile import UserProfile, load_user_profile, save_user_profile
from gpu_alerts.storage import Storage


LOGGER = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "null"):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_terms(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("\r", "\n")
    parts = text.replace(",", "\n").split("\n")
    return [part.strip() for part in parts if part.strip()]


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _branding_assets_dir() -> Path:
    return _runtime_base_dir() / "assets" / "branding"


def _control_center_template_path() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / "gpu_alerts" / "control_center_template.html"
            if bundled.exists():
                return bundled
    return Path(__file__).resolve().with_name("control_center_template.html")


def _load_control_center_html() -> str:
    template_path = _control_center_template_path()
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    LOGGER.warning("Control center template not found: %s", template_path)
    return "<!doctype html><html><body><h1>Alertivo</h1></body></html>"


@dataclass(slots=True)
class SourceRuntimeState:
    total_polls: int = 0
    total_success: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    last_poll_started_at: str | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error: str | None = None
    last_observation_count: int = 0


class MonitorRuntime:
    def __init__(self, config: AppConfig):
        self.started_at = _utc_now_iso()
        self._sources = {source.name: SourceRuntimeState() for source in config.sources}

    def sync_sources(self, sources: list[SourceConfig]) -> None:
        for source in sources:
            self._sources.setdefault(source.name, SourceRuntimeState())

    def mark_poll_started(self, source_name: str) -> None:
        state = self._sources.setdefault(source_name, SourceRuntimeState())
        state.total_polls += 1
        state.last_poll_started_at = _utc_now_iso()

    def mark_poll_success(self, source_name: str, observation_count: int) -> None:
        state = self._sources.setdefault(source_name, SourceRuntimeState())
        state.total_success += 1
        state.consecutive_failures = 0
        state.last_success_at = _utc_now_iso()
        state.last_observation_count = observation_count
        state.last_error = None

    def mark_poll_error(self, source_name: str, error: Exception) -> None:
        state = self._sources.setdefault(source_name, SourceRuntimeState())
        state.total_failures += 1
        state.consecutive_failures += 1
        state.last_error_at = _utc_now_iso()
        state.last_error = str(error)

    def snapshot(self, sources: list[SourceConfig]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for source in sources:
            state = self._sources.setdefault(source.name, SourceRuntimeState())
            items.append(
                {
                    "name": source.name,
                    "type": source.type,
                    "enabled": source.enabled,
                    "url": source.url,
                    "interval_seconds": source.interval_seconds,
                    "timeout_seconds": source.timeout_seconds,
                    "shop": source.shop,
                    "shop_id": source.shop_id,
                    "source": source.source,
                    "scope": source.scope,
                    "product_hint": source.product_hint,
                    "tracker_id": source.tracker_id,
                    "tracker_name": source.tracker_name,
                    "include_title_terms": list(source.include_title_terms),
                    "exclude_title_terms": list(source.exclude_title_terms),
                    "price_ceiling": str(source.price_ceiling) if source.price_ceiling is not None else None,
                    "new_listing_price_below": (
                        str(source.new_listing_price_below) if source.new_listing_price_below is not None else None
                    ),
                    "total_polls": state.total_polls,
                    "total_success": state.total_success,
                    "total_failures": state.total_failures,
                    "consecutive_failures": state.consecutive_failures,
                    "last_poll_started_at": state.last_poll_started_at,
                    "last_success_at": state.last_success_at,
                    "last_error_at": state.last_error_at,
                    "last_error": state.last_error,
                    "last_observation_count": state.last_observation_count,
                }
            )
        return items


class ControlCenter:
    def __init__(
        self,
        app: web.Application,
        *,
        config: AppConfig,
        engine: AlertEngine,
        notifiers: NotifierManager,
        storage: Storage,
        runtime: MonitorRuntime,
        runtime_controller: Any | None = None,
        profile_path: Path | None = None,
        migration_state_path: Path | None = None,
        autostart_launcher: Path | None = None,
    ):
        self._app = app
        self._config = config
        self._engine = engine
        self._notifiers = notifiers
        self._storage = storage
        self._runtime = runtime
        self._runtime_controller = runtime_controller
        self._profile_path = profile_path or config.settings_path
        self._migration_state_path = migration_state_path or config.migration_state_path
        self._autostart_launcher = autostart_launcher
        self._restart_task: asyncio.Task[Any] | None = None
        app.router.add_get("/", self._handle_root)
        app.router.add_get("/control-center", self._handle_root)
        app.router.add_get("/status-dashboard", self._handle_status_dashboard)
        app.router.add_get("/api/control-center/state", self._handle_state)
        app.router.add_get("/api/control-center/runtime", self._handle_runtime_state)
        app.router.add_post("/api/control-center/test-alert", self._handle_test_alert)
        app.router.add_post("/api/control-center/notifications/test", self._handle_notification_test)
        app.router.add_post("/api/control-center/distill-preview", self._handle_distill_preview)
        app.router.add_post("/api/control-center/settings", self._handle_settings)
        app.router.add_post("/api/control-center/source/{name}", self._handle_source_update)
        app.router.add_post("/api/control-center/runtime/command", self._handle_runtime_command)
        app.router.add_post("/api/control-center/onboarding", self._handle_onboarding)
        app.router.add_post("/api/control-center/trackers", self._handle_tracker_create)
        app.router.add_post("/api/control-center/tracker/{tracker_id}", self._handle_tracker_update)
        app.router.add_post("/api/control-center/migration/rollback", self._handle_migration_rollback)
        assets_dir = _branding_assets_dir()
        if assets_dir.exists():
            app.router.add_static("/assets/branding", str(assets_dir))
        else:
            LOGGER.warning("Branding assets directory not found: %s", assets_dir)

    async def _handle_root(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        return web.Response(text=CONTROL_CENTER_HTML, content_type="text/html")

    async def _handle_status_dashboard(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        raise web.HTTPFound("/control-center")

    async def _handle_state(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        return web.json_response(self._build_state())

    async def _handle_runtime_state(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        return web.json_response({"ok": True, "runtime": self._runtime_status()})

    async def _handle_test_alert(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json() if request.can_read_body else {}
        preset = str(payload.get("preset", "price_drop"))
        event = self._build_test_event(preset)
        await self._notifiers.send(event)
        return web.json_response({"ok": True, "preset": preset, "message": format_event_message(event)})

    async def _handle_notification_test(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json() if request.can_read_body else {}
        channels_raw = payload.get("channels")
        if isinstance(channels_raw, list):
            channels = [str(item).strip().lower() for item in channels_raw if str(item).strip()]
        elif payload.get("channel"):
            channels = [str(payload.get("channel")).strip().lower()]
        else:
            channels = []

        display_name = str(payload.get("display_name") or self._config.settings.user.display_name or "Alertivo User").strip()
        telegram, discord, windows, sound = self._notification_test_configs(payload)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            results = await send_test_notifications(
                session,
                display_name=display_name or "Alertivo User",
                telegram=telegram,
                discord=discord,
                windows=windows,
                sound=sound,
                channels=channels,
            )
        return web.json_response(
            {
                "ok": all(result.get("ok") for result in results.values()) if results else False,
                "results": results,
                "message": self._notification_test_message(results),
            }
        )

    async def _handle_distill_preview(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json() if request.can_read_body else {}
        tracker_payload = self._tracker_payload_from_request(payload)
        if not tracker_payload.get("name"):
            return web.json_response({"ok": False, "error": "tracker_name_required"}, status=400)
        tracker = TrackerConfig.from_dict(tracker_payload)
        token = str(payload.get("distill_token") or self._config.settings.integrations.distill.token or "").strip() or None
        targets = build_distill_targets_for_tracker(
            tracker,
            system=self._config.system,
            host=self._config.webhook.host,
            port=self._config.webhook.port,
            path=self._config.webhook.path,
            token=token,
        )
        return web.json_response({"ok": True, "targets": targets})

    async def _handle_settings(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json()
        restart_required = self._apply_settings_payload(payload)
        return web.json_response(
            {
                "ok": True,
                "restart_required": restart_required,
                "profile": self._profile_payload(),
                "settings": self._settings_payload(),
                "app_settings": self._build_state()["app_settings"],
            }
        )

    async def _handle_source_update(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        name = request.match_info["name"]
        payload = await request.json()
        source = next((item for item in self._config.sources if item.name == name), None)
        if not source:
            return web.json_response({"ok": False, "error": "source_not_found"}, status=404)

        tracker = next((item for item in self._config.trackers if item.id == source.tracker_id), None)
        if tracker is None:
            return web.json_response({"ok": False, "error": "tracker_not_found"}, status=404)
        shop = next((item for item in tracker.shops if item.shop_id == source.shop_id), None)
        if shop is None:
            return web.json_response({"ok": False, "error": "shop_not_found"}, status=404)

        if "enabled" in payload:
            value = _to_bool(payload["enabled"])
            source.enabled = value
            shop.enabled = value
        if "interval_seconds" in payload:
            value = max(5, int(payload["interval_seconds"]))
            source.interval_seconds = value
            shop.interval_seconds = value
        if "timeout_seconds" in payload:
            value = max(5, int(payload["timeout_seconds"]))
            source.timeout_seconds = value
            shop.timeout_seconds = value

        save_tracker_config(tracker)
        self._runtime.sync_sources(self._config.sources)
        return web.json_response(
            {
                "ok": True,
                "source": next(item for item in self._runtime.snapshot(self._config.sources) if item["name"] == name),
            }
        )

    async def _handle_runtime_command(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        if not self._runtime_controller:
            return web.json_response({"ok": False, "error": "runtime_controller_unavailable"}, status=409)
        payload = await request.json()
        command = str(payload.get("command", "")).strip().lower()
        if command in {"pause", "stop"}:
            if command == "stop" and hasattr(self._runtime_controller, "stop_monitoring"):
                self._runtime_controller.stop_monitoring()
            else:
                self._runtime_controller.pause()
        elif command in {"resume", "start"}:
            if command == "start" and hasattr(self._runtime_controller, "start_monitoring"):
                self._runtime_controller.start_monitoring()
            else:
                self._runtime_controller.resume()
        elif command == "restart":
            if not hasattr(self._runtime_controller, "restart"):
                return web.json_response({"ok": False, "error": "restart_unavailable"}, status=409)
            self._schedule_restart()
            return web.json_response(
                {
                    "ok": True,
                    "runtime": self._runtime_status(),
                    "restart_required": True,
                }
            )
        else:
            return web.json_response({"ok": False, "error": "invalid_command"}, status=400)
        return web.json_response({"ok": True, "runtime": self._runtime_status()})

    async def _handle_onboarding(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json()
        payload["onboarding_completed"] = True
        restart_required = self._apply_settings_payload(payload)

        first_tracker_raw = payload.get("first_tracker")
        if isinstance(first_tracker_raw, dict):
            first_tracker = self._tracker_payload_from_request({"tracker": first_tracker_raw})
        else:
            first_tracker = self._tracker_payload_from_request(payload)
        created_tracker = None
        if first_tracker and first_tracker.get("name"):
            tracker = create_tracker_config(trackers_dir=self._config.trackers_dir, payload=first_tracker)
            created_tracker = tracker.id
            self._reload_config()
            restart_required = True
            self._schedule_restart()

        return web.json_response(
            {
                "ok": True,
                "restart_required": restart_required,
                "created_tracker": created_tracker,
                "profile": self._profile_payload(),
                "state": self._build_state(),
            }
        )

    async def _handle_tracker_create(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json()
        tracker_payload = self._tracker_payload_from_request(payload)
        if not tracker_payload.get("name"):
            return web.json_response({"ok": False, "error": "tracker_name_required"}, status=400)
        tracker_id = tracker_payload.get("id") or slugify_identifier(tracker_payload["name"])
        if any(item.id == tracker_id for item in self._config.trackers):
            return web.json_response({"ok": False, "error": "tracker_exists"}, status=409)
        tracker_payload["id"] = tracker_id
        create_tracker_config(trackers_dir=self._config.trackers_dir, payload=tracker_payload)
        self._reload_config()
        self._schedule_restart()
        return web.json_response({"ok": True, "tracker": self._serialize_tracker(next(item for item in self._config.trackers if item.id == tracker_id)), "restart_required": True})

    async def _handle_tracker_update(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        tracker_id = request.match_info["tracker_id"]
        payload = await request.json()
        tracker = next((item for item in self._config.trackers if item.id == tracker_id), None)
        if tracker is None:
            return web.json_response({"ok": False, "error": "tracker_not_found"}, status=404)

        if _to_bool(payload.get("delete", False)):
            delete_tracker_config(tracker)
            self._reload_config()
            self._schedule_restart()
            return web.json_response({"ok": True, "deleted": tracker_id, "restart_required": True})

        tracker.name = str(payload.get("name") or tracker.name).strip()
        tracker.query = str(payload.get("query") or tracker.query).strip()
        tracker.enabled = _to_bool(payload.get("enabled", tracker.enabled))
        tracker.filters = TrackerFilterConfig(
            include_terms=_parse_terms(payload.get("include_terms", tracker.filters.include_terms)),
            exclude_terms=_parse_terms(payload.get("exclude_terms", tracker.filters.exclude_terms)),
            price_ceiling=_parse_decimal(payload.get("price_ceiling", tracker.filters.price_ceiling)),
            new_listing_price_below=_parse_decimal(
                payload.get("new_listing_price_below", tracker.filters.new_listing_price_below)
            ),
        )
        if "shops" in payload:
            tracker.shops = [
                TrackerShopConfig.from_dict(item)
                for item in payload.get("shops", [])
                if str(item.get("shop_id") or "").strip()
            ]
        tracker.meta = TrackerMeta.from_dict(tracker.meta.to_dict())
        save_tracker_config(tracker)
        self._reload_config()
        self._schedule_restart()
        return web.json_response({"ok": True, "tracker": self._serialize_tracker(next(item for item in self._config.trackers if item.id == tracker_id)), "restart_required": True})

    async def _handle_migration_rollback(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        if not self._migration_state_path:
            return web.json_response({"ok": False, "error": "migration_unavailable"}, status=409)
        ok = rollback_monitor_config(self._migration_state_path)
        return web.json_response({"ok": ok, "migration": self._migration_payload()})

    def _build_state(self) -> dict[str, Any]:
        self._runtime.sync_sources(self._config.sources)
        return {
            "runtime": {
                "started_at": self._runtime.started_at,
                "uptime_seconds": self._uptime_seconds(),
                "config_path": str(self._config.config_path),
                "settings_path": str(self._config.settings_path),
                "trackers_dir": str(self._config.trackers_dir),
                "database_path": str(self._config.database_path),
                "webhook_url": f"http://{self._config.webhook.host}:{self._config.webhook.port}{self._config.webhook.path}",
                "control_center_url": f"http://{self._config.webhook.host}:{self._config.webhook.port}/control-center",
            },
            "channels": {
                "telegram": self._config.telegram is not None,
                "discord": self._config.discord is not None,
                "windows": self._config.windows.enabled,
                "sound": self._config.sound.enabled,
                "webhook_enabled": self._config.webhook.enabled,
            },
            "desktop": self._runtime_status(),
            "profile": self._profile_payload(),
            "settings": self._settings_payload(),
            "migration": self._migration_payload(),
            "app_settings": {
                "enable_restock_alerts": self._engine.enable_restock_alerts,
                "new_listing_reference_min_age_seconds": self._engine.new_listing_reference_min_age_seconds,
            },
            "trackers": [self._serialize_tracker(tracker) for tracker in self._config.trackers],
            "summary": self._storage.get_summary(),
            "sources": self._runtime.snapshot(self._config.sources),
            "setup_options": {
                "shops": list_available_shops(),
            },
            "distill_targets": build_distill_targets(self._config),
            "events": self._storage.list_recent_events(40),
            "offers": self._storage.list_recent_offers(60),
        }

    def _build_test_event(self, preset: str) -> AlertEvent:
        tracker = self._config.trackers[0] if self._config.trackers else None
        product_family = tracker.id if tracker else "sample-tracker"
        title = f"{tracker.name} Beispieltreffer" if tracker else "Alertivo Beispieltreffer"
        url = tracker.shops[0].url if tracker and tracker.shops else "https://example.com/offer"
        if preset == "new_listing_under_threshold":
            return AlertEvent(
                event_type="new_listing_under_threshold",
                shop="sample-shop",
                source="shop",
                product_family=product_family,
                canonical_model=f"{product_family}-sample",
                title=title,
                url=url,
                old_price=None,
                new_price=Decimal("199"),
                currency="EUR",
                in_stock=True,
                dedupe_key=f"manual-test-{preset}",
                threshold_price=Decimal("220"),
            )
        return AlertEvent(
            event_type="price_drop",
            shop="sample-shop",
            source="shop",
            product_family=product_family,
            canonical_model=f"{product_family}-sample",
            title=title,
            url=url,
            old_price=Decimal("249"),
            new_price=Decimal("219"),
            currency="EUR",
            in_stock=True,
            dedupe_key=f"manual-test-{preset}",
        )

    @staticmethod
    def _ensure_local(request: web.Request) -> None:
        remote = request.remote or ""
        if remote in {"127.0.0.1", "::1"} or remote.startswith("::ffff:127.0.0.1"):
            return
        raise web.HTTPForbidden(text="local_only")

    def _uptime_seconds(self) -> int:
        started = datetime.fromisoformat(self._runtime.started_at)
        return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))

    def _runtime_status(self) -> dict[str, Any]:
        if self._runtime_controller and hasattr(self._runtime_controller, "status"):
            try:
                status = self._runtime_controller.status()
                if isinstance(status, dict):
                    return status
            except Exception:
                LOGGER.exception("Could not read runtime controller status")
        return {
            "state": "running",
            "paused": False,
            "monitoring_active": True,
            "started_at": None,
            "control_center_url": f"http://{self._config.webhook.host}:{self._config.webhook.port}/control-center",
            "webhook_url": f"http://{self._config.webhook.host}:{self._config.webhook.port}{self._config.webhook.path}",
            "last_error": None,
            "thread_alive": True,
        }

    def _load_profile(self) -> UserProfile:
        profile = load_user_profile(self._profile_path)
        profile.autostart_enabled = is_autostart_enabled("Alertivo") if sys.platform.startswith("win") else False
        return profile

    def _save_profile(self, profile: UserProfile) -> None:
        save_user_profile(self._profile_path, profile)

    def _profile_payload(self) -> dict[str, Any]:
        profile = self._load_profile()
        return profile.to_dict()

    def _settings_payload(self) -> dict[str, Any]:
        payload = self._config.settings.to_dict()
        payload["notifications"]["telegram"]["bot_token"] = self._config.settings.notifications.telegram.bot_token
        payload["notifications"]["telegram"]["chat_id"] = self._config.settings.notifications.telegram.chat_id
        payload["notifications"]["discord"]["webhook_url"] = self._config.settings.notifications.discord.webhook_url
        payload["integrations"]["distill"]["token"] = self._config.settings.integrations.distill.token
        return payload

    def _migration_payload(self) -> dict[str, Any] | None:
        if not self._migration_state_path or not self._migration_state_path.exists():
            return None
        try:
            payload = json.loads(self._migration_state_path.read_text(encoding="utf-8-sig"))
        except Exception:
            LOGGER.exception("Could not read migration state")
            return None
        return payload

    def _serialize_tracker(self, tracker: TrackerConfig) -> dict[str, Any]:
        return tracker.to_dict()

    def _notification_test_configs(
        self,
        payload: dict[str, Any],
    ) -> tuple[TelegramConfig | None, DiscordConfig | None, WindowsConfig | None, SoundConfig | None]:
        settings = self._config.settings

        telegram_token = str(payload.get("telegram_bot_token", settings.notifications.telegram.bot_token) or "").strip()
        telegram_chat_id = str(payload.get("telegram_chat_id", settings.notifications.telegram.chat_id) or "").strip()
        telegram_enabled = _to_bool(
            payload.get(
                "telegram_enabled",
                settings.notifications.telegram.enabled or bool(telegram_token and telegram_chat_id),
            )
        )
        telegram = (
            TelegramConfig(bot_token=telegram_token, chat_id=telegram_chat_id)
            if telegram_enabled and telegram_token and telegram_chat_id
            else None
        )

        discord_webhook_url = str(
            payload.get("discord_webhook_url", settings.notifications.discord.webhook_url) or ""
        ).strip()
        discord_enabled = _to_bool(
            payload.get("discord_enabled", settings.notifications.discord.enabled or bool(discord_webhook_url))
        )
        discord = (
            DiscordConfig(webhook_url=discord_webhook_url)
            if discord_enabled and discord_webhook_url
            else None
        )

        windows_enabled = _to_bool(
            payload.get("windows_notifications_enabled", settings.notifications.windows.enabled)
        )
        windows_app_id = str(payload.get("windows_app_id", settings.notifications.windows.app_id) or "Alertivo").strip() or "Alertivo"
        windows = WindowsConfig(enabled=windows_enabled, app_id=windows_app_id)

        sound_enabled = _to_bool(payload.get("sound_enabled", settings.notifications.sound.enabled))
        sound_file_raw = payload.get("sound_file", settings.notifications.sound.sound_file)
        sound_file = str(sound_file_raw).strip() if sound_file_raw is not None else None
        sound = SoundConfig(enabled=sound_enabled, sound_file=sound_file or None)
        return telegram, discord, windows, sound

    @staticmethod
    def _notification_test_message(results: dict[str, dict[str, Any]]) -> str:
        if not results:
            return "Keine Benachrichtigungskanaele ausgewaehlt."
        successful = [channel for channel, result in results.items() if result.get("ok")]
        failed = [f"{channel}: {result.get('error', 'unknown_error')}" for channel, result in results.items() if not result.get("ok")]
        if successful and not failed:
            return f"Testnachricht gesendet: {', '.join(successful)}."
        if successful:
            return f"Teilweise erfolgreich: {', '.join(successful)} | Fehler: {'; '.join(failed)}"
        return f"Test fehlgeschlagen: {'; '.join(failed)}"

    def _apply_settings_payload(self, payload: dict[str, Any]) -> bool:
        profile = self._load_profile()
        if "display_name" in payload:
            display_name = str(payload.get("display_name") or "").strip()
            if display_name:
                profile.display_name = display_name
        if "simple_mode" in payload:
            profile.simple_mode = _to_bool(payload.get("simple_mode"))
        if "close_to_tray" in payload:
            profile.close_to_tray = _to_bool(payload.get("close_to_tray"))
        if "intro_enabled" in payload:
            profile.intro_enabled = _to_bool(payload.get("intro_enabled"))
        if "onboarding_completed" in payload:
            profile.onboarding_completed = _to_bool(payload.get("onboarding_completed"))

        requested_autostart = _to_bool(payload.get("autostart_enabled", profile.autostart_enabled))
        if self._autostart_launcher:
            profile.autostart_enabled = set_autostart(
                requested_autostart,
                launcher_path=self._autostart_launcher,
                app_name="Alertivo",
            )
        else:
            profile.autostart_enabled = requested_autostart
        self._save_profile(profile)

        settings = self._config.settings
        restart_required = False

        if "telegram_enabled" in payload:
            settings.notifications.telegram.enabled = _to_bool(payload.get("telegram_enabled"))
            restart_required = True
        if "telegram_bot_token" in payload:
            settings.notifications.telegram.bot_token = str(payload.get("telegram_bot_token") or "").strip()
            restart_required = True
        if "telegram_chat_id" in payload:
            settings.notifications.telegram.chat_id = str(payload.get("telegram_chat_id") or "").strip()
            restart_required = True
        if "discord_enabled" in payload:
            settings.notifications.discord.enabled = _to_bool(payload.get("discord_enabled"))
            restart_required = True
        if "discord_webhook_url" in payload:
            settings.notifications.discord.webhook_url = str(payload.get("discord_webhook_url") or "").strip()
            restart_required = True
        if "windows_notifications_enabled" in payload:
            settings.notifications.windows.enabled = _to_bool(payload.get("windows_notifications_enabled"))
            restart_required = True
        if "windows_app_id" in payload:
            settings.notifications.windows.app_id = str(payload.get("windows_app_id") or "Alertivo").strip() or "Alertivo"
            restart_required = True
        if "sound_enabled" in payload:
            settings.notifications.sound.enabled = _to_bool(payload.get("sound_enabled"))
            restart_required = True
        if "sound_file" in payload:
            value = str(payload.get("sound_file") or "").strip()
            settings.notifications.sound.sound_file = value or None
            restart_required = True
        if "distill_enabled" in payload:
            settings.integrations.distill.enabled = _to_bool(payload.get("distill_enabled"))
            restart_required = True
        if "distill_token" in payload:
            settings.integrations.distill.token = str(payload.get("distill_token") or "").strip()
            restart_required = True

        settings.user.display_name = profile.display_name
        settings.user.onboarding_completed = profile.onboarding_completed
        settings.ui.simple_mode = profile.simple_mode
        settings.ui.close_to_tray = profile.close_to_tray
        settings.ui.intro_enabled = profile.intro_enabled
        settings.desktop.autostart_enabled = profile.autostart_enabled
        save_settings_config(settings)

        if "enable_restock_alerts" in payload or "new_listing_reference_min_age_seconds" in payload:
            upsert_system_monitoring(
                self._config.system,
                enable_restock_alerts=(
                    _to_bool(payload.get("enable_restock_alerts")) if "enable_restock_alerts" in payload else None
                ),
                new_listing_reference_min_age_seconds=(
                    max(0, int(payload.get("new_listing_reference_min_age_seconds")))
                    if "new_listing_reference_min_age_seconds" in payload
                    else None
                ),
            )
            self._engine.enable_restock_alerts = self._config.system.monitoring.enable_restock_alerts
            self._engine.new_listing_reference_min_age_seconds = (
                self._config.system.monitoring.new_listing_reference_min_age_seconds
            )

        self._reload_config()
        if restart_required:
            self._schedule_restart()
        return restart_required

    def _tracker_payload_from_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        tracker_payload = payload.get("tracker") if isinstance(payload.get("tracker"), dict) else payload
        name = str(tracker_payload.get("name") or tracker_payload.get("tracker_name") or "").strip()
        query = str(tracker_payload.get("query") or tracker_payload.get("tracker_query") or name).strip()
        tracker_id = str(tracker_payload.get("id") or slugify_identifier(name or query or "tracker")).strip()
        shops_raw = tracker_payload.get("shops")
        if not isinstance(shops_raw, list):
            shops_raw = [
                {
                    "shop_id": shop_id,
                    "enabled": True,
                    "mode": "auto",
                }
                for shop_id in tracker_payload.get("shop_ids", [])
            ]
        return {
            "schema_version": 1,
            "id": tracker_id,
            "name": name,
            "enabled": _to_bool(tracker_payload.get("enabled", True)),
            "query": query,
            "filters": {
                "include_terms": _parse_terms(tracker_payload.get("include_terms", [])),
                "exclude_terms": _parse_terms(tracker_payload.get("exclude_terms", [])),
                "price_ceiling": (
                    float(_parse_decimal(tracker_payload.get("price_ceiling")))
                    if _parse_decimal(tracker_payload.get("price_ceiling")) is not None
                    else None
                ),
                "new_listing_price_below": (
                    float(_parse_decimal(tracker_payload.get("new_listing_price_below")))
                    if _parse_decimal(tracker_payload.get("new_listing_price_below")) is not None
                    else None
                ),
            },
            "shops": shops_raw,
            "meta": {
                "created_at": tracker_payload.get("created_at") or "",
                "updated_at": tracker_payload.get("updated_at") or "",
            },
        }

    def _reload_config(self) -> None:
        self._config = load_config(self._config.config_path)
        self._runtime.sync_sources(self._config.sources)

    def _schedule_restart(self) -> None:
        if not self._runtime_controller or not hasattr(self._runtime_controller, "restart"):
            return
        if self._restart_task and not self._restart_task.done():
            return
        self._restart_task = asyncio.create_task(self._restart_after_response())

    async def _restart_after_response(self) -> None:
        await asyncio.sleep(0.25)
        try:
            await asyncio.to_thread(self._runtime_controller.restart)
        except Exception:
            LOGGER.exception("Could not restart runtime after configuration change")


CONTROL_CENTER_HTML = _load_control_center_html()
