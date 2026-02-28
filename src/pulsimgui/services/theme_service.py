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
        # Base colors - airy web-app feel
        background="#f5f7fb",
        background_alt="#edf2fa",
        foreground="#0b1220",
        foreground_muted="#4f627a",
        # Primary accent
        primary="#1d4ed8",
        primary_hover="#1e40af",
        primary_pressed="#1e3a8a",
        primary_foreground="#ffffff",
        # Secondary (neutral action)
        secondary="#e2e8f0",
        secondary_hover="#cbd5e1",
        secondary_foreground="#1e293b",
        # Status colors
        success="#059669",
        success_background="#d1fae5",
        error="#dc2626",
        error_background="#fee2e2",
        warning="#d97706",
        warning_background="#ffedd5",
        info="#0284c7",
        info_background="#e0f2fe",
        # Borders and dividers
        border="#cdd9e8",
        border_focus="#2563eb",
        divider="#dfe7f2",
        # Input
        input_background="#ffffff",
        input_border="#bcc9db",
        input_focus_border="#2563eb",
        input_placeholder="#7f93ac",
        # Toolbar
        toolbar_background="#f8fbff",
        toolbar_border="#cdd9e8",
        menu_background="#ffffff",
        menu_hover="#eff6ff",
        menu_separator="#d6e1ed",
        # Panel
        panel_background="#f8fbff",
        panel_header="#eef3fb",
        panel_border="#cfdceb",
        # Tree
        tree_background="#f8fbff",
        tree_item_hover="#eff6ff",
        tree_item_selected="#dbeafe",
        tree_item_selected_inactive="#d8e2ef",
        # Tabs
        tab_background="#edf2fa",
        tab_active="#ffffff",
        tab_hover="#e2e8f0",
        tab_border="#cfdceb",
        # Status bar
        statusbar_background="#eaf1ff",
        statusbar_foreground="#1e3a8a",
        # Scrollbar
        scrollbar_background="#edf2fa",
        scrollbar_handle="#b5c7de",
        scrollbar_handle_hover="#8fa9c6",
        # Schematic
        schematic_background="#f9fbff",
        schematic_grid="#c5d3e4",
        schematic_wire="#0d9488",
        schematic_wire_preview="#2563eb",
        schematic_component="#0f172a",
        schematic_component_fill="#ffffff",
        schematic_pin="#dc2626",
        schematic_selection="#2563eb",
        schematic_text="#0f172a",
        # Simulation
        sim_running="#059669",
        sim_paused="#d97706",
        sim_stopped="#64748b",
        sim_error="#dc2626",
        # Icons/context/overlays
        icon_default="#25364d",
        icon_hover="#0f172a",
        icon_active="#ffffff",
        icon_disabled="#94a3b8",
        icon_accent="#1d4ed8",
        context_icon="#334155",
        overlay_pin_highlight="#16a34a",
        overlay_alignment_guides="#dc2626",
        overlay_drop_preview_fill="#1d4ed833",
        overlay_drop_preview_border="#1d4ed8cc",
        overlay_minimap_viewport_fill="#1d4ed833",
        overlay_minimap_viewport_border="#1d4ed8cc",
        # Plot surfaces
        plot_background="#ffffff",
        plot_grid="#becbdb",
        plot_axis="#3b4f67",
        plot_text="#26384e",
        plot_legend_background="#ffffff",
        plot_legend_border="#dbe4f0",
    ),
)

