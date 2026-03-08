from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Iterable

import aiohttp

from gpu_alerts.collectors.command import CommandCollector
from gpu_alerts.collectors.http import HttpCollector
from gpu_alerts.config import AppConfig, SourceConfig, load_config
from gpu_alerts.control_center import MonitorRuntime
from gpu_alerts.engine import AlertEngine
from gpu_alerts.matcher import ProductMatcher
from gpu_alerts.notifiers import build_notifier_manager
from gpu_alerts.storage import Storage
from gpu_alerts.webhook import start_webhook_server


LOGGER = logging.getLogger(__name__)


async def run(config: AppConfig, *, check_once: bool = False) -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    storage = Storage(config.database_path)
    runtime = MonitorRuntime(config)
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=20)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        notifiers = build_notifier_manager(
            session,
            telegram=config.telegram,
            discord=config.discord,
            windows=config.windows,
            sound=config.sound,
        )
        engine = AlertEngine(
            storage,
            ProductMatcher(),
            notifiers,
            enable_restock_alerts=config.enable_restock_alerts,
            new_listing_reference_min_age_seconds=config.new_listing_reference_min_age_seconds,
        )

        webhook_runner = None
        if not check_once:
            webhook_runner = await start_webhook_server(
                engine,
                config=config,
                notifiers=notifiers,
                storage=storage,
                runtime=runtime,
                host=config.webhook.host,
                port=config.webhook.port,
                path=config.webhook.path,
                token=config.webhook.token,
                webhook_enabled=config.webhook.enabled,
            )

        collectors = build_collectors(session, config)

        try:
            if check_once:
                await poll_all_collectors(collectors, engine, runtime)
            else:
                tasks = [
                    asyncio.create_task(poll_forever(source, collector, engine, runtime))
                    for source, collector in collectors
                ]
                await asyncio.gather(*tasks) if tasks else asyncio.Event().wait()
        finally:
            if webhook_runner:
                await webhook_runner.cleanup()
            storage.close()


def build_collectors(session: aiohttp.ClientSession, config: AppConfig) -> list[tuple[SourceConfig, object]]:
    collectors: list[tuple[SourceConfig, object]] = []
    for source in config.sources:
        if not source.enabled:
            continue
        if source.type == "distill":
            continue
        if source.type == "http":
            collectors.append((source, HttpCollector(session, source, config.user_agent)))
            continue
        if source.type == "command":
            collectors.append((source, CommandCollector(source)))
            continue
        raise ValueError(f"Unsupported source type: {source.type}")
    return collectors


async def poll_all_collectors(
    collectors: Iterable[tuple[SourceConfig, object]],
    engine: AlertEngine,
    runtime: MonitorRuntime,
) -> None:
    for source, collector in collectors:
        await poll_once(source, collector, engine, runtime)


async def poll_forever(source: SourceConfig, collector: object, engine: AlertEngine, runtime: MonitorRuntime) -> None:
    while True:
        if source.enabled:
            await poll_once(source, collector, engine, runtime)
        await asyncio.sleep(source.interval_seconds)


async def poll_once(source: SourceConfig, collector: object, engine: AlertEngine, runtime: MonitorRuntime) -> None:
    runtime.mark_poll_started(source.name)
    try:
        observations = await collector.collect()
    except Exception as exc:
        runtime.mark_poll_error(source.name, exc)
        LOGGER.exception("Collector %s failed", source.name)
        return
    runtime.mark_poll_success(source.name, len(observations))

    for observation in observations:
        try:
            await engine.process(observation)
        except Exception:
            LOGGER.exception("Engine failed for %s", observation.title)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alertivo local monitoring runtime.")
    parser.add_argument("--config", default="system.json", help="Path to system.json.")
    parser.add_argument("--check-once", action="store_true", help="Run each source once and exit.")
    args = parser.parse_args()

    config = load_config(args.config)
    asyncio.run(run(config, check_once=args.check_once))


if __name__ == "__main__":
    main()
