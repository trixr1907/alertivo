from __future__ import annotations

from pathlib import Path, PosixPath

import gpu_alerts.autostart as autostart


def test_set_autostart_writes_startup_bat_on_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(autostart.os, "name", "nt", raising=False)
    monkeypatch.setattr(autostart, "Path", PosixPath)
    launcher = tmp_path / "bundle" / "Alertivo.exe"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("demo", encoding="utf-8")
    startup_bat = tmp_path / "Startup" / "Alertivo.bat"
    monkeypatch.setattr(autostart, "startup_bat_path", lambda app_name="Alertivo": startup_bat)

    assert autostart.set_autostart(True, launcher, app_name="Alertivo") is True

    assert startup_bat.exists()
    content = startup_bat.read_text(encoding="ascii")
    assert "start \"\"" in content
    assert str(launcher.resolve()) in content
    assert autostart.is_autostart_enabled("Alertivo") is True


def test_disable_autostart_removes_startup_bat_on_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(autostart.os, "name", "nt", raising=False)
    monkeypatch.setattr(autostart, "Path", PosixPath)
    launcher = tmp_path / "bundle" / "Alertivo.exe"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("demo", encoding="utf-8")
    startup_bat = tmp_path / "Startup" / "Alertivo.bat"
    monkeypatch.setattr(autostart, "startup_bat_path", lambda app_name="Alertivo": startup_bat)

    autostart.set_autostart(True, launcher, app_name="Alertivo")
    assert startup_bat.exists()

    assert autostart.set_autostart(False, launcher, app_name="Alertivo") is False
    assert not startup_bat.exists()
    assert autostart.is_autostart_enabled("Alertivo") is False


def test_set_autostart_is_noop_on_non_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(autostart.os, "name", "posix", raising=False)
    monkeypatch.setattr(autostart, "Path", PosixPath)
    launcher = tmp_path / "bundle" / "Alertivo.exe"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("demo", encoding="utf-8")
    startup_bat = tmp_path / "Startup" / "Alertivo.bat"
    monkeypatch.setattr(autostart, "startup_bat_path", lambda app_name="Alertivo": startup_bat)

    assert autostart.set_autostart(True, launcher, app_name="Alertivo") is False
    assert not startup_bat.exists()
    assert autostart.is_autostart_enabled("Alertivo") is False
