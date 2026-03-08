from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrayState:
    monitoring_paused: bool = False
    window_visible: bool = True
    exiting: bool = False

    def minimize_to_tray(self) -> str:
        self.window_visible = False
        return "minimized"

    def open_window(self) -> str:
        self.window_visible = True
        return "opened"

    def toggle_pause_resume(self) -> str:
        self.monitoring_paused = not self.monitoring_paused
        return "paused" if self.monitoring_paused else "resumed"

    def mark_exit(self) -> str:
        self.exiting = True
        self.window_visible = False
        return "exit"
