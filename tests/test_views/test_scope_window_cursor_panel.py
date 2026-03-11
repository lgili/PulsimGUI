"""Tests for cursor-driven bottom panel behavior in ScopeWindow."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.scope_window import ScopeWindow


def _sample_result(signal_count: int = 2, sample_count: int = 40) -> SimulationResult:
    time = [idx * 1e-6 for idx in range(sample_count)]
    signals = {
        f"S{sig_idx + 1}": [(sig_idx + 1) * 0.2 + (idx * 0.01) for idx in range(sample_count)]
        for sig_idx in range(signal_count)
    }
    return SimulationResult(time=time, signals=signals, statistics={})


def _prepare_window(window: ScopeWindow) -> None:
    result = _sample_result(signal_count=3)
    window._current_result = result
    window._refresh_stacked_sidebar(result)
    window._rebuild_stacked_plots(result)


def test_scope_bottom_panel_is_cursor_driven(qapp) -> None:
    window = ScopeWindow("scope-cursor-panel-1", "Cursor Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        assert window._scope_bottom_tab.isHidden()

        window._stacked_cursor_toggle.setChecked(True)
        assert not window._scope_bottom_tab.isHidden()

        window._stacked_cursor_toggle.setChecked(False)
        assert window._scope_bottom_tab.isHidden()
    finally:
        window.close()


def test_scope_measurement_columns_can_be_toggled(qapp) -> None:
    window = ScopeWindow("scope-cursor-panel-2", "Cursor Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._stacked_cursor_toggle.setChecked(True)

        assert "rms" in window._stacked_measurements.visible_measurement_keys()
        window._on_measurement_key_toggled("rms", False)
        assert "rms" not in window._stacked_measurements.visible_measurement_keys()

        # Prevent empty selection.
        only_key = window._stacked_measurements.visible_measurement_keys()[0]
        for key in window._stacked_measurements.visible_measurement_keys()[1:]:
            window._on_measurement_key_toggled(key, False)
        window._on_measurement_key_toggled(only_key, False)
        assert window._stacked_measurements.visible_measurement_keys() == [only_key]
    finally:
        window.close()


def test_ctrl_b_shortcut_toggles_left_panel(qapp) -> None:
    window = ScopeWindow("scope-cursor-panel-3", "Cursor Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._left_panel_visible is True
        window._toggle_sidebar_shortcut.activated.emit()
        assert window._left_panel_visible is False
        window._toggle_sidebar_shortcut.activated.emit()
        assert window._left_panel_visible is True
    finally:
        window.close()
