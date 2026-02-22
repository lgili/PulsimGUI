"""Entry point for PulsimGui application."""

import os
import stat
import sys
import time
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
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication, QSplashScreen  # noqa: E402

try:  # noqa: E402
    from PySide6.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - optional fallback
    QSvgRenderer = None

from pulsimgui.views.main_window import MainWindow  # noqa: E402


def _branding_logo_path() -> Path:
    """Return the logo path used for startup branding."""
    return Path(__file__).resolve().parent / "resources" / "branding" / "pulsim_logo.svg"


def _create_startup_splash(logo_path: Path) -> QSplashScreen:
    """Create a branded startup splash screen."""
    width, height = 620, 320
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)

    panel_rect = QRectF(18.0, 16.0, width - 36.0, height - 32.0)
    gradient = QLinearGradient(0.0, 0.0, float(width), float(height))
    gradient.setColorAt(0.0, QColor("#0f172a"))
    gradient.setColorAt(0.55, QColor("#111827"))
    gradient.setColorAt(1.0, QColor("#1f2937"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#334155"), 1.4))
    painter.drawRoundedRect(panel_rect, 22.0, 22.0)

    title_font = QFont()
    title_font.setPointSize(22)
    title_font.setWeight(QFont.Weight.Bold)
    painter.setPen(QColor("#e5e7eb"))
    painter.setFont(title_font)
    painter.drawText(QRectF(0.0, 36.0, float(width), 38.0), Qt.AlignmentFlag.AlignCenter, "PulsimGui")

    subtitle_font = QFont()
    subtitle_font.setPointSize(9)
    subtitle_font.setWeight(QFont.Weight.Medium)
    painter.setPen(QColor("#94a3b8"))
    painter.setFont(subtitle_font)
    painter.drawText(
        QRectF(0.0, 84.0, float(width), 24.0),
        Qt.AlignmentFlag.AlignCenter,
        "Power Electronics Simulation Workspace",
    )

    logo_size = 142.0
    logo_rect = QRectF((width - logo_size) / 2.0, 98.0, logo_size, logo_size)
    rendered = False
    if logo_path.exists() and QSvgRenderer is not None:
        renderer = QSvgRenderer(str(logo_path))
        if renderer.isValid():
            renderer.render(painter, logo_rect)
            rendered = True

    if not rendered:
        fallback_pen = QPen(QColor("#22d3ee"), 7.0)
        fallback_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        fallback_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(fallback_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        x0 = logo_rect.left() + 18.0
        y_mid = logo_rect.top() + logo_rect.height() * 0.62
        step = (logo_rect.width() - 36.0) / 6.0
        amp = logo_rect.height() * 0.28

        trace = [
            QPointF(x0, y_mid),
            QPointF(x0 + step, y_mid),
            QPointF(x0 + step, y_mid - amp),
            QPointF(x0 + 2.0 * step, y_mid - amp),
            QPointF(x0 + 2.0 * step, y_mid),
            QPointF(x0 + 3.0 * step, y_mid),
            QPointF(x0 + 3.0 * step, y_mid - amp * 0.72),
            QPointF(x0 + 4.0 * step, y_mid - amp * 0.72),
            QPointF(x0 + 4.0 * step, y_mid),
            QPointF(x0 + 5.0 * step, y_mid),
            QPointF(x0 + 5.0 * step, y_mid - amp * 1.26),
            QPointF(x0 + 6.0 * step, y_mid - amp * 1.26),
            QPointF(x0 + 6.0 * step, y_mid),
        ]
        painter.drawPolyline(QPolygonF(trace))

    painter.end()

    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.showMessage(
        "Inicializando interface...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#cbd5e1"),
    )
    return splash


def _wait_min_splash_time(app: QApplication, start_time: float, min_seconds: float = 0.9) -> None:
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
    _wait_min_splash_time(app, splash_start, min_seconds=0.9)
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
