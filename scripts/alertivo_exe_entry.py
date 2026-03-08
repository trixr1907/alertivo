from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from gpu_alerts.config import load_config
from gpu_alerts.desktop_app import run_desktop_app
from gpu_alerts.main import run


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    candidate = (base_dir / path).resolve()
    if candidate.exists():
        return candidate
    return (Path.cwd() / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Alertivo Windows desktop launcher.")
    parser.add_argument("--config", default="system.json", help="Path to system.json.")
    parser.add_argument("--headless", action="store_true", help="Run monitor without desktop UI.")
    args = parser.parse_args()

    base_dir = _base_dir()
    config_path = _resolve_path(args.config, base_dir)
    launcher_path = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve()

    if args.headless:
        config = load_config(config_path)
        asyncio.run(run(config))
        return
    run_desktop_app(
        config_path=config_path,
        launcher_path=launcher_path,
    )


if __name__ == "__main__":
    main()
