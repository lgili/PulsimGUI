"""Keyboard shortcut service for managing customizable shortcuts."""

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence


@dataclass
class ShortcutInfo:
    """Information about a keyboard shortcut."""

    action_id: str
    name: str
    category: str
    default_shortcut: str
    current_shortcut: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.current_shortcut:
            self.current_shortcut = self.default_shortcut


# Default keyboard shortcuts organized by category
DEFAULT_SHORTCUTS: dict[str, ShortcutInfo] = {
    # File operations
    "file.new": ShortcutInfo("file.new", "New Project", "File", "Ctrl+N", description="Create a new project"),
    "file.open": ShortcutInfo("file.open", "Open Project", "File", "Ctrl+O", description="Open an existing project"),
    "file.save": ShortcutInfo("file.save", "Save", "File", "Ctrl+S", description="Save the current project"),
    "file.save_as": ShortcutInfo("file.save_as", "Save As", "File", "Ctrl+Shift+S", description="Save project with a new name"),
    "file.close": ShortcutInfo("file.close", "Close Project", "File", "Ctrl+W", description="Close the current project"),
    "file.quit": ShortcutInfo("file.quit", "Exit", "File", "Ctrl+Q", description="Exit the application"),

    # Edit operations
    "edit.undo": ShortcutInfo("edit.undo", "Undo", "Edit", "Ctrl+Z", description="Undo the last action"),
    "edit.redo": ShortcutInfo("edit.redo", "Redo", "Edit", "Ctrl+Shift+Z", description="Redo the last undone action"),
    "edit.cut": ShortcutInfo("edit.cut", "Cut", "Edit", "Ctrl+X", description="Cut selected items"),
    "edit.copy": ShortcutInfo("edit.copy", "Copy", "Edit", "Ctrl+C", description="Copy selected items"),
    "edit.paste": ShortcutInfo("edit.paste", "Paste", "Edit", "Ctrl+V", description="Paste items from clipboard"),
    "edit.delete": ShortcutInfo("edit.delete", "Delete", "Edit", "Delete", description="Delete selected items"),
    "edit.select_all": ShortcutInfo("edit.select_all", "Select All", "Edit", "Ctrl+A", description="Select all items"),
    "edit.preferences": ShortcutInfo("edit.preferences", "Preferences", "Edit", "Ctrl+,", description="Open preferences"),

    # View operations
    "view.zoom_in": ShortcutInfo("view.zoom_in", "Zoom In", "View", "Ctrl++", description="Zoom in the view"),
    "view.zoom_out": ShortcutInfo("view.zoom_out", "Zoom Out", "View", "Ctrl+-", description="Zoom out the view"),
    "view.zoom_fit": ShortcutInfo("view.zoom_fit", "Zoom to Fit", "View", "Ctrl+0", description="Fit all items in view"),
    "view.toggle_grid": ShortcutInfo("view.toggle_grid", "Toggle Grid", "View", "G", description="Show/hide grid"),
    "view.toggle_dc": ShortcutInfo("view.toggle_dc", "Toggle DC Overlay", "View", "D", description="Show/hide DC values"),

    # Schematic operations
    "schematic.wire": ShortcutInfo("schematic.wire", "Wire Tool", "Schematic", "W", description="Activate wire drawing tool"),
    "schematic.rotate_cw": ShortcutInfo("schematic.rotate_cw", "Rotate CW", "Schematic", "R", description="Rotate selected 90° clockwise"),
    "schematic.rotate_ccw": ShortcutInfo("schematic.rotate_ccw", "Rotate CCW", "Schematic", "Shift+R", description="Rotate selected 90° counter-clockwise"),
    "schematic.mirror_h": ShortcutInfo("schematic.mirror_h", "Mirror Horizontal", "Schematic", "H", description="Mirror selected horizontally"),
    "schematic.mirror_v": ShortcutInfo("schematic.mirror_v", "Mirror Vertical", "Schematic", "V", description="Mirror selected vertically"),
    "schematic.escape": ShortcutInfo("schematic.escape", "Cancel/Escape", "Schematic", "Escape", description="Cancel current operation"),

    # Component shortcuts
    "component.resistor": ShortcutInfo("component.resistor", "Add Resistor", "Components", "Shift+R", description="Add a resistor"),
    "component.capacitor": ShortcutInfo("component.capacitor", "Add Capacitor", "Components", "Shift+C", description="Add a capacitor"),
    "component.inductor": ShortcutInfo("component.inductor", "Add Inductor", "Components", "Shift+L", description="Add an inductor"),
    "component.voltage": ShortcutInfo("component.voltage", "Add Voltage Source", "Components", "Shift+V", description="Add a voltage source"),
    "component.ground": ShortcutInfo("component.ground", "Add Ground", "Components", "Shift+G", description="Add a ground"),
    "component.diode": ShortcutInfo("component.diode", "Add Diode", "Components", "Shift+D", description="Add a diode"),
    "component.mosfet": ShortcutInfo("component.mosfet", "Add MOSFET", "Components", "Shift+M", description="Add a MOSFET"),

    # Simulation operations
    "sim.run": ShortcutInfo("sim.run", "Run Simulation", "Simulation", "F5", description="Run transient simulation"),
    "sim.stop": ShortcutInfo("sim.stop", "Stop Simulation", "Simulation", "Shift+F5", description="Stop running simulation"),
    "sim.pause": ShortcutInfo("sim.pause", "Pause/Resume", "Simulation", "F8", description="Pause or resume simulation"),
    "sim.dc": ShortcutInfo("sim.dc", "DC Analysis", "Simulation", "F6", description="Run DC operating point analysis"),
    "sim.ac": ShortcutInfo("sim.ac", "AC Analysis", "Simulation", "F7", description="Run AC frequency analysis"),
    "sim.settings": ShortcutInfo("sim.settings", "Simulation Settings", "Simulation", "Ctrl+Alt+S", description="Open simulation settings"),
}


