from __future__ import annotations

import os
from pathlib import Path


def startup_bat_path(app_name: str = "Alertivo") -> Path:
    startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup_dir / f"{app_name}.bat"


def is_autostart_enabled(app_name: str = "Alertivo") -> bool:
    if os.name != "nt":
        return False
    return startup_bat_path(app_name).exists()


def set_autostart(enabled: bool, launcher_path: str | Path, app_name: str = "Alertivo") -> bool:
    if os.name != "nt":
        return False
    target = startup_bat_path(app_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        if target.exists():
            target.unlink()
        return False

    launcher = Path(launcher_path).resolve()
    lines = [
        "@echo off",
        f"start \"\" \"{launcher}\"",
        "exit /b 0",
    ]
    target.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
    return True
