"""Entry point for PulsimGui application."""

import os
import stat
import sys
import time
from importlib import metadata
from pathlib import Path


def _clear_hidden_flag(path: str) -> None:
    """Remove macOS hidden flag if present.

    Some PySide6 wheels end up with Qt plugin dylibs flagged as hidden, and Qt
    ignores hidden plugin files during discovery.
    """
    if not hasattr(os, "chflags") or not hasattr(stat, "UF_HIDDEN"):
        return
    try:
        current = os.stat(path, follow_symlinks=False).st_flags
    except OSError:
        return
    if current & stat.UF_HIDDEN:
        try:
            os.chflags(path, current & ~stat.UF_HIDDEN, follow_symlinks=False)
        except OSError:
            pass


def _ensure_qt_plugins_visible(plugin_path: str) -> None:
    """Ensure Qt plugin files are visible to Qt on macOS."""
    for root, dirs, files in os.walk(plugin_path):
        for name in dirs:
            _clear_hidden_flag(os.path.join(root, name))
        for name in files:
            _clear_hidden_flag(os.path.join(root, name))


def _setup_qt_plugin_path() -> None:
    """Configure Qt plugin path before any Qt imports.

    This fixes the "Could not find the Qt platform plugin cocoa" error
    on macOS by setting the plugin path to the PySide6 installation.
    """
    if sys.platform == "darwin":
        try:
            import importlib.util
            spec = importlib.util.find_spec("PySide6")
            if spec and spec.origin:
                pyside_dir = os.path.dirname(spec.origin)
                plugin_path = os.path.join(pyside_dir, "Qt", "plugins")
                platforms_path = os.path.join(plugin_path, "platforms")
                if os.path.isdir(platforms_path):
                    _ensure_qt_plugins_visible(plugin_path)
                    # Set the specific platforms plugin path
                    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_path
                    # Also set QT_PLUGIN_PATH for other Qt plugins
                    os.environ["QT_PLUGIN_PATH"] = plugin_path
                    # Set library path for dylib loading
                    lib_path = os.path.join(pyside_dir, "Qt", "lib")
                    if os.path.isdir(lib_path):
                        existing = os.environ.get("DYLD_LIBRARY_PATH", "")
                        if lib_path not in existing:
                            os.environ["DYLD_LIBRARY_PATH"] = f"{lib_path}:{existing}" if existing else lib_path
        except Exception:
            pass  # If this fails, Qt might still find plugins via other means


# MUST be called before any PySide6/Qt imports
_setup_qt_plugin_path()

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QSplashScreen  # noqa: E402

try:  # noqa: E402
    from PySide6.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - optional fallback
    QSvgRenderer = None

from pulsimgui.views.main_window import MainWindow  # noqa: E402


def _ui_font_path() -> Path:
    """Return bundled UI font path used for cross-platform visual consistency."""
    return Path(__file__).resolve().parent / "resources" / "fonts" / "DejaVuSans.ttf"


def _load_embedded_ui_font_family() -> str | None:
    """Load bundled UI font and return the resolved family name."""
    font_path = _ui_font_path()
    if not font_path.exists():
        return None

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        return None

    families = QFontDatabase.applicationFontFamilies(font_id)
    return families[0] if families else None


def _preferred_ui_font(base_font: QFont) -> QFont:
    """Return a stable UI font profile across platforms."""
    font = QFont(base_font)
    embedded_family = _load_embedded_ui_font_family()
    if embedded_family:
        font.setFamily(embedded_family)
    else:
        # Keep deterministic fallback order if the bundled font fails to load.
        db = QFontDatabase()
        families = set(db.families())
        for family in ("DejaVu Sans", "Noto Sans", "Segoe UI", "Helvetica Neue", "Arial"):
            if family in families:
                font.setFamily(family)
                break

    if font.pointSizeF() <= 0:
        font.setPointSize(10)

    return font


def _resolve_app_version() -> str:
    """Return app version for runtime branding."""
    env_version = os.environ.get("PULSIMGUI_VERSION", "").strip().lstrip("v")
    if env_version:
        return env_version

    try:
        return metadata.version("pulsimgui")
    except Exception:
        pass

    try:
        from pulsimgui import __version__ as package_version

        return str(package_version).strip().lstrip("v")
    except Exception:
        return ""


def _branding_logo_path() -> Path:
    """Return the logo path used for startup branding."""
    return Path(__file__).resolve().parent / "resources" / "branding" / "pulsim_logo.svg"


