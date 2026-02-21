"""Theme management service with customizable color schemes."""

from dataclasses import dataclass, field, asdict
from pathlib import Path
import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


@dataclass
class ThemeColors:
    """Color definitions for a theme."""

    # Base colors
    background: str = "#ffffff"
    background_alt: str = "#f5f5f5"
    foreground: str = "#1a1a1a"
    foreground_muted: str = "#666666"

    # Primary accent (main brand color)
    primary: str = "#0078d4"
    primary_hover: str = "#106ebe"
    primary_pressed: str = "#005a9e"
    primary_foreground: str = "#ffffff"

    # Secondary accent
    secondary: str = "#6c757d"
    secondary_hover: str = "#5a6268"
    secondary_foreground: str = "#ffffff"

    # Success/Error/Warning
    success: str = "#28a745"
    success_background: str = "#d4edda"
    error: str = "#dc3545"
    error_background: str = "#f8d7da"
    warning: str = "#ffc107"
    warning_background: str = "#fff3cd"
    info: str = "#17a2b8"
    info_background: str = "#d1ecf1"

    # Borders and dividers
    border: str = "#e0e0e0"
    border_focus: str = "#0078d4"
    divider: str = "#e8e8e8"

    # Input/Form elements
    input_background: str = "#ffffff"
    input_border: str = "#cccccc"
    input_focus_border: str = "#0078d4"
    input_placeholder: str = "#999999"

    # Toolbar/Menu
    toolbar_background: str = "#f8f9fa"
    toolbar_border: str = "#e0e0e0"
    menu_background: str = "#ffffff"
    menu_hover: str = "#e8f0fe"
    menu_separator: str = "#e0e0e0"

    # Sidebar/Panel
    panel_background: str = "#f8f9fa"
    panel_header: str = "#e9ecef"
    panel_border: str = "#dee2e6"

    # Tree/List
    tree_background: str = "#ffffff"
    tree_item_hover: str = "#e8f0fe"
    tree_item_selected: str = "#cce5ff"
    tree_item_selected_inactive: str = "#e2e6ea"

    # Tabs
    tab_background: str = "#e9ecef"
    tab_active: str = "#ffffff"
    tab_hover: str = "#dee2e6"
    tab_border: str = "#dee2e6"

    # Status bar
    statusbar_background: str = "#007acc"
    statusbar_foreground: str = "#ffffff"

    # Scrollbar
    scrollbar_background: str = "#f1f1f1"
    scrollbar_handle: str = "#c1c1c1"
    scrollbar_handle_hover: str = "#a8a8a8"

    # Schematic specific
    schematic_background: str = "#ffffff"
    schematic_grid: str = "#e0e0e0"
    schematic_wire: str = "#006400"
    schematic_wire_preview: str = "#6464ff"
    schematic_component: str = "#1a1a1a"
    schematic_component_fill: str = "#ffffff"
    schematic_pin: str = "#cc0000"
    schematic_selection: str = "#0078d4"
    schematic_text: str = "#1a1a1a"

    # Simulation
    sim_running: str = "#28a745"
    sim_paused: str = "#ffc107"
    sim_stopped: str = "#6c757d"
    sim_error: str = "#dc3545"

    # Icons
    icon_default: str = "#374151"
    icon_hover: str = "#1f2937"
    icon_active: str = "#ffffff"
    icon_disabled: str = "#9ca3af"
    icon_accent: str = "#2563eb"

    # Context menus and custom overlays
    context_icon: str = "#374151"
    overlay_pin_highlight: str = "#22c55e"
    overlay_alignment_guides: str = "#ef4444"
    overlay_drop_preview_fill: str = "#2563eb44"
    overlay_drop_preview_border: str = "#2563ebcc"
    overlay_minimap_viewport_fill: str = "#2563eb33"
    overlay_minimap_viewport_border: str = "#2563ebcc"

    # Plot surfaces (pyqtgraph-backed views)
    plot_background: str = "#ffffff"
    plot_grid: str = "#d1d5db"
    plot_axis: str = "#374151"
    plot_text: str = "#374151"
    plot_legend_background: str = "#ffffff"
    plot_legend_border: str = "#e5e7eb"


