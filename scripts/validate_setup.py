from __future__ import annotations

import argparse
import os
from pathlib import Path

from gpu_alerts.config import load_config


PLACEHOLDER_MARKERS = ("replace-me", "123456789:replace-me")


def is_real(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return lowered != "" and not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local GPU alert setup.")
    parser.add_argument("--config", default="config/monitor.yaml")
    parser.add_argument("--env", default="config/alerts.env.ps1")
    args = parser.parse_args()

    config_path = Path(args.config)
    env_path = Path(args.env)

    print(f"Config: {config_path}")
    print(f"Env: {env_path}")

    if not config_path.exists():
        raise SystemExit("Config file missing.")
    if not env_path.exists():
        raise SystemExit("Env file missing.")

    config = load_config(config_path)
    print(f"Sources enabled: {len(config.sources)}")
    print(f"Webhook enabled: {config.webhook.enabled}")
    print(f"Database path: {config.database_path}")

    telegram_ok = is_real(os.environ.get("TELEGRAM_BOT_TOKEN")) and is_real(os.environ.get("TELEGRAM_CHAT_ID"))
    discord_ok = is_real(os.environ.get("DISCORD_WEBHOOK_URL"))
    webhook_ok = is_real(os.environ.get("WEBHOOK_TOKEN"))

    print(f"Telegram configured: {'yes' if telegram_ok else 'no'}")
    print(f"Discord configured: {'yes' if discord_ok else 'no'}")
    print(f"Webhook token configured: {'yes' if webhook_ok else 'no'}")

    if not webhook_ok:
        raise SystemExit("WEBHOOK_TOKEN is missing or still placeholder.")

    direct_sources = [source.name for source in config.sources if source.enabled]
    print("Active sources:")
    for source in direct_sources:
        print(f" - {source}")

    print("Validation OK")
