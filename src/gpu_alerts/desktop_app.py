from __future__ import annotations

import logging
import os
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from gpu_alerts.migration import ensure_monitor_config_state
from gpu_alerts.orchestrator import MonitorOrchestrator
from gpu_alerts.profile import load_user_profile, save_user_profile
from gpu_alerts.tray_state import TrayState


LOGGER = logging.getLogger(__name__)

try:
    import webview
except Exception:  # pragma: no cover - optional desktop dependency
    webview = None

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - optional desktop dependency
    pystray = None
    Image = None
    ImageDraw = None


class DesktopController:
    def __init__(
        self,
        orchestrator: MonitorOrchestrator,
        *,
        app_name: str = "Alertivo",
        profile_path: Path | None = None,
    ):
        self._orchestrator = orchestrator
        self._app_name = app_name
        self._profile_path = profile_path
        self._tray_state = TrayState()
        self._tray_icon = None
        self._window = None
        self._tray_thread: threading.Thread | None = None

    def run(self) -> None:
        self._orchestrator.start()
        control_center_url = self._orchestrator.control_center_url or "http://127.0.0.1:8787/control-center"
        if webview is None:
            LOGGER.warning("pywebview not available, opening browser fallback: %s", control_center_url)
            webbrowser.open(control_center_url, new=2)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            return
        self._start_tray()
        self._window = webview.create_window(
            title=f"{self._app_name} Control Center",
            url=control_center_url,
            min_size=(1120, 760),
            confirm_close=False,
        )

        def _on_closing() -> bool:
            if self._tray_state.exiting:
                return True
            if not self._close_to_tray_enabled():
                return True
            self._tray_state.minimize_to_tray()
            try:
                self._window.hide()
            except Exception:
                LOGGER.exception("Could not hide window")
            return False

        self._window.events.closing += _on_closing
        webview.start(debug=False)
        self._stop_tray()

    def open_window(self) -> None:
        self._tray_state.open_window()
        if self._window is None:
            return
        try:
            self._window.show()
            self._window.restore()
        except Exception:
            LOGGER.exception("Could not open window")

    def pause_resume(self) -> None:
        action = self._tray_state.toggle_pause_resume()
        if action == "paused":
            self._orchestrator.pause()
        else:
            self._orchestrator.resume()

    def restart(self) -> None:
        self._orchestrator.restart()

    def exit(self) -> None:
        self._tray_state.mark_exit()
        self._orchestrator.stop()
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                LOGGER.exception("Could not destroy window")
        self._stop_tray()

    def _start_tray(self) -> None:
        if os.name != "nt" or pystray is None or Image is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda icon, item: self.open_window()),
            pystray.MenuItem("Pause/Resume Monitoring", lambda icon, item: self.pause_resume()),
            pystray.MenuItem("Restart Monitoring", lambda icon, item: self.restart()),
            pystray.MenuItem("Exit", lambda icon, item: self.exit()),
        )
        self._tray_icon = pystray.Icon("alertivo", icon=self._build_tray_icon(), title=self._app_name, menu=menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True, name="alertivo-tray")
        self._tray_thread.start()

    def _close_to_tray_enabled(self) -> bool:
        if not self._profile_path:
            return False
        try:
            profile = load_user_profile(self._profile_path)
            return bool(profile.close_to_tray)
        except Exception:
            LOGGER.exception("Could not read profile for close-to-tray state")
            return False

    def _stop_tray(self) -> None:
        if self._tray_icon is None:
            return
        try:
            self._tray_icon.stop()
        except Exception:
            LOGGER.exception("Could not stop tray icon")
        self._tray_icon = None
        if self._tray_thread and self._tray_thread.is_alive():
            self._tray_thread.join(timeout=2)
        self._tray_thread = None

    @staticmethod
    def _build_tray_icon() -> Any:
        assert Image is not None
        assert ImageDraw is not None
        img = Image.new("RGBA", (64, 64), (7, 14, 24, 255))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((6, 6, 58, 58), radius=14, outline=(92, 176, 255, 255), width=3)
        draw.polygon([(16, 45), (28, 18), (42, 33), (48, 19), (50, 49)], fill=(73, 210, 255, 255))
        return img


def run_desktop_app(
    *,
    config_path: str | Path,
    env_path: str | Path,
    profile_path: str | Path,
    migration_state_path: str | Path,
    launcher_path: str | Path | None = None,
) -> None:
    profile = load_user_profile(profile_path)
    if not profile.created_at:
        save_user_profile(profile_path, profile)
    ensure_monitor_config_state(state_path=migration_state_path, monitor_config_path=config_path)

    orchestrator = MonitorOrchestrator(
        config_path=config_path,
        env_path=env_path,
        profile_path=profile_path,
        migration_state_path=migration_state_path,
        autostart_launcher=Path(launcher_path).resolve() if launcher_path else None,
    )
    controller = DesktopController(orchestrator, profile_path=Path(profile_path))
    try:
        controller.run()
    finally:
        orchestrator.stop()
