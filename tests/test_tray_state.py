from __future__ import annotations

from gpu_alerts.tray_state import TrayState


def test_tray_state_transitions() -> None:
    state = TrayState()
    assert state.window_visible is True
    assert state.monitoring_active is True

    assert state.minimize_to_tray() == "minimized"
    assert state.window_visible is False

    assert state.open_window() == "opened"
    assert state.window_visible is True

    assert state.stop_monitoring() == "stopped"
    assert state.monitoring_active is False
    assert state.start_monitoring() == "started"
    assert state.monitoring_active is True

    assert state.mark_exit() == "exit"
    assert state.exiting is True
