"""Icon management for PulsimGui using QtAwesome."""

from PySide6.QtGui import QIcon

try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False

# Map our icon names to QtAwesome Phosphor icons (ph prefix)
# Using regular weight for a clean look similar to Feather/Lucide
ICON_MAP = {
    # File operations
    "file-plus": "ph.file-plus",
    "folder-open": "ph.folder-open",
    "save": "ph.floppy-disk",
    "file": "ph.file",
    "folder": "ph.folder",

    # Edit operations
    "undo": "ph.arrow-u-up-left",
    "redo": "ph.arrow-u-up-right",
    "cut": "ph.scissors",
    "copy": "ph.copy",
    "paste": "ph.clipboard",
    "trash": "ph.trash",
    "delete": "ph.x",
    "edit": "ph.pencil-simple",
    "rename": "ph.textbox",

    # View/Zoom
    "zoom-in": "ph.magnifying-glass-plus",
    "zoom-out": "ph.magnifying-glass-minus",
    "maximize": "ph.arrows-out",
    "minimize": "ph.arrows-in",

    # Playback/Simulation
    "play": "ph.play",
    "stop": "ph.stop",
    "pause": "ph.pause",
    "square": "ph.stop",

    # Navigation
    "chevron-right": "ph.caret-right",
    "chevron-down": "ph.caret-down",
    "chevron-up": "ph.caret-up",
    "chevron-left": "ph.caret-left",

    # UI elements
    "search": "ph.magnifying-glass",
    "settings": "ph.gear",
    "menu": "ph.list",
    "x": "ph.x",
    "plus": "ph.plus",
    "minus": "ph.minus",
    "check": "ph.check",
    "info": "ph.info",
    "warning": "ph.warning",
    "error": "ph.x-circle",

    # Component library categories
    "zap": "ph.lightning",  # Sources
    "cpu": "ph.cpu",  # Semiconductors
    "box": "ph.cube",  # Passive
    "activity": "ph.pulse",  # Measurements
    "tool": "ph.wrench",  # Misc
    "grid": "ph.grid-four",  # Grid
    "wire": "ph.path",  # Schematic wire tool
    "hand": "ph.hand",  # Selection/hand tool
    "star": "ph.star",  # Favorites
    "heart": "ph.heart",  # Favorites alt
    "clock": "ph.clock",  # Recently Used

    # Status bar icons
    "crosshairs": "ph.crosshair",
    "zoom": "ph.magnifying-glass",
    "selection": "ph.selection",
    "cursor": "ph.cursor",
    "modified": "ph.pencil-simple",
    "saved": "ph.check-circle",
    "sim-ready": "ph.circle",
    "sim-running": "ph.spinner",
    "sim-done": "ph.check",
    "sim-error": "ph.warning",

    # Properties panel icons
    "sliders": "ph.sliders",
    "move": "ph.arrows-out-cardinal",

    # Additional icons
    "layers": "ph.stack",
    "lock": "ph.lock",
    "unlock": "ph.lock-open",
    "eye": "ph.eye",
    "eye-off": "ph.eye-slash",
    "download": "ph.download",
    "upload": "ph.upload",
    "refresh": "ph.arrow-clockwise",
    "external-link": "ph.arrow-square-out",
    "link": "ph.link",
    "image": "ph.image",
    "code": "ph.code",
    "terminal": "ph.terminal",
    "help": "ph.question",
    "about": "ph.info",
}


class IconService:
    """Service for creating and managing application icons using QtAwesome."""

    _cache: dict[tuple[str, str], QIcon] = {}

    @classmethod
    def get_icon(cls, name: str, color: str = "#666666", size: int = 16) -> QIcon:
        """Get a QIcon for the given icon name.

        Args:
            name: Icon name (e.g., "save", "undo")
            color: Hex color for the icon
            size: Icon size in pixels (used for scaling)

        Returns:
            QIcon instance
        """
        if not HAS_QTAWESOME:
            return QIcon()

        cache_key = (name, color)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        # Get the QtAwesome icon name
        qta_name = ICON_MAP.get(name, f"ph.{name}")

        try:
            icon = qta.icon(qta_name, color=color)
        except Exception:
            # Fallback to a default icon if not found
            try:
                icon = qta.icon("ph.circle", color=color)
            except Exception:
                return QIcon()

        cls._cache[cache_key] = icon
        return icon

    @classmethod
    def get_themed_icon(
        cls,
        name: str,
        light_color: str = "#374151",
        dark_color: str = "#d1d5db",
        is_dark: bool = False,
        size: int = 16,
    ) -> QIcon:
        """Get an icon with appropriate color for the current theme.

        Args:
            name: Icon name
            light_color: Color to use in light theme
            dark_color: Color to use in dark theme
            is_dark: Whether dark theme is active
            size: Icon size

        Returns:
            QIcon with theme-appropriate color
        """
        color = dark_color if is_dark else light_color
        return cls.get_icon(name, color, size)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the icon cache (useful when theme changes)."""
        cls._cache.clear()

    @classmethod
    def list_icons(cls) -> list[str]:
        """Get list of available icon names."""
        return list(ICON_MAP.keys())


# Convenience function
def icon(name: str, color: str = "#666666", size: int = 16) -> QIcon:
    """Quick access to get an icon.

    Args:
        name: Icon name
        color: Icon color
        size: Size in pixels

    Returns:
        QIcon instance
    """
    return IconService.get_icon(name, color, size)


# Keep backward compatibility
def get_icon_svg(name: str, color: str = "#000000", size: int = 24) -> str:
    """Legacy function - returns empty string as we now use QtAwesome."""
    return ""


def get_available_icons() -> list[str]:
    """Get list of available icon names."""
    return list(ICON_MAP.keys())


# Legacy exports for compatibility
ICONS = ICON_MAP

__all__ = ["IconService", "icon", "ICONS", "get_icon_svg", "get_available_icons", "ICON_MAP"]
