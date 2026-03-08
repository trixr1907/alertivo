from __future__ import annotations

import logging
import os
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from gpu_alerts.config import load_config
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
        settings_path: Path | None = None,
    ):
        self._orchestrator = orchestrator
        self._app_name = app_name
        self._settings_path = settings_path
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

    def start_monitoring(self) -> None:
        self._tray_state.start_monitoring()
        self._orchestrator.start_monitoring()

    def stop_monitoring(self) -> None:
        self._tray_state.stop_monitoring()
        self._orchestrator.stop_monitoring()

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
            pystray.MenuItem("Start Monitoring", lambda icon, item: self.start_monitoring()),
            pystray.MenuItem("Stop Monitoring", lambda icon, item: self.stop_monitoring()),
            pystray.MenuItem("Restart Monitoring", lambda icon, item: self.restart()),
            pystray.MenuItem("Exit", lambda icon, item: self.exit()),
        )
        self._tray_icon = pystray.Icon("alertivo", icon=self._build_tray_icon(), title=self._app_name, menu=menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True, name="alertivo-tray")
        self._tray_thread.start()

    def _close_to_tray_enabled(self) -> bool:
        if not self._settings_path:
            return False
        try:
            profile = load_user_profile(self._settings_path)
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
    launcher_path: str | Path | None = None,
) -> None:
    config = load_config(config_path)
    profile = load_user_profile(config.settings_path)
    if not profile.created_at:
        save_user_profile(config.settings_path, profile)

    orchestrator = MonitorOrchestrator(
        config_path=config.config_path,
        settings_path=config.settings_path,
        migration_state_path=config.migration_state_path,
        autostart_launcher=Path(launcher_path).resolve() if launcher_path else None,
    )
    controller = DesktopController(
        orchestrator,
        app_name=config.system.app.name,
        settings_path=config.settings_path,
    )
    try:
        controller.run()
    finally:
        orchestrator.stop()
