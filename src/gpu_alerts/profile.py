from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gpu_alerts.config import SettingsConfig, load_settings_config, save_settings_config


@dataclass(slots=True)
class UserProfile:
    display_name: str = "Alertivo User"
    onboarding_completed: bool = False
    simple_mode: bool = True
    autostart_enabled: bool = False
    close_to_tray: bool = False
    intro_enabled: bool = True
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_settings(cls, settings: SettingsConfig) -> "UserProfile":
        return cls(
            display_name=settings.user.display_name,
            onboarding_completed=settings.user.onboarding_completed,
            simple_mode=settings.ui.simple_mode,
            autostart_enabled=settings.desktop.autostart_enabled,
            close_to_tray=settings.ui.close_to_tray,
            intro_enabled=settings.ui.intro_enabled,
            created_at=settings.meta.created_at,
            updated_at=settings.meta.updated_at,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UserProfile":
        return cls(
            display_name=str(payload.get("display_name") or "Alertivo User"),
            onboarding_completed=bool(payload.get("onboarding_completed", False)),
            simple_mode=bool(payload.get("simple_mode", True)),
            autostart_enabled=bool(payload.get("autostart_enabled", False)),
            close_to_tray=bool(payload.get("close_to_tray", False)),
            intro_enabled=bool(payload.get("intro_enabled", True)),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def apply_to_settings(self, settings: SettingsConfig) -> SettingsConfig:
        settings.user.display_name = self.display_name
        settings.user.onboarding_completed = self.onboarding_completed
        settings.ui.simple_mode = self.simple_mode
        settings.desktop.autostart_enabled = self.autostart_enabled
        settings.ui.close_to_tray = self.close_to_tray
        settings.ui.intro_enabled = self.intro_enabled
        if self.created_at:
            settings.meta.created_at = self.created_at
        if self.updated_at:
            settings.meta.updated_at = self.updated_at
        settings.meta.touch()
        return settings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_user_profile(path: str | Path) -> UserProfile:
    settings = load_settings_config(path)
    return UserProfile.from_settings(settings)


def save_user_profile(path: str | Path, profile: UserProfile) -> None:
    settings = load_settings_config(path)
    profile.apply_to_settings(settings)
    save_settings_config(settings)
