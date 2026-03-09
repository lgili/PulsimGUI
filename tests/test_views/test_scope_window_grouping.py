"""Tests for grouping multiple signals onto the same scope plot."""

from __future__ import annotations

from PySide6.QtCore import Qt

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.scope_window import ScopeWindow


def _sample_result(signal_count: int = 3, sample_count: int = 24) -> SimulationResult:
    time = [idx * 1e-6 for idx in range(sample_count)]
    signals = {
        f"S{sig_idx + 1}": [(sig_idx + 1) * 0.1 + (idx * 0.01) for idx in range(sample_count)]
        for sig_idx in range(signal_count)
    }
    return SimulationResult(time=time, signals=signals, statistics={})


def test_scope_can_overlay_signals_on_same_plot(qapp) -> None:
    """Assigning a signal to another signal's group should reduce plot count."""
    window = ScopeWindow("scope-group-1", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)
        assert len(window._plot_widgets) == 3

        window._set_signal_plot_group("S2", "S1")
        assert len(window._plot_widgets) == 2
        assert window._plot_group_leader("S2") == "S1"
    finally:
        window.close()


def test_scope_split_all_groups_restores_dedicated_plots(qapp) -> None:
    """Split-all should return each signal to its own plot."""
    window = ScopeWindow("scope-group-2", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=4)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._set_signal_plot_group("S2", "S1")
        window._set_signal_plot_group("S3", "S1")
        assert len(window._plot_widgets) == 2

        window._split_all_plot_groups()
        assert len(window._plot_widgets) == 4
        for signal_name in ("S1", "S2", "S3", "S4"):
            assert window._plot_group_leader(signal_name) == signal_name
    finally:
        window.close()


def test_scope_hover_tooltip_includes_all_overlay_curves(qapp) -> None:
    """Hover tooltip text should include values for every overlaid signal."""
    window = ScopeWindow("scope-group-3", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        html = window._build_hover_tooltip_html(
            1.2e-6,
            [
                ("S1", 1.23, (255, 0, 0)),
                ("S2", 2.34, (0, 255, 0)),
            ],
            primary_signal_name="S1",
        )
        assert "S1" in html
        assert "S2" in html
        assert "1.23" in html
        assert "2.34" in html
    finally:
        window.close()


def test_scope_wheel_zoom_mask_uses_expected_axes() -> None:
    """Wheel modifiers should map to axis-specific zoom behavior."""
    assert ScopeWindow._wheel_zoom_mask(Qt.KeyboardModifier.NoModifier) == (False, True)
    assert ScopeWindow._wheel_zoom_mask(Qt.KeyboardModifier.ShiftModifier) == (True, False)
    assert ScopeWindow._wheel_zoom_mask(Qt.KeyboardModifier.ControlModifier) == (True, True)
