from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from aiohttp import web

from gpu_alerts.autostart import is_autostart_enabled, set_autostart
from gpu_alerts.config import AppConfig, SourceConfig
from gpu_alerts.engine import AlertEngine
from gpu_alerts.migration import rollback_monitor_config
from gpu_alerts.models import AlertEvent
from gpu_alerts.notifiers import NotifierManager, format_event_message
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


def _yaml_decimal(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral():
        return int(value)
    return float(value)


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
                    "source": source.source,
                    "scope": source.scope,
                    "product_hint": source.product_hint,
                    "exclude_title_terms": list(source.exclude_title_terms),
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


def persist_source_settings(config_path: Path, source_name: str, updates: dict[str, Any]) -> None:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sources = raw.get("sources", [])
    for source in sources:
        if source.get("name") != source_name:
            continue
        if "enabled" in updates:
            source["enabled"] = bool(updates["enabled"])
        if "interval_seconds" in updates:
            source["interval_seconds"] = int(updates["interval_seconds"])
        if "timeout_seconds" in updates:
            source["timeout_seconds"] = int(updates["timeout_seconds"])
        if "exclude_title_terms" in updates:
            terms = list(updates["exclude_title_terms"])
            if terms:
                source["exclude_title_terms"] = terms
            else:
                source.pop("exclude_title_terms", None)
        if "new_listing_price_below" in updates:
            threshold = _yaml_decimal(updates["new_listing_price_below"])
            if threshold is None:
                source.pop("new_listing_price_below", None)
            else:
                source["new_listing_price_below"] = threshold
        break
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")


def persist_enabled_sources(config_path: Path, enabled_source_names: set[str]) -> None:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sources = raw.get("sources", [])
    for source in sources:
        name = str(source.get("name", ""))
        source["enabled"] = name in enabled_source_names
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")


def persist_app_settings(config_path: Path, updates: dict[str, Any]) -> None:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if "enable_restock_alerts" in updates:
        raw["enable_restock_alerts"] = bool(updates["enable_restock_alerts"])
    if "new_listing_reference_min_age_seconds" in updates:
        raw["new_listing_reference_min_age_seconds"] = int(updates["new_listing_reference_min_age_seconds"])
    for key in (
        "rtx_5070_ti_exclude_complete_pc_terms",
        "rtx_5070_ti_exclude_notebook_terms",
        "rtx_5070_ti_exclude_bundle_terms",
        "rtx_5070_ti_exclude_defect_terms",
    ):
        if key in updates:
            terms = list(updates[key])
            if terms:
                raw[key] = terms
            else:
                raw.pop(key, None)
    raw.pop("rtx_5070_ti_exclude_title_terms", None)
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")


def persist_webhook_settings(config_path: Path, *, enabled: bool) -> None:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    webhook = dict(raw.get("webhook", {}))
    webhook["enabled"] = bool(enabled)
    raw["webhook"] = webhook
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")


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
        self._profile_path = profile_path
        self._migration_state_path = migration_state_path
        self._autostart_launcher = autostart_launcher
        app.router.add_get("/", self._handle_root)
        app.router.add_get("/control-center", self._handle_root)
        app.router.add_get("/status-dashboard", self._handle_status_dashboard)
        app.router.add_get("/api/control-center/state", self._handle_state)
        app.router.add_get("/api/control-center/runtime", self._handle_runtime_state)
        app.router.add_post("/api/control-center/test-alert", self._handle_test_alert)
        app.router.add_post("/api/control-center/settings", self._handle_settings)
        app.router.add_post("/api/control-center/source/{name}", self._handle_source_update)
        app.router.add_post("/api/control-center/runtime/command", self._handle_runtime_command)
        app.router.add_post("/api/control-center/onboarding", self._handle_onboarding)
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

    async def _handle_settings(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json()
        if "enable_restock_alerts" in payload:
            self._engine.enable_restock_alerts = _to_bool(payload["enable_restock_alerts"])
            self._config.enable_restock_alerts = self._engine.enable_restock_alerts
        if "new_listing_reference_min_age_seconds" in payload:
            value = max(0, int(payload["new_listing_reference_min_age_seconds"]))
            self._engine.new_listing_reference_min_age_seconds = value
            self._config.new_listing_reference_min_age_seconds = value
        if "rtx_5070_ti_exclude_complete_pc_terms" in payload:
            terms = _parse_terms(payload["rtx_5070_ti_exclude_complete_pc_terms"])
            self._engine.rtx_5070_ti_exclude_complete_pc_terms = terms
            self._config.rtx_5070_ti_exclude_complete_pc_terms = list(terms)
        if "rtx_5070_ti_exclude_notebook_terms" in payload:
            terms = _parse_terms(payload["rtx_5070_ti_exclude_notebook_terms"])
            self._engine.rtx_5070_ti_exclude_notebook_terms = terms
            self._config.rtx_5070_ti_exclude_notebook_terms = list(terms)
        if "rtx_5070_ti_exclude_bundle_terms" in payload:
            terms = _parse_terms(payload["rtx_5070_ti_exclude_bundle_terms"])
            self._engine.rtx_5070_ti_exclude_bundle_terms = terms
            self._config.rtx_5070_ti_exclude_bundle_terms = list(terms)
        if "rtx_5070_ti_exclude_defect_terms" in payload:
            terms = _parse_terms(payload["rtx_5070_ti_exclude_defect_terms"])
            self._engine.rtx_5070_ti_exclude_defect_terms = terms
            self._config.rtx_5070_ti_exclude_defect_terms = list(terms)
        persist_app_settings(
            self._config.config_path,
            {
                "enable_restock_alerts": self._engine.enable_restock_alerts,
                "new_listing_reference_min_age_seconds": self._engine.new_listing_reference_min_age_seconds,
                "rtx_5070_ti_exclude_complete_pc_terms": self._engine.rtx_5070_ti_exclude_complete_pc_terms,
                "rtx_5070_ti_exclude_notebook_terms": self._engine.rtx_5070_ti_exclude_notebook_terms,
                "rtx_5070_ti_exclude_bundle_terms": self._engine.rtx_5070_ti_exclude_bundle_terms,
                "rtx_5070_ti_exclude_defect_terms": self._engine.rtx_5070_ti_exclude_defect_terms,
            },
        )
        return web.json_response({"ok": True, "settings": self._build_state()["app_settings"]})

    async def _handle_source_update(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        name = request.match_info["name"]
        payload = await request.json()
        source = next((item for item in self._config.sources if item.name == name), None)
        if not source:
            return web.json_response({"ok": False, "error": "source_not_found"}, status=404)

        if "enabled" in payload:
            source.enabled = _to_bool(payload["enabled"])
        if "interval_seconds" in payload:
            source.interval_seconds = max(5, int(payload["interval_seconds"]))
        if "timeout_seconds" in payload:
            source.timeout_seconds = max(5, int(payload["timeout_seconds"]))
        if "exclude_title_terms" in payload:
            source.exclude_title_terms = _parse_terms(payload["exclude_title_terms"])
        if "new_listing_price_below" in payload:
            source.new_listing_price_below = _parse_decimal(payload["new_listing_price_below"])

        persist_source_settings(
            self._config.config_path,
            name,
            {
                "enabled": source.enabled,
                "interval_seconds": source.interval_seconds,
                "timeout_seconds": source.timeout_seconds,
                "exclude_title_terms": source.exclude_title_terms,
                "new_listing_price_below": source.new_listing_price_below,
            },
        )
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
        if command == "pause":
            self._runtime_controller.pause()
        elif command == "resume":
            self._runtime_controller.resume()
        elif command == "restart":
            self._runtime_controller.restart()
        else:
            return web.json_response({"ok": False, "error": "invalid_command"}, status=400)
        return web.json_response({"ok": True, "runtime": self._runtime_status()})

    async def _handle_onboarding(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        payload = await request.json()
        profile = self._load_profile()
        display_name = str(payload.get("display_name") or "").strip()
        if display_name:
            profile.display_name = display_name
        profile.simple_mode = _to_bool(payload.get("simple_mode", True))
        requested_autostart = _to_bool(payload.get("autostart_enabled", False))
        if self._autostart_launcher:
            profile.autostart_enabled = set_autostart(
                requested_autostart,
                launcher_path=self._autostart_launcher,
                app_name="Alertivo",
            )
        else:
            profile.autostart_enabled = requested_autostart
        profile.close_to_tray = _to_bool(payload.get("close_to_tray", profile.close_to_tray))
        profile.onboarding_completed = True
        profile.intro_enabled = _to_bool(payload.get("intro_enabled", True))
        selected_source = str(payload.get("start_source") or "").strip()
        if selected_source and any(source.name == selected_source for source in self._config.sources):
            profile.preferred_source = selected_source
            enabled_names = {selected_source}
            for source in self._config.sources:
                source.enabled = source.name in enabled_names
            persist_enabled_sources(self._config.config_path, enabled_names)
        self._save_profile(profile)

        if profile.simple_mode:
            self._config.webhook.enabled = False
            persist_webhook_settings(self._config.config_path, enabled=False)
        elif "webhook_enabled" in payload:
            self._config.webhook.enabled = _to_bool(payload.get("webhook_enabled"))
            persist_webhook_settings(self._config.config_path, enabled=self._config.webhook.enabled)

        return web.json_response({"ok": True, "profile": self._profile_payload()})

    async def _handle_migration_rollback(self, request: web.Request) -> web.Response:
        self._ensure_local(request)
        if not self._migration_state_path:
            return web.json_response({"ok": False, "error": "migration_unavailable"}, status=409)
        ok = rollback_monitor_config(self._migration_state_path)
        return web.json_response({"ok": ok, "migration": self._migration_payload()})

    def _build_state(self) -> dict[str, Any]:
        return {
            "runtime": {
                "started_at": self._runtime.started_at,
                "uptime_seconds": self._uptime_seconds(),
                "config_path": str(self._config.config_path),
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
            "migration": self._migration_payload(),
            "app_settings": {
                "enable_restock_alerts": self._engine.enable_restock_alerts,
                "new_listing_reference_min_age_seconds": self._engine.new_listing_reference_min_age_seconds,
                "rtx_5070_ti_exclude_complete_pc_terms": self._engine.rtx_5070_ti_exclude_complete_pc_terms,
                "rtx_5070_ti_exclude_notebook_terms": self._engine.rtx_5070_ti_exclude_notebook_terms,
                "rtx_5070_ti_exclude_bundle_terms": self._engine.rtx_5070_ti_exclude_bundle_terms,
                "rtx_5070_ti_exclude_defect_terms": self._engine.rtx_5070_ti_exclude_defect_terms,
            },
            "summary": self._storage.get_summary(),
            "sources": self._runtime.snapshot(self._config.sources),
            "setup_options": {
                "sources": [
                    {
                        "name": source.name,
                        "label": f"{source.shop} / {source.name}",
                        "enabled": source.enabled,
                    }
                    for source in self._config.sources
                ],
            },
            "distill_targets": self._distill_targets(),
            "events": self._storage.list_recent_events(40),
            "offers": self._storage.list_recent_offers(60),
        }

    def _build_test_event(self, preset: str) -> AlertEvent:
        if preset == "new_listing_under_threshold":
            return AlertEvent(
                event_type="new_listing_under_threshold",
                shop="kleinanzeigen",
                source="classifieds",
                product_family="glinet-flint-2",
                canonical_model="glinet-flint-2-gl-mt6000",
                title="GL.iNet Flint 2 Router (GL-MT6000)",
                url="https://www.kleinanzeigen.de/s-multimedia-elektronik/mt6000/k0c161",
                old_price=None,
                new_price=Decimal("140"),
                currency="EUR",
                in_stock=True,
                dedupe_key=f"manual-test-{preset}",
                threshold_price=Decimal("150"),
            )
        if preset == "new_listing_below_last_seen":
            return AlertEvent(
                event_type="new_listing_below_last_seen",
                shop="billiger",
                source="billiger",
                product_family="rtx-5070-ti",
                canonical_model="rtx-5070-ti-gigabyte-eagle-oc-sff",
                title="Gigabyte GeForce RTX 5070 Ti Eagle OC SFF",
                url="https://www.billiger.de/search?searchstring=rtx+5070+ti",
                old_price=Decimal("929"),
                new_price=Decimal("899.90"),
                currency="EUR",
                in_stock=True,
                dedupe_key=f"manual-test-{preset}",
            )
        return AlertEvent(
            event_type="price_drop",
            shop="mindfactory",
            source="shop",
            product_family="rtx-5070-ti",
            canonical_model="rtx-5070-ti-msi-gaming-trio-oc",
            title="MSI GeForce RTX 5070 Ti Gaming Trio OC 16GB",
            url="https://www.mindfactory.de/search_result.php?search_query=rtx+5070+ti",
            old_price=Decimal("1039"),
            new_price=Decimal("999"),
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
            "started_at": None,
            "control_center_url": f"http://{self._config.webhook.host}:{self._config.webhook.port}/control-center",
            "webhook_url": f"http://{self._config.webhook.host}:{self._config.webhook.port}{self._config.webhook.path}",
            "last_error": None,
            "thread_alive": True,
        }

    def _load_profile(self) -> UserProfile:
        if not self._profile_path:
            return UserProfile(onboarding_completed=True)
        profile = load_user_profile(self._profile_path)
        profile.autostart_enabled = is_autostart_enabled("Alertivo") if sys.platform.startswith("win") else False
        return profile

    def _save_profile(self, profile: UserProfile) -> None:
        if not self._profile_path:
            return
        save_user_profile(self._profile_path, profile)

    def _profile_payload(self) -> dict[str, Any]:
        profile = self._load_profile()
        return profile.to_dict()

    def _migration_payload(self) -> dict[str, Any] | None:
        if not self._migration_state_path or not self._migration_state_path.exists():
            return None
        try:
            payload = json.loads(self._migration_state_path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("Could not read migration state")
            return None
        return payload

    @staticmethod
    def _distill_targets() -> list[dict[str, str]]:
        return [
            {
                "name": "eBay RTX 5070 Ti Sofort-Kaufen",
                "url": "https://www.ebay.de/sch/i.html?_nkw=rtx+5070+ti+-defekt+-bastler+-reparatur+-besch%C3%A4digt&_sacat=27386&LH_BIN=1&LH_ItemCondition=1000&rt=nc&LH_PrefLoc=3",
                "note": "Buy-it-now only. Defekt-/Bastler-Begriffe im Payload ausschliessen.",
            },
            {
                "name": "Amazon RTX 5070 Ti",
                "url": "https://www.amazon.de/s?k=rtx+5070+ti",
                "note": "Lokal in Distill mit 15-20s. Browser-Session offen halten.",
            },
            {
                "name": "Amazon Flint 2",
                "url": "https://www.amazon.de/s?k=gl-mt6000",
                "note": "Preis und Lagerstatus getrennt beobachten.",
            },
            {
                "name": "Caseking RTX 5070 Ti",
                "url": "https://www.caseking.de/search?search=rtx+5070+ti",
                "note": "Cloudflare-lastig. Distill im eingeloggten Browser.",
            },
            {
                "name": "MediaMarkt RTX 5070 Ti",
                "url": "https://www.mediamarkt.de/de/search.html?query=rtx%205070%20ti",
                "note": "Schneller Suchseiten-Monitor.",
            },
            {
                "name": "Saturn RTX 5070 Ti",
                "url": "https://www.saturn.de/de/search.html?query=rtx%205070%20ti",
                "note": "Schneller Suchseiten-Monitor.",
            },
        ]


CONTROL_CENTER_HTML = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Alertivo Control Center</title>
  <style>
    :root {
      --bg: #04070d;
      --panel: rgba(11, 18, 30, 0.92);
      --panel-2: rgba(15, 24, 40, 0.94);
      --line: #213754;
      --text: #f2f6ff;
      --muted: #9cb5d6;
      --ok: #2ed889;
      --warn: #ffbe4d;
      --bad: #ff6b6b;
      --info: #67bdff;
      --accent: #45d0ff;
      --chip: rgba(255, 255, 255, 0.06);
      --shadow: 0 20px 48px rgba(0, 0, 0, 0.34);
      --radius: 18px;
      --radius-sm: 12px;
      --font: "Rajdhani", "Bahnschrift", "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      font-family: var(--font);
      color: var(--text);
      background:
        radial-gradient(circle at 9% 14%, rgba(69,208,255,0.19), transparent 32%),
        radial-gradient(circle at 88% 9%, rgba(103,189,255,0.14), transparent 22%),
        linear-gradient(180deg, #04070d 0%, #08101d 45%, #060a13 100%);
    }
    .shell {
      max-width: 1560px;
      margin: 0 auto;
      padding: 24px 18px 36px;
    }
    .hero, .panel {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, var(--panel-2), var(--panel));
      box-shadow: var(--shadow);
      border-radius: var(--radius);
    }
    .hero {
      padding: 28px;
      margin-bottom: 18px;
      overflow: hidden;
      position: relative;
    }
    .hero:before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 22% 10%, rgba(69, 208, 255, 0.24), transparent 30%),
        radial-gradient(circle at 87% 90%, rgba(103, 189, 255, 0.16), transparent 28%);
      pointer-events: none;
    }
    .hero-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 18px;
      flex-wrap: wrap;
      position: relative;
      z-index: 1;
    }
    h1, h2, h3, p { margin: 0; }
    h1 {
      font-size: clamp(30px, 4vw, 54px);
      line-height: 1.02;
      letter-spacing: -0.02em;
      text-transform: uppercase;
    }
    .sub {
      margin-top: 12px;
      max-width: 900px;
      line-height: 1.5;
      color: var(--muted);
      font-size: 17px;
    }
    .hero-brand {
      display: grid;
      grid-template-columns: 180px minmax(0, 1fr);
      gap: 16px;
      align-items: center;
      min-width: min(100%, 760px);
    }
    .hero-logo {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.05);
      box-shadow: 0 0 34px rgba(102, 192, 255, 0.28);
    }
    .brand-line {
      margin-top: 10px;
      font-size: 14px;
      letter-spacing: 0.08em;
      color: #bcd4f1;
      text-transform: uppercase;
    }
    .brand-line a {
      color: #6dd6ff;
      text-decoration: none;
    }
    .hero-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .btn, button {
      border: 1px solid var(--line);
      background: var(--chip);
      color: var(--text);
      border-radius: 999px;
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
    }
    .btn:hover, button:hover { transform: translateY(-1px); border-color: #3d567d; }
    .btn.primary, button.primary { background: linear-gradient(180deg, #1f8fff, #1568c8); border-color: #237ddd; }
    .btn.good, button.good { background: linear-gradient(180deg, #19ae6f, #118955); border-color: #149660; }
    .btn.warn, button.warn { background: linear-gradient(180deg, #cf8d1d, #9b670d); border-color: #c88416; }
    .app-footer {
      margin-top: 18px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: rgba(255,255,255,0.03);
      color: #8ea8cb;
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: center;
      padding: 13px 12px;
      font-size: 13px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .app-footer a {
      color: #6dd6ff;
      text-decoration: none;
    }
    .intro-overlay {
      position: fixed;
      inset: 0;
      z-index: 60;
      display: grid;
      place-items: center;
      padding: 20px;
      background: rgba(2, 4, 8, 0.92);
      backdrop-filter: blur(5px);
    }
    .intro-overlay[hidden] {
      display: none !important;
    }
    .intro-card {
      width: min(960px, 100%);
      border-radius: 16px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.18);
      background: #04070d;
      box-shadow: 0 28px 62px rgba(0, 0, 0, 0.55);
    }
    .intro-video-wrap {
      width: 100%;
      background: #000;
      aspect-ratio: 16 / 9;
      overflow: hidden;
    }
    .intro-video {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .intro-actions {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      flex-wrap: wrap;
      padding: 14px 14px 16px;
      border-top: 1px solid rgba(255,255,255,0.1);
      background: linear-gradient(180deg, rgba(14,22,34,0.98), rgba(11,18,30,0.98));
    }
    .setup-form {
      display: grid;
      gap: 12px;
      padding: 16px;
      border-top: 1px solid rgba(255,255,255,0.1);
      background: linear-gradient(180deg, rgba(14,22,34,0.98), rgba(11,18,30,0.98));
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 18px;
    }
    .panel { padding: 20px; }
    .span-12 { grid-column: span 12; }
    .span-8 { grid-column: span 8; }
    .span-7 { grid-column: span 7; }
    .span-6 { grid-column: span 6; }
    .span-5 { grid-column: span 5; }
    .span-4 { grid-column: span 4; }
    .section-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
    }
    .section-title h2 {
      font-size: 20px;
      letter-spacing: -0.02em;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      color: var(--muted);
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .ok { background: var(--ok); }
    .warn { background: var(--warn); }
    .bad { background: var(--bad); }
    .info { background: var(--info); }
    .stats {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .stat {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: rgba(255,255,255,0.04);
      padding: 14px;
    }
    .stat .k {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .stat .v {
      margin-top: 8px;
      font-size: 24px;
      font-weight: 700;
    }
    .muted { color: var(--muted); }
    .kv {
      display: grid;
      gap: 10px;
    }
    .kv-row {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .kv-row:last-child { border-bottom: 0; }
    .chip-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .chip {
      padding: 8px 10px;
      border-radius: 999px;
      background: var(--chip);
      border: 1px solid rgba(255,255,255,0.08);
      font-size: 13px;
    }
    .control-form, .source-grid {
      display: grid;
      gap: 14px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .field {
      display: grid;
      gap: 8px;
    }
    label {
      font-size: 13px;
      color: var(--muted);
    }
    input[type="text"], input[type="number"], textarea, select {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #0b1626;
      color: var(--text);
      padding: 12px 13px;
      font: inherit;
    }
    textarea { min-height: 94px; resize: vertical; }
    .check {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 13px;
      border-radius: 12px;
      background: #0b1626;
      border: 1px solid var(--line);
    }
    .check input { width: 18px; height: 18px; }
    .source-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .source-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
      padding: 16px;
      display: grid;
      gap: 12px;
    }
    .source-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }
    .source-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .source-meta .chip { font-size: 12px; }
    .source-url {
      word-break: break-all;
      color: #cce2ff;
      font-size: 13px;
      text-decoration: none;
    }
    .source-runtime {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 16px;
      font-size: 13px;
    }
    .runtime-box {
      padding: 10px 12px;
      border-radius: 12px;
      background: #0b1626;
      border: 1px solid rgba(255,255,255,0.06);
    }
    .runtime-box strong { display: block; margin-bottom: 4px; font-size: 12px; color: var(--muted); }
    table {
      width: 100%;
      border-collapse: collapse;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    th, td {
      padding: 11px 12px;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      vertical-align: top;
      font-size: 13px;
    }
    th {
      background: rgba(255,255,255,0.04);
      color: var(--muted);
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.08em;
    }
    tr:last-child td { border-bottom: 0; }
    .event-type {
      display: inline-block;
      padding: 5px 9px;
      border-radius: 999px;
      font-size: 11px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
    }
    .event-price {
      white-space: nowrap;
      font-feature-settings: "tnum";
    }
    .toast {
      position: fixed;
      right: 16px;
      bottom: 16px;
      min-width: 280px;
      max-width: 420px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(10, 20, 34, 0.96);
      box-shadow: var(--shadow);
      display: none;
      z-index: 30;
    }
    .toast.show { display: block; }
    .small { font-size: 12px; }
    @media (max-width: 1200px) {
      .span-8, .span-7, .span-6, .span-5, .span-4 { grid-column: span 12; }
      .source-grid, .stats, .form-grid { grid-template-columns: 1fr; }
      .hero-brand { grid-template-columns: 1fr; max-width: 100%; }
      .hero-logo { max-width: 280px; }
      .hero-actions { justify-content: flex-start; }
      .intro-actions { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-brand">
          <img class="hero-logo" src="/assets/branding/logo-main.png" alt="ivo-tech logo">
          <div>
            <h1>Alertivo Control Center</h1>
            <p class="sub">Lokales Live-Control-Center fuer benutzerdefinierte Alerts und Monitoring-Quellen. Alles bleibt lokal, minimierbar und fuer neue Nutzer im KISS-Setup nutzbar. Aenderungen werden in <code>monitor.yaml</code> gespeichert und greifen im naechsten Poll-Zyklus.</p>
            <div class="brand-line">dev by Ivo &bull; <a href="http://ivo-tech.com" target="_blank" rel="noreferrer">ivo-tech.com</a></div>
          </div>
        </div>
        <div class="hero-actions">
          <button class="btn primary" id="refreshBtn">Jetzt aktualisieren</button>
          <button class="btn" id="pauseResumeBtn">Monitoring pausieren</button>
          <button class="btn" id="restartRuntimeBtn">Monitoring neu starten</button>
          <button class="btn good" data-preset="price_drop">Test Preisdrop</button>
          <button class="btn good" data-preset="new_listing_below_last_seen">Test Neues guenstigeres Listing</button>
          <button class="btn warn" data-preset="new_listing_under_threshold">Test Schwellen-Alert</button>
        </div>
      </div>
      <div class="stats" id="stats"></div>
    </section>

    <div class="grid">
      <section class="panel span-4">
        <div class="section-title">
          <h2>Laufzeit</h2>
          <span class="badge"><span class="dot ok"></span> Lokal</span>
        </div>
        <div class="kv" id="runtimeMeta"></div>
        <div class="chip-row" id="channelChips"></div>
      </section>

      <section class="panel span-8">
        <div class="section-title">
          <h2>Globale Regeln (Advanced)</h2>
          <span class="badge"><span class="dot info"></span> Persistiert in monitor.yaml</span>
        </div>
        <form class="control-form" id="settingsForm">
          <div class="form-grid">
            <div class="field">
              <label for="refAge">Mindestalter fuer Referenzpreis in Sekunden</label>
              <input id="refAge" name="new_listing_reference_min_age_seconds" type="number" min="0" step="1">
            </div>
            <div class="field">
              <label>&nbsp;</label>
              <label class="check"><input id="restockToggle" name="enable_restock_alerts" type="checkbox"> Restock-Alerts aktiv</label>
            </div>
          </div>
          <div class="form-grid">
            <div class="field">
              <label for="rtxExcludeCompletePcTerms">RTX Blockliste: Komplett-PCs</label>
              <textarea id="rtxExcludeCompletePcTerms" name="rtx_5070_ti_exclude_complete_pc_terms" placeholder="z. B. gaming pc, komplettsystem, tower"></textarea>
            </div>
            <div class="field">
              <label for="rtxExcludeNotebookTerms">RTX Blockliste: Notebooks</label>
              <textarea id="rtxExcludeNotebookTerms" name="rtx_5070_ti_exclude_notebook_terms" placeholder="z. B. notebook, laptop"></textarea>
            </div>
            <div class="field">
              <label for="rtxExcludeBundleTerms">RTX Blockliste: Bundles / Zubehoer</label>
              <textarea id="rtxExcludeBundleTerms" name="rtx_5070_ti_exclude_bundle_terms" placeholder="z. B. bundle, set, netzteil, mainboard"></textarea>
            </div>
            <div class="field">
              <label for="rtxExcludeDefectTerms">RTX Blockliste: Defekt / Bastler</label>
              <textarea id="rtxExcludeDefectTerms" name="rtx_5070_ti_exclude_defect_terms" placeholder="z. B. defekt, bastler, reparatur"></textarea>
            </div>
          </div>
          <div class="small muted">Greift fuer alle RTX-5070-Ti-Quellen gleichzeitig. Quelle-spezifische Ausschlussbegriffe pro Source bleiben zusaetzlich moeglich.</div>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button type="submit" class="primary">Globale Einstellungen speichern</button>
          </div>
        </form>
      </section>

      <section class="panel span-12">
        <div class="section-title">
          <h2>Quellen und Feineinstellungen</h2>
          <span class="badge"><span class="dot warn"></span> Live-Edit fuer enabled, Intervalle, Schwellen, Ausschlussbegriffe</span>
        </div>
        <div class="source-grid" id="sources"></div>
      </section>

      <section class="panel span-12">
        <div class="section-title">
          <h2>Distill-only Ziele</h2>
          <span class="badge"><span class="dot info"></span> Manuelle Browser-Monitore fuer blockige Shops</span>
        </div>
        <div class="source-grid" id="distillTargets"></div>
      </section>

      <section class="panel span-6">
        <div class="section-title">
          <h2>Letzte Events</h2>
          <span class="badge"><span class="dot ok"></span> SQLite</span>
        </div>
        <div style="overflow:auto;">
          <table>
            <thead>
              <tr>
                <th>Zeit</th>
                <th>Typ</th>
                <th>Shop</th>
                <th>Titel</th>
                <th>Preis</th>
              </tr>
            </thead>
            <tbody id="eventsTable"></tbody>
          </table>
        </div>
      </section>

      <section class="panel span-6">
        <div class="section-title">
          <h2>Letzte Offers</h2>
          <span class="badge"><span class="dot info"></span> Letzter bekannter Zustand</span>
        </div>
        <div style="overflow:auto;">
          <table>
            <thead>
              <tr>
                <th>Shop</th>
                <th>Titel</th>
                <th>Preis</th>
                <th>Stock</th>
                <th>Zuletzt gesehen</th>
              </tr>
            </thead>
            <tbody id="offersTable"></tbody>
          </table>
        </div>
      </section>
    </div>

    <footer class="app-footer">
      <span>Alertivo • dev by Ivo</span>
      <span>&bull;</span>
      <a href="http://ivo-tech.com" target="_blank" rel="noreferrer">ivo-tech.com</a>
      <span>&bull;</span>
      <a href="/status-dashboard">Status-Dashboard Einstieg</a>
    </footer>
  </div>

  <div class="intro-overlay" id="introOverlay" hidden>
    <div class="intro-card">
      <div class="intro-video-wrap">
        <video class="intro-video" id="introVideo" muted playsinline preload="auto" poster="/assets/branding/logo-main.png"></video>
      </div>
      <div class="intro-actions">
        <button class="btn primary" id="introSkipBtn">Skip Intro</button>
        <button class="btn warn" id="introDisableBtn">Nicht mehr anzeigen</button>
      </div>
    </div>
  </div>

  <div class="intro-overlay" id="setupOverlay" hidden>
    <div class="intro-card">
      <div class="intro-actions" style="border-top:0;">
        <div>
          <strong>Willkommen bei Alertivo</strong>
          <div class="small muted" style="margin-top:6px;">KISS-Setup fuer neue Nutzer. Webhook und Integrationen bleiben optional.</div>
        </div>
      </div>
      <form class="setup-form" id="setupForm">
        <div class="field">
          <label for="setupDisplayName">Anzeigename</label>
          <input id="setupDisplayName" type="text" maxlength="60" placeholder="z. B. Ivo">
        </div>
        <label class="check"><input id="setupSimpleMode" type="checkbox" checked> Simple Mode (Webhook aus, lokal starten)</label>
        <label class="check"><input id="setupAutostart" type="checkbox"> Autostart aktivieren</label>
        <label class="check"><input id="setupIntroEnabled" type="checkbox" checked> Intro-Reveal anzeigen</label>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
          <button class="primary" type="submit">Setup speichern und starten</button>
          <button class="btn warn" id="rollbackConfigBtn" type="button">Migration-Backup wiederherstellen</button>
        </div>
      </form>
    </div>
  </div>

  <div class="toast" id="toast"></div>

  <script>
    const state = {
      data: null,
      dirtySources: new Set(),
      introInitialized: false,
    };

    const api = {
      state: "/api/control-center/state",
      runtime: "/api/control-center/runtime",
      runtimeCommand: "/api/control-center/runtime/command",
      test: "/api/control-center/test-alert",
      settings: "/api/control-center/settings",
      source: (name) => `/api/control-center/source/${encodeURIComponent(name)}`,
      onboarding: "/api/control-center/onboarding",
      migrationRollback: "/api/control-center/migration/rollback",
    };
    const INTRO_DISABLED_KEY = "ivo_intro_disabled";
    const introVideos = [
      "/assets/branding/intro-cinlogoreveal.mp4",
      "/assets/branding/intro-firefly-scanning.mp4",
      "/assets/branding/intro-firefly-epic.mp4",
      "/assets/branding/intro-grok.mp4",
    ];

    function closeIntroOverlay() {
      const overlay = document.getElementById("introOverlay");
      const video = document.getElementById("introVideo");
      overlay.hidden = true;
      video.pause();
      video.removeAttribute("src");
      video.load();
    }

    function initIntroOverlay(profile) {
      const overlay = document.getElementById("introOverlay");
      const video = document.getElementById("introVideo");
      const skipBtn = document.getElementById("introSkipBtn");
      const disableBtn = document.getElementById("introDisableBtn");

      if (profile && profile.intro_enabled === false) {
        overlay.hidden = true;
        return;
      }
      if (localStorage.getItem(INTRO_DISABLED_KEY) === "1") {
        overlay.hidden = true;
        return;
      }

      const selected = introVideos[Math.floor(Math.random() * introVideos.length)];
      video.src = selected;
      overlay.hidden = false;

      const playPromise = video.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(() => {});
      }

      skipBtn.addEventListener("click", closeIntroOverlay);
      disableBtn.addEventListener("click", () => {
        localStorage.setItem(INTRO_DISABLED_KEY, "1");
        closeIntroOverlay();
      });
      video.addEventListener("ended", closeIntroOverlay);
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function fmtDate(value) {
      if (!value) return "–";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return new Intl.DateTimeFormat("de-DE", {
        dateStyle: "short",
        timeStyle: "medium",
      }).format(date);
    }

    function fmtMoney(value, currency = "EUR") {
      if (value === null || value === undefined || value === "") return "–";
      const num = Number(String(value).replace(",", "."));
      if (Number.isNaN(num)) return `${value} ${currency}`;
      return new Intl.NumberFormat("de-DE", {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }).format(num);
    }

    function uptimeLabel(seconds) {
      const sec = Number(seconds || 0);
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      return `${h}h ${m}m ${s}s`;
    }

    function showToast(message, isError = false) {
      const node = document.getElementById("toast");
      node.innerHTML = `<strong>${isError ? "Fehler" : "Info"}</strong><div class="small muted" style="margin-top:6px;">${escapeHtml(message)}</div>`;
      node.style.borderColor = isError ? "rgba(255,107,107,0.45)" : "rgba(93,176,255,0.35)";
      node.classList.add("show");
      clearTimeout(showToast.timer);
      showToast.timer = setTimeout(() => node.classList.remove("show"), 3600);
    }

    async function request(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || data.message || response.statusText);
      }
      return data;
    }

    function renderStats(data) {
      const stats = [
        ["Direkte Quellen", data.sources.length],
        ["Aktive Quellen", data.sources.filter((source) => source.enabled).length],
        ["Bekannte Offers", data.summary.offers_count],
        ["Gespeicherte Events", data.summary.events_count],
        ["Laufzeit", uptimeLabel(data.runtime.uptime_seconds)],
      ];
      document.getElementById("stats").innerHTML = stats.map(([k, v]) => `
        <div class="stat">
          <div class="k">${escapeHtml(k)}</div>
          <div class="v">${escapeHtml(v)}</div>
        </div>
      `).join("");
    }

    function renderRuntime(data) {
      const webhookLabel = data.channels.webhook_enabled ? data.runtime.webhook_url : "deaktiviert (Simple Mode)";
      const runtime = [
        ["Control Center", data.runtime.control_center_url],
        ["Webhook", webhookLabel],
        ["Desktop Runtime", `${data.desktop.state}${data.desktop.paused ? " (paused)" : ""}`],
        ["Config", data.runtime.config_path],
        ["Datenbank", data.runtime.database_path],
        ["Gestartet", fmtDate(data.runtime.started_at)],
        ["Letztes Event", fmtDate(data.summary.last_event_at)],
      ];
      document.getElementById("runtimeMeta").innerHTML = runtime.map(([k, v]) => `
        <div class="kv-row">
          <div class="muted">${escapeHtml(k)}</div>
          <div style="text-align:right; max-width:60%;">${escapeHtml(v)}</div>
        </div>
      `).join("");

      const channels = Object.entries(data.channels).map(([name, enabled]) => {
        const cls = enabled ? "ok" : "bad";
        return `<div class="chip"><span class="dot ${cls}"></span> ${escapeHtml(name)}</div>`;
      }).join("");
      document.getElementById("channelChips").innerHTML = channels;
      document.getElementById("pauseResumeBtn").textContent = data.desktop.paused ? "Monitoring fortsetzen" : "Monitoring pausieren";
    }

    function renderSettings(data) {
      document.getElementById("refAge").value = data.app_settings.new_listing_reference_min_age_seconds;
      document.getElementById("restockToggle").checked = !!data.app_settings.enable_restock_alerts;
      document.getElementById("rtxExcludeCompletePcTerms").value = (data.app_settings.rtx_5070_ti_exclude_complete_pc_terms || []).join(", ");
      document.getElementById("rtxExcludeNotebookTerms").value = (data.app_settings.rtx_5070_ti_exclude_notebook_terms || []).join(", ");
      document.getElementById("rtxExcludeBundleTerms").value = (data.app_settings.rtx_5070_ti_exclude_bundle_terms || []).join(", ");
      document.getElementById("rtxExcludeDefectTerms").value = (data.app_settings.rtx_5070_ti_exclude_defect_terms || []).join(", ");
    }

    function sourceStatusBadge(source) {
      if (!source.enabled) return '<span class="badge"><span class="dot warn"></span> deaktiviert</span>';
      if (source.consecutive_failures > 0) return '<span class="badge"><span class="dot bad"></span> Fehler aktiv</span>';
      if (source.last_success_at) return '<span class="badge"><span class="dot ok"></span> gesund</span>';
      return '<span class="badge"><span class="dot info"></span> wartet</span>';
    }

    function renderSources(data) {
      const root = document.getElementById("sources");
      const existingCards = new Map([...root.querySelectorAll(".source-card")].map((node) => [node.dataset.name, node]));
      const html = data.sources.map((source) => {
        const preserve = state.dirtySources.has(source.name) && existingCards.has(source.name);
        if (preserve) return existingCards.get(source.name).outerHTML;
        const excludeTerms = (source.exclude_title_terms || []).join(", ");
        return `
          <article class="source-card" data-name="${escapeHtml(source.name)}">
            <div class="source-head">
              <div>
                <h3>${escapeHtml(source.name)}</h3>
                <div class="source-meta">
                  <div class="chip">${escapeHtml(source.shop)}</div>
                  <div class="chip">${escapeHtml(source.type)}</div>
                  <div class="chip">${escapeHtml(source.source)}</div>
                  <div class="chip">${escapeHtml(source.scope)}</div>
                </div>
              </div>
              ${sourceStatusBadge(source)}
            </div>
            <a class="source-url" href="${escapeHtml(source.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(source.url || "keine URL")}</a>
            <div class="source-runtime">
              <div class="runtime-box"><strong>Polls</strong>${escapeHtml(source.total_polls)}</div>
              <div class="runtime-box"><strong>Letzte Trefferzahl</strong>${escapeHtml(source.last_observation_count)}</div>
              <div class="runtime-box"><strong>Letzter Erfolg</strong>${escapeHtml(fmtDate(source.last_success_at))}</div>
              <div class="runtime-box"><strong>Letzter Fehler</strong>${escapeHtml(source.last_error ? `${fmtDate(source.last_error_at)} | ${source.last_error}` : "–")}</div>
            </div>
            <div class="form-grid">
              <label class="check"><input data-field="enabled" type="checkbox" ${source.enabled ? "checked" : ""}> Quelle aktiv</label>
              <div class="field">
                <label>Intervall Sekunden</label>
                <input data-field="interval_seconds" type="number" min="5" step="1" value="${escapeHtml(source.interval_seconds)}">
              </div>
              <div class="field">
                <label>Timeout Sekunden</label>
                <input data-field="timeout_seconds" type="number" min="5" step="1" value="${escapeHtml(source.timeout_seconds)}">
              </div>
              <div class="field">
                <label>Neue Listings unter Preis</label>
                <input data-field="new_listing_price_below" type="number" min="0" step="0.01" value="${escapeHtml(source.new_listing_price_below || "")}" placeholder="leer = aus">
              </div>
            </div>
            <div class="field">
              <label>Ausschlussbegriffe fuer Titel</label>
              <textarea data-field="exclude_title_terms" placeholder="z. B. defekt, bastler, reparatur">${escapeHtml(excludeTerms)}</textarea>
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap;">
              <button class="primary" data-action="save-source" data-name="${escapeHtml(source.name)}">Quelle speichern</button>
              <button data-action="reset-source" data-name="${escapeHtml(source.name)}">Formular zuruecksetzen</button>
              <a class="btn" href="${escapeHtml(source.url || "#")}" target="_blank" rel="noreferrer">Quelle oeffnen</a>
            </div>
          </article>
        `;
      }).join("");
      root.innerHTML = html;

      root.querySelectorAll(".source-card input, .source-card textarea").forEach((node) => {
        node.addEventListener("input", (event) => {
          const card = event.target.closest(".source-card");
          if (!card) return;
          state.dirtySources.add(card.dataset.name);
        });
      });
    }

    function renderEvents(data) {
      const rows = data.events.map((event) => `
        <tr>
          <td>${escapeHtml(fmtDate(event.timestamp))}</td>
          <td><span class="event-type">${escapeHtml(event.event_type)}</span></td>
          <td>${escapeHtml(event.shop)}</td>
          <td><a class="source-url" href="${escapeHtml(event.offer_url)}" target="_blank" rel="noreferrer">${escapeHtml(event.title)}</a></td>
          <td class="event-price">${escapeHtml(event.old_price ? `${fmtMoney(event.old_price, event.currency)} -> ${fmtMoney(event.new_price, event.currency)}` : fmtMoney(event.new_price, event.currency))}</td>
        </tr>
      `).join("");
      document.getElementById("eventsTable").innerHTML = rows || '<tr><td colspan="5" class="muted">Noch keine Events vorhanden.</td></tr>';
    }

    function renderOffers(data) {
      const rows = data.offers.map((offer) => `
        <tr>
          <td>${escapeHtml(offer.shop)}</td>
          <td><a class="source-url" href="${escapeHtml(offer.offer_url)}" target="_blank" rel="noreferrer">${escapeHtml(offer.last_seen_title)}</a></td>
          <td>${escapeHtml(fmtMoney(offer.last_seen_price))}</td>
          <td>${escapeHtml(offer.last_seen_stock === null ? "–" : (offer.last_seen_stock ? "in stock" : "out of stock"))}</td>
          <td>${escapeHtml(fmtDate(offer.last_seen_at))}</td>
        </tr>
      `).join("");
      document.getElementById("offersTable").innerHTML = rows || '<tr><td colspan="5" class="muted">Noch keine Offers vorhanden.</td></tr>';
    }

    async function loadState() {
      const data = await request(api.state);
      state.data = data;
      renderStats(data);
      renderRuntime(data);
      renderSetupOverlay(data);
      renderSettings(data);
      renderSources(data);
      renderDistillTargets(data);
      renderEvents(data);
      renderOffers(data);
      if (!state.introInitialized) {
        initIntroOverlay(data.profile);
        state.introInitialized = true;
      }
    }

    function renderSetupOverlay(data) {
      const overlay = document.getElementById("setupOverlay");
      const profile = data.profile || {};
      if (profile.onboarding_completed) {
        overlay.hidden = true;
        return;
      }
      overlay.hidden = false;
      document.getElementById("setupDisplayName").value = profile.display_name || "";
      document.getElementById("setupSimpleMode").checked = profile.simple_mode !== false;
      document.getElementById("setupAutostart").checked = !!profile.autostart_enabled;
      document.getElementById("setupIntroEnabled").checked = profile.intro_enabled !== false;
    }

    function renderDistillTargets(data) {
      const root = document.getElementById("distillTargets");
      root.innerHTML = data.distill_targets.map((target) => `
        <article class="source-card">
          <div class="source-head">
            <div>
              <h3>${escapeHtml(target.name)}</h3>
              <div class="source-meta">
                <div class="chip">Distill</div>
                <div class="chip">lokaler Browser</div>
              </div>
            </div>
            <span class="badge"><span class="dot warn"></span> manuell</span>
          </div>
          <a class="source-url" href="${escapeHtml(target.url)}" target="_blank" rel="noreferrer">${escapeHtml(target.url)}</a>
          <div class="muted" style="line-height:1.5;">${escapeHtml(target.note)}</div>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <a class="btn" href="${escapeHtml(target.url)}" target="_blank" rel="noreferrer">In Browser oeffnen</a>
          </div>
        </article>
      `).join("");
    }

    async function saveSettings(event) {
      event.preventDefault();
      const payload = {
        enable_restock_alerts: document.getElementById("restockToggle").checked,
        new_listing_reference_min_age_seconds: Number(document.getElementById("refAge").value || 0),
        rtx_5070_ti_exclude_complete_pc_terms: document.getElementById("rtxExcludeCompletePcTerms").value,
        rtx_5070_ti_exclude_notebook_terms: document.getElementById("rtxExcludeNotebookTerms").value,
        rtx_5070_ti_exclude_bundle_terms: document.getElementById("rtxExcludeBundleTerms").value,
        rtx_5070_ti_exclude_defect_terms: document.getElementById("rtxExcludeDefectTerms").value,
      };
      await request(api.settings, { method: "POST", body: JSON.stringify(payload) });
      showToast("Globale Einstellungen gespeichert.");
      await loadState();
    }

    async function saveSource(name) {
      const card = document.querySelector(`.source-card[data-name="${CSS.escape(name)}"]`);
      if (!card) return;
      const payload = {
        enabled: card.querySelector('[data-field="enabled"]').checked,
        interval_seconds: Number(card.querySelector('[data-field="interval_seconds"]').value || 0),
        timeout_seconds: Number(card.querySelector('[data-field="timeout_seconds"]').value || 0),
        new_listing_price_below: card.querySelector('[data-field="new_listing_price_below"]').value.trim(),
        exclude_title_terms: card.querySelector('[data-field="exclude_title_terms"]').value,
      };
      await request(api.source(name), { method: "POST", body: JSON.stringify(payload) });
      state.dirtySources.delete(name);
      showToast(`Quelle ${name} gespeichert.`);
      await loadState();
    }

    async function sendRuntimeCommand(command) {
      await request(api.runtimeCommand, { method: "POST", body: JSON.stringify({ command }) });
      await loadState();
    }

    async function saveOnboarding(event) {
      event.preventDefault();
      const payload = {
        display_name: document.getElementById("setupDisplayName").value.trim(),
        simple_mode: document.getElementById("setupSimpleMode").checked,
        autostart_enabled: document.getElementById("setupAutostart").checked,
        intro_enabled: document.getElementById("setupIntroEnabled").checked,
      };
      await request(api.onboarding, { method: "POST", body: JSON.stringify(payload) });
      showToast("Setup gespeichert.");
      await loadState();
    }

    async function rollbackMigration() {
      const response = await request(api.migrationRollback, { method: "POST", body: JSON.stringify({}) });
      if (!response.ok) {
        throw new Error("Rollback nicht verfuegbar.");
      }
      showToast("Backup wiederhergestellt. Monitoring neu starten empfohlen.");
      await loadState();
    }

    async function sendTestAlert(preset) {
      const response = await request(api.test, { method: "POST", body: JSON.stringify({ preset }) });
      showToast(`Test-Alert gesendet: ${preset}`);
      console.log(response.message);
    }

    document.getElementById("refreshBtn").addEventListener("click", loadState);
    document.getElementById("pauseResumeBtn").addEventListener("click", () => {
      const command = state.data && state.data.desktop && state.data.desktop.paused ? "resume" : "pause";
      sendRuntimeCommand(command).catch((error) => showToast(error.message, true));
    });
    document.getElementById("restartRuntimeBtn").addEventListener("click", () => {
      sendRuntimeCommand("restart").catch((error) => showToast(error.message, true));
    });
    document.getElementById("settingsForm").addEventListener("submit", (event) => {
      saveSettings(event).catch((error) => showToast(error.message, true));
    });
    document.getElementById("setupForm").addEventListener("submit", (event) => {
      saveOnboarding(event).catch((error) => showToast(error.message, true));
    });
    document.getElementById("rollbackConfigBtn").addEventListener("click", () => {
      rollbackMigration().catch((error) => showToast(error.message, true));
    });

    document.body.addEventListener("click", (event) => {
      const preset = event.target.getAttribute("data-preset");
      if (preset) {
        sendTestAlert(preset).catch((error) => showToast(error.message, true));
        return;
      }
      const action = event.target.getAttribute("data-action");
      const name = event.target.getAttribute("data-name");
      if (action === "save-source" && name) {
        saveSource(name).catch((error) => showToast(error.message, true));
      }
      if (action === "reset-source" && name) {
        state.dirtySources.delete(name);
        loadState().catch((error) => showToast(error.message, true));
      }
    });

    loadState().catch((error) => showToast(error.message, true));
    setInterval(() => {
      loadState().catch(() => {});
    }, 5000);
  </script>
</body>
</html>
"""

# Keep a file-based template for maintainable UI iteration.
CONTROL_CENTER_HTML = _load_control_center_html()
