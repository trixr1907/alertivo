from __future__ import annotations

from gpu_alerts.tray_state import TrayState


def test_tray_state_transitions() -> None:
    state = TrayState()
    assert state.window_visible is True
    assert state.monitoring_paused is False

    assert state.minimize_to_tray() == "minimized"
    assert state.window_visible is False

    assert state.open_window() == "opened"
    assert state.window_visible is True

    assert state.toggle_pause_resume() == "paused"
    assert state.monitoring_paused is True
    assert state.toggle_pause_resume() == "resumed"
    assert state.monitoring_paused is False

    assert state.mark_exit() == "exit"
    assert state.exiting is True