@dataclass
class Theme:
    """Complete theme definition."""

    name: str
    display_name: str
    is_dark: bool
    colors: ThemeColors = field(default_factory=ThemeColors)

    def to_dict(self) -> dict:
        """Convert theme to dictionary for serialization."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "is_dark": self.is_dark,
            "colors": asdict(self.colors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        """Create theme from dictionary."""
        colors = ThemeColors(**data.get("colors", {}))
        return cls(
            name=data["name"],
            display_name=data["display_name"],
            is_dark=data["is_dark"],
            colors=colors,
        )

    def get_color(self, name: str) -> QColor:
        """Get a QColor for a named color."""
        color_str = getattr(self.colors, name, "#ff00ff")  # Magenta for missing
        return QColor(color_str)


# Built-in themes

LIGHT_THEME = Theme(
    name="light",
    display_name="Light",
    is_dark=False,
    colors=ThemeColors(
        # Base colors - clean, professional look
        background="#ffffff",
        background_alt="#f9fafb",
        foreground="#1f2937",
        foreground_muted="#6b7280",
        # Primary accent - professional blue
        primary="#2563eb",
        primary_hover="#1d4ed8",
        primary_pressed="#1e40af",
        primary_foreground="#ffffff",
        # Secondary
        secondary="#6b7280",
        secondary_hover="#4b5563",
        secondary_foreground="#ffffff",
        # Status colors - refined
        success="#059669",
        success_background="#d1fae5",
        error="#dc2626",
        error_background="#fee2e2",
        warning="#d97706",
        warning_background="#fef3c7",
        info="#0284c7",
        info_background="#e0f2fe",
        # Borders - subtle
        border="#e5e7eb",
        border_focus="#2563eb",
        divider="#f3f4f6",
        # Input
        input_background="#ffffff",
        input_border="#d1d5db",
        input_focus_border="#2563eb",
        input_placeholder="#9ca3af",
        # Toolbar
        toolbar_background="#f9fafb",
        toolbar_border="#e5e7eb",
        menu_background="#ffffff",
        menu_hover="#f3f4f6",
        menu_separator="#e5e7eb",
        # Panel
        panel_background="#f9fafb",
        panel_header="#f3f4f6",
        panel_border="#e5e7eb",
        # Tree
        tree_background="#ffffff",
        tree_item_hover="#f3f4f6",
        tree_item_selected="#dbeafe",
        tree_item_selected_inactive="#e5e7eb",
        # Tabs
        tab_background="#f3f4f6",
        tab_active="#ffffff",
        tab_hover="#e5e7eb",
        tab_border="#e5e7eb",
        # Status bar - professional blue
        statusbar_background="#2563eb",
        statusbar_foreground="#ffffff",
        # Scrollbar
        scrollbar_background="#f3f4f6",
        scrollbar_handle="#d1d5db",
        scrollbar_handle_hover="#9ca3af",
        # Schematic
        schematic_background="#ffffff",
        schematic_grid="#e5e7eb",
        schematic_wire="#059669",
        schematic_wire_preview="#2563eb",
        schematic_component="#1f2937",
        schematic_component_fill="#ffffff",
        schematic_pin="#dc2626",
        schematic_selection="#2563eb",
        schematic_text="#1f2937",
        # Simulation
        sim_running="#059669",
        sim_paused="#d97706",
        sim_stopped="#6b7280",
        sim_error="#dc2626",
        # Context and overlays
        context_icon="#374151",
        overlay_pin_highlight="#16a34a",
        overlay_alignment_guides="#dc2626",
        overlay_drop_preview_fill="#2563eb33",
        overlay_drop_preview_border="#2563ebcc",
        overlay_minimap_viewport_fill="#2563eb33",
        overlay_minimap_viewport_border="#2563ebcc",
        # Plot surfaces
        plot_background="#ffffff",
        plot_grid="#d1d5db",
        plot_axis="#374151",
        plot_text="#374151",
        plot_legend_background="#ffffff",
        plot_legend_border="#e5e7eb",
    ),
)

DARK_THEME = Theme(
    name="dark",
    display_name="Dark",
    is_dark=True,
    colors=ThemeColors(
        # Base colors - VS Code style
        background="#1e1e1e",
        background_alt="#252526",
        foreground="#e0e0e0",
        foreground_muted="#b0b0b0",  # Brighter for labels
        # Primary accent - brighter blue
        primary="#4fc3f7",
        primary_hover="#29b6f6",
        primary_pressed="#0288d1",
        primary_foreground="#000000",
        # Secondary - lighter for visibility
        secondary="#4a4a4a",
        secondary_hover="#5a5a5a",
        secondary_foreground="#ffffff",
        # Status colors
        success="#4ec9b0",
        success_background="#1e3a34",
        error="#f14c4c",
        error_background="#3a1e1e",
        warning="#ffca28",
        warning_background="#3a3a1e",
        info="#4fc3f7",
        info_background="#1e2a3a",
        # Borders - slightly lighter
        border="#4a4a4a",
        border_focus="#4fc3f7",
        divider="#404040",
        # Input - more visible
        input_background="#2d2d2d",
        input_border="#4a4a4a",
        input_focus_border="#4fc3f7",
        input_placeholder="#808080",
        # Toolbar
        toolbar_background="#2d2d2d",
        toolbar_border="#404040",
        menu_background="#2d2d2d",
        menu_hover="#3d3d3d",
        menu_separator="#404040",
        # Panel
        panel_background="#252526",
        panel_header="#2d2d2d",
        panel_border="#404040",
        # Tree - better contrast
        tree_background="#252526",
        tree_item_hover="#323232",
        tree_item_selected="#37373d",
        tree_item_selected_inactive="#2d2d2d",
        # Tabs
        tab_background="#2d2d2d",
        tab_active="#1e1e1e",
        tab_hover="#3d3d3d",
        tab_border="#404040",
        # Status bar
        statusbar_background="#007acc",
        statusbar_foreground="#ffffff",
        # Scrollbar - more visible
        scrollbar_background="transparent",
        scrollbar_handle="#5a5a5a",
        scrollbar_handle_hover="#6a6a6a",
        # Schematic
        schematic_background="#1e1e1e",
        schematic_grid="#404040",
        schematic_wire="#4ec9b0",
        schematic_wire_preview="#4fc3f7",
        schematic_component="#e0e0e0",
        schematic_component_fill="#2d2d2d",
        schematic_pin="#ff8a80",
        schematic_selection="#4fc3f7",
        schematic_text="#e0e0e0",
        # Simulation
        sim_running="#4ec9b0",
        sim_paused="#ffca28",
        sim_stopped="#808080",
        sim_error="#f14c4c",
        # Icons - much brighter for visibility
        icon_default="#d0d0d0",
        icon_hover="#e8e8e8",
        icon_active="#ffffff",
        icon_disabled="#707070",
        icon_accent="#4fc3f7",
        # Context and overlays
        context_icon="#e8e8e8",
        overlay_pin_highlight="#4ec9b0",
        overlay_alignment_guides="#ff8a80",
        overlay_drop_preview_fill="#4fc3f744",
        overlay_drop_preview_border="#4fc3f7cc",
        overlay_minimap_viewport_fill="#4fc3f744",
        overlay_minimap_viewport_border="#4fc3f7cc",
        # Plot surfaces
        plot_background="#1e1e1e",
        plot_grid="#4a4a4a",
        plot_axis="#d0d0d0",
        plot_text="#e8e8e8",
        plot_legend_background="#252526",
        plot_legend_border="#404040",
    ),
)

MODERN_DARK_THEME = Theme(
    name="modern_dark",
    display_name="Modern Dark",
    is_dark=True,
    colors=ThemeColors(
        # Base - slightly purple tinted
        background="#0d1117",
        background_alt="#161b22",
        foreground="#c9d1d9",
        foreground_muted="#8b949e",
        # Primary - GitHub-style blue
        primary="#58a6ff",
        primary_hover="#79b8ff",
        primary_pressed="#388bfd",
        primary_foreground="#0d1117",
        # Secondary
        secondary="#30363d",
        secondary_hover="#484f58",
        secondary_foreground="#c9d1d9",
        # Status colors
        success="#3fb950",
        success_background="#1b4721",
        error="#f85149",
        error_background="#490202",
        warning="#d29922",
        warning_background="#3d2d00",
        info="#58a6ff",
        info_background="#0c2d6b",
        # Borders
        border="#30363d",
        border_focus="#58a6ff",
        divider="#21262d",
        # Input - visible borders
        input_background="#161b22",
        input_border="#3d444d",
        input_focus_border="#58a6ff",
        input_placeholder="#6e7681",
        # Toolbar
        toolbar_background="#161b22",
        toolbar_border="#30363d",
        menu_background="#1c2128",
        menu_hover="#2d333b",
        menu_separator="#30363d",
        # Panel
        panel_background="#0d1117",
        panel_header="#161b22",
        panel_border="#30363d",
        # Tree
        tree_background="#0d1117",
        tree_item_hover="#161b22",
        tree_item_selected="#1f6feb44",
        tree_item_selected_inactive="#30363d",
        # Tabs
        tab_background="#010409",
        tab_active="#0d1117",
        tab_hover="#161b22",
        tab_border="#30363d",
        # Status bar - accent color
        statusbar_background="#238636",
        statusbar_foreground="#ffffff",
        # Scrollbar
        scrollbar_background="#0d1117",
        scrollbar_handle="#30363d",
        scrollbar_handle_hover="#484f58",
        # Schematic
        schematic_background="#0d1117",
        schematic_grid="#21262d",
        schematic_wire="#3fb950",
        schematic_wire_preview="#58a6ff",
        schematic_component="#c9d1d9",
        schematic_component_fill="#161b22",
        schematic_pin="#f85149",
        schematic_selection="#58a6ff",
        schematic_text="#c9d1d9",
        # Simulation
        sim_running="#3fb950",
        sim_paused="#d29922",
        sim_stopped="#6e7681",
        sim_error="#f85149",
        # Icons
        icon_default="#c9d1d9",
        icon_hover="#f0f6fc",
        icon_active="#ffffff",
        icon_disabled="#6e7681",
        icon_accent="#58a6ff",
        # Context and overlays
        context_icon="#c9d1d9",
        overlay_pin_highlight="#3fb950",
        overlay_alignment_guides="#f85149",
        overlay_drop_preview_fill="#58a6ff44",
        overlay_drop_preview_border="#58a6ffcc",
        overlay_minimap_viewport_fill="#58a6ff44",
        overlay_minimap_viewport_border="#58a6ffcc",
        # Plot surfaces
        plot_background="#0d1117",
        plot_grid="#30363d",
        plot_axis="#8b949e",
        plot_text="#c9d1d9",
        plot_legend_background="#161b22",
        plot_legend_border="#30363d",
    ),
)

# All built-in themes
BUILTIN_THEMES = {
    "light": LIGHT_THEME,
    "dark": DARK_THEME,
    "modern_dark": MODERN_DARK_THEME,
}


class ThemeService(QObject):
    """Service for managing application themes."""

    theme_changed = Signal(Theme)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_theme: Theme = LIGHT_THEME
        self._custom_themes: dict[str, Theme] = {}
        self._themes_dir: Path | None = None

    @property
    def current_theme(self) -> Theme:
        """Get the current theme."""
        return self._current_theme

    @property
    def is_dark(self) -> bool:
        """Check if current theme is dark."""
        return self._current_theme.is_dark

    def set_themes_directory(self, path: Path) -> None:
        """Set directory for custom themes."""
        self._themes_dir = path
        self._load_custom_themes()

    def _load_custom_themes(self) -> None:
        """Load custom themes from themes directory."""
        if self._themes_dir is None or not self._themes_dir.exists():
            return

        for theme_file in self._themes_dir.glob("*.json"):
            try:
                with open(theme_file) as f:
                    data = json.load(f)
                theme = Theme.from_dict(data)
                self._custom_themes[theme.name] = theme
            except Exception:
                pass  # Skip invalid theme files

    def get_available_themes(self) -> list[Theme]:
        """Get list of all available themes."""
        all_themes = list(BUILTIN_THEMES.values())
        all_themes.extend(self._custom_themes.values())
        return all_themes

    def get_theme(self, name: str) -> Theme | None:
        """Get a theme by name."""
        if name in BUILTIN_THEMES:
            return BUILTIN_THEMES[name]
        return self._custom_themes.get(name)

    def set_theme(self, name: str) -> bool:
        """Set the current theme by name."""
        theme = self.get_theme(name)
        if theme is None:
            return False

        self._current_theme = theme
        self.theme_changed.emit(theme)
        return True

    def save_custom_theme(self, theme: Theme) -> bool:
        """Save a custom theme to file."""
        if self._themes_dir is None:
            return False

        self._themes_dir.mkdir(parents=True, exist_ok=True)
        theme_file = self._themes_dir / f"{theme.name}.json"

        try:
            with open(theme_file, "w") as f:
                json.dump(theme.to_dict(), f, indent=2)
            self._custom_themes[theme.name] = theme
            return True
        except Exception:
            return False

    @staticmethod
    def _hex_to_rgb(color: str) -> tuple[int, int, int]:
        """Convert a hex-like color string to RGB tuple with safe fallback."""
        value = QColor(color)
        if not value.isValid():
            return (255, 0, 255)
        return (value.red(), value.green(), value.blue())

    def get_trace_palette(self, theme: Theme | None = None) -> list[tuple[int, int, int]]:
        """Return a theme-aware trace palette for waveform/thermal plots."""
        active = theme or self._current_theme
        c = active.colors
        if active.is_dark:
            colors = [
                c.primary,
                c.success,
                c.warning,
                c.error,
                c.info,
                "#c084fc",
                "#fb7185",
                "#fbbf24",
                "#34d399",
                "#93c5fd",
            ]
        else:
            colors = [
                c.primary,
                c.success,
                c.warning,
                c.error,
                c.info,
                "#7c3aed",
                "#db2777",
                "#0d9488",
                "#4f46e5",
                "#ca8a04",
            ]
        return [self._hex_to_rgb(color) for color in colors]

    def get_cursor_palette(self, theme: Theme | None = None) -> list[tuple[int, int, int]]:
        """Return two high-contrast cursor colors for the active theme."""
        active = theme or self._current_theme
        c = active.colors
        return [self._hex_to_rgb(c.error), self._hex_to_rgb(c.primary)]

    def generate_stylesheet(self) -> str:
        """Generate Qt stylesheet for current theme."""
        c = self._current_theme.colors

        return f"""
