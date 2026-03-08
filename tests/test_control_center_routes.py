from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
from aiohttp import web

from gpu_alerts.config import load_config
from gpu_alerts.control_center import ControlCenter, MonitorRuntime
from gpu_alerts.engine import AlertEngine
from gpu_alerts.matcher import ProductMatcher
from gpu_alerts.notifiers import NotifierManager
from gpu_alerts.storage import Storage


async def _start_app(tmp_path: Path) -> tuple[web.AppRunner, Storage, str]:
    config = load_config("config/monitor.yaml")
    config.database_path = tmp_path / "alerts.sqlite"
    storage = Storage(config.database_path)
    engine = AlertEngine(storage, ProductMatcher(), NotifierManager([]), enable_restock_alerts=False)
    runtime = MonitorRuntime(config)

    app = web.Application()
    profile_path = tmp_path / "user-profile.json"
    migration_path = tmp_path / "monitor-config.json"
    ControlCenter(
        app,
        config=config,
        engine=engine,
        notifiers=NotifierManager([]),
        storage=storage,
        runtime=runtime,
        profile_path=profile_path,
        migration_state_path=migration_path,
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    return runner, storage, f"http://127.0.0.1:{port}"


def test_status_dashboard_redirects_to_control_center(tmp_path) -> None:
    async def _case() -> None:
        runner, storage, base_url = await _start_app(tmp_path)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/status-dashboard", allow_redirects=False) as response:
                    assert response.status in {302, 303}
                    assert response.headers.get("Location") == "/control-center"
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())


def test_branding_logo_asset_is_served(tmp_path) -> None:
    async def _case() -> None:
        runner, storage, base_url = await _start_app(tmp_path)
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


def test_control_center_contains_branding_markers(tmp_path) -> None:
    async def _case() -> None:
        runner, storage, base_url = await _start_app(tmp_path)
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


def test_runtime_state_endpoint_available(tmp_path) -> None:
    async def _case() -> None:
        runner, storage, base_url = await _start_app(tmp_path)
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


def test_onboarding_endpoint_persists_profile(tmp_path) -> None:
    async def _case() -> None:
        runner, storage, base_url = await _start_app(tmp_path)
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
        finally:
            await runner.cleanup()
            storage.close()

    asyncio.run(_case())
