from __future__ import annotations

import json
from pathlib import Path

from gpu_alerts.config import build_distill_targets, load_config
from tests.helpers import write_system_json


def test_first_run_creates_appdata_structure_without_legacy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    install_dir = tmp_path / "install"
    system_path = write_system_json(install_dir / "system.json")

    config = load_config(system_path)

    assert config.settings_path.exists()
    assert config.trackers_dir.exists()
    assert config.logs_dir.exists()
    assert config.database_path.parent.exists()
    assert config.migration_state_path.parent.exists()
    assert config.trackers == []
    assert config.sources == []


def test_legacy_import_creates_settings_and_trackers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    install_dir = tmp_path / "install"
    system_path = write_system_json(install_dir / "system.json")
    legacy_dir = install_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "monitor.yaml").write_text(
        """
windows:
  enabled: true
sound:
  enabled: false
webhook:
  enabled: true
sources:
  - name: amazon_ps5_pro
    type: http
    enabled: true
    url: https://www.amazon.de/s?k=ps5+pro
    interval_seconds: 15
    timeout_seconds: 20
    shop: amazon
    source: shop
    scope: shop_search
    product_hint: ps5-pro
    exclude_title_terms:
      - bundle
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (legacy_dir / "alerts.env.ps1").write_text(
        "$env:DISCORD_WEBHOOK_URL = \"https://discord.com/api/webhooks/demo\"\n$env:WEBHOOK_TOKEN = \"secret-token\"\n",
        encoding="utf-8",
    )
    (legacy_dir / "user-profile.json").write_text(
        json.dumps(
            {
                "display_name": "Legacy User",
                "onboarding_completed": True,
                "simple_mode": False,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    config = load_config(system_path)

    assert config.settings.user.display_name == "Legacy User"
    assert config.settings.notifications.discord.webhook_url == "https://discord.com/api/webhooks/demo"
    assert config.webhook.token == "secret-token"
    assert len(config.trackers) == 1
    tracker = config.trackers[0]
    assert tracker.id == "ps5-pro"
    assert tracker.filters.exclude_terms == ["bundle"]
    assert tracker.shops[0].shop_id == "amazon-search"
    assert config.migration_state_path.exists()


def test_source_checkout_skips_repo_legacy_import_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    install_dir = tmp_path / "install"
    (install_dir / ".git").mkdir(parents=True, exist_ok=True)
    system_path = write_system_json(install_dir / "system.json")
    legacy_dir = install_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "monitor.yaml").write_text(
        """
sources:
  - name: amazon_ps5_pro
    type: http
    enabled: true
    url: https://www.amazon.de/s?k=ps5+pro
    interval_seconds: 15
    timeout_seconds: 20
    shop: amazon
    source: shop
    scope: shop_search
    product_hint: ps5-pro
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (legacy_dir / "alerts.env.ps1").write_text(
        "$env:DISCORD_WEBHOOK_URL = \"https://discord.com/api/webhooks/demo\"\n",
        encoding="utf-8",
    )

    config = load_config(system_path)

    assert config.trackers == []
    assert config.sources == []
    assert config.settings.notifications.discord.webhook_url == ""
    assert not config.migration_state_path.exists()


def test_source_checkout_can_force_legacy_import(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("ALERTIVO_IMPORT_LEGACY_FROM_REPO", "1")
    install_dir = tmp_path / "install"
    (install_dir / ".git").mkdir(parents=True, exist_ok=True)
    system_path = write_system_json(install_dir / "system.json")
    legacy_dir = install_dir / "config"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "monitor.yaml").write_text(
        """
webhook:
  enabled: true
sources:
  - name: amazon_ps5_pro
    type: http
    enabled: true
    url: https://www.amazon.de/s?k=ps5+pro
    interval_seconds: 15
    timeout_seconds: 20
    shop: amazon
    source: shop
    scope: shop_search
    product_hint: ps5-pro
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (legacy_dir / "alerts.env.ps1").write_text(
        "$env:WEBHOOK_TOKEN = \"secret-token\"\n",
        encoding="utf-8",
    )

    config = load_config(system_path)

    assert len(config.trackers) == 1
    assert config.webhook.token == "secret-token"
    assert config.migration_state_path.exists()


def test_tracker_sources_and_distill_targets_are_built_from_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    install_dir = tmp_path / "install"
    system_path = write_system_json(install_dir / "system.json")
    appdata_dir = Path(tmp_path / "appdata" / "Alertivo")
    trackers_dir = appdata_dir / "trackers"
    trackers_dir.mkdir(parents=True, exist_ok=True)
    tracker_path = trackers_dir / "ps5-pro.json"
    tracker_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "ps5-pro",
                "name": "PS5 Pro",
                "enabled": True,
                "query": "PS5 Pro",
                "filters": {
                    "include_terms": ["ps5", "pro"],
                    "exclude_terms": ["bundle", "digital"],
                    "price_ceiling": 799,
                    "new_listing_price_below": None,
                },
                "shops": [
                    {
                        "shop_id": "amazon",
                        "enabled": True,
                        "mode": "distill",
                        "url": "https://www.amazon.de/s?k=ps5+pro",
                    },
                    {
                        "shop_id": "mediamarkt",
                        "enabled": True,
                        "mode": "auto",
                        "url": "https://www.mediamarkt.de/de/search.html?query=ps5%20pro",
                    },
                ],
                "meta": {
                    "created_at": "",
                    "updated_at": "",
                },
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(system_path)
    sources_by_shop = {source.shop: source for source in config.sources}
    targets = build_distill_targets(config)

    assert len(config.trackers) == 1
    assert len(config.sources) == 2
    assert sources_by_shop["amazon"].type == "distill"
    assert sources_by_shop["mediamarkt"].type == "distill"
    assert sources_by_shop["amazon"].include_title_terms == ["ps5", "pro"]
    assert str(sources_by_shop["amazon"].price_ceiling) == "799"
    assert targets[0]["tracker_id"] == "ps5-pro"
    assert '"product_hint": "ps5-pro"' in targets[0]["snippet"]


def test_first_run_json_with_utf8_bom_is_loaded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    install_dir = tmp_path / "install"
    system_path = write_system_json(install_dir / "system.json")
    appdata_dir = Path(tmp_path / "appdata" / "Alertivo")
    appdata_dir.mkdir(parents=True, exist_ok=True)
    settings_path = appdata_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "user": {
                    "display_name": "BOM User",
                    "onboarding_completed": True,
                },
                "ui": {
                    "simple_mode": True,
                    "close_to_tray": False,
                    "intro_enabled": True,
                },
                "desktop": {
                    "autostart_enabled": False,
                },
                "notifications": {
                    "telegram": {
                        "enabled": False,
                        "bot_token": "",
                        "chat_id": "",
                    },
                    "discord": {
                        "enabled": False,
                        "webhook_url": "",
                    },
                    "windows": {
                        "enabled": True,
                        "app_id": "Alertivo",
                    },
                    "sound": {
                        "enabled": True,
                        "sound_file": None,
                    },
                },
                "integrations": {
                    "distill": {
                        "enabled": False,
                        "token": "",
                    },
                },
                "meta": {
                    "created_at": "",
                    "updated_at": "",
                },
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8-sig",
    )

    config = load_config(system_path)

    assert config.settings.user.display_name == "BOM User"
    assert config.settings.user.onboarding_completed is True