/* ===== Base Application ===== */
QMainWindow, QDialog {{
    background-color: {c.background};
    color: {c.foreground};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

QWidget {{
    background-color: transparent;
    color: {c.foreground};
    font-size: 13px;
}}

/* ===== Menu Bar ===== */
QMenuBar {{
    background-color: {c.toolbar_background};
    border-bottom: 1px solid {c.toolbar_border};
    padding: 4px 8px;
    spacing: 4px;
}}

QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 6px;
    margin: 2px;
}}

QMenuBar::item:selected {{
    background-color: {c.menu_hover};
}}

QMenu {{
    background-color: {c.menu_background};
    border: 1px solid {c.border};
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    padding: 8px 32px 8px 12px;
    border-radius: 6px;
    margin: 2px;
}}

QMenu::item:selected {{
    background-color: {c.menu_hover};
}}

QMenu::separator {{
    height: 1px;
    background-color: {c.menu_separator};
    margin: 6px 10px;
}}

QMenu::icon {{
    padding-left: 8px;
}}

/* ===== Toolbar - Modern flat design ===== */
QToolBar {{
    background-color: {c.toolbar_background};
    border: none;
    border-bottom: 1px solid {c.toolbar_border};
    padding: 6px 12px;
    spacing: 2px;
}}

