from __future__ import annotations

import asyncio

import aiohttp
from aiohttp import web

import gpu_alerts.notifiers as notifiers_module
from gpu_alerts.config import DiscordConfig, TelegramConfig
from gpu_alerts.notifiers import send_test_notifications


async def _start_server(handler_map):  # type: ignore[no-untyped-def]
    app = web.Application()
    for method, path, handler in handler_map:
        app.router.add_route(method, path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


def test_send_test_notifications_maps_telegram_invalid_token(monkeypatch) -> None:
    async def _case() -> None:
        async def telegram_handler(request: web.Request) -> web.Response:
            return web.json_response({"ok": False, "description": "Unauthorized"}, status=401)

        runner, base_url = await _start_server([("POST", "/botdemo/sendMessage", telegram_handler)])
        monkeypatch.setattr(notifiers_module, "TELEGRAM_API_BASE_URL", base_url)
        try:
            async with aiohttp.ClientSession() as session:
                results = await send_test_notifications(
                    session,
                    telegram=TelegramConfig(bot_token="demo", chat_id="123"),
                    channels=["telegram"],
                )
                assert results["telegram"]["ok"] is False
                assert results["telegram"]["code"] == "telegram_invalid_token"
                assert "@BotFather" in results["telegram"]["message"]
        finally:
            await runner.cleanup()

    asyncio.run(_case())


def test_send_test_notifications_maps_telegram_invalid_chat_id(monkeypatch) -> None:
    async def _case() -> None:
        async def telegram_handler(request: web.Request) -> web.Response:
            return web.json_response({"ok": False, "description": "Bad Request: chat not found"}, status=400)

        runner, base_url = await _start_server([("POST", "/botdemo/sendMessage", telegram_handler)])
        monkeypatch.setattr(notifiers_module, "TELEGRAM_API_BASE_URL", base_url)
        try:
            async with aiohttp.ClientSession() as session:
                results = await send_test_notifications(
                    session,
                    telegram=TelegramConfig(bot_token="demo", chat_id="999"),
                    channels=["telegram"],
                )
                assert results["telegram"]["ok"] is False
                assert results["telegram"]["code"] == "telegram_invalid_chat_id"
                assert "@userinfobot" in results["telegram"]["message"]
        finally:
            await runner.cleanup()

    asyncio.run(_case())


def test_send_test_notifications_maps_discord_webhook_not_found() -> None:
    async def _case() -> None:
        async def discord_handler(request: web.Request) -> web.Response:
            return web.json_response({"message": "Unknown Webhook"}, status=404)

        runner, base_url = await _start_server([("POST", "/discord/webhook", discord_handler)])
        try:
            async with aiohttp.ClientSession() as session:
                results = await send_test_notifications(
                    session,
                    discord=DiscordConfig(webhook_url=f"{base_url}/discord/webhook"),
                    channels=["discord"],
                )
                assert results["discord"]["ok"] is False
                assert results["discord"]["code"] == "discord_invalid_webhook"
                assert "Webhook" in results["discord"]["message"]
        finally:
            await runner.cleanup()

    asyncio.run(_case())


def test_send_test_notifications_maps_timeout(monkeypatch) -> None:
    async def fake_send(self, event):  # type: ignore[no-untyped-def]
        raise asyncio.TimeoutError()

    monkeypatch.setattr(notifiers_module.TelegramNotifier, "send", fake_send)

    async def _case() -> None:
        async with aiohttp.ClientSession() as session:
            results = await send_test_notifications(
                session,
                telegram=TelegramConfig(bot_token="demo", chat_id="123"),
                channels=["telegram"],
            )
            assert results["telegram"]["ok"] is False
            assert results["telegram"]["code"] == "telegram_timeout"
            assert "lange gedauert" in results["telegram"]["message"]

    asyncio.run(_case())