DARK_THEME = Theme(
    name="dark",
    display_name="Dark",
    is_dark=True,
    colors=ThemeColors(
        # Base colors - neutral deep slate
        background="#11151c",
        background_alt="#171d26",
        foreground="#f1f6ff",
        foreground_muted="#b3c3d8",
        # Primary accent
        primary="#2ea8ff",
        primary_hover="#4ab4ff",
        primary_pressed="#1485d6",
        primary_foreground="#041322",
        # Secondary actions
        secondary="#1f2a37",
        secondary_hover="#2b3a4b",
        secondary_foreground="#e9f1ff",
        # Status colors
        success="#22c55e",
        success_background="#113222",
        error="#ff5d5d",
        error_background="#3c161b",
        warning="#fbbf24",
        warning_background="#3a2c09",
        info="#38bdf8",
        info_background="#102d42",
        # Borders/dividers
        border="#33465e",
        border_focus="#38bdf8",
        divider="#223042",
        # Input
        input_background="#141c27",
        input_border="#3a4f69",
        input_focus_border="#38bdf8",
        input_placeholder="#8ea2bc",
        # Toolbar
        toolbar_background="#121a24",
        toolbar_border="#2b3e56",
        menu_background="#17202b",
        menu_hover="#202c3a",
        menu_separator="#263548",
        # Panel
        panel_background="#121a24",
        panel_header="#182334",
        panel_border="#2d435c",
        # Tree
        tree_background="#101824",
        tree_item_hover="#1a2738",
        tree_item_selected="#1d4ed866",
        tree_item_selected_inactive="#273a52",
        # Tabs
        tab_background="#121b27",
        tab_active="#0f141c",
        tab_hover="#1b2838",
        tab_border="#2d435c",
        # Status bar
        statusbar_background="#111a24",
        statusbar_foreground="#a7c0dc",
        # Scrollbar
        scrollbar_background="transparent",
        scrollbar_handle="#2f435a",
        scrollbar_handle_hover="#3f5978",
        # Schematic
        schematic_background="#101722",
        schematic_grid="#314055",
        schematic_wire="#25c8a8",
        schematic_wire_preview="#38bdf8",
        schematic_component="#edf3ff",
        schematic_component_fill="#162131",
        schematic_pin="#ff7b7b",
        schematic_selection="#2ea8ff",
        schematic_text="#edf3ff",
        # Simulation
        sim_running="#22c55e",
        sim_paused="#fbbf24",
        sim_stopped="#7f95b2",
        sim_error="#ff5d5d",
        # Icons/context/overlays
        icon_default="#d2dff1",
        icon_hover="#e8f1ff",
        icon_active="#ffffff",
        icon_disabled="#62748a",
        icon_accent="#2ea8ff",
        context_icon="#d3e2f4",
        overlay_pin_highlight="#25c8a8",
        overlay_alignment_guides="#ff7b7b",
        overlay_drop_preview_fill="#2ea8ff44",
        overlay_drop_preview_border="#2ea8ffcc",
        overlay_minimap_viewport_fill="#2ea8ff44",
        overlay_minimap_viewport_border="#2ea8ffcc",
        # Plot surfaces
        plot_background="#101722",
        plot_grid="#2c3b4f",
        plot_axis="#9ab0c8",
        plot_text="#d5e4f6",
        plot_legend_background="#141e2b",
        plot_legend_border="#26364a",
    ),
)

