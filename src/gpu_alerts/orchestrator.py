from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from gpu_alerts.config import AppConfig, SourceConfig, load_config
from gpu_alerts.control_center import MonitorRuntime
from gpu_alerts.engine import AlertEngine
from gpu_alerts.main import build_collectors, poll_once
from gpu_alerts.matcher import ProductMatcher
from gpu_alerts.notifiers import build_notifier_manager
from gpu_alerts.storage import Storage
from gpu_alerts.webhook import start_webhook_server


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class OrchestratorStatus:
    state: str
    paused: bool
    monitoring_active: bool
    started_at: float | None
    control_center_url: str | None
    webhook_url: str | None
    last_error: str | None
    thread_alive: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "paused": self.paused,
            "monitoring_active": self.monitoring_active,
            "started_at": self.started_at,
            "control_center_url": self.control_center_url,
            "webhook_url": self.webhook_url,
            "last_error": self.last_error,
            "thread_alive": self.thread_alive,
        }


class MonitorOrchestrator:
    def __init__(
        self,
        *,
        config_path: str | Path,
        settings_path: str | Path | None = None,
        migration_state_path: str | Path | None = None,
        autostart_launcher: str | Path | None = None,
    ):
        self._config_path = Path(config_path).resolve()
        self._settings_path = Path(settings_path).resolve() if settings_path else None
        self._migration_state_path = Path(migration_state_path).resolve() if migration_state_path else None
        self._autostart_launcher = Path(autostart_launcher).resolve() if autostart_launcher else None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._startup_event = threading.Event()
        self._startup_error: Exception | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._resume_event: asyncio.Event | None = None
        self._status = OrchestratorStatus(
            state="stopped",
            paused=False,
            monitoring_active=False,
            started_at=None,
            control_center_url=None,
            webhook_url=None,
            last_error=None,
            thread_alive=False,
        )

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._startup_event.clear()
            self._startup_error = None
            self._status.state = "starting"
            self._status.last_error = None
            thread = threading.Thread(target=self._thread_main, daemon=True, name="alertivo-monitor")
            self._thread = thread
            thread.start()
        if not self._startup_event.wait(timeout=25):
            raise TimeoutError("Alertivo monitor startup timed out")
        if self._startup_error is not None:
            raise RuntimeError(str(self._startup_error))

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            loop = self._loop
            stop_event = self._stop_event
            resume_event = self._resume_event
            if not thread:
                self._status.state = "stopped"
                self._status.paused = False
                self._status.monitoring_active = False
                self._status.thread_alive = False
                return
            self._status.state = "stopping"
        if loop and stop_event and resume_event:
            loop.call_soon_threadsafe(stop_event.set)
            loop.call_soon_threadsafe(resume_event.set)
        thread.join(timeout=25)
        with self._lock:
            self._thread = None
            self._loop = None
            self._stop_event = None
            self._resume_event = None
            self._status.state = "stopped"
            self._status.paused = False
            self._status.monitoring_active = False
            self._status.thread_alive = False

    def restart(self) -> None:
        self.stop()
        self.start()

    def pause(self) -> None:
        loop = self._loop
        resume_event = self._resume_event
        if not loop or not resume_event:
            return
        loop.call_soon_threadsafe(resume_event.clear)
        with self._lock:
            if self._status.state == "running":
                self._status.state = "paused"
            self._status.paused = True
            self._status.monitoring_active = False

    def resume(self) -> None:
        loop = self._loop
        resume_event = self._resume_event
        if not loop or not resume_event:
            return
        loop.call_soon_threadsafe(resume_event.set)
        with self._lock:
            self._status.state = "running"
            self._status.paused = False
            self._status.monitoring_active = True

    def stop_monitoring(self) -> None:
        loop = self._loop
        resume_event = self._resume_event
        if not loop or not resume_event:
            return
        loop.call_soon_threadsafe(resume_event.clear)
        with self._lock:
            self._status.state = "idle"
            self._status.paused = False
            self._status.monitoring_active = False

    def start_monitoring(self) -> None:
        loop = self._loop
        resume_event = self._resume_event
        if not loop or not resume_event:
            return
        loop.call_soon_threadsafe(resume_event.set)
        with self._lock:
            self._status.state = "running"
            self._status.paused = False
            self._status.monitoring_active = True

    def is_monitoring_active(self) -> bool:
        with self._lock:
            return self._status.monitoring_active

    def status(self) -> dict[str, Any]:
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            self._status.thread_alive = thread_alive
            return self._status.to_dict()

    @property
    def control_center_url(self) -> str | None:
        return self.status().get("control_center_url")

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            LOGGER.exception("Monitor worker crashed")
            with self._lock:
                self._status.state = "error"
                self._status.last_error = str(exc)
                self._status.monitoring_active = False
            if not self._startup_event.is_set():
                self._startup_error = exc
                self._startup_event.set()
        finally:
            with self._lock:
                if self._status.state not in {"error", "stopped"}:
                    self._status.state = "stopped"
                self._status.monitoring_active = False
                self._status.thread_alive = False

    async def _run_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()

        config = load_config(self._config_path)
        self._status.control_center_url = f"http://{config.webhook.host}:{config.webhook.port}/control-center"
        self._status.webhook_url = f"http://{config.webhook.host}:{config.webhook.port}{config.webhook.path}"

        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

        storage = Storage(config.database_path)
        runtime = MonitorRuntime(config)
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(limit=20)
        with self._lock:
            self._status.state = "running"
            self._status.paused = False
            self._status.monitoring_active = True
            self._status.started_at = time.time()
            self._status.thread_alive = True

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
            runner = await start_webhook_server(
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
                runtime_controller=self,
                profile_path=self._settings_path or config.settings_path,
                migration_state_path=self._migration_state_path or config.migration_state_path,
                autostart_launcher=self._autostart_launcher,
            )
            if not self._startup_event.is_set():
                self._startup_event.set()

            collectors = build_collectors(session, config)
            try:
                if collectors:
                    await asyncio.gather(
                        *[
                            self._poll_loop(
                                source=source,
                                collector=collector,
                                engine=engine,
                                runtime=runtime,
                            )
                            for source, collector in collectors
                        ]
                    )
                else:
                    await self._stop_event.wait()
            finally:
                await runner.cleanup()
                storage.close()

    async def _poll_loop(
        self,
        *,
        source: SourceConfig,
        collector: object,
        engine: AlertEngine,
        runtime: MonitorRuntime,
    ) -> None:
        assert self._stop_event is not None
        assert self._resume_event is not None
        while not self._stop_event.is_set():
            await self._resume_event.wait()
            if self._stop_event.is_set():
                break
            if source.enabled:
                await poll_once(source, collector, engine, runtime)
            wait_for = min(max(source.interval_seconds, 1), 3600)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_for)
            except asyncio.TimeoutError:
                continue
