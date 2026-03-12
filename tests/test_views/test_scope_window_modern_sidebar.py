"""Headless GUI tests for the modern scope sidebar tabs and collapsed rail (task 7.2)."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.scope_window import ScopeWindow


def _sample_result(signal_count: int = 3, sample_count: int = 16) -> SimulationResult:
    time = [idx * 1e-6 for idx in range(sample_count)]
    signals = {
        f"S{i + 1}": [(i + 1) * 0.1 + j * 0.01 for j in range(sample_count)]
        for i in range(signal_count)
    }
    return SimulationResult(time=time, signals=signals, statistics={})


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


# ── Collapse / expand rail ───────────────────────────────────────────────────

def test_panel_starts_expanded(qapp) -> None:
    """Sidebar tabs not hidden, collapsed rail hidden on startup."""
    window = ScopeWindow("mst-collapse-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        # isHidden() reflects the widget's own explicit show/hide state,
        # regardless of whether the top-level window has been shown.
        assert not window._sidebar_tabs.isHidden()
        assert window._collapsed_rail.isHidden()
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

def test_interval_combo_has_four_options(qapp) -> None:
    """Interval combo must expose all four INTERVAL_TARGETS values."""
    from pulsimgui.scope_workbench import INTERVAL_TARGETS

    window = ScopeWindow("mst-interval-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        combo = window._interval_combo
        data_values = {combo.itemData(i) for i in range(combo.count())}
        assert data_values == set(INTERVAL_TARGETS)
    finally:
        window.close()


def test_interval_combo_default_is_a_to_b(qapp) -> None:
    """Default interval target should be A→B."""
    window = ScopeWindow("mst-interval-2", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert window._interval_combo.currentData() == "a_to_b"
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
    """Overview mini-plot must exist with 80 px fixed height."""
    window = ScopeWindow("mst-overview-1", "Modern Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        assert hasattr(window, "_overview_plot")
        assert window._overview_plot.height() == 80
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
