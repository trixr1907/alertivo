from __future__ import annotations

import asyncio
from pathlib import Path

from gpu_alerts.orchestrator import MonitorOrchestrator
from tests.helpers import write_system_json


class DummyOrchestrator(MonitorOrchestrator):
    async def _run_async(self) -> None:  # type: ignore[override]
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._status.state = "running"
        self._status.paused = False
        self._status.monitoring_active = True
        self._status.control_center_url = "http://127.0.0.1:8787/control-center"
        self._status.webhook_url = "http://127.0.0.1:8787/webhook/distill"
        self._startup_event.set()
        await self._stop_event.wait()


def test_orchestrator_lifecycle(tmp_path: Path) -> None:
    config = write_system_json(tmp_path / "system.json")
    orchestrator = DummyOrchestrator(config_path=config)
    orchestrator.start()
    status = orchestrator.status()
    assert status["state"] == "running"
    assert status["thread_alive"] is True
    assert status["monitoring_active"] is True

    orchestrator.stop_monitoring()
    stopped_monitoring = orchestrator.status()
    assert stopped_monitoring["state"] == "idle"
    assert stopped_monitoring["monitoring_active"] is False

    orchestrator.start_monitoring()
    resumed = orchestrator.status()
    assert resumed["monitoring_active"] is True

    orchestrator.stop()
    stopped = orchestrator.status()
    assert stopped["state"] == "stopped"
