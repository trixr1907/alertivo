from __future__ import annotations

import json
from pathlib import Path


def write_system_json(path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "app": {"name": "Alertivo"},
        "control_center": {"host": "127.0.0.1", "port": 8787},
        "webhook": {"path": "/webhook/distill"},
        "logging": {"level": "INFO"},
        "monitoring": {
            "enable_restock_alerts": True,
            "new_listing_reference_min_age_seconds": 60,
            "default_timeout_seconds": 20,
            "default_interval_seconds": 60,
            "user_agent": "Alertivo/1.0",
        },
        "storage": {
            "appdata_subdir": "Alertivo",
            "database_filename": "alerts.sqlite",
            "logs_dirname": "logs",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path