def _create_startup_splash(logo_path: Path) -> QSplashScreen:
    """Create a branded startup splash screen."""
    width, height = 680, 360
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )

    # ── Background card ─────────────────────────────────────────────────────
    card = QRectF(0.0, 0.0, float(width), float(height))
    bg_grad = QLinearGradient(0.0, 0.0, float(width), float(height))
    bg_grad.setColorAt(0.0,  QColor("#0a0f1e"))
    bg_grad.setColorAt(0.45, QColor("#0d1424"))
    bg_grad.setColorAt(1.0,  QColor("#111827"))
    painter.setBrush(bg_grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(card, 16.0, 16.0)

    # ── Subtle dot-grid pattern ──────────────────────────────────────────────
    dot_color = QColor(255, 255, 255, 14)
    painter.setPen(QPen(dot_color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    grid_step = 28
    margin = 10
    x = margin
    while x < width - margin:
        y = margin
        while y < height - margin:
            painter.drawPoint(QPointF(float(x), float(y)))
            y += grid_step
        x += grid_step

    # ── Top accent bar ───────────────────────────────────────────────────────
    accent_grad = QLinearGradient(0.0, 0.0, float(width), 0.0)
    accent_grad.setColorAt(0.0,  QColor(0, 0, 0, 0))
    accent_grad.setColorAt(0.25, QColor("#06b6d4"))
    accent_grad.setColorAt(0.55, QColor("#818cf8"))
    accent_grad.setColorAt(0.80, QColor("#06b6d4"))
    accent_grad.setColorAt(1.0,  QColor(0, 0, 0, 0))
    painter.setBrush(accent_grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(0.0, 0.0, float(width), 3.5), 2.0, 2.0)

    # ── Radial glow behind the logo area ────────────────────────────────────
    cx, cy = width / 2.0, 155.0
    glow = QRadialGradient(cx, cy, 130.0)
    glow.setColorAt(0.0, QColor(6, 182, 212, 38))
    glow.setColorAt(0.6, QColor(99, 102, 241, 18))
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setBrush(glow)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(cx - 160, cy - 130, 320.0, 260.0))

    # ── Logo (SVG or fallback waveform) ─────────────────────────────────────
    logo_size = 96.0
    logo_rect = QRectF((width - logo_size) / 2.0, 54.0, logo_size, logo_size)
    rendered = False
    if logo_path.exists() and QSvgRenderer is not None:
        renderer = QSvgRenderer(str(logo_path))
        if renderer.isValid():
            renderer.render(painter, logo_rect)
            rendered = True

    if not rendered:
        # Stylised square-wave oscilloscope trace as fallback
        wave_pen = QPen(QColor("#06b6d4"), 4.0)
        wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        wave_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(wave_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        lx = logo_rect.left() + 8.0
        ym = logo_rect.top() + logo_rect.height() * 0.60
        sw = (logo_rect.width() - 16.0) / 6.0
        ah = logo_rect.height() * 0.30
        wave = [
            QPointF(lx,            ym),
            QPointF(lx,            ym),
            QPointF(lx + sw,       ym),
            QPointF(lx + sw,       ym - ah),
            QPointF(lx + 2*sw,     ym - ah),
            QPointF(lx + 2*sw,     ym),
            QPointF(lx + 3*sw,     ym),
            QPointF(lx + 3*sw,     ym - ah * 0.7),
            QPointF(lx + 4*sw,     ym - ah * 0.7),
            QPointF(lx + 4*sw,     ym),
            QPointF(lx + 5*sw,     ym),
            QPointF(lx + 5*sw,     ym - ah * 1.3),
            QPointF(lx + 6*sw,     ym - ah * 1.3),
            QPointF(lx + 6*sw,     ym),
        ]
        painter.drawPolyline(QPolygonF(wave))

    # ── Title "Pulsim" ───────────────────────────────────────────────────────
    title_font = QFont()
    title_font.setPointSize(28)
    title_font.setWeight(QFont.Weight.Bold)
    title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)

    # Shadow
    painter.setFont(title_font)
    painter.setPen(QColor(0, 0, 0, 90))
    painter.drawText(QRectF(2.0, 162.0, float(width), 44.0), Qt.AlignmentFlag.AlignCenter, "Pulsim")

    # Gradient text via clip trick
    text_grad = QLinearGradient(width * 0.3, 0.0, width * 0.7, 0.0)
    text_grad.setColorAt(0.0, QColor("#e2e8f0"))
    text_grad.setColorAt(0.5, QColor("#f8fafc"))
    text_grad.setColorAt(1.0, QColor("#cbd5e1"))
    painter.setPen(QColor("#f1f5f9"))
    painter.setFont(title_font)
    painter.drawText(QRectF(0.0, 160.0, float(width), 44.0), Qt.AlignmentFlag.AlignCenter, "Pulsim")

    # ── Subtitle ─────────────────────────────────────────────────────────────
    sub_font = QFont()
    sub_font.setPointSize(10)
    sub_font.setWeight(QFont.Weight.Normal)
    sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
    painter.setFont(sub_font)
    painter.setPen(QColor("#06b6d4"))
    painter.drawText(
        QRectF(0.0, 208.0, float(width), 22.0),
        Qt.AlignmentFlag.AlignCenter,
        "POWER ELECTRONICS SIMULATION",
    )

    # ── Thin separator line ──────────────────────────────────────────────────
    sep_grad = QLinearGradient(0.0, 0.0, float(width), 0.0)
    sep_grad.setColorAt(0.0,  QColor(0, 0, 0, 0))
    sep_grad.setColorAt(0.35, QColor(99, 102, 241, 160))
    sep_grad.setColorAt(0.65, QColor(6, 182, 212, 160))
    sep_grad.setColorAt(1.0,  QColor(0, 0, 0, 0))
    sep_pen = QPen(sep_grad, 1.0)
    painter.setPen(sep_pen)
    sep_y = 242.0
    painter.drawLine(QPointF(60.0, sep_y), QPointF(float(width) - 60.0, sep_y))

    # ── Version badge ────────────────────────────────────────────────────────
    ver_font = QFont()
    ver_font.setPointSize(8)
    ver_font.setWeight(QFont.Weight.Medium)
    ver_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
    painter.setFont(ver_font)

    resolved_version = _resolve_app_version()
    version_text = f"v{resolved_version}" if resolved_version else "dev"
    badge_w = max(56.0, float(painter.fontMetrics().horizontalAdvance(version_text) + 18))
    badge_h = 18.0
    badge_x = (width - badge_w) / 2.0
    badge_y = 254.0
    badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

    badge_bg = QColor(6, 182, 212, 28)
    painter.setBrush(badge_bg)
    badge_border = QPen(QColor(6, 182, 212, 80), 0.8)
    painter.setPen(badge_border)
    painter.drawRoundedRect(badge_rect, 9.0, 9.0)

    painter.setPen(QColor("#67e8f9"))
    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, version_text)

    # ── Bottom status area ───────────────────────────────────────────────────
    status_font = QFont()
    status_font.setPointSize(8)
    status_font.setWeight(QFont.Weight.Normal)
    painter.setFont(status_font)
    painter.setPen(QColor(148, 163, 184, 140))
    painter.drawText(
        QRectF(0.0, float(height) - 34.0, float(width), 18.0),
        Qt.AlignmentFlag.AlignCenter,
        "Initializing…",
    )

    # ── Bottom accent bar ────────────────────────────────────────────────────
    bot_grad = QLinearGradient(0.0, 0.0, float(width), 0.0)
    bot_grad.setColorAt(0.0,  QColor(0, 0, 0, 0))
    bot_grad.setColorAt(0.30, QColor("#818cf8"))
    bot_grad.setColorAt(0.70, QColor("#06b6d4"))
    bot_grad.setColorAt(1.0,  QColor(0, 0, 0, 0))
    painter.setBrush(bot_grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(
        QRectF(0.0, float(height) - 3.5, float(width), 3.5), 2.0, 2.0
    )

    # ── Card border ──────────────────────────────────────────────────────────
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
    painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), 16.0, 16.0)

    painter.end()

    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return splash


def _wait_min_splash_time(app: QApplication, start_time: float, min_seconds: float = 3.0) -> None:
    """Keep splash visible for a minimum time to avoid a fast flash."""
    elapsed = time.perf_counter() - start_time
    remaining = max(0.0, min_seconds - elapsed)
    while remaining > 0.0:
        app.processEvents()
        step = min(0.03, remaining)
        time.sleep(step)
        remaining -= step


def main() -> int:
    """Run the PulsimGui application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(_preferred_ui_font(app.font()))
    app.setApplicationName("PulsimGui")
    app.setOrganizationName("Pulsim")
    app.setOrganizationDomain("pulsim.org")

    logo_path = _branding_logo_path()
    if logo_path.exists():
        app_icon = QIcon(str(logo_path))
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)

    splash = _create_startup_splash(logo_path)
    splash_start = time.perf_counter()
    splash.show()
    app.processEvents()

    window = MainWindow()
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()
    _wait_min_splash_time(app, splash_start, min_seconds=3.0)
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
