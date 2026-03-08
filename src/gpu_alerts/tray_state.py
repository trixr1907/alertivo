from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrayState:
    monitoring_active: bool = True
    window_visible: bool = True
    exiting: bool = False

    def minimize_to_tray(self) -> str:
        self.window_visible = False
        return "minimized"

    def open_window(self) -> str:
        self.window_visible = True
        return "opened"

    def stop_monitoring(self) -> str:
        self.monitoring_active = False
        return "stopped"

    def start_monitoring(self) -> str:
        self.monitoring_active = True
        return "started"

    def mark_exit(self) -> str:
        self.exiting = True
        self.window_visible = False
        return "exit"
