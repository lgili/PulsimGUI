"""Headless GUI tests for the modern scope sidebar tabs and collapsed rail (task 7.2)."""

from __future__ import annotations

import pytest

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


def test_fft_tab_keeps_local_settings_after_switch(qapp) -> None:
    """FFT controls should persist across tab switches without affecting Scope."""
    window = ScopeWindow("mst-tabs-fft-state", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._analysis_tabs.setCurrentIndex(1)
        window._fft_window_combo.setCurrentIndex(window._fft_window_combo.findData("blackman"))
        window._fft_points_combo.setCurrentIndex(window._fft_points_combo.findData(2048))
        window._fft_scale_combo.setCurrentIndex(window._fft_scale_combo.findData("linear"))

        window._analysis_tabs.setCurrentIndex(0)
        window._analysis_tabs.setCurrentIndex(1)

        assert window._fft_window_combo.currentData() == "blackman"
        assert window._fft_points_combo.currentData() == 2048
        assert window._fft_scale_combo.currentData() == "linear"
    finally:
        window.close()


def test_compare_tab_keeps_local_settings_after_switch(qapp) -> None:
    """Compare controls should persist across tab switches without losing reference state."""
    window = ScopeWindow("mst-tabs-compare-state", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._analysis_tabs.setCurrentIndex(2)
        window._compare_reference_combo.setCurrentIndex(window._compare_reference_combo.findData("S2"))
        window._compare_mode_combo.setCurrentIndex(window._compare_mode_combo.findData("delta"))
        window._compare_normalize_toggle.setChecked(True)

        window._analysis_tabs.setCurrentIndex(0)
        window._analysis_tabs.setCurrentIndex(2)

        assert window._compare_reference_combo.currentData() == "S2"
        assert window._compare_mode_combo.currentData() == "delta"
        assert window._compare_normalize_toggle.isChecked() is True
    finally:
        window.close()


def test_top_level_scope_actions_expose_shortcuts_and_tooltips(qapp) -> None:
    """Top chrome actions should exist as QAction objects with discoverable metadata."""
    window = ScopeWindow("mst-tabs-4", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        actions = window._scope_actions
        assert {
            "run",
            "fit_view",
            "toggle_cursors",
            "toggle_measurements",
            "toggle_grid",
            "add_expression",
            "export_snapshot",
            "toggle_inspector",
            "show_fft_tab",
            "show_compare_tab",
            "show_shortcuts",
        } <= set(actions)
        assert actions["run"].shortcut().toString() == "Space"
        assert actions["fit_view"].shortcut().toString() == "F"
        assert actions["toggle_cursors"].shortcut().toString() == "C"
        assert actions["toggle_measurements"].shortcut().toString() == "M"
        assert actions["toggle_grid"].shortcut().toString() == "G"
        assert actions["add_expression"].shortcut().toString() == "Ctrl+E"
        assert actions["toggle_inspector"].shortcut().toString() == "Ctrl+I"
        assert actions["show_fft_tab"].shortcut().toString() == "Ctrl+2"
        assert actions["show_compare_tab"].shortcut().toString() == "Ctrl+3"
        assert actions["show_shortcuts"].shortcut().toString() == "F1"
        assert "\n" in actions["run"].toolTip()
        assert "Space" in actions["run"].toolTip()
        assert "Ctrl+Shift+E" in actions["export_snapshot"].toolTip()
    finally:
        window.close()


def test_top_toolbar_icons_are_present_and_legible(qapp) -> None:
    """Top toolbar buttons must keep non-null icons with readable compact sizing."""
    window = ScopeWindow("mst-tabs-toolbar-icons", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        buttons = (
            window._toolbar_run_btn,
            window._toolbar_step_btn,
            window._toolbar_grid_btn,
            window._toolbar_measure_btn,
            window._toolbar_math_btn,
            window._toolbar_fft_btn,
            window._toolbar_copy_btn,
            window._toolbar_right_btn,
        )
        for btn in buttons:
            assert not btn.icon().isNull()
            assert btn.iconSize().width() >= 14
            assert btn.iconSize().height() >= 14
    finally:
        window.close()


def test_panel_toggle_buttons_have_icons_and_english_tooltips(qapp) -> None:
    """Sidebar and inspector collapse buttons must show icons and descriptive English tooltips."""
    window = ScopeWindow("mst-tabs-panel-toggle-icons", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert not window._left_panel_toggle_btn.icon().isNull()
        assert not window._right_panel_toggle_btn.icon().isNull()
        assert "signals panel" in window._left_panel_toggle_btn.toolTip().lower()
        assert "inspector panel" in window._right_panel_toggle_btn.toolTip().lower()
        assert "ctrl+b" in window._left_panel_toggle_btn.toolTip().lower()
        assert "ctrl+i" in window._right_panel_toggle_btn.toolTip().lower()

        window._on_toggle_left_panel_clicked(False)
        window._on_toggle_right_panel_clicked(False)

        assert "expand signals panel" in window._left_panel_toggle_btn.toolTip().lower()
        assert "expand inspector panel" in window._right_panel_toggle_btn.toolTip().lower()
        assert "ctrl+b" in window._left_panel_toggle_btn.toolTip().lower()
        assert "ctrl+i" in window._right_panel_toggle_btn.toolTip().lower()
    finally:
        window.close()


def test_run_action_toggles_pause_when_already_running(qapp) -> None:
    """The Space/Run QAction should act as pause when the lightweight sim state is already running."""
    window = ScopeWindow("mst-tabs-run-toggle", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        window._set_simulation_state("running")

        window._scope_actions["run"].trigger()

        assert window._simulation_state == "paused"
    finally:
        window.close()


# ── Collapse / expand rail ───────────────────────────────────────────────────

def test_panel_starts_collapsed_for_waveform_first_layout(qapp) -> None:
    """Scope should start with side panels and bottom drawer closed to prioritize the plot."""
    window = ScopeWindow("mst-collapse-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._left_panel_visible is False
        assert window._right_panel_visible is False
        assert window._bottom_drawer_expanded is False
        assert window._sidebar_tabs.isHidden()
        assert not window._collapsed_rail.isHidden()
        assert window._stacked_right_panel.isHidden()
    finally:
        window.close()


def test_bottom_quick_metrics_hide_when_drawer_is_expanded(qapp) -> None:
    """Quick metric chips should get out of the way when the detailed drawer is open."""
    window = ScopeWindow("mst-collapse-quick-row", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert not window._scope_quick_metrics_row.isHidden()
        window._on_bottom_drawer_toggled(True)
        assert window._scope_quick_metrics_row.isHidden()
        window._on_bottom_drawer_toggled(False)
        assert not window._scope_quick_metrics_row.isHidden()
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
        window._on_toggle_right_panel_clicked(True)
        assert window._right_panel_visible is True
        assert not window._stacked_right_panel.isHidden()

        window._on_toggle_right_panel_clicked(False)
        assert window._right_panel_visible is False
        assert window._stacked_right_panel.isHidden()
    finally:
        window.close()


def test_sidebar_shortcut_toggles_panel(qapp) -> None:
    """Keyboard shortcut handler mirrors toggle button behavior."""
    window = ScopeWindow("mst-collapse-4", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert not window._left_panel_visible
        window._on_toggle_sidebar_shortcut()
        assert window._left_panel_visible
        window._on_toggle_sidebar_shortcut()
        assert not window._left_panel_visible
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
        assert window._delete_view_btn.isEnabled() is False
    finally:
        window.close()


def test_save_view_captures_current_visible_time_window(monkeypatch, qapp) -> None:
    """Saved views should store the active viewport instead of the full simulation range."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QInputDialog

    window = ScopeWindow("mst-views-3", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._timeline_slider.setValues(220, 640)
        qapp.processEvents()

        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *args, **kwargs: ("Window A", True)))
        window._on_save_view_clicked()

        start, end = window._saved_views["Window A"]
        t_min = float(window._stacked_time[0])
        span = float(window._stacked_time[-1] - window._stacked_time[0])
        expected_start = t_min + span * 0.22
        expected_end = t_min + span * 0.64
        assert start == pytest.approx(expected_start, abs=span / 1000.0)
        assert end == pytest.approx(expected_end, abs=span / 1000.0)
        assert window._views_list_widget.currentItem().data(Qt.ItemDataRole.UserRole) == "Window A"
    finally:
        window.close()


def test_saved_view_selection_can_restore_and_delete(qapp) -> None:
    """Selecting a saved view should allow restore and delete through the Views tab controls."""
    window = ScopeWindow("mst-views-4", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._saved_views["Focus"] = (5e-6, 18e-6)
        window._refresh_views_tab()
        assert window._delete_view_btn.isEnabled() is True

        window._timeline_slider.setValues(100, 220)
        window._on_view_list_item_activated(window._views_list_widget.currentItem())

        t_min = float(window._stacked_time[0])
        span = float(window._stacked_time[-1] - window._stacked_time[0])
        restored_start = t_min + span * (window._timeline_slider.lowValue() / 1000.0)
        restored_end = t_min + span * (window._timeline_slider.highValue() / 1000.0)
        assert restored_start == pytest.approx(5e-6, abs=span / 1000.0)
        assert restored_end == pytest.approx(18e-6, abs=span / 1000.0)

        window._delete_view_btn.click()
        assert "Focus" not in window._saved_views
        assert window._views_list_widget.count() == 0
        assert window._delete_view_btn.isEnabled() is False
    finally:
        window.close()


# ── Zoom overview ────────────────────────────────────────────────────────────

def test_overview_plot_stays_disabled(qapp) -> None:
    """Overview mini-plot remains disabled and must not overlay the plots."""
    window = ScopeWindow("mst-overview-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert hasattr(window, "_overview_plot")
        assert hasattr(window, "_overview_inset")
        assert window._overview_enabled is False

        _prepare_window(window)

        assert window._overview_inset.isHidden()
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


def test_analysis_tab_state_roundtrips_in_ui_state(qapp) -> None:
    """FFT and Compare local settings should survive UI-state capture/apply."""
    window = ScopeWindow("mst-analysis-state-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    restored = ScopeWindow("mst-analysis-state-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._analysis_tabs.setCurrentIndex(1)
        window._fft_window_combo.setCurrentIndex(window._fft_window_combo.findData("blackman"))
        window._fft_points_combo.setCurrentIndex(window._fft_points_combo.findData(2048))
        window._fft_scale_combo.setCurrentIndex(window._fft_scale_combo.findData("linear"))
        window._analysis_tabs.setCurrentIndex(2)
        window._compare_reference_combo.setCurrentIndex(window._compare_reference_combo.findData("S2"))
        window._compare_mode_combo.setCurrentIndex(window._compare_mode_combo.findData("delta"))
        window._compare_normalize_toggle.setChecked(True)
        state = window.capture_ui_state()

        _prepare_window(restored)
        restored.apply_ui_state(state)

        assert restored._analysis_tabs.currentIndex() == 2
        restored._analysis_tabs.setCurrentIndex(1)
        assert restored._fft_window_combo.currentData() == "blackman"
        assert restored._fft_points_combo.currentData() == 2048
        assert restored._fft_scale_combo.currentData() == "linear"
        restored._analysis_tabs.setCurrentIndex(2)
        assert restored._compare_reference_combo.currentData() == "S2"
        assert restored._compare_mode_combo.currentData() == "delta"
        assert restored._compare_normalize_toggle.isChecked() is True
    finally:
        restored.close()
        window.close()


def test_bottom_measurements_table_fits_drawer_body_without_large_dead_space(qapp) -> None:
    """The bottom measurements table should fill the drawer body closely for small datasets."""
    window = ScopeWindow("mst-bottom-fit-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._on_bottom_drawer_toggled(True)
        window._refresh_bottom_measurements(
            {
                "S1": {"rms": 1.0, "max": 2.0},
                "S2": {"rms": 2.0, "max": 3.0},
            },
            dt=None,
        )

        gap = window._bottom_drawer_height - window._scope_bottom_measure_table.height()
        assert gap <= 16
    finally:
        window.close()


def test_bottom_measurements_many_signals_expand_window_height(qapp) -> None:
    """A large signal set should grow the drawer and overall window instead of clipping early."""
    window = ScopeWindow("mst-bottom-fit-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        result = _sample_result(signal_count=18, sample_count=64)
        window.resize(1040, 700)
        initial_height = window.height()
        initial_drawer_height = window._bottom_drawer_height
        window._current_result = result
        window._refresh_stacked_sidebar(result)
        window._rebuild_stacked_plots(result)
        window._on_bottom_drawer_toggled(True)

        table_data = {
            f"S{index + 1}": {"rms": float(index), "max": float(index + 1)}
            for index in range(18)
        }
        window._refresh_bottom_measurements(table_data, dt=None)

        assert window._bottom_drawer_height > initial_drawer_height
        assert window._bottom_drawer_height >= window._preferred_bottom_drawer_height()
        assert window._scope_bottom_measure_table.height() >= window._bottom_measure_table_content_height()
    finally:
        window.close()


def test_workspace_layout_state_roundtrips_in_ui_state(qapp) -> None:
    """Panel sizes, visible traces, drawer height, and scope viewport must survive restore."""
    window = ScopeWindow("mst-layout-state-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    restored = ScopeWindow("mst-layout-state-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._left_panel_width = 332
        window._right_panel_width = 288
        window._sidebar_tabs.setCurrentIndex(3)
        window._stacked_signal_list._toggle_group_collapsed("S1")
        window._stacked_signal_list.set_signal_visible("S3", False)
        window._on_stacked_signal_visibility_changed("S3", False)
        window._trace_styles["S2"] = {"color": (12, 34, 56), "width": 3.0}
        window._apply_trace_styles_to_viewer()
        window._apply_stacked_trace_colors()
        window._timeline_slider.setValues(180, 620)
        window._on_bottom_drawer_toggled(True)
        window._on_bottom_drawer_resize_requested(48)
        window._saved_views["Focus"] = (1e-6, 8e-6)
        window._refresh_views_tab()
        state = window.capture_ui_state()

        _prepare_window(restored)
        restored.apply_ui_state(state)

        assert restored._left_panel_width == 332
        assert restored._right_panel_width == 288
        assert restored._sidebar_tabs.currentIndex() == 3
        assert set(restored._stacked_signal_list.get_visible_signals()) == {"S1", "S2"}
        assert restored._stacked_signal_list.collapsed_groups().get("S1") is True
        assert restored._trace_styles["S2"]["color"] == (12, 34, 56)
        assert restored._trace_styles["S2"]["width"] == 3.0
        assert restored._timeline_slider.lowValue() == 180
        assert restored._timeline_slider.highValue() == 620
        assert restored._bottom_drawer_expanded is True
        assert restored._bottom_drawer_height == window._bottom_drawer_height
        assert restored._scope_bottom_tab.minimumHeight() == restored._bottom_drawer_height
        assert restored._saved_views["Focus"] == (1e-6, 8e-6)
    finally:
        restored.close()
        window.close()


def test_focus_shortcut_reveals_sidebar_and_focuses_signal_filter(qapp) -> None:
    """Ctrl+L handler should reveal the left panel and move focus into the signal filter."""
    from PySide6.QtWidgets import QLineEdit

    window = ScopeWindow("mst-a11y-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.show()
        qapp.processEvents()
        window._on_toggle_left_panel_clicked(False)
        qapp.processEvents()

        filter_edit = window._stacked_signal_list.findChild(QLineEdit, "signalFilterEdit")
        assert filter_edit is not None

        window._focus_filter_shortcut.activated.emit()
        qapp.processEvents()

        assert window._left_panel_visible is True
        assert window._sidebar_tabs.currentIndex() == 0
        assert filter_edit.hasFocus() is True
    finally:
        window.close()


def test_signal_drag_mime_roundtrip_uses_explicit_scope_payload() -> None:
    """Signal drag/drop payload should carry the explicit scope signal MIME format."""
    mime = SignalListPanel.create_signal_mime_data("S2")

    assert SignalListPanel.signal_name_from_mime(mime) == "S2"
