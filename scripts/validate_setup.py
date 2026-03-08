from __future__ import annotations

import argparse
from pathlib import Path

from gpu_alerts.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local Alertivo setup.")
    parser.add_argument("--config", default="system.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    print(f"System config: {config_path}")

    if not config_path.exists():
        raise SystemExit("system.json missing.")

    config = load_config(config_path)
    print(f"Sources enabled: {len([source for source in config.sources if source.enabled])}")
    print(f"Trackers: {len(config.trackers)}")
    print(f"Webhook enabled: {config.webhook.enabled}")
    print(f"Database path: {config.database_path}")
    print(f"Settings path: {config.settings_path}")
    print(f"Trackers dir: {config.trackers_dir}")
    print(f"Telegram configured: {'yes' if config.telegram else 'no'}")
    print(f"Discord configured: {'yes' if config.discord else 'no'}")
    print(f"Distill token configured: {'yes' if config.webhook.token else 'no'}")
    print("Validation OK")


if __name__ == "__main__":
    main()
