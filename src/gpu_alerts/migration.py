from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@dataclass(slots=True)
class MonitorConfigState:
    version: int
    migrated: bool
    migrated_at: str
    monitor_config_path: str
    backup_path: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MonitorConfigState":
        return cls(
            version=int(payload.get("version", 1)),
            migrated=bool(payload.get("migrated", False)),
            migrated_at=str(payload.get("migrated_at") or _utc_now_iso()),
            monitor_config_path=str(payload.get("monitor_config_path") or ""),
            backup_path=str(payload["backup_path"]) if payload.get("backup_path") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_monitor_config_state(
    *,
    state_path: str | Path,
    monitor_config_path: str | Path,
    create_backup: bool = True,
) -> MonitorConfigState:
    state_file = Path(state_path)
    if state_file.exists():
        return MonitorConfigState.from_dict(json.loads(state_file.read_text(encoding="utf-8")))

    config_file = Path(monitor_config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if config_file.exists() and create_backup:
        backup_path = config_file.with_name(f"{config_file.name}.backup-{_timestamp()}")
        shutil.copy2(config_file, backup_path)

    state = MonitorConfigState(
        version=1,
        migrated=True,
        migrated_at=_utc_now_iso(),
        monitor_config_path=str(config_file.resolve()),
        backup_path=str(backup_path.resolve()) if backup_path else None,
    )
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")
    return state


def rollback_monitor_config(state_path: str | Path) -> bool:
    state_file = Path(state_path)
    if not state_file.exists():
        return False
    state = MonitorConfigState.from_dict(json.loads(state_file.read_text(encoding="utf-8")))
    if not state.backup_path:
        return False
    backup = Path(state.backup_path)
    monitor_config = Path(state.monitor_config_path)
    if not backup.exists():
        return False
    shutil.copy2(backup, monitor_config)
    return True