QToolBar::separator {{
    width: 1px;
    background-color: {c.divider};
    margin: 6px 12px;
}}

QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 8px;
    margin: 2px;
}}

QToolButton:hover {{
    background-color: {c.menu_hover};
}}

QToolButton:pressed {{
    background-color: {c.primary};
    color: {c.primary_foreground};
}}

QToolButton:checked {{
    background-color: {c.primary};
    color: {c.primary_foreground};
}}

/* ===== Dock Widgets - Clean panel design ===== */
QDockWidget {{
    font-weight: 600;
    font-size: 12px;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {c.panel_header};
    padding: 10px 12px;
    border-bottom: 1px solid {c.panel_border};
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 11px;
    font-weight: 600;
    color: {c.foreground_muted};
}}

QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
}}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {c.menu_hover};
}}

/* ===== Scroll Bars - Thin modern style ===== */
QScrollBar:vertical {{
    background-color: transparent;
    width: 10px;
    border: none;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background-color: {c.scrollbar_handle};
    border-radius: 4px;
    min-height: 40px;
    margin: 0px 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c.scrollbar_handle_hover};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 10px;
    border: none;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background-color: {c.scrollbar_handle};
    border-radius: 4px;
    min-width: 40px;
    margin: 2px 0px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {c.scrollbar_handle_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0;
}}

