"""Tests for grouping multiple signals onto the same scope plot."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QToolButton

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
        assert len(window._plot_widgets) == 1

        window._split_all_plot_groups()
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
        window._split_all_plot_groups()
        window._set_signal_plot_group("S2", "S1")
        window._set_signal_plot_group("S3", "S1")
        assert len(window._plot_widgets) == 2

        window._split_all_plot_groups()
        assert len(window._plot_widgets) == 4
        for signal_name in ("S1", "S2", "S3", "S4"):
            assert window._plot_group_leader(signal_name) == signal_name
    finally:
        window.close()


def test_scope_drag_mapping_can_overlay_hidden_signal_into_target_plot(qapp) -> None:
    """Dropping a hidden signal onto a plot target should show and overlay it."""
    window = ScopeWindow("scope-group-drop-overlay", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._split_all_plot_groups()

        window._stacked_signal_list.set_signal_visible("S2", False)
        window._on_stacked_signal_visibility_changed("S2", False)
        assert "S2" not in window._stacked_signal_list.get_visible_signals()
        assert len(window._plot_widgets) == 2

        applied = window._apply_dragged_signal_mapping("S2", target_group_leader="S1")
        assert applied is True
        assert "S2" in window._stacked_signal_list.get_visible_signals()
        assert window._plot_group_leader("S2") == "S1"
        assert len(window._plot_widgets) == 2
    finally:
        window.close()


def test_scope_drag_mapping_can_place_signal_in_dedicated_pane(qapp) -> None:
    """Dropping on workspace area should move signal to a dedicated pane."""
    window = ScopeWindow("scope-group-drop-pane", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)
        assert len(window._plot_widgets) == 1

        applied = window._apply_dragged_signal_mapping("S2", target_group_leader=None)
        assert applied is True
        assert window._plot_group_leader("S2") == "S2"
        assert len(window._plot_widgets) == 2
    finally:
        window.close()


def test_scope_drag_drop_handler_selects_signal_and_creates_dedicated_pane(qapp) -> None:
    """Workspace drop handler should move the signal and synchronize active selection."""
    window = ScopeWindow("scope-group-drop-handler", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)

        applied = window._handle_signal_drop_request("S2", None)

        assert applied is True
        assert window._stacked_active_signal == "S2"
        assert window._plot_group_leader("S2") == "S2"
        assert len(window._plot_widgets) == 2
    finally:
        window.close()


def test_scope_can_render_right_axis_for_overlay_group(qapp) -> None:
    """Assigning a trace to the right axis should create a real secondary viewbox."""
    window = ScopeWindow("scope-group-right-axis", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)

        window._set_signal_axis_target("S2", "right")

        assert len(window._plot_widgets) == 1
        assert len(window._plot_right_view_boxes) == 1
        assert window._plot_widgets[0].getPlotItem().getAxis("right").isVisible()
    finally:
        window.close()


def test_scope_ui_state_roundtrip_restores_plot_groups(qapp) -> None:
    """Captured UI state should restore per-signal plot-group mapping."""
    source = ScopeWindow("scope-group-state-source", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    target = ScopeWindow("scope-group-state-target", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        source._current_result = result
        source._refresh_stacked_sidebar(result)
        source._split_all_plot_groups()
        source._set_signal_plot_group("S2", "S1")
        source._set_signal_plot_group("S3", "S3")
        state = source.capture_ui_state()

        target._current_result = result
        target._refresh_stacked_sidebar(result)
        target._rebuild_stacked_plots(result)
        target.apply_ui_state(state)

        assert target._plot_group_leader("S2") == "S1"
        assert target._plot_group_leader("S3") == "S3"
    finally:
        source.close()
        target.close()


def test_scope_exposes_copy_button_per_plot(qapp) -> None:
    """Each stacked plot should have one copy button in its corner."""
    window = ScopeWindow("scope-group-copy-1", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._split_all_plot_groups()

        copy_buttons = window.findChildren(QToolButton, "scopePlotCopyBtn")
        assert len(copy_buttons) == len(window._plot_widgets) == 3
    finally:
        window.close()


def test_scope_copy_plot_to_clipboard_writes_pixmap(monkeypatch, qapp) -> None:
    """Copy action should store a non-null pixmap in clipboard."""
    window = ScopeWindow("scope-group-copy-2", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        copied: dict[str, QPixmap] = {}

        class _FakeClipboard:
            def setPixmap(self, pixmap: QPixmap) -> None:
                copied["pixmap"] = pixmap

        class _FakePlot:
            @staticmethod
            def grab() -> QPixmap:
                pixmap = QPixmap(32, 20)
                pixmap.fill(Qt.GlobalColor.white)
                return pixmap

        monkeypatch.setattr(
            "pulsimgui.views.scope.scope_window.QGuiApplication.clipboard",
            lambda: _FakeClipboard(),
        )

        window._copy_plot_to_clipboard(_FakePlot())

        assert "pixmap" in copied
        assert not copied["pixmap"].isNull()
        assert window._message_label.text() == "Plot image copied to clipboard."
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
