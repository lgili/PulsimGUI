"""Theme management service with customizable color schemes."""

from dataclasses import dataclass, field, asdict
from enum import Enum
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
    colors=ThemeColors(),  # Uses all defaults
)

DARK_THEME = Theme(
    name="dark",
    display_name="Dark",
    is_dark=True,
    colors=ThemeColors(
        # Base colors
        background="#1e1e1e",
        background_alt="#252526",
        foreground="#d4d4d4",
        foreground_muted="#808080",
        # Primary accent
        primary="#0078d4",
        primary_hover="#1c8ae6",
        primary_pressed="#005a9e",
        primary_foreground="#ffffff",
        # Secondary
        secondary="#5a5a5a",
        secondary_hover="#6a6a6a",
        secondary_foreground="#ffffff",
        # Status colors
        success="#4ec9b0",
        success_background="#1e3a34",
        error="#f14c4c",
        error_background="#3a1e1e",
        warning="#cca700",
        warning_background="#3a3a1e",
        info="#3794ff",
        info_background="#1e2a3a",
        # Borders
        border="#3c3c3c",
        border_focus="#0078d4",
        divider="#3c3c3c",
        # Input
        input_background="#3c3c3c",
        input_border="#3c3c3c",
        input_focus_border="#0078d4",
        input_placeholder="#6e6e6e",
        # Toolbar
        toolbar_background="#333333",
        toolbar_border="#3c3c3c",
        menu_background="#2d2d2d",
        menu_hover="#094771",
        menu_separator="#3c3c3c",
        # Panel
        panel_background="#252526",
        panel_header="#383838",
        panel_border="#3c3c3c",
        # Tree
        tree_background="#252526",
        tree_item_hover="#2a2d2e",
        tree_item_selected="#094771",
        tree_item_selected_inactive="#3c3c3c",
        # Tabs
        tab_background="#2d2d2d",
        tab_active="#1e1e1e",
        tab_hover="#3c3c3c",
        tab_border="#3c3c3c",
        # Status bar
        statusbar_background="#007acc",
        statusbar_foreground="#ffffff",
        # Scrollbar
        scrollbar_background="#1e1e1e",
        scrollbar_handle="#424242",
        scrollbar_handle_hover="#4f4f4f",
        # Schematic
        schematic_background="#1e1e1e",
        schematic_grid="#3c3c3c",
        schematic_wire="#64c864",
        schematic_wire_preview="#6464ff",
        schematic_component="#d4d4d4",
        schematic_component_fill="#252526",
        schematic_pin="#ff6464",
        schematic_selection="#0078d4",
        schematic_text="#d4d4d4",
        # Simulation
        sim_running="#4ec9b0",
        sim_paused="#cca700",
        sim_stopped="#6e6e6e",
        sim_error="#f14c4c",
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
        # Input
        input_background="#0d1117",
        input_border="#30363d",
        input_focus_border="#58a6ff",
        input_placeholder="#6e7681",
        # Toolbar
        toolbar_background="#161b22",
        toolbar_border="#30363d",
        menu_background="#161b22",
        menu_hover="#1f6feb33",
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
    background-color: transparent;
    color: {c.foreground};
}}

/* ===== Menu Bar ===== */
QMenuBar {{
    background-color: {c.toolbar_background};
    border-bottom: 1px solid {c.toolbar_border};
    padding: 2px;
}}

QMenuBar::item {{
    padding: 6px 10px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {c.menu_hover};
}}

QMenu {{
    background-color: {c.menu_background};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {c.menu_hover};
}}

QMenu::separator {{
    height: 1px;
    background-color: {c.menu_separator};
    margin: 4px 8px;
}}

/* ===== Toolbar ===== */
QToolBar {{
    background-color: {c.toolbar_background};
    border: none;
    border-bottom: 1px solid {c.toolbar_border};
    padding: 4px;
    spacing: 4px;
}}

QToolBar::separator {{
    width: 1px;
    background-color: {c.divider};
    margin: 4px 8px;
}}

QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 6px;
}}

QToolButton:hover {{
    background-color: {c.menu_hover};
}}

QToolButton:pressed {{
    background-color: {c.primary_pressed};
}}

QToolButton:checked {{
    background-color: {c.primary};
    color: {c.primary_foreground};
}}

/* ===== Dock Widgets ===== */
QDockWidget {{
    font-weight: 600;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {c.panel_header};
    padding: 8px;
    border-bottom: 1px solid {c.panel_border};
}}

QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    padding: 2px;
}}

/* ===== Scroll Bars ===== */
QScrollBar:vertical {{
    background-color: {c.scrollbar_background};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: {c.scrollbar_handle};
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c.scrollbar_handle_hover};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: {c.scrollbar_background};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: {c.scrollbar_handle};
    border-radius: 6px;
    min-width: 30px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {c.scrollbar_handle_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== Tree View ===== */
QTreeView, QTreeWidget {{
    background-color: {c.tree_background};
    border: none;
    outline: none;
}}

QTreeView::item, QTreeWidget::item {{
    padding: 6px 4px;
    border-radius: 4px;
}}

QTreeView::item:hover, QTreeWidget::item:hover {{
    background-color: {c.tree_item_hover};
}}

QTreeView::item:selected, QTreeWidget::item:selected {{
    background-color: {c.tree_item_selected};
}}

QTreeView::item:selected:!active, QTreeWidget::item:selected:!active {{
    background-color: {c.tree_item_selected_inactive};
}}

QTreeView::branch {{
    background-color: transparent;
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

/* ===== Buttons ===== */
QPushButton {{
    background-color: {c.secondary};
    color: {c.secondary_foreground};
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: 500;
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
}}

QPushButton[primary="true"] {{
    background-color: {c.primary};
    color: {c.primary_foreground};
}}

QPushButton[primary="true"]:hover {{
    background-color: {c.primary_hover};
}}

/* ===== Input Fields ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {c.input_background};
    border: 1px solid {c.input_border};
    border-radius: 4px;
    padding: 6px 10px;
    selection-background-color: {c.primary};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c.input_focus_border};
}}

QLineEdit:disabled {{
    background-color: {c.background_alt};
    color: {c.foreground_muted};
}}

/* ===== Combo Box ===== */
QComboBox {{
    background-color: {c.input_background};
    border: 1px solid {c.input_border};
    border-radius: 4px;
    padding: 6px 10px;
    min-width: 100px;
}}

QComboBox:focus {{
    border-color: {c.input_focus_border};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {c.menu_background};
    border: 1px solid {c.border};
    selection-background-color: {c.menu_hover};
}}

/* ===== Group Box ===== */
QGroupBox {{
    font-weight: 600;
    border: 1px solid {c.border};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {c.foreground};
}}

/* ===== Status Bar ===== */
QStatusBar {{
    background-color: {c.statusbar_background};
    color: {c.statusbar_foreground};
    border: none;
}}

QStatusBar::item {{
    border: none;
}}

QStatusBar QLabel {{
    color: {c.statusbar_foreground};
    padding: 2px 8px;
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
    font-size: 16px;
    font-weight: 600;
}}

QLabel[muted="true"] {{
    color: {c.foreground_muted};
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
