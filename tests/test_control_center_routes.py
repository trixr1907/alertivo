from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
from aiohttp import web

import gpu_alerts.control_center as control_center_module
from gpu_alerts.config import load_config
from gpu_alerts.control_center import ControlCenter, MonitorRuntime
from gpu_alerts.engine import AlertEngine
from gpu_alerts.matcher import ProductMatcher
from gpu_alerts.notifiers import NotifierManager
from gpu_alerts.storage import Storage
from tests.helpers import write_system_json


class DummyRuntimeController:
    def __init__(self) -> None:
        self.restart_calls = 0
        self._status = {
            "state": "running",
            "paused": False,
            "monitoring_active": True,
            "started_at": None,
            "control_center_url": "http://127.0.0.1:8787/control-center",
            "webhook_url": "http://127.0.0.1:8787/webhook/distill",
            "last_error": None,
            "thread_alive": True,
        }

    def status(self) -> dict:
        return dict(self._status)

    def start_monitoring(self) -> None:
        self._status["state"] = "running"
        self._status["monitoring_active"] = True
        self._status["paused"] = False

    def stop_monitoring(self) -> None:
        self._status["state"] = "idle"
        self._status["monitoring_active"] = False
        self._status["paused"] = False

    def restart(self) -> None:
        self.restart_calls += 1
        self._status["state"] = "running"
        self._status["monitoring_active"] = True
        self._status["paused"] = False


async def _start_app(tmp_path: Path, runtime_controller: DummyRuntimeController | None = None) -> tuple[web.AppRunner, Storage, str, Path]:
    install_dir = tmp_path / "install"
    system_path = write_system_json(install_dir / "system.json")
    config = load_config(system_path)
    config.database_path = tmp_path / "alerts.sqlite"
    storage = Storage(config.database_path)
    engine = AlertEngine(storage, ProductMatcher(), NotifierManager([]), enable_restock_alerts=False)
    runtime = MonitorRuntime(config)

    app = web.Application()
    ControlCenter(
        app,
        config=config,
        engine=engine,
        notifiers=NotifierManager([]),
        storage=storage,
        runtime=runtime,
        runtime_controller=runtime_controller,
        profile_path=config.settings_path,
        migration_state_path=config.migration_state_path,
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    return runner, storage, f"http://127.0.0.1:{port}", config.settings_path


def test_status_dashboard_redirects_to_control_center(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/status-dashboard", allow_redirects=False) as response:
                    assert response.status in {302, 303}
                    assert response.headers.get("Location") == "/control-center"
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_branding_logo_asset_is_served(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/assets/branding/logo-main.png") as response:
                    assert response.status == 200
                    assert "image/" in response.headers.get("Content-Type", "")
                    body = await response.read()
                    assert len(body) > 0
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_control_center_contains_branding_markers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/control-center") as response:
                    assert response.status == 200
                    html = await response.text()
                    assert "/assets/branding/logo-main.png" in html
                    assert "ivo-tech.com" in html
                    assert 'id="introOverlay"' in html
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_runtime_state_endpoint_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/api/control-center/runtime") as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["ok"] is True
                    assert "runtime" in payload
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_onboarding_endpoint_persists_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, settings_path = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "display_name": "QA User",
                    "simple_mode": True,
                    "autostart_enabled": False,
                    "intro_enabled": False,
                }
                async with session.post(f"{base_url}/api/control-center/onboarding", json=payload) as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["ok"] is True
                async with session.get(f"{base_url}/api/control-center/state") as response:
                    state = await response.json()
                    assert state["profile"]["display_name"] == "QA User"
                    assert state["profile"]["onboarding_completed"] is True
                    assert state["profile"]["intro_enabled"] is False
                assert settings_path.exists()
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_onboarding_endpoint_persists_first_tracker_filters(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "display_name": "QA User",
                    "distill_token": "demo-token",
                    "first_tracker": {
                        "name": "Smoke Console",
                        "query": "Smoke Console",
                        "include_terms": ["smoke", "console"],
                        "exclude_terms": ["bundle", "gebraucht"],
                        "shops": [
                            {"shop_id": "amazon-search", "enabled": True, "mode": "auto"},
                            {"shop_id": "mediamarkt-search", "enabled": True, "mode": "auto"},
                        ],
                    },
                }
                async with session.post(f"{base_url}/api/control-center/onboarding", json=payload) as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["ok"] is True
                    assert data["created_tracker"] == "smoke-console"
                state_config = load_config(tmp_path / "install" / "system.json")
                tracker = next(item for item in state_config.trackers if item.id == "smoke-console")
                assert tracker.filters.include_terms == ["smoke", "console"]
                assert tracker.filters.exclude_terms == ["bundle", "gebraucht"]
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_runtime_command_endpoint_supports_start_and_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runtime_controller = DummyRuntimeController()
        runner, storage, base_url, _ = await _start_app(tmp_path, runtime_controller=runtime_controller)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{base_url}/api/control-center/runtime/command", json={"command": "stop"}) as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["runtime"]["monitoring_active"] is False
                    assert payload["runtime"]["state"] == "idle"
                async with session.post(f"{base_url}/api/control-center/runtime/command", json={"command": "start"}) as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["runtime"]["monitoring_active"] is True
                    assert payload["runtime"]["state"] == "running"
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_runtime_command_endpoint_schedules_restart_after_response(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runtime_controller = DummyRuntimeController()
        runner, storage, base_url, _ = await _start_app(tmp_path, runtime_controller=runtime_controller)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{base_url}/api/control-center/runtime/command", json={"command": "restart"}) as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["ok"] is True
                    assert payload["restart_required"] is True
                assert runtime_controller.restart_calls == 0
                await asyncio.sleep(0.4)
                assert runtime_controller.restart_calls == 1
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_notification_test_endpoint_returns_channel_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def fake_send_test_notifications(session, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "telegram": {"ok": True},
            "discord": {"ok": False, "error": "discord_failed"},
        }

    monkeypatch.setattr(control_center_module, "send_test_notifications", fake_send_test_notifications)

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/control-center/notifications/test",
                    json={
                        "display_name": "QA User",
                        "channels": ["telegram", "discord"],
                        "telegram_bot_token": "demo",
                        "telegram_chat_id": "123",
                        "discord_webhook_url": "https://discord.example/webhook",
                    },
                ) as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["ok"] is False
                    assert payload["results"]["telegram"]["ok"] is True
                    assert payload["results"]["discord"]["ok"] is False
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_distill_preview_endpoint_returns_snippets_for_tracker_draft(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    async def _case() -> None:
        runner, storage, base_url, _ = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/control-center/distill-preview",
                    json={
                        "name": "PS5 Pro",
                        "query": "PS5 Pro",
                        "include_terms": ["ps5", "pro"],
                        "exclude_terms": ["bundle"],
                        "shops": [
                            {"shop_id": "amazon", "enabled": True, "mode": "distill"},
                            {"shop_id": "mediamarkt", "enabled": True, "mode": "auto"},
                        ],
                        "distill_token": "demo-token",
                    },
                ) as response:
                    assert response.status == 200
                    payload = await response.json()
                    assert payload["ok"] is True
                    assert len(payload["targets"]) >= 1
                    assert '"product_hint": "ps5-pro"' in payload["targets"][0]["snippet"]
                    assert '"X-Webhook-Token": "demo-token"' in payload["targets"][0]["snippet"]
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())
