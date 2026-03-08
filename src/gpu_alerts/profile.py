from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class UserProfile:
    display_name: str = "Alertivo User"
    onboarding_completed: bool = False
    simple_mode: bool = True
    autostart_enabled: bool = False
    close_to_tray: bool = False
    intro_enabled: bool = True
    preferred_source: str = ""
    created_at: str = ""
    updated_at: str = ""

    def ensure_timestamps(self) -> None:
        now = _utc_now_iso()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UserProfile":
        profile = cls(
            display_name=str(payload.get("display_name") or "Alertivo User"),
            onboarding_completed=bool(payload.get("onboarding_completed", False)),
            simple_mode=bool(payload.get("simple_mode", True)),
            autostart_enabled=bool(payload.get("autostart_enabled", False)),
            close_to_tray=bool(payload.get("close_to_tray", False)),
            intro_enabled=bool(payload.get("intro_enabled", True)),
            preferred_source=str(payload.get("preferred_source") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )
        profile.ensure_timestamps()
        return profile

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_user_profile(path: str | Path) -> UserProfile:
    profile_path = Path(path)
    if not profile_path.exists():
        profile = UserProfile()
        profile.ensure_timestamps()
        return profile
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    return UserProfile.from_dict(payload)


def save_user_profile(path: str | Path, profile: UserProfile) -> None:
    profile_path = Path(path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile.ensure_timestamps()
    profile_path.write_text(json.dumps(profile.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")