/* ===== Tree View - Component library style ===== */
QTreeView, QTreeWidget {{
    background-color: {c.tree_background};
    border: none;
    outline: none;
    padding: 4px;
    selection-background-color: transparent;
}}

QTreeView::item, QTreeWidget::item {{
    padding: 8px 8px;
    border-radius: 6px;
    margin: 1px 4px;
}}

QTreeView::item:hover, QTreeWidget::item:hover {{
    background-color: {c.tree_item_hover};
}}

QTreeView::item:selected, QTreeWidget::item:selected {{
    background-color: {c.primary}20;
    color: {c.foreground};
    border-left: 3px solid {c.primary};
}}

QTreeView::item:selected:active, QTreeWidget::item:selected:active {{
    background-color: {c.primary}25;
    color: {c.foreground};
}}

QTreeView::item:selected:!active, QTreeWidget::item:selected:!active {{
    background-color: {c.tree_item_selected_inactive};
    border-left: 3px solid {c.border};
}}

QTreeView::branch {{
    background-color: transparent;
}}

QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    border-image: none;
}}

QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    border-image: none;
}}

/* Header for tree view */
QHeaderView::section {{
    background-color: {c.panel_header};
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {c.border};
    font-weight: 600;
    font-size: 11px;
    color: {c.foreground_muted};
}}

