"""Headless GUI tests for the modern scope sidebar tabs and collapsed rail (task 7.2)."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.scope_window import ScopeWindow
from pulsimgui.views.waveform.waveform_viewer import SignalListPanel


def _sample_result(signal_count: int = 3, sample_count: int = 16) -> SimulationResult:
    time = [idx * 1e-6 for idx in range(sample_count)]
    signals = {
        f"S{i + 1}": [(i + 1) * 0.1 + j * 0.01 for j in range(sample_count)]
        for i in range(signal_count)
    }
    return SimulationResult(time=time, signals=signals, statistics={})


def _prepare_window(window: ScopeWindow) -> None:
    result = _sample_result(signal_count=3, sample_count=64)
    window._current_result = result
    window._refresh_stacked_sidebar(result)
    window._rebuild_stacked_plots(result)


# ── Sidebar tab structure ────────────────────────────────────────────────────

def test_sidebar_has_four_named_tabs(qapp) -> None:
    """Sidebar QTabWidget must expose Signals/Scopes/Traces/Views tabs."""
    window = ScopeWindow("mst-tabs-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        tabs = window._sidebar_tabs
        assert tabs.count() == 4
        tab_labels = [tabs.tabText(i) for i in range(tabs.count())]
        assert "Signals" in tab_labels
        assert "Scopes" in tab_labels
        assert "Traces" in tab_labels
        assert "Views" in tab_labels
    finally:
        window.close()


def test_sidebar_signals_tab_is_first(qapp) -> None:
    """Signals tab is at index 0 and selected by default."""
    window = ScopeWindow("mst-tabs-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._sidebar_tabs.tabText(0) == "Signals"
        assert window._sidebar_tabs.currentIndex() == 0
    finally:
        window.close()


def test_analysis_tabs_expose_scope_fft_compare(qapp) -> None:
    """Central workspace must expose Scope, FFT, and Compare tabs."""
    window = ScopeWindow("mst-tabs-3", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        tabs = window._analysis_tabs
        assert tabs.count() == 3
        assert [tabs.tabText(i) for i in range(tabs.count())] == ["Scope", "FFT", "Compare"]
    finally:
        window.close()


def test_top_level_scope_actions_expose_shortcuts_and_tooltips(qapp) -> None:
    """Top chrome actions should exist as QAction objects with discoverable metadata."""
    window = ScopeWindow("mst-tabs-4", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        actions = window._scope_actions
        assert {"run", "fit_view", "toggle_cursors", "toggle_measurements", "toggle_grid", "add_expression", "export_snapshot"} <= set(actions)
        assert actions["run"].shortcut().toString() == "Space"
        assert actions["fit_view"].shortcut().toString() == "F"
        assert actions["toggle_cursors"].shortcut().toString() == "C"
        assert actions["toggle_measurements"].shortcut().toString() == "M"
        assert actions["toggle_grid"].shortcut().toString() == "G"
        assert actions["add_expression"].shortcut().toString() == "Ctrl+E"
        assert "Shortcut:" in actions["export_snapshot"].toolTip()
    finally:
        window.close()


# ── Collapse / expand rail ───────────────────────────────────────────────────

def test_panel_starts_expanded(qapp) -> None:
    """Sidebar tabs and inspector start expanded; collapsed rail stays hidden."""
    window = ScopeWindow("mst-collapse-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        # isHidden() reflects the widget's own explicit show/hide state,
        # regardless of whether the top-level window has been shown.
        assert not window._sidebar_tabs.isHidden()
        assert window._collapsed_rail.isHidden()
        assert not window._stacked_right_panel.isHidden()
    finally:
        window.close()


def test_toggle_button_collapses_sidebar(qapp) -> None:
    """Clicking the toggle button once hides tabs and shows the compact rail."""
    window = ScopeWindow("mst-collapse-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        window._on_toggle_left_panel_clicked(False)

        assert window._sidebar_tabs.isHidden()
        assert not window._collapsed_rail.isHidden()
    finally:
        window.close()


def test_toggle_button_expand_restores_sidebar(qapp) -> None:
    """Expanding after collapse shows tabs again and hides the rail."""
    window = ScopeWindow("mst-collapse-3", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        window._on_toggle_left_panel_clicked(False)
        window._on_toggle_left_panel_clicked(True)

        assert not window._sidebar_tabs.isHidden()
        assert window._collapsed_rail.isHidden()
    finally:
        window.close()


def test_right_panel_toggle_hides_and_restores_inspector(qapp) -> None:
    """Inspector panel toggle should collapse and expand the right sidebar."""
    window = ScopeWindow("mst-collapse-6", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._right_panel_visible is True
        window._on_toggle_right_panel_clicked(False)
        assert window._right_panel_visible is False
        assert window._stacked_right_panel.isHidden()

        window._on_toggle_right_panel_clicked(True)
        assert window._right_panel_visible is True
        assert not window._stacked_right_panel.isHidden()
    finally:
        window.close()


def test_sidebar_shortcut_toggles_panel(qapp) -> None:
    """Keyboard shortcut handler mirrors toggle button behavior."""
    window = ScopeWindow("mst-collapse-4", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._left_panel_visible
        window._on_toggle_sidebar_shortcut()
        assert not window._left_panel_visible
        window._on_toggle_sidebar_shortcut()
        assert window._left_panel_visible
    finally:
        window.close()


def test_collapsed_rail_has_tooltips(qapp) -> None:
    """Every icon button in the collapsed rail must have a non-empty tooltip."""
    from PySide6.QtWidgets import QToolButton

    window = ScopeWindow("mst-collapse-5", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        rail_buttons = window._collapsed_rail.findChildren(QToolButton)
        assert len(rail_buttons) > 0, "Collapsed rail has no icon buttons"
        for btn in rail_buttons:
            assert btn.toolTip(), f"Rail button '{btn.text()}' has no tooltip"
    finally:
        window.close()


# ── Interval selector ────────────────────────────────────────────────────────

def test_interval_combo_has_supported_scope_options(qapp) -> None:
    """Interval combo must expose the supported professional measurement scopes."""
    from pulsimgui.scope_workbench import INTERVAL_TARGETS

    window = ScopeWindow("mst-interval-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        combo = window._interval_combo
        data_values = {combo.itemData(i) for i in range(combo.count())}
        assert data_values == set(INTERVAL_TARGETS)
        assert combo.count() == 3
    finally:
        window.close()


def test_interval_combo_default_is_full_range(qapp) -> None:
    """Default interval target should be Full Range."""
    window = ScopeWindow("mst-interval-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._interval_combo.currentData() == "full"
    finally:
        window.close()


# ── Views tab ────────────────────────────────────────────────────────────────

def test_views_tab_has_save_and_delete_buttons(qapp) -> None:
    """Views tab must contain Save view and Delete action buttons."""
    window = ScopeWindow("mst-views-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert hasattr(window, "_save_view_btn")
        assert hasattr(window, "_delete_view_btn")
        assert window._save_view_btn.text() == "Save view"
    finally:
        window.close()


def test_views_list_initially_empty(qapp) -> None:
    """Views list widget should start with zero items."""
    window = ScopeWindow("mst-views-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._views_list_widget.count() == 0
    finally:
        window.close()


# ── Zoom overview ────────────────────────────────────────────────────────────

def test_overview_plot_exists_and_is_compact(qapp) -> None:
    """Overview mini-plot must be an inset, not a full-width strip."""
    window = ScopeWindow("mst-overview-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert hasattr(window, "_overview_plot")
        assert hasattr(window, "_overview_inset")
        assert window._stacked_page_layout.indexOf(window._overview_inset) == -1
        assert window._overview_plot.width() == 148
        assert window._overview_plot.height() == 82

        _prepare_window(window)

        assert not window._overview_inset.isHidden()
        assert window._overview_inset.parent() is not None
    finally:
        window.close()


# ── Grouped signal list ──────────────────────────────────────────────────────

def test_grouped_signal_list_shows_group_header(qapp) -> None:
    """After loading signals, the signal list should contain a group header item."""
    from PySide6.QtCore import Qt

    window = ScopeWindow("mst-group-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=3)
        window._current_result = result
        window._refresh_stacked_sidebar(result)

        lw = window._stacked_signal_list._list_widget
        header_items = [
            lw.item(row)
            for row in range(lw.count())
            if lw.item(row).data(Qt.ItemDataRole.UserRole) == "__group_header__"
        ]
        assert len(header_items) >= 1
    finally:
        window.close()


def test_grouped_signal_list_headers_can_collapse_and_expand(qapp) -> None:
    """Group headers should hide/show child signal rows when toggled."""
    from PySide6.QtCore import Qt

    window = ScopeWindow("mst-group-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        lw = window._stacked_signal_list._list_widget
        header_item = next(
            lw.item(row)
            for row in range(lw.count())
            if lw.item(row).data(Qt.ItemDataRole.UserRole) == "__group_header__"
        )
        signal_items = [
            lw.item(row)
            for row in range(lw.count())
            if hasattr(lw.item(row), "signal_name")
        ]
        assert signal_items
        assert all(not item.isHidden() for item in signal_items)

        window._stacked_signal_list._on_item_clicked(header_item)
        assert all(item.isHidden() for item in signal_items)

        window._stacked_signal_list._on_item_clicked(header_item)
        assert all(not item.isHidden() for item in signal_items)
    finally:
        window.close()


def test_signal_axis_badge_cycles_left_right_new_plot(qapp) -> None:
    """Clicking the axis badge should rotate the active signal assignment deterministically."""
    window = ScopeWindow("mst-group-3", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        signal_name = window._stacked_active_signal
        assert signal_name is not None
        row = window._stacked_signal_list._signal_widgets[signal_name]

        assert window._signal_axis_targets[signal_name] == "left"
        row._axis_button.click()
        assert window._signal_axis_targets[signal_name] == "right"

        row._axis_button.click()
        assert window._signal_axis_targets[signal_name] == "new_plot"

        row._axis_button.click()
        assert window._signal_axis_targets[signal_name] == "left"
    finally:
        window.close()


def test_signal_alias_roundtrips_in_ui_state(qapp) -> None:
    """Inspector aliases and simulation state should survive UI-state roundtrip."""
    window = ScopeWindow("mst-group-4", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    restored = ScopeWindow("mst-group-5", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        signal_name = window._stacked_active_signal
        assert signal_name is not None

        window._set_signal_alias(signal_name, "Alias Vout")
        window._on_run_requested()
        state = window.capture_ui_state()

        _prepare_window(restored)
        restored.apply_ui_state(state)

        assert restored._display_signal_name(signal_name) == "Alias Vout"
        assert restored._simulation_state == "running"
        assert restored._stacked_signal_list._signal_widgets[signal_name]._label.text() == "Alias Vout"
    finally:
        restored.close()
        window.close()


def test_signal_drag_mime_roundtrip_uses_explicit_scope_payload() -> None:
    """Signal drag/drop payload should carry the explicit scope signal MIME format."""
    mime = SignalListPanel.create_signal_mime_data("S2")

    assert SignalListPanel.signal_name_from_mime(mime) == "S2"