class ShortcutService(QObject):
    """Service for managing keyboard shortcuts."""

    shortcuts_changed = Signal()

    def __init__(self, settings_service, parent=None):
        super().__init__(parent)
        self._settings = settings_service
        self._shortcuts: dict[str, ShortcutInfo] = {}
        self._action_map: dict[str, object] = {}  # Maps action_id to QAction
        self._load_shortcuts()

    def _load_shortcuts(self) -> None:
        """Load shortcuts from settings or use defaults."""
        custom_shortcuts = self._settings._settings.value("keyboard_shortcuts", {})

        for action_id, default_info in DEFAULT_SHORTCUTS.items():
            info = ShortcutInfo(
                action_id=default_info.action_id,
                name=default_info.name,
                category=default_info.category,
                default_shortcut=default_info.default_shortcut,
                description=default_info.description,
            )
            # Apply custom shortcut if exists
            if isinstance(custom_shortcuts, dict) and action_id in custom_shortcuts:
                info.current_shortcut = custom_shortcuts[action_id]
            else:
                info.current_shortcut = default_info.default_shortcut

            self._shortcuts[action_id] = info

    def save_shortcuts(self) -> None:
        """Save current shortcuts to settings."""
        custom = {}
        for action_id, info in self._shortcuts.items():
            if info.current_shortcut != info.default_shortcut:
                custom[action_id] = info.current_shortcut
        self._settings._settings.setValue("keyboard_shortcuts", custom)

    def get_shortcut(self, action_id: str) -> str:
        """Get the current shortcut for an action."""
        if action_id in self._shortcuts:
            return self._shortcuts[action_id].current_shortcut
        return ""

    def set_shortcut(self, action_id: str, shortcut: str) -> bool:
        """Set a shortcut for an action. Returns True if successful."""
        if action_id not in self._shortcuts:
            return False

        # Check for conflicts
        conflict = self.find_conflict(action_id, shortcut)
        if conflict:
            return False

        self._shortcuts[action_id].current_shortcut = shortcut
        self._update_action(action_id)
        self.save_shortcuts()
        self.shortcuts_changed.emit()
        return True

    def reset_shortcut(self, action_id: str) -> None:
        """Reset a shortcut to its default."""
        if action_id in self._shortcuts:
            self._shortcuts[action_id].current_shortcut = self._shortcuts[action_id].default_shortcut
            self._update_action(action_id)
            self.save_shortcuts()
            self.shortcuts_changed.emit()

    def reset_all_shortcuts(self) -> None:
        """Reset all shortcuts to defaults."""
        for info in self._shortcuts.values():
            info.current_shortcut = info.default_shortcut
            self._update_action(info.action_id)
        self._settings._settings.remove("keyboard_shortcuts")
        self.shortcuts_changed.emit()

    def find_conflict(self, action_id: str, shortcut: str) -> ShortcutInfo | None:
        """Find if a shortcut conflicts with another action."""
        if not shortcut:
            return None
        for aid, info in self._shortcuts.items():
            if aid != action_id and info.current_shortcut == shortcut:
                return info
        return None

    def get_all_shortcuts(self) -> dict[str, ShortcutInfo]:
        """Get all shortcuts."""
        return self._shortcuts.copy()

    def get_shortcuts_by_category(self) -> dict[str, list[ShortcutInfo]]:
        """Get shortcuts grouped by category."""
        categories: dict[str, list[ShortcutInfo]] = {}
        for info in self._shortcuts.values():
            if info.category not in categories:
                categories[info.category] = []
            categories[info.category].append(info)
        return categories

    def register_action(self, action_id: str, action) -> None:
        """Register a QAction with the shortcut service."""
        self._action_map[action_id] = action
        self._update_action(action_id)

    def _update_action(self, action_id: str) -> None:
        """Update the shortcut on a registered action."""
        if action_id in self._action_map and action_id in self._shortcuts:
            action = self._action_map[action_id]
            shortcut = self._shortcuts[action_id].current_shortcut
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            else:
                action.setShortcut(QKeySequence())

    def apply_all_shortcuts(self) -> None:
        """Apply all shortcuts to registered actions."""
        for action_id in self._action_map:
            self._update_action(action_id)