/* ===== Tab Widget ===== */
QTabWidget::pane {{
    border: 1px solid {c.tab_border};
    border-radius: 4px;
    background-color: {c.background};
}}

QTabBar::tab {{
    background-color: {c.tab_background};
    border: 1px solid {c.tab_border};
    padding: 8px 16px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {c.tab_active};
    border-bottom-color: {c.tab_active};
}}

QTabBar::tab:hover:!selected {{
    background-color: {c.tab_hover};
}}

/* ===== Buttons - Modern rounded style ===== */
QPushButton {{
    background-color: {c.secondary};
    color: {c.secondary_foreground};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 500;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: {c.secondary_hover};
}}

QPushButton:pressed {{
    background-color: {c.primary_pressed};
}}

QPushButton:disabled {{
    background-color: {c.border};
    color: {c.foreground_muted};
    opacity: 0.6;
}}

QPushButton[primary="true"] {{
    background-color: {c.primary};
    color: {c.primary_foreground};
}}

QPushButton[primary="true"]:hover {{
    background-color: {c.primary_hover};
}}

/* Small variant for dialogs */
QPushButton[size="small"] {{
    padding: 6px 12px;
    font-size: 12px;
}}

/* ===== Input Fields - Clean modern inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c.input_background};
    border: 1px solid {c.input_border};
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: {c.primary};
    selection-color: {c.primary_foreground};
    font-size: 13px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c.input_focus_border};
    border-width: 2px;
}}

QLineEdit:disabled {{
    background-color: {c.background_alt};
    color: {c.foreground_muted};
}}

QLineEdit::placeholder {{
    color: {c.input_placeholder};
}}

/* Spin boxes */
QSpinBox, QDoubleSpinBox {{
    background-color: {c.input_background};
    border: 1px solid {c.input_border};
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 13px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c.input_focus_border};
    border-width: 2px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: right;
    width: 20px;
    border: none;
    border-radius: 0 8px 0 0;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: right;
    width: 20px;
    border: none;
    border-radius: 0 0 8px 0;
}}

