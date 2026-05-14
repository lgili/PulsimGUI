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


def _mixed_scale_result(sample_count: int = 128) -> SimulationResult:
    time = [idx * 1e-5 for idx in range(sample_count)]
    signals = {
        "Vsw": [12.0 if (idx % 2 == 0) else 0.0 for idx in range(sample_count)],
        "Vout": [1.2 + 0.6 * (idx / sample_count) for idx in range(sample_count)],
        "IL": [0.4 + 0.15 * ((idx % 10) / 10.0) for idx in range(sample_count)],
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


def test_scope_auto_separates_mixed_scale_or_unit_traces(qapp) -> None:
    """Default composition should avoid overlaying traces that are hard to read together."""
    window = ScopeWindow("scope-group-auto-separate", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _mixed_scale_result()
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)

        leaders = {name: window._plot_group_leader(name) for name in result.signals}
        assert leaders["IL"] == "IL"
        assert len(set(leaders.values())) >= 2
    finally:
        window.close()


def test_manual_plot_group_override_survives_refresh_after_auto_composition(qapp) -> None:
    """User plot reassignment should not be undone by later sidebar refreshes."""
    window = ScopeWindow("scope-group-manual-preserve", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _mixed_scale_result()
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._set_signal_plot_group("Vout", "Vsw")

        window._refresh_stacked_sidebar(result)

        assert window._plot_group_leader("Vout") == "Vsw"
        assert window._plot_composition_overridden is True
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


def test_scope_plot_context_menu_exposes_analysis_actions(qapp) -> None:
    """Plot context menu should expose scope-aware navigation and analysis actions."""
    window = ScopeWindow("scope-group-menu-1", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)

        menu = window._build_plot_context_menu("S1")
        action_texts = [action.text() for action in menu.actions() if action.text()]

        assert "Fit All" in action_texts
        assert "Reset Zoom" in action_texts
        assert "Hide Grid" in action_texts
        assert "Add Cursors" in action_texts
        assert "Show Measurements" in action_texts
        assert "Copy Plot Image" in action_texts
        assert "Split Plot" in action_texts
    finally:
        window.close()


def test_scope_plot_context_menu_actions_update_scope_state(qapp) -> None:
    """Context-menu actions should mutate grid, cursors, drawer, and grouping deterministically."""
    window = ScopeWindow("scope-group-menu-2", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)

        window._apply_plot_context_action("S1", "toggle_grid")
        assert window._stacked_grid_enabled is False

        window._apply_plot_context_action("S1", "toggle_cursors")
        assert window._stacked_cursors_enabled is True

        window._apply_plot_context_action("S1", "show_measurements")
        assert window._bottom_drawer_expanded is True
        assert window._scope_bottom_tabs.currentIndex() == 0

        window._apply_plot_context_action("S1", "split_plot")
        assert window._plot_group_leader("S2") == "S2"
        assert window._plot_group_leader("S3") == "S3"
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


def test_plot_group_selection_updates_active_context_without_rebuild(monkeypatch, qapp) -> None:
    """Switching the active plot group should not rebuild all plots when structure is unchanged."""
    window = ScopeWindow("scope-group-perf-1", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._split_all_plot_groups()
        rebuilds: list[bool] = []
        monkeypatch.setattr(window, "_rebuild_stacked_plots", lambda *_args, **_kwargs: rebuilds.append(True))

        window._on_group_plot_selected("S2")

        assert window._stacked_active_signal == "S2"
        assert window._selected_plot_group_leader == "S2"
        assert rebuilds == []
    finally:
        window.close()


def test_signal_alias_updates_plot_header_without_rebuild(monkeypatch, qapp) -> None:
    """Alias edits should refresh visible plot chrome without forcing a full plot rebuild."""
    window = ScopeWindow("scope-group-perf-2", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=2)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)
        rebuilds: list[bool] = []
        monkeypatch.setattr(window, "_rebuild_stacked_plots", lambda *_args, **_kwargs: rebuilds.append(True))

        window._set_signal_alias("S1", "Alias S1")

        title_label = window._plot_header_refs["S1"]["title_label"]
        assert title_label.text() == "Alias S1"
        assert rebuilds == []
    finally:
        window.close()


def test_trace_width_refreshes_existing_plot_item_without_rebuild(monkeypatch, qapp) -> None:
    """Trace-width edits should restyle the current PlotDataItem in place."""
    window = ScopeWindow("scope-group-perf-3", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=2)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)
        trace = window._plot_trace_items_by_signal["S1"]
        before_width = trace.opts["pen"].widthF()
        rebuilds: list[bool] = []
        monkeypatch.setattr(window, "_rebuild_stacked_plots", lambda *_args, **_kwargs: rebuilds.append(True))

        window._set_trace_width_for_signal("S1", 4.0)

        assert window._plot_trace_items_by_signal["S1"].opts["pen"].widthF() > before_width
        assert rebuilds == []
    finally:
        window.close()


def test_decimated_trace_cache_reuses_signal_projection(qapp) -> None:
    """Repeated decimation requests for the same signal and point budget should reuse the cached projection."""
    window = ScopeWindow("scope-group-perf-4", "Group Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=2, sample_count=256)
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        before_cache_size = len(window._stacked_decimation_cache)

        first = window._decimated_trace_for_signal("S1", window._stacked_signals["S1"], max_points=32)
        second = window._decimated_trace_for_signal("S1", window._stacked_signals["S1"], max_points=32)

        assert first[0] is second[0]
        assert first[1] is second[1]
        assert len(window._stacked_decimation_cache) == before_cache_size + 1
    finally:
        window.close()
