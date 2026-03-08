from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from gpu_alerts.config import load_config
from gpu_alerts.desktop_app import run_desktop_app
from gpu_alerts.main import run


ENV_LINE = re.compile(r"^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


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


def _parse_env_value(value: str) -> str:
    parsed = value.strip()
    if (parsed.startswith('"') and parsed.endswith('"')) or (parsed.startswith("'") and parsed.endswith("'")):
        parsed = parsed[1:-1]
    return parsed


def _load_powershell_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        os.environ[key] = _parse_env_value(raw_value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alertivo Windows desktop launcher.")
    parser.add_argument("--config", default="config/monitor.yaml", help="Path to monitor config.")
    parser.add_argument("--env", default="config/alerts.env.ps1", help="Path to PowerShell env file.")
    parser.add_argument("--profile", default="config/user-profile.json", help="Path to Alertivo user profile.")
    parser.add_argument(
        "--migration-state",
        default="config/monitor-config.json",
        help="Path to monitor migration metadata.",
    )
    parser.add_argument("--headless", action="store_true", help="Run monitor without desktop UI.")
    args = parser.parse_args()

    base_dir = _base_dir()
    config_path = _resolve_path(args.config, base_dir)
    env_path = _resolve_path(args.env, base_dir)
    profile_path = _resolve_path(args.profile, base_dir)
    migration_state_path = _resolve_path(args.migration_state, base_dir)
    launcher_path = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve()

    _load_powershell_env(env_path)
    if args.headless:
        config = load_config(config_path)
        asyncio.run(run(config))
        return
    run_desktop_app(
        config_path=config_path,
        env_path=env_path,
        profile_path=profile_path,
        migration_state_path=migration_state_path,
        launcher_path=launcher_path,
    )


if __name__ == "__main__":
    main()
