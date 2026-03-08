from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
from decimal import Decimal
from typing import Protocol

import aiohttp

from gpu_alerts.config import DiscordConfig, SoundConfig, TelegramConfig, WindowsConfig
from gpu_alerts.models import AlertEvent


LOGGER = logging.getLogger(__name__)


class Notifier(Protocol):
    async def send(self, event: AlertEvent) -> None:
        ...


def format_event_message(event: AlertEvent) -> str:
    lines = [
        f"[{event.event_type}] {event.shop} | {event.title}",
        f"Produkt: {event.product_family} / {event.canonical_model}",
    ]
    if event.event_type == "new_listing_under_threshold" and event.threshold_price is not None:
        lines.append(f"Preis: {event.new_price or '-'} {event.currency}")
        lines.append(f"Schwelle: < {event.threshold_price} {event.currency}")
    else:
        lines.append(f"Preis: {event.old_price or '-'} -> {event.new_price or '-'} {event.currency}")
    if event.delta is not None:
        percent = f"{event.delta_percent:.2f}%" if event.delta_percent is not None else "-"
        lines.append(f"Delta: {event.delta} {event.currency} ({percent})")
    if event.in_stock is not None:
        lines.append(f"Verfügbarkeit: {'in stock' if event.in_stock else 'out of stock'}")
    lines.append(f"Quelle: {event.source}")
    lines.append(event.url)
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self, session: aiohttp.ClientSession, config: TelegramConfig):
        self._session = session
        self._config = config

    async def send(self, event: AlertEvent) -> None:
        payload = {
            "chat_id": self._config.chat_id,
            "text": format_event_message(event),
            "disable_web_page_preview": False,
        }
        url = f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage"
        async with self._session.post(url, json=payload) as response:
            response.raise_for_status()


class DiscordNotifier:
    def __init__(self, session: aiohttp.ClientSession, config: DiscordConfig):
        self._session = session
        self._config = config

    async def send(self, event: AlertEvent) -> None:
        embed = {
            "title": event.title[:256],
            "description": format_event_message(event)[:4000],
            "url": event.url,
        }
        async with self._session.post(self._config.webhook_url, json={"embeds": [embed]}) as response:
            response.raise_for_status()


class WindowsToastNotifier:
    def __init__(self, config: WindowsConfig):
        self._config = config

    async def send(self, event: AlertEvent) -> None:
        if os.name != "nt":
            return

        title = f"{event.shop}: {event.new_price or '-'} {event.currency}"
        body = f"{event.title} [{event.event_type}]"
        xml = (
            "<toast>"
            "<visual><binding template=\"ToastGeneric\">"
            f"<text>{_xml_escape(title)}</text>"
            f"<text>{_xml_escape(body)}</text>"
            "</binding></visual></toast>"
        )
        encoded_xml = base64.b64encode(xml.encode("utf-8")).decode("ascii")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] > $null;"
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
            "ContentType = WindowsRuntime] > $null;"
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
            f"$xmlText=[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{encoded_xml}'));"
            "$xml.LoadXml($xmlText);"
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{self._config.app_id}').Show($toast);"
        )
        process = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            LOGGER.warning("Windows toast failed: %s", stderr.decode("utf-8", errors="ignore").strip())


class SoundNotifier:
    def __init__(self, config: SoundConfig):
        self._config = config

    async def send(self, event: AlertEvent) -> None:
        if os.name != "nt":
            return

        script = "Add-Type -AssemblyName System.Media;"
        if self._config.sound_file:
            path = self._config.sound_file.replace("\\", "\\\\")
            script += f"(New-Object System.Media.SoundPlayer '{path}').PlaySync();"
        else:
            script += "[console]::beep(1400, 350);"

        process = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            LOGGER.warning("Sound notifier failed: %s", stderr.decode("utf-8", errors="ignore").strip())


class ConsoleNotifier:
    async def send(self, event: AlertEvent) -> None:
        print(format_event_message(event), file=sys.stderr, flush=True)


class NotifierManager:
    def __init__(self, notifiers: list[Notifier]):
        self._notifiers = notifiers

    async def send(self, event: AlertEvent) -> None:
        for notifier in self._notifiers:
            try:
                await notifier.send(event)
            except Exception:
                LOGGER.exception("Notifier %s failed", notifier.__class__.__name__)


def build_notifier_manager(
    session: aiohttp.ClientSession,
    *,
    telegram: TelegramConfig | None,
    discord: DiscordConfig | None,
    windows: WindowsConfig,
    sound: SoundConfig,
) -> NotifierManager:
    notifiers: list[Notifier] = [ConsoleNotifier()]
    if telegram:
        notifiers.append(TelegramNotifier(session, telegram))
    if discord:
        notifiers.append(DiscordNotifier(session, discord))
    if windows.enabled:
        notifiers.append(WindowsToastNotifier(windows))
    if sound.enabled:
        notifiers.append(SoundNotifier(sound))
    return NotifierManager(notifiers)


def build_test_event(*, display_name: str = "Alertivo User", channel: str = "manual_test") -> AlertEvent:
    return AlertEvent(
        event_type="manual_test",
        shop="alertivo",
        source=channel,
        product_family="alertivo-test",
        canonical_model="alertivo-test",
        title=f"Alertivo Testnachricht fuer {display_name or 'Alertivo User'}",
        url="http://127.0.0.1:8787/control-center",
        old_price=Decimal("249"),
        new_price=Decimal("199"),
        currency="EUR",
        in_stock=True,
        dedupe_key=f"alertivo-test-{channel}",
    )


async def send_test_notifications(
    session: aiohttp.ClientSession,
    *,
    display_name: str = "Alertivo User",
    telegram: TelegramConfig | None = None,
    discord: DiscordConfig | None = None,
    windows: WindowsConfig | None = None,
    sound: SoundConfig | None = None,
    channels: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    requested_channels = [item.strip().lower() for item in (channels or []) if item.strip()]
    if not requested_channels:
        requested_channels = ["telegram", "discord", "windows", "sound"]

    results: dict[str, dict[str, Any]] = {}
    for channel in requested_channels:
        event = build_test_event(display_name=display_name, channel=channel)
        try:
            if channel == "telegram":
                if telegram is None:
                    raise ValueError("telegram_not_configured")
                await TelegramNotifier(session, telegram).send(event)
            elif channel == "discord":
                if discord is None:
                    raise ValueError("discord_not_configured")
                await DiscordNotifier(session, discord).send(event)
            elif channel == "windows":
                if windows is None or not windows.enabled:
                    raise ValueError("windows_notifications_disabled")
                await WindowsToastNotifier(windows).send(event)
            elif channel == "sound":
                if sound is None or not sound.enabled:
                    raise ValueError("sound_notifications_disabled")
                await SoundNotifier(sound).send(event)
            else:
                raise ValueError("unsupported_channel")
        except Exception as exc:
            results[channel] = {"ok": False, "error": str(exc)}
            continue
        results[channel] = {"ok": True}
    return results


def _xml_escape(value: str) -> str:
    return json.dumps(value)[1:-1].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
