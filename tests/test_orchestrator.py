from __future__ import annotations

import asyncio
from pathlib import Path

from gpu_alerts.orchestrator import MonitorOrchestrator


class DummyOrchestrator(MonitorOrchestrator):
    async def _run_async(self) -> None:  # type: ignore[override]
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._status.state = "running"
        self._status.paused = False
        self._status.control_center_url = "http://127.0.0.1:8787/control-center"
        self._status.webhook_url = "http://127.0.0.1:8787/webhook/distill"
        self._startup_event.set()
        await self._stop_event.wait()


def test_orchestrator_lifecycle(tmp_path: Path) -> None:
    config = tmp_path / "monitor.yaml"
    config.write_text("sources: []\n", encoding="utf-8")
    orchestrator = DummyOrchestrator(config_path=config)
    orchestrator.start()
    status = orchestrator.status()
    assert status["state"] == "running"
    assert status["thread_alive"] is True

    orchestrator.pause()
    paused = orchestrator.status()
    assert paused["paused"] is True

    orchestrator.resume()
    resumed = orchestrator.status()
    assert resumed["paused"] is False

    orchestrator.stop()
    stopped = orchestrator.status()
    assert stopped["state"] == "stopped"
