"""Tests for theme propagation across scope-owned surfaces (refactor-scope-theme-service-unification)."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QComboBox

from pulsimgui.models.component import ComponentType
from pulsimgui.services.theme_service import BUILTIN_THEMES, DARK_THEME, LIGHT_THEME
from pulsimgui.views.scope.scope_window import MathSignalDialog, ScopeWindow


# ── Token derivation helpers ─────────────────────────────────────────────────

def test_scope_shell_palette_derives_tokens_from_light_theme(qapp) -> None:
    """_scope_shell_palette() must map ThemeService tokens, not hard-coded constants."""
    window = ScopeWindow("tsp-shell-light", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        shell = window._scope_shell_palette(LIGHT_THEME)
        assert shell["window_bg"] == LIGHT_THEME.colors.background
        assert shell["text"] == LIGHT_THEME.colors.foreground
        assert shell["accent"] == LIGHT_THEME.colors.primary
        assert shell["menu_bg"] == LIGHT_THEME.colors.menu_background
        assert shell["field_bg"] == LIGHT_THEME.colors.input_background
    finally:
        window.close()


def test_scope_shell_palette_differs_between_light_and_dark(qapp) -> None:
    """Shell palette must produce distinct tokens for each built-in theme."""
    window = ScopeWindow("tsp-shell-diff", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        light_shell = window._scope_shell_palette(LIGHT_THEME)
        dark_shell = window._scope_shell_palette(DARK_THEME)
        assert light_shell["window_bg"] != dark_shell["window_bg"]
        assert light_shell["menu_bg"] != dark_shell["menu_bg"]
    finally:
        window.close()


def test_scope_plot_palette_returns_theme_plot_background(qapp) -> None:
    """_scope_plot_palette() must carry the active theme's plot_background token."""
    window = ScopeWindow("tsp-plot-tok", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        for theme in BUILTIN_THEMES.values():
            tokens = window._scope_plot_palette(theme)
            assert tokens["plot_bg"] == theme.colors.plot_background
    finally:
        window.close()


# ── apply_theme() stylesheet propagation ────────────────────────────────────

def test_apply_theme_injects_theme_background_into_stylesheet(qapp) -> None:
    """apply_theme() must produce a stylesheet that contains the theme background color."""
    window = ScopeWindow("tsp-ss-bg", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        style = window.styleSheet()
        assert LIGHT_THEME.colors.background in style

        window.apply_theme(DARK_THEME)
        style = window.styleSheet()
        assert DARK_THEME.colors.background in style
    finally:
        window.close()


def test_light_theme_stylesheet_has_no_hardcoded_dark_shell_colors(qapp) -> None:
    """After applying light theme, scope chrome must not contain dark-only hex constants."""
    window = ScopeWindow("tsp-no-dark", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        style = window.styleSheet().lower()
        assert "#10151f" not in style, "Hard-coded FFT/compare dark plot bg leaked into chrome"
        assert "#1e2438" not in style, "Hard-coded dark sidebar card color leaked into chrome"
    finally:
        window.close()


def test_stylesheet_changes_between_themes(qapp) -> None:
    """Switching themes must produce a different stylesheet each time."""
    window = ScopeWindow("tsp-switch", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        light_style = window.styleSheet()
        window.apply_theme(DARK_THEME)
        dark_style = window.styleSheet()
        assert light_style != dark_style
    finally:
        window.close()


# ── FFT / Compare analysis plot surfaces ────────────────────────────────────

def test_fft_plot_background_derives_from_theme(qapp) -> None:
    """FFT plot background must update when apply_theme() is called."""
    window = ScopeWindow("tsp-fft-bg", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        light_bg = window._fft_plot.backgroundBrush().color().name()

        window.apply_theme(DARK_THEME)
        dark_bg = window._fft_plot.backgroundBrush().color().name()

        assert light_bg != dark_bg, "FFT plot background must differ between light and dark themes"
    finally:
        window.close()


def test_compare_plot_background_derives_from_theme(qapp) -> None:
    """Compare plot background must update when apply_theme() is called."""
    window = ScopeWindow("tsp-cmp-bg", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        light_bg = window._compare_plot.backgroundBrush().color().name()

        window.apply_theme(DARK_THEME)
        dark_bg = window._compare_plot.backgroundBrush().color().name()

        assert light_bg != dark_bg, "Compare plot background must differ between light and dark themes"
    finally:
        window.close()


# ── Math expression dialog ───────────────────────────────────────────────────

def test_math_dialog_stylesheet_uses_scope_shell_palette(qapp) -> None:
    """MathSignalDialog must be styled with the current scope shell palette tokens."""
    window = ScopeWindow("tsp-math-dlg", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(DARK_THEME)
        shell = window._scope_shell_palette()
        dialog = MathSignalDialog(
            window,
            signal_data={"A": np.array([1.0, 2.0])},
            signal_units={"A": "V"},
            time_values=np.array([0.0, 1.0]),
            default_signal="A",
            theme=DARK_THEME,
            scope_theme=shell,
        )
        style = dialog.styleSheet()
        assert DARK_THEME.colors.panel_background in style
        assert DARK_THEME.colors.foreground in style
    finally:
        window.close()


def test_math_dialog_theme_differs_between_themes(qapp) -> None:
    """MathSignalDialog stylesheet must differ when opened under light vs dark theme."""
    window = ScopeWindow("tsp-math-dlg2", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        light_dialog = MathSignalDialog(
            window,
            signal_data={"A": np.array([1.0, 2.0])},
            signal_units={"A": "V"},
            time_values=np.array([0.0, 1.0]),
            default_signal="A",
            theme=LIGHT_THEME,
            scope_theme=window._scope_shell_palette(LIGHT_THEME),
        )
        dark_dialog = MathSignalDialog(
            window,
            signal_data={"A": np.array([1.0, 2.0])},
            signal_units={"A": "V"},
            time_values=np.array([0.0, 1.0]),
            default_signal="A",
            theme=DARK_THEME,
            scope_theme=window._scope_shell_palette(DARK_THEME),
        )
        assert light_dialog.styleSheet() != dark_dialog.styleSheet()
    finally:
        window.close()


# ── QComboBox popup and QMenu theming ────────────────────────────────────────

def test_combo_popup_views_are_themed_after_apply_theme(qapp) -> None:
    """All QComboBox popup item views must be explicitly styled after apply_theme()."""
    window = ScopeWindow("tsp-combo", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(DARK_THEME)
        combos = window.findChildren(QComboBox)
        assert combos, "ScopeWindow must contain at least one QComboBox"
        for combo in combos:
            view = combo.view()
            if view is not None:
                style = view.styleSheet()
                assert DARK_THEME.colors.menu_background in style, (
                    f"Combo popup view has no dark theme menu_background in stylesheet"
                )
    finally:
        window.close()


def test_scope_menu_stylesheet_uses_theme_menu_background(qapp) -> None:
    """Scope-owned QMenus must derive their background from the active theme."""
    window = ScopeWindow("tsp-menu", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        light_style = window._trace_style_menu.styleSheet()
        window.apply_theme(DARK_THEME)
        dark_style = window._trace_style_menu.styleSheet()
        assert LIGHT_THEME.colors.menu_background in light_style
        assert DARK_THEME.colors.menu_background in dark_style
        assert light_style != dark_style
    finally:
        window.close()


def test_top_menus_reuse_scope_menu_theme(qapp) -> None:
    """Top workspace menus must be styled with the same theme-aware menu contract."""
    window = ScopeWindow("tsp-top-menu", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(DARK_THEME)
        assert DARK_THEME.colors.menu_background in window._file_menu.styleSheet()
        assert DARK_THEME.colors.menu_background in window._tools_menu.styleSheet()
    finally:
        window.close()


def test_dynamic_plot_context_menu_is_themed(qapp) -> None:
    """Context menus created on demand must also use the active scope menu styling."""
    window = ScopeWindow("tsp-dynamic-menu", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window._stacked_time = np.array([0.0, 1.0, 2.0], dtype=float)
        window._stacked_signals = {"Vsw": np.array([1.0, 2.0, 3.0], dtype=float)}
        window._stacked_signal_list.set_signals_with_groups({"Vsw": ["Vsw"]}, {"Vsw": "Main"})
        window._stacked_signal_list.set_signal_visible("Vsw", True)
        window.apply_theme(DARK_THEME)

        menu = window._build_plot_context_menu("Vsw")
        assert DARK_THEME.colors.menu_background in menu.styleSheet()
    finally:
        window.close()


def test_scope_message_boxes_use_theme_tokens(qapp) -> None:
    """Scope-owned message boxes must derive their chrome from the active theme."""
    window = ScopeWindow("tsp-message-box", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window.apply_theme(LIGHT_THEME)
        light_box = window._build_scope_message_box("Info", "Light theme message", level="information")
        light_style = light_box.styleSheet()

        window.apply_theme(DARK_THEME)
        dark_box = window._build_scope_message_box("Warning", "Dark theme message", level="warning")
        dark_style = dark_box.styleSheet()

        assert LIGHT_THEME.colors.panel_background in light_style
        assert LIGHT_THEME.colors.foreground in light_style
        assert DARK_THEME.colors.panel_background in dark_style
        assert DARK_THEME.colors.foreground in dark_style
        assert light_style != dark_style
    finally:
        window.close()


def test_group_header_icons_refresh_when_scope_theme_changes(qapp) -> None:
    """Signal-group header icons must refresh between light and dark themes."""
    window = ScopeWindow("tsp-group-icons", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        window._stacked_signal_list.set_signals_with_groups(
            {"vsw": ["Vsw", "Vout"]},
            {"vsw": "Voltages"},
        )
        header = window._stacked_signal_list._group_widgets["vsw"]

        window.apply_theme(LIGHT_THEME)
        light_collapse_icon = header._collapse_btn.icon().cacheKey()
        light_visibility_icon = header._visible_btn.icon().cacheKey()

        window.apply_theme(DARK_THEME)
        dark_collapse_icon = header._collapse_btn.icon().cacheKey()
        dark_visibility_icon = header._visible_btn.icon().cacheKey()

        assert light_collapse_icon != dark_collapse_icon
        assert light_visibility_icon != dark_visibility_icon
    finally:
        window.close()


def test_collapsed_rail_icons_refresh_when_scope_theme_changes(qapp) -> None:
    """Collapsed-rail icons must follow the active theme instead of fixed colors."""
    window = ScopeWindow("tsp-rail-icons", "Test", ComponentType.ELECTRICAL_SCOPE)
    try:
        rail_buttons = window.findChildren(type(window._toolbar_left_btn), "scopeCollapsedRailBtn")
        assert rail_buttons

        window.apply_theme(LIGHT_THEME)
        light_keys = [button.icon().cacheKey() for button in rail_buttons]

        window.apply_theme(DARK_THEME)
        dark_keys = [button.icon().cacheKey() for button in rail_buttons]

        assert light_keys != dark_keys
    finally:
        window.close()
