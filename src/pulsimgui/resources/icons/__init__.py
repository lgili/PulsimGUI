"""Icon management for PulsimGUI — bundled SVG set first.

Redesign slice 2. Icons previously rendered exclusively through
QtAwesome and mixed two icon FONTS — Phosphor (``ph.*``) and Material
Design (``mdi6.*``) — with visibly different stroke weights and
metaphors in the same toolbar. Without qtawesome installed the entire
app silently rendered empty icons, and any unknown name silently
became a filled circle.

Resolution order now:

1. **The bundled SVG set** (:mod:`pulsimgui.resources.icons.icons`) —
   one Lucide-convention family (24 grid, stroke 2, round caps),
   including the EDA-domain glyphs (probes, wire, net label, FFT,
   engine, auto-layout) that no icon font ships. Self-contained: no
   runtime dependency, identical rendering on every platform,
   HiDPI-crisp through QSvgRenderer.
2. **QtAwesome passthrough** for names that carry an explicit font
   prefix (``ph.house``, ``mdi6.chart-line``) — migration escape
   hatch for call sites not yet on the canonical set.
3. **Legacy alias map** (``ICON_MAP``) through QtAwesome, for any
   unprefixed name the SVG set doesn't cover yet.
4. ``help-circle`` from the SVG set, with a debug log — a visible,
   consistent "missing icon" instead of a silently wrong one.

Public API is unchanged: ``IconService.get_icon / get_themed_icon /
clear_cache / list_icons``, module-level ``icon()``, plus the legacy
``get_icon_svg`` / ``get_available_icons`` / ``ICONS`` exports.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

from pulsimgui.resources.icons.icons import (
    ICONS as SVG_ICONS,
)
from pulsimgui.resources.icons.icons import (
    get_available_icons as _svg_available,
)
from pulsimgui.resources.icons.icons import (
    get_icon_svg as _svg_document,
)
from pulsimgui.resources.icons.icons import (
    svg_for as _svg_for,
)

try:
    from PySide6.QtSvg import QSvgRenderer
    HAS_QTSVG = True
except Exception:  # pragma: no cover - QtSvg ships with PySide6
    QSvgRenderer = None  # type: ignore[assignment]
    HAS_QTSVG = False

try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False

logger = logging.getLogger(__name__)

# Legacy alias map (unprefixed name -> qtawesome name). Only consulted
# for names the bundled SVG set does not carry; kept so nothing breaks
# mid-migration. Do NOT add new entries — add the glyph to the SVG set.
ICON_MAP = {
    "file-plus": "ph.file-plus",
    "folder-open": "ph.folder-open",
    "save": "ph.floppy-disk",
    "file": "ph.file",
    "folder": "ph.folder",
    "undo": "ph.arrow-u-up-left",
    "redo": "ph.arrow-u-up-right",
    "cut": "ph.scissors",
    "copy": "ph.copy",
    "paste": "ph.clipboard",
    "trash": "ph.trash",
    "delete": "ph.x",
    "edit": "ph.pencil-simple",
    "rename": "ph.text-t",
    "zoom-in": "ph.magnifying-glass-plus",
    "zoom-out": "ph.magnifying-glass-minus",
    "maximize": "ph.arrows-out",
    "minimize": "ph.arrows-in",
    "play": "ph.play",
    "stop": "ph.stop",
    "pause": "ph.pause",
    "square": "ph.stop",
    "step-forward": "ph.skip-forward",
    "step-forward-filled": "ph.skip-forward-fill",
    "chevron-right": "ph.caret-right",
    "chevron-down": "ph.caret-down",
    "chevron-up": "ph.caret-up",
    "chevron-left": "ph.caret-left",
    "search": "ph.magnifying-glass",
    "settings": "ph.gear",
    "menu": "ph.list",
    "sidebar": "ph.sidebar-simple",
    "sidebar-filled": "ph.sidebar-simple-fill",
    "panel-left": "mdi6.page-layout-sidebar-left",
    "panel-right": "mdi6.page-layout-sidebar-right",
    "x": "ph.x",
    "plus": "ph.plus",
    "minus": "ph.minus",
    "check": "ph.check",
    "info": "ph.info",
    "warning": "ph.warning",
    "error": "ph.x-circle",
    "zap": "ph.lightning",
    "cpu": "ph.cpu",
    "box": "ph.cube",
    "activity": "ph.activity",
    "tool": "ph.wrench",
    "grid": "ph.grid-four",
    "grid-filled": "ph.grid-four-fill",
    "wire": "ph.path",
    "hand": "ph.hand",
    "rotate-cw": "ph.arrows-clockwise",
    "rotate-ccw": "ph.arrows-counter-clockwise",
    "star": "ph.star",
    "heart": "ph.heart",
    "clock": "ph.clock",
    "crosshairs": "ph.crosshair",
    "crosshair-simple": "ph.crosshair-simple",
    "zoom": "ph.magnifying-glass",
    "selection": "ph.selection",
    "cursor": "ph.cursor",
    "modified": "ph.pencil-simple",
    "saved": "ph.check-circle",
    "sim-ready": "ph.circle",
    "sim-running": "ph.spinner",
    "sim-done": "ph.check",
    "sim-error": "ph.warning",
    "sliders": "ph.sliders",
    "move": "ph.arrows-out-cardinal",
    "layers": "ph.stack",
    "table": "ph.table",
    "wave": "ph.wave-sine",
    "waveform": "ph.waveform",
    "fit-view": "ph.corners-out",
    "measurements": "ph.ruler",
    "measurements-filled": "ph.ruler-fill",
    "math": "ph.function",
    "math-function": "mdi6.function-variant",
    "fft-chart": "mdi6.chart-bell-curve-cumulative",
    "brand-wave": "ph.wave-sine",
    "sliders-horizontal": "ph.sliders-horizontal",
    "style-tune": "mdi6.tune-variant",
    "copy-filled": "ph.copy-fill",
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

# Sizes baked into each QIcon (logical px). Every size is rendered at
# 2x and tagged with a device-pixel-ratio of 2 so retina displays get
# genuinely sharp strokes instead of upscaled 1x rasters.
_RENDER_SIZES = (16, 20, 24, 32, 48)
_DPR = 2.0


class IconService:
    """Application icon factory — bundled SVG set with legacy fallbacks."""

    _cache: dict[tuple[str, str], QIcon] = {}

    # ------------------------------------------------------------------
    # SVG rendering
    # ------------------------------------------------------------------
    @staticmethod
    def _render_svg_icon(name: str, color: str) -> QIcon | None:
        """Rasterize a bundled glyph into a multi-size, HiDPI QIcon."""
        if not HAS_QTSVG:
            return None
        svg = _svg_for(name, color=color, size=24)
        if svg is None:
            return None

        renderer = QSvgRenderer(svg.encode("utf-8"))
        if not renderer.isValid():  # pragma: no cover - authoring error
            logger.warning("icon %r: invalid SVG body", name)
            return None

        out = QIcon()
        for logical in _RENDER_SIZES:
            physical = int(logical * _DPR)
            image = QImage(physical, physical, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter, QRectF(0, 0, physical, physical))
            painter.end()
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(_DPR)
            out.addPixmap(pixmap)
        return out

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @classmethod
    def get_icon(cls, name: str, color: str = "#666666", size: int = 16) -> QIcon:
        """Get a QIcon for ``name``.

        ``size`` is kept for API compatibility; the returned icon
        carries multiple pre-rendered sizes and scales to whatever the
        widget requests.
        """
        cache_key = (name, color)
        cached = cls._cache.get(cache_key)
        if cached is not None:
            return cached

        icon_obj: QIcon | None = None

        # 1. Explicit font-prefixed names go straight to qtawesome.
        if "." in name:
            icon_obj = cls._qtawesome_icon(name, color)
        else:
            # 2. Bundled SVG set — the canonical path.
            icon_obj = cls._render_svg_icon(name, color)
            # 3. Legacy alias map through qtawesome.
            if icon_obj is None:
                qta_name = ICON_MAP.get(name)
                if qta_name is not None:
                    icon_obj = cls._qtawesome_icon(qta_name, color)
            # 4. Visible, consistent "missing icon".
            if icon_obj is None:
                logger.debug("icon %r not in the bundled set; using fallback", name)
                icon_obj = cls._render_svg_icon("help-circle", color)

        if icon_obj is None:  # pragma: no cover - QtSvg and qtawesome both absent
            icon_obj = QIcon()

        cls._cache[cache_key] = icon_obj
        return icon_obj

    @staticmethod
    def _qtawesome_icon(qta_name: str, color: str) -> QIcon | None:
        if not HAS_QTAWESOME:
            return None
        try:
            return qta.icon(qta_name, color=color)
        except Exception:
            return None

    @classmethod
    def get_themed_icon(
        cls,
        name: str,
        light_color: str = "#374151",
        dark_color: str = "#d1d5db",
        is_dark: bool = False,
        size: int = 16,
    ) -> QIcon:
        """Get an icon colored for the current theme."""
        color = dark_color if is_dark else light_color
        return cls.get_icon(name, color, size)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the icon cache (useful when theme changes)."""
        cls._cache.clear()

    @classmethod
    def list_icons(cls) -> list[str]:
        """All canonical icon names (bundled SVG set)."""
        return _svg_available()


# Convenience function
def icon(name: str, color: str = "#666666", size: int = 16) -> QIcon:
    """Quick access to get an icon."""
    return IconService.get_icon(name, color, size)


def get_icon_svg(name: str, color: str = "#000000", size: int = 24) -> str:
    """Return the recolored SVG document for ``name`` (bundled set)."""
    return _svg_document(name, color, size)


def get_available_icons() -> list[str]:
    """All canonical icon names."""
    return _svg_available()


# Canonical set export (legacy alias kept pointing at the SVG bodies).
ICONS = SVG_ICONS

__all__ = [
    "IconService",
    "icon",
    "ICONS",
    "ICON_MAP",
    "get_icon_svg",
    "get_available_icons",
    "HAS_QTAWESOME",
    "HAS_QTSVG",
]
