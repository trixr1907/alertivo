from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aiohttp import web

from gpu_alerts.control_center import ControlCenter, MonitorRuntime
from gpu_alerts.config import AppConfig
from gpu_alerts.engine import AlertEngine
from gpu_alerts.models import OfferObservation
from gpu_alerts.notifiers import NotifierManager
from gpu_alerts.parsing import parse_price, parse_stock
from gpu_alerts.storage import Storage


LOGGER = logging.getLogger(__name__)


class WebhookServer:
    def __init__(
        self,
        engine: AlertEngine,
        *,
        config: AppConfig,
        notifiers: NotifierManager,
        storage: Storage,
        runtime: MonitorRuntime,
        path: str,
        token: str | None = None,
        webhook_enabled: bool = True,
        runtime_controller: object | None = None,
        profile_path: Path | None = None,
        migration_state_path: Path | None = None,
        autostart_launcher: Path | None = None,
    ):
        self._engine = engine
        self._path = path
        self._token = token
        self._webhook_enabled = webhook_enabled
        self._runtime_controller = runtime_controller
        self._app = web.Application()
        if self._webhook_enabled:
            self._app.router.add_post(self._path, self._handle)
        ControlCenter(
            self._app,
            config=config,
            engine=engine,
            notifiers=notifiers,
            storage=storage,
            runtime=runtime,
            runtime_controller=runtime_controller,
            profile_path=profile_path,
            migration_state_path=migration_state_path,
            autostart_launcher=autostart_launcher,
        )

    @property
    def app(self) -> web.Application:
        return self._app

    async def _handle(self, request: web.Request) -> web.Response:
        if self._runtime_controller and hasattr(self._runtime_controller, "is_monitoring_active"):
            if not self._runtime_controller.is_monitoring_active():
                return web.json_response({"ok": False, "error": "monitoring_stopped"}, status=409)
        if self._token:
            auth = request.headers.get("X-Webhook-Token", "")
            if auth != self._token:
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

        payload = await request.json()
        observation = self._parse_payload(payload)
        if not observation:
            return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)

        event = await self._engine.process(observation)
        return web.json_response({"ok": True, "event_type": event.event_type if event else None})

    @staticmethod
    def _parse_payload(payload: dict) -> OfferObservation | None:
        title = payload.get("title") or payload.get("product") or payload.get("name")
        shop = payload.get("shop")
        source = payload.get("source", "shop")
        scope = payload.get("scope", "shop_search")
        url = payload.get("url", "")
        price = payload.get("price")
        stock = payload.get("in_stock")

        if not title or not shop:
            return None

        parsed_price = None
        if isinstance(price, (int, float, Decimal)):
            parsed_price = Decimal(str(price))
        elif isinstance(price, str) and price.strip():
            parsed_price = parse_price(price)
            if parsed_price is None:
                try:
                    parsed_price = Decimal(price.strip())
                except InvalidOperation:
                    parsed_price = None
        parsed_stock = stock if isinstance(stock, bool) else parse_stock(str(stock)) if stock is not None else None

        return OfferObservation(
            shop=shop,
            source=source,
            scope=scope,
            title=title,
            url=url,
            price=parsed_price,
            in_stock=parsed_stock,
            product_hint=payload.get("product_hint"),
            include_title_terms=list(payload.get("include_title_terms", [])),
            exclude_title_terms=list(payload.get("exclude_title_terms", [])),
            price_ceiling=(
                Decimal(str(payload["price_ceiling"]))
                if payload.get("price_ceiling") is not None
                else None
            ),
            new_listing_price_below=(
                Decimal(str(payload["new_listing_price_below"]))
                if payload.get("new_listing_price_below") is not None
                else None
            ),
            raw_payload=payload,
        )


async def start_webhook_server(
    engine: AlertEngine,
    *,
    config: AppConfig,
    notifiers: NotifierManager,
    storage: Storage,
    runtime: MonitorRuntime,
    host: str,
    port: int,
    path: str,
    token: str | None,
    webhook_enabled: bool = True,
    runtime_controller: object | None = None,
    profile_path: Path | None = None,
    migration_state_path: Path | None = None,
    autostart_launcher: Path | None = None,
) -> web.AppRunner:
    server = WebhookServer(
        engine,
        config=config,
        notifiers=notifiers,
        storage=storage,
        runtime=runtime,
        path=path,
        token=token,
        webhook_enabled=webhook_enabled,
        runtime_controller=runtime_controller,
        profile_path=profile_path,
        migration_state_path=migration_state_path,
        autostart_launcher=autostart_launcher,
    )
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    LOGGER.info("Control center listening on http://%s:%s/control-center", host, port)
    if webhook_enabled:
        LOGGER.info("Webhook listening on http://%s:%s%s", host, port, path)
    else:
        LOGGER.info("Webhook disabled (simple mode)")
    return runner