MODERN_DARK_THEME = Theme(
    name="modern_dark",
    display_name="Modern Dark",
    is_dark=True,
    colors=ThemeColors(
        # Base - inky background with bright data accents
        background="#0b1018",
        background_alt="#121927",
        foreground="#dbe7f8",
        foreground_muted="#8ea2bf",
        # Primary
        primary="#33b1ff",
        primary_hover="#57c0ff",
        primary_pressed="#0f8ae0",
        primary_foreground="#04111c",
        # Secondary
        secondary="#1a2433",
        secondary_hover="#253346",
        secondary_foreground="#dce8f8",
        # Status colors
        success="#24d18a",
        success_background="#11382b",
        error="#ff6b6b",
        error_background="#431a20",
        warning="#f7c948",
        warning_background="#3d310f",
        info="#50c6ff",
        info_background="#123249",
        # Borders
        border="#2a3b55",
        border_focus="#50c6ff",
        divider="#1d2b3d",
        # Input
        input_background="#121b2a",
        input_border="#32465f",
        input_focus_border="#50c6ff",
        input_placeholder="#7085a4",
        # Toolbar
        toolbar_background="#0f1826",
        toolbar_border="#213248",
        menu_background="#141f2f",
        menu_hover="#1e2d42",
        menu_separator="#25364d",
        # Panel
        panel_background="#0d1624",
        panel_header="#142033",
        panel_border="#22364d",
        # Tree
        tree_background="#0d1624",
        tree_item_hover="#162539",
        tree_item_selected="#33b1ff55",
        tree_item_selected_inactive="#223248",
        # Tabs
        tab_background="#0f1825",
        tab_active="#0b1018",
        tab_hover="#16253a",
        tab_border="#22364d",
        # Status bar
        statusbar_background="#11253f",
        statusbar_foreground="#9bd8ff",
        # Scrollbar
        scrollbar_background="transparent",
        scrollbar_handle="#304760",
        scrollbar_handle_hover="#426383",
        # Schematic
        schematic_background="#0b1018",
        schematic_grid="#213047",
        schematic_wire="#22d3a6",
        schematic_wire_preview="#50c6ff",
        schematic_component="#dbe7f8",
        schematic_component_fill="#121b2a",
        schematic_pin="#ff7878",
        schematic_selection="#33b1ff",
        schematic_text="#dbe7f8",
        # Simulation
        sim_running="#22d3a6",
        sim_paused="#f7c948",
        sim_stopped="#7f95b2",
        sim_error="#ff6b6b",
        # Icons/context/overlays
        icon_default="#c4d6ec",
        icon_hover="#eef6ff",
        icon_active="#ffffff",
        icon_disabled="#7085a4",
        icon_accent="#33b1ff",
        context_icon="#c4d6ec",
        overlay_pin_highlight="#22d3a6",
        overlay_alignment_guides="#ff7878",
        overlay_drop_preview_fill="#33b1ff44",
        overlay_drop_preview_border="#33b1ffcc",
        overlay_minimap_viewport_fill="#33b1ff44",
        overlay_minimap_viewport_border="#33b1ffcc",
        # Plot surfaces
        plot_background="#0a1018",
        plot_grid="#293d57",
        plot_axis="#93abc7",
        plot_text="#dbe7f8",
        plot_legend_background="#121b2a",
        plot_legend_border="#263a52",
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
}}

QWidget {{
    color: {c.foreground};
    font-size: 13px;
    font-family: "SF Pro Text", "Segoe UI", "Noto Sans";
}}

/* ===== Menu Bar ===== */
QMenuBar {{
    background-color: {c.toolbar_background};
    border-bottom: 1px solid {c.toolbar_border};
    padding: 6px 10px;
    spacing: 4px;
}}

QMenuBar::item {{
    padding: 7px 12px;
    border-radius: 8px;
    margin: 2px;
}}

QMenuBar::item:selected {{
    background-color: {c.menu_hover};
}}

QMenu {{
    background-color: {c.menu_background};
    border: 1px solid {c.border};
    border-radius: 10px;
    background-clip: padding;
    padding: 8px;
}}

QMenu::item {{
    padding: 8px 32px 8px 12px;
    border-radius: 8px;
    background-clip: padding;
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
    padding: 8px 12px;
    spacing: 4px;
}}

QToolBar::separator {{
    width: 1px;
    background-color: {c.divider};
    margin: 6px 12px;
}}

QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    background-clip: padding;
    padding: 7px 10px;
    margin: 2px;
    font-weight: 500;
}}

QToolButton:hover {{
    background-color: {c.menu_hover};
    border-color: {c.border};
}}

QToolButton:pressed {{
    background-color: {c.primary}20;
    color: {c.primary};
    border-color: {c.primary}66;
}}

