from __future__ import annotations

import json
from pathlib import Path

from gpu_alerts.migration import ensure_monitor_config_state, rollback_monitor_config


def test_migration_creates_backup_and_state(tmp_path: Path) -> None:
    monitor = tmp_path / "monitor.yaml"
    monitor.write_text("webhook:\n  enabled: true\n", encoding="utf-8")
    state_path = tmp_path / "monitor-config.json"

    state = ensure_monitor_config_state(state_path=state_path, monitor_config_path=monitor)
    assert state.migrated is True
    assert state.backup_path is not None
    assert Path(state.backup_path).exists()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["monitor_config_path"].endswith("monitor.yaml")


def test_migration_is_idempotent(tmp_path: Path) -> None:
    monitor = tmp_path / "monitor.yaml"
    monitor.write_text("webhook:\n  enabled: false\n", encoding="utf-8")
    state_path = tmp_path / "monitor-config.json"

    first = ensure_monitor_config_state(state_path=state_path, monitor_config_path=monitor)
    second = ensure_monitor_config_state(state_path=state_path, monitor_config_path=monitor)
    assert first.backup_path == second.backup_path


def test_rollback_restores_backup(tmp_path: Path) -> None:
    monitor = tmp_path / "monitor.yaml"
    monitor.write_text("webhook:\n  enabled: true\n", encoding="utf-8")
    state_path = tmp_path / "monitor-config.json"
    state = ensure_monitor_config_state(state_path=state_path, monitor_config_path=monitor)

    monitor.write_text("webhook:\n  enabled: false\n", encoding="utf-8")
    assert rollback_monitor_config(state_path) is True
    restored = monitor.read_text(encoding="utf-8")
    backup = Path(state.backup_path).read_text(encoding="utf-8") if state.backup_path else ""
    assert restored == backup