/* ===== Combo Box - Modern dropdown ===== */
QComboBox {{
    background-color: {c.input_background};
    border: 1px solid {c.input_border};
    border-radius: 8px;
    padding: 8px 12px;
    min-width: 120px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {c.input_focus_border};
    border-width: 2px;
}}

QComboBox:hover {{
    border-color: {c.primary};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}}

QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {c.menu_background};
    border: 1px solid {c.border};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {c.menu_hover};
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 2px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {c.menu_hover};
}}

/* ===== Group Box - Section headers ===== */
QGroupBox {{
    font-weight: 600;
    font-size: 12px;
    border: 1px solid {c.border};
    border-radius: 10px;
    margin-top: 16px;
    padding: 16px 12px 12px 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: {c.foreground};
    background-color: {c.background};
    border-radius: 4px;
    left: 12px;
}}

/* ===== Status Bar - Accent bar ===== */
QStatusBar {{
    background-color: {c.statusbar_background};
    color: {c.statusbar_foreground};
    border: none;
    min-height: 28px;
    padding: 0 8px;
}}

QStatusBar::item {{
    border: none;
}}

QStatusBar QLabel {{
    color: {c.statusbar_foreground};
    padding: 4px 10px;
    font-size: 12px;
}}

QStatusBar QProgressBar {{
    background-color: rgba(255, 255, 255, 0.2);
    border: none;
    border-radius: 4px;
    max-height: 6px;
    min-height: 6px;
}}

QStatusBar QProgressBar::chunk {{
    background-color: rgba(255, 255, 255, 0.9);
    border-radius: 3px;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background-color: {c.divider};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ===== Progress Bar ===== */
QProgressBar {{
    background-color: {c.background_alt};
    border: none;
    border-radius: 4px;
    text-align: center;
    height: 8px;
}}

QProgressBar::chunk {{
    background-color: {c.primary};
    border-radius: 4px;
}}

/* ===== Tooltip ===== */
QToolTip {{
    background-color: {c.menu_background};
    color: {c.foreground};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 6px 10px;
}}

/* ===== Labels ===== */
QLabel {{
    color: {c.foreground};
}}

QLabel[heading="true"] {{
    font-size: 13px;
    font-weight: 600;
}}

QLabel[muted="true"] {{
    color: {c.foreground_muted};
}}

QLabel#sectionTitle {{
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.3px;
}}

QLabel#typeLabel {{
    color: {c.foreground_muted};
    font-size: 12px;
    font-weight: 500;
}}

QLabel#noSelectionLabel {{
    color: {c.foreground_muted};
    font-size: 12px;
    padding: 40px 20px;
}}

/* ===== Check Box ===== */
QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {c.border};
    border-radius: 4px;
    background-color: {c.input_background};
}}

QCheckBox::indicator:hover {{
    border-color: {c.primary};
}}

QCheckBox::indicator:checked {{
    background-color: {c.primary};
    border-color: {c.primary};
}}

/* ===== Radio Button ===== */
QRadioButton {{
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {c.border};
    border-radius: 10px;
    background-color: {c.input_background};
}}

QRadioButton::indicator:hover {{
    border-color: {c.primary};
}}

QRadioButton::indicator:checked {{
    background-color: {c.primary};
    border-color: {c.primary};
}}

/* ===== Slider ===== */
QSlider::groove:horizontal {{
    background-color: {c.background_alt};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {c.primary};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {c.primary_hover};
}}
"""