QToolButton:checked {{
    background-color: {c.primary}24;
    color: {c.primary};
    border-color: {c.primary}66;
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
    padding: 11px 12px;
    border-bottom: 1px solid {c.panel_border};
    font-size: 12px;
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
    width: 12px;
    border: none;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background-color: {c.scrollbar_handle};
    border-radius: 6px;
    min-height: 40px;
    margin: 0px 3px;
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
    height: 12px;
    border: none;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background-color: {c.scrollbar_handle};
    border-radius: 6px;
    min-width: 40px;
    margin: 3px 0px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {c.scrollbar_handle_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0;
}}

QAbstractScrollArea::corner {{
    background: transparent;
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
    border: 1px solid transparent;
    border-radius: 8px;
    margin: 1px 4px;
}}

QTreeView::item:hover, QTreeWidget::item:hover {{
    background-color: {c.tree_item_hover};
}}

QTreeView::item:selected, QTreeWidget::item:selected {{
    background-color: {c.primary}24;
    color: {c.foreground};
    border: 1px solid {c.primary}66;
}}

QTreeView::item:selected:active, QTreeWidget::item:selected:active {{
    background-color: {c.primary}2b;
    color: {c.foreground};
}}

QTreeView::item:selected:!active, QTreeWidget::item:selected:!active {{
    background-color: {c.tree_item_selected_inactive};
    border: 1px solid {c.border};
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
    border-radius: 10px;
    background-clip: padding;
    background-color: {c.background};
}}

QTabBar::tab {{
    background-color: {c.tab_background};
    border: 1px solid {c.tab_border};
    border-radius: 9px;
    background-clip: padding;
    padding: 8px 14px;
    margin-right: 4px;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background-color: {c.tab_active};
    border-color: {c.primary}66;
}}

QTabBar::tab:hover:!selected {{
    background-color: {c.tab_hover};
}}

/* ===== Buttons - Modern rounded style ===== */
QPushButton {{
    background-color: {c.secondary};
    color: {c.secondary_foreground};
    border: 1px solid {c.border};
    border-radius: 10px;
    background-clip: padding;
    padding: 9px 16px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: {c.secondary_hover};
}}

QPushButton:pressed {{
    background-color: {c.menu_hover};
}}

QPushButton:disabled {{
    background-color: {c.background_alt};
    color: {c.foreground_muted};
}}

QPushButton[primary="true"] {{
    background-color: {c.primary};
    color: {c.primary_foreground};
    border: 1px solid {c.primary};
}}

QPushButton[primary="true"]:hover {{
    background-color: {c.primary_hover};
}}

QPushButton[primary="true"]:pressed {{
    background-color: {c.primary_pressed};
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
    border-radius: 10px;
    background-clip: padding;
    padding: 9px 12px;
    selection-background-color: {c.primary};
    selection-color: {c.primary_foreground};
    font-size: 13px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c.input_focus_border};
    border-width: 1px;
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
    border-radius: 10px;
    background-clip: padding;
    padding: 7px 9px;
    font-size: 13px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c.input_focus_border};
    border-width: 1px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: right;
    width: 20px;
    border: none;
    border-radius: 0 10px 0 0;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: right;
    width: 20px;
    border: none;
    border-radius: 0 0 10px 0;
}}

/* ===== Combo Box - Modern dropdown ===== */
QComboBox {{
    background-color: {c.input_background};
    border: 1px solid {c.input_border};
    border-radius: 10px;
    background-clip: padding;
    padding: 8px 12px;
    min-width: 120px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {c.input_focus_border};
    border-width: 1px;
}}

QComboBox:hover {{
    border-color: {c.primary};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}}

QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {c.menu_background};
    border: 1px solid {c.border};
    border-radius: 10px;
    background-clip: padding;
    padding: 4px;
    selection-background-color: {c.menu_hover};
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 8px;
    background-clip: padding;
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
    border-radius: 12px;
    background-clip: padding;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    color: {c.foreground_muted};
    background-color: {c.background_alt};
    border-radius: 6px;
    left: 12px;
}}

/* ===== Status Bar ===== */
QStatusBar {{
    background-color: {c.statusbar_background};
    color: {c.statusbar_foreground};
    border-top: 1px solid {c.border};
    min-height: 30px;
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
    background-color: {c.background_alt};
    border: 1px solid {c.border};
    border-radius: 4px;
    max-height: 6px;
    min-height: 6px;
}}

QStatusBar QProgressBar::chunk {{
    background-color: {c.primary};
    border-radius: 3px;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background-color: {c.divider};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

/* ===== Progress Bar ===== */
QProgressBar {{
    background-color: {c.background_alt};
    border: 1px solid {c.border};
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
    border-radius: 8px;
    background-clip: padding;
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
    border: 1px solid {c.border};
    border-radius: 5px;
    background-clip: padding;
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
    border: 1px solid {c.border};
    border-radius: 10px;
    background-clip: padding;
    background-color: {c.input_background};
}}

QRadioButton::indicator:hover {{
    border-color: {c.primary};
}}

QRadioButton::indicator:checked {{
    background-color: {c.input_background};
    border: 5px solid {c.primary};
    border-color: {c.primary};
}}

/* ===== Slider ===== */
QSlider::groove:horizontal {{
    background-color: {c.divider};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {c.primary};
    border: 2px solid {c.background};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {c.primary_hover};
}}
"""
