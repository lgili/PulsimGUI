"""Component library panel with grid card layout and drag-and-drop support."""

from PySide6.QtCore import Qt, QMimeData, QByteArray, Signal, QPointF, QRectF, QSize, QEvent
from PySide6.QtGui import (
    QDrag, QPixmap, QPainter, QColor, QPen, QBrush, QLinearGradient,
    QFont, QPainterPath, QCursor,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLineEdit,
    QLabel,
    QScrollArea,
    QFrame,
    QApplication,
    QSizePolicy,
    QStyleOptionGraphicsItem,
    QToolButton,
)

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.component_catalog import COMPONENT_LIBRARY as SUPPORTED_COMPONENT_LIBRARY
from pulsimgui.resources.icons import IconService
from pulsimgui.services.theme_service import ThemeService, Theme


# Component metadata for library display.
# Keep this list aligned with backend-supported + GUI-functional blocks only.
COMPONENT_LIBRARY = SUPPORTED_COMPONENT_LIBRARY

COMPONENT_META: dict[ComponentType, dict[str, str]] = {
    comp["type"]: {"name": comp["name"], "shortcut": comp["shortcut"]}
    for comps in COMPONENT_LIBRARY.values()
    for comp in comps
}

# Category colors for visual distinction
CATEGORY_COLORS = {
    "Circuit": "#0f766e",
    "Signal & Control": "#2563eb",
    "Thermal": "#ea580c",
}


def _infer_dark_mode_from_color(color: str) -> bool:
    """Infer dark-mode rendering intent from icon tone."""
    value = QColor(color)
    if not value.isValid():
        return False
    luminance = (0.2126 * value.red()) + (0.7152 * value.green()) + (0.0722 * value.blue())
    return luminance > 140


def create_component_icon(
    comp_type: ComponentType,
    size: int = 48,
    color: str = "#374151",
    dark_mode: bool | None = None,
) -> QPixmap:
    """Render a component icon using the same drawing engine as schematic items."""
    from pulsimgui.views.schematic.items import create_component_item

    dark_mode = _infer_dark_mode_from_color(color) if dark_mode is None else dark_mode
    dpr = 2.0
    app = QApplication.instance()
    if app:
        screen = app.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 2.0

    render_size = int(size * dpr)
    pixmap = QPixmap(render_size, render_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    component = Component(type=comp_type, name="")
    item = create_component_item(component)
    item.set_show_labels(False)
    item.set_show_value_labels(False)
    item.set_dark_mode(dark_mode)

    rect = item.boundingRect().adjusted(-4, -4, 4, 4)
    draw_size = max(size - 4, 1)
    scale = min(draw_size / max(rect.width(), 1), draw_size / max(rect.height(), 1))

    painter.translate(size / 2.0, size / 2.0)
    painter.scale(scale, scale)
    painter.translate(-rect.center())
    item.paint(painter, QStyleOptionGraphicsItem(), None)

    painter.end()
    return pixmap


def _draw_resistor_icon(painter: QPainter) -> None:
    """Draw modern resistor icon - rectangular with color bands."""
    # Body
    body_rect = QRectF(-18, -8, 36, 16)
    painter.setBrush(QColor("#d4c4a8"))
    painter.drawRoundedRect(body_rect, 3, 3)

    # Color bands
    bands = [("#8B4513", -12), ("#FF0000", -6), ("#FFA500", 0), ("#FFD700", 6)]
    painter.setPen(Qt.PenStyle.NoPen)
    for color, x in bands:
        painter.setBrush(QColor(color))
        painter.drawRect(QRectF(x - 2, -8, 4, 16))

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(-28, 0), QPointF(-18, 0))
    painter.drawLine(QPointF(18, 0), QPointF(28, 0))


def _draw_capacitor_icon(painter: QPainter) -> None:
    """Draw modern capacitor icon."""
    # Plates with gradient
    grad1 = QLinearGradient(-6, -14, -6, 14)
    grad1.setColorAt(0, QColor("#a0a0a0"))
    grad1.setColorAt(1, QColor("#606060"))
    painter.setBrush(grad1)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(QRectF(-8, -14, 4, 28))

    grad2 = QLinearGradient(6, -14, 6, 14)
    grad2.setColorAt(0, QColor("#a0a0a0"))
    grad2.setColorAt(1, QColor("#606060"))
    painter.setBrush(grad2)
    painter.drawRect(QRectF(4, -14, 4, 28))

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(-25, 0), QPointF(-8, 0))
    painter.drawLine(QPointF(8, 0), QPointF(25, 0))


def _draw_inductor_icon(painter: QPainter) -> None:
    """Draw modern inductor icon - copper coil."""
    # Coil with copper color
    painter.setPen(QPen(QColor("#b87333"), 3))
    for i in range(4):
        x = -15 + i * 10
        painter.drawArc(QRectF(x, -8, 10, 16), 0, 180 * 16)

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2.5))
    painter.drawLine(QPointF(-25, 0), QPointF(-15, 0))
    painter.drawLine(QPointF(25, 0), QPointF(25, 0))


def _draw_transformer_icon(painter: QPainter) -> None:
    """Draw transformer icon with two coils."""
    # Primary coil
    painter.setPen(QPen(QColor("#b87333"), 2.5))
    for i in range(3):
        y = -12 + i * 12
        painter.drawArc(QRectF(-18, y, 10, 12), 90 * 16, 180 * 16)

    # Secondary coil
    for i in range(3):
        y = -12 + i * 12
        painter.drawArc(QRectF(8, y, 10, 12), -90 * 16, 180 * 16)

    # Core
    painter.setPen(QPen(QColor("#404040"), 2))
    painter.drawLine(QPointF(-4, -18), QPointF(-4, 18))
    painter.drawLine(QPointF(4, -18), QPointF(4, 18))


def _draw_voltage_source_icon(painter: QPainter) -> None:
    """Draw voltage source icon."""
    # Circle with gradient
    grad = QLinearGradient(0, -18, 0, 18)
    grad.setColorAt(0, QColor("#fef3c7"))
    grad.setColorAt(1, QColor("#f59e0b"))
    painter.setBrush(grad)
    painter.setPen(QPen(QColor("#d97706"), 2))
    painter.drawEllipse(QPointF(0, 0), 16, 16)

    # + and - symbols
    painter.setPen(QPen(QColor("#92400e"), 2.5))
    # Plus
    painter.drawLine(QPointF(-8, 0), QPointF(-2, 0))
    painter.drawLine(QPointF(-5, -3), QPointF(-5, 3))
    # Minus
    painter.drawLine(QPointF(2, 0), QPointF(8, 0))


def _draw_current_source_icon(painter: QPainter) -> None:
    """Draw current source icon."""
    # Circle with gradient
    grad = QLinearGradient(0, -18, 0, 18)
    grad.setColorAt(0, QColor("#d1fae5"))
    grad.setColorAt(1, QColor("#10b981"))
    painter.setBrush(grad)
    painter.setPen(QPen(QColor("#059669"), 2))
    painter.drawEllipse(QPointF(0, 0), 16, 16)

    # Arrow
    painter.setPen(QPen(QColor("#065f46"), 2.5))
    painter.drawLine(QPointF(-8, 0), QPointF(8, 0))
    painter.drawLine(QPointF(4, -4), QPointF(8, 0))
    painter.drawLine(QPointF(4, 4), QPointF(8, 0))


def _draw_ground_icon(painter: QPainter) -> None:
    """Draw ground icon."""
    painter.setPen(QPen(QColor("#666666"), 2.5))
    painter.drawLine(QPointF(0, -15), QPointF(0, 0))
    painter.drawLine(QPointF(-14, 0), QPointF(14, 0))
    painter.drawLine(QPointF(-9, 6), QPointF(9, 6))
    painter.drawLine(QPointF(-4, 12), QPointF(4, 12))


def _draw_diode_icon(painter: QPainter) -> None:
    """Draw diode icon with filled triangle."""
    # Triangle (anode)
    path = QPainterPath()
    path.moveTo(-10, 0)
    path.lineTo(8, -12)
    path.lineTo(8, 12)
    path.closeSubpath()

    painter.setPen(QPen(QColor("#1f2937"), 2))
    painter.setBrush(QColor("#374151"))
    painter.drawPath(path)

    # Cathode bar
    painter.setPen(QPen(QColor("#9ca3af"), 3))
    painter.drawLine(QPointF(8, -12), QPointF(8, 12))

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2.5))
    painter.drawLine(QPointF(-25, 0), QPointF(-10, 0))
    painter.drawLine(QPointF(8, 0), QPointF(25, 0))


def _draw_mosfet_icon(painter: QPainter, is_nmos: bool) -> None:
    """Draw MOSFET icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Gate
    painter.setPen(QPen(QColor("#3b82f6"), 2.5))
    painter.drawLine(QPointF(-18, 0), QPointF(-8, 0))
    painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))

    # Channel
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.drawLine(QPointF(-4, -12), QPointF(-4, -6))
    painter.drawLine(QPointF(-4, -3), QPointF(-4, 3))
    painter.drawLine(QPointF(-4, 6), QPointF(-4, 12))

    # D/S connections
    painter.drawLine(QPointF(-4, -9), QPointF(10, -9))
    painter.drawLine(QPointF(10, -9), QPointF(10, -18))
    painter.drawLine(QPointF(-4, 9), QPointF(10, 9))
    painter.drawLine(QPointF(10, 9), QPointF(10, 18))

    # Body
    painter.drawLine(QPointF(-4, 0), QPointF(10, 0))
    painter.drawLine(QPointF(10, 0), QPointF(10, 9))

    # Arrow
    color = "#10b981" if is_nmos else "#ef4444"
    painter.setPen(QPen(QColor(color), 2))
    if is_nmos:
        painter.drawLine(QPointF(2, 0), QPointF(6, -4))
        painter.drawLine(QPointF(2, 0), QPointF(6, 4))
    else:
        painter.drawLine(QPointF(-2, -4), QPointF(2, 0))
        painter.drawLine(QPointF(-2, 4), QPointF(2, 0))


def _draw_igbt_icon(painter: QPainter) -> None:
    """Draw IGBT icon."""
    _draw_mosfet_icon(painter, True)
    painter.setPen(QPen(QColor("#f59e0b"), 2.5))
    painter.drawLine(QPointF(8, -14), QPointF(12, -14))


def _draw_switch_icon(painter: QPainter) -> None:
    """Draw switch icon."""
    # Contacts
    painter.setPen(QPen(QColor("#666666"), 2))
    painter.setBrush(QColor("#fbbf24"))
    painter.drawEllipse(QPointF(-12, 0), 4, 4)
    painter.drawEllipse(QPointF(12, 0), 4, 4)

    # Switch arm
    painter.setPen(QPen(QColor("#78716c"), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(-8, 0), QPointF(8, -12))

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2.5))
    painter.drawLine(QPointF(-25, 0), QPointF(-16, 0))
    painter.drawLine(QPointF(16, 0), QPointF(25, 0))


def _draw_control_block_icon(painter: QPainter, label: str, accent_color: str) -> None:
    """Draw control block icon."""
    rect = QRectF(-18, -14, 36, 28)

    # White fill with border
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(rect, 4, 4)

    # Accent stripe
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(accent_color))
    painter.drawRoundedRect(QRectF(-16, -10, 4, 20), 2, 2)

    # Label
    painter.setPen(QColor("#374151"))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(10)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


def _draw_pwm_icon(painter: QPainter) -> None:
    """Draw PWM icon with waveform."""
    rect = QRectF(-18, -14, 36, 28)

    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(rect, 4, 4)

    # PWM waveform
    painter.setPen(QPen(QColor("#8b5cf6"), 2))
    points = [
        QPointF(-12, 6), QPointF(-12, -6), QPointF(-4, -6), QPointF(-4, 6),
        QPointF(4, 6), QPointF(4, -6), QPointF(12, -6), QPointF(12, 6)
    ]
    for i in range(len(points) - 1):
        painter.drawLine(points[i], points[i + 1])


def _draw_scope_icon(painter: QPainter) -> None:
    """Draw scope icon."""
    # Body
    body = QRectF(-20, -16, 40, 32)
    painter.setPen(QPen(QColor("#1f2937"), 2))
    painter.setBrush(QColor("#1f2937"))
    painter.drawRoundedRect(body, 4, 4)

    # Screen
    screen = QRectF(-16, -12, 32, 24)
    painter.setBrush(QColor("#064e3b"))
    painter.drawRoundedRect(screen, 2, 2)

    # Waveform
    painter.setPen(QPen(QColor("#34d399"), 2))
    points = [QPointF(-12, 4), QPointF(-6, -6), QPointF(0, 2), QPointF(6, -8), QPointF(12, 0)]
    for i in range(len(points) - 1):
        painter.drawLine(points[i], points[i + 1])


def _draw_thermal_scope_icon(painter: QPainter) -> None:
    """Draw thermal scope icon."""
    body = QRectF(-20, -16, 40, 32)
    painter.setPen(QPen(QColor("#1f2937"), 2))
    painter.setBrush(QColor("#1f2937"))
    painter.drawRoundedRect(body, 4, 4)

    # Screen with warm color
    screen = QRectF(-16, -12, 32, 24)
    grad = QLinearGradient(-16, -12, -16, 12)
    grad.setColorAt(0, QColor("#dc2626"))
    grad.setColorAt(0.5, QColor("#f59e0b"))
    grad.setColorAt(1, QColor("#3b82f6"))
    painter.setBrush(grad)
    painter.drawRoundedRect(screen, 2, 2)


def _draw_mux_icon(painter: QPainter) -> None:
    """Draw mux icon - vertical bar style."""
    # Central bar
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#374151"))
    painter.drawRect(QRectF(-4, -16, 8, 32))

    # Input lines
    painter.setPen(QPen(QColor("#374151"), 2))
    for y in [-10, 0, 10]:
        painter.drawLine(QPointF(-20, y), QPointF(-4, y))

    # Output line
    painter.drawLine(QPointF(4, 0), QPointF(20, 0))


def _draw_demux_icon(painter: QPainter) -> None:
    """Draw demux icon - vertical bar style."""
    # Central bar
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#374151"))
    painter.drawRect(QRectF(-4, -16, 8, 32))

    # Input line
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.drawLine(QPointF(-20, 0), QPointF(-4, 0))

    # Output lines
    for y in [-10, 0, 10]:
        painter.drawLine(QPointF(4, y), QPointF(20, y))


# === NEW ICON FUNCTIONS ===

def _draw_zener_icon(painter: QPainter) -> None:
    """Draw Zener diode icon."""
    _draw_diode_icon(painter)
    # Add bent cathode ends
    painter.setPen(QPen(QColor("#9ca3af"), 2))
    painter.drawLine(QPointF(8, -12), QPointF(5, -12))
    painter.drawLine(QPointF(8, 12), QPointF(11, 12))


def _draw_led_icon(painter: QPainter) -> None:
    """Draw LED icon."""
    _draw_diode_icon(painter)
    # Light emission arrows
    painter.setPen(QPen(QColor("#ef4444"), 1.5))
    painter.drawLine(QPointF(0, -10), QPointF(6, -16))
    painter.drawLine(QPointF(6, -16), QPointF(4, -14))
    painter.drawLine(QPointF(4, -10), QPointF(10, -16))
    painter.drawLine(QPointF(10, -16), QPointF(8, -14))


def _draw_bjt_icon(painter: QPainter, is_npn: bool) -> None:
    """Draw BJT transistor icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Base vertical
    painter.setPen(QPen(QColor("#374151"), 3))
    painter.drawLine(QPointF(-6, -10), QPointF(-6, 10))

    # Base terminal
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.drawLine(QPointF(-18, 0), QPointF(-6, 0))

    # Collector
    painter.drawLine(QPointF(-6, -6), QPointF(10, -14))
    painter.drawLine(QPointF(10, -14), QPointF(10, -20))

    # Emitter
    painter.drawLine(QPointF(-6, 6), QPointF(10, 14))
    painter.drawLine(QPointF(10, 14), QPointF(10, 20))

    # Arrow
    color = "#22c55e" if is_npn else "#ef4444"
    painter.setPen(QPen(QColor(color), 2))
    painter.setBrush(QColor(color))
    if is_npn:
        path = QPainterPath()
        path.moveTo(8, 12)
        path.lineTo(4, 8)
        path.lineTo(6, 14)
        path.closeSubpath()
        painter.drawPath(path)
    else:
        path = QPainterPath()
        path.moveTo(-4, 4)
        path.lineTo(0, 8)
        path.lineTo(-2, 2)
        path.closeSubpath()
        painter.drawPath(path)


def _draw_thyristor_icon(painter: QPainter) -> None:
    """Draw thyristor (SCR) icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Terminals
    painter.drawLine(QPointF(0, -20), QPointF(0, -8))
    painter.drawLine(QPointF(0, 8), QPointF(0, 20))

    # Gate
    painter.drawLine(QPointF(-18, 8), QPointF(-6, 8))
    painter.drawLine(QPointF(-6, 8), QPointF(-6, 4))

    # Triangle
    path = QPainterPath()
    path.moveTo(-8, -8)
    path.lineTo(8, -8)
    path.lineTo(0, 6)
    path.closeSubpath()
    painter.setBrush(QColor("#6b7280"))
    painter.drawPath(path)

    # Cathode bar
    painter.drawLine(QPointF(-8, 6), QPointF(8, 6))


def _draw_triac_icon(painter: QPainter) -> None:
    """Draw TRIAC icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Terminals
    painter.drawLine(QPointF(0, -20), QPointF(0, -10))
    painter.drawLine(QPointF(0, 10), QPointF(0, 20))

    # Gate
    painter.drawLine(QPointF(-18, 8), QPointF(-8, 8))
    painter.drawLine(QPointF(-8, 8), QPointF(-8, 0))

    # Two triangles
    painter.setBrush(QColor("#6b7280"))
    # Upper
    path1 = QPainterPath()
    path1.moveTo(-6, -10)
    path1.lineTo(6, -10)
    path1.lineTo(0, 0)
    path1.closeSubpath()
    painter.drawPath(path1)
    # Lower
    path2 = QPainterPath()
    path2.moveTo(-6, 10)
    path2.lineTo(6, 10)
    path2.lineTo(0, 0)
    path2.closeSubpath()
    painter.drawPath(path2)


def _draw_opamp_icon(painter: QPainter) -> None:
    """Draw op-amp icon."""
    # Triangle
    path = QPainterPath()
    path.moveTo(-16, -16)
    path.lineTo(-16, 16)
    path.lineTo(16, 0)
    path.closeSubpath()

    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#f8fafc"))
    painter.drawPath(path)

    # Input symbols
    painter.setPen(QPen(QColor("#22c55e"), 2))
    painter.drawLine(QPointF(-14, -8), QPointF(-10, -8))
    painter.drawLine(QPointF(-12, -10), QPointF(-12, -6))

    painter.setPen(QPen(QColor("#ef4444"), 2))
    painter.drawLine(QPointF(-14, 8), QPointF(-10, 8))


def _draw_comparator_icon(painter: QPainter) -> None:
    """Draw comparator icon."""
    _draw_opamp_icon(painter)
    # Output indicator
    painter.setPen(QPen(QColor("#374151"), 1.5))
    painter.drawRect(QRectF(10, -3, 4, 6))


def _draw_fuse_icon(painter: QPainter) -> None:
    """Draw fuse icon."""
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#f8fafc"))
    painter.drawRect(QRectF(-12, -8, 24, 16))

    # Fuse element
    painter.setPen(QPen(QColor("#9ca3af"), 1.5))
    path = QPainterPath()
    path.moveTo(-10, 0)
    path.cubicTo(-4, -4, 0, 4, 6, -2)
    path.lineTo(10, 0)
    painter.drawPath(path)

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2))
    painter.drawLine(QPointF(-20, 0), QPointF(-12, 0))
    painter.drawLine(QPointF(12, 0), QPointF(20, 0))


def _draw_breaker_icon(painter: QPainter) -> None:
    """Draw circuit breaker icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Contacts
    painter.setBrush(QColor("#fbbf24"))
    painter.drawEllipse(QPointF(-10, 0), 3, 3)
    painter.drawEllipse(QPointF(10, 0), 3, 3)

    # Open arm
    painter.setPen(QPen(QColor("#374151"), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(-10, 0), QPointF(6, -10))

    # Trip indicator
    painter.setPen(QPen(QColor("#ef4444"), 2))
    painter.drawRect(QRectF(-3, -12, 6, 4))

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2))
    painter.drawLine(QPointF(-20, 0), QPointF(-13, 0))
    painter.drawLine(QPointF(13, 0), QPointF(20, 0))


def _draw_relay_icon(painter: QPainter) -> None:
    """Draw relay icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Coil rectangle
    painter.setBrush(QColor("#d4c4a8"))
    painter.drawRect(QRectF(-18, -10, 14, 20))

    # Dashed coupling line
    painter.setPen(QPen(QColor("#374151"), 1, Qt.PenStyle.DashLine))
    painter.drawLine(QPointF(0, -14), QPointF(0, 14))

    # Switch arm
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#fbbf24"))
    painter.drawEllipse(QPointF(10, 0), 3, 3)
    painter.drawLine(QPointF(10, 0), QPointF(16, -10))


def _draw_simple_block_icon(painter: QPainter, comp_type: ComponentType) -> None:
    """Draw simple block icon with label."""
    labels = {
        ComponentType.INTEGRATOR: "∫",
        ComponentType.DIFFERENTIATOR: "d/dt",
        ComponentType.LIMITER: "⊏⊐",
        ComponentType.RATE_LIMITER: "↗",
        ComponentType.HYSTERESIS: "⊂⊃",
        ComponentType.LOOKUP_TABLE: "f(x)",
        ComponentType.TRANSFER_FUNCTION: "H(s)",
        ComponentType.DELAY_BLOCK: "T",
        ComponentType.SAMPLE_HOLD: "S/H",
        ComponentType.STATE_MACHINE: "FSM",
    }
    label = labels.get(comp_type, "?")

    rect = QRectF(-16, -12, 32, 24)
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(rect, 4, 4)

    # Accent stripe
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#8b5cf6"))
    painter.drawRoundedRect(QRectF(-14, -8, 4, 16), 2, 2)

    # Label
    painter.setPen(QColor("#374151"))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(8)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


def _draw_probe_icon(painter: QPainter, symbol: str, color: str) -> None:
    """Draw measurement probe icon."""
    painter.setPen(QPen(QColor("#374151"), 2))
    painter.setBrush(QColor("#fffbeb"))
    painter.drawEllipse(QPointF(0, 0), 14, 14)

    painter.setPen(QPen(QColor(color), 2.5))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(12)
    painter.setFont(font)
    painter.drawText(QRectF(-10, -10, 20, 20), Qt.AlignmentFlag.AlignCenter, symbol)


def _draw_saturable_inductor_icon(painter: QPainter) -> None:
    """Draw saturable inductor icon."""
    _draw_inductor_icon(painter)
    # Filled core line
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#374151"))
    painter.drawRect(QRectF(-12, -2, 24, 4))


def _draw_coupled_inductor_icon(painter: QPainter) -> None:
    """Draw coupled inductor icon."""
    _draw_transformer_icon(painter)


def _draw_snubber_icon(painter: QPainter) -> None:
    """Draw RC snubber icon."""
    painter.setPen(QPen(QColor("#374151"), 2))

    # Resistor part
    painter.setBrush(QColor("#d4c4a8"))
    painter.drawRect(QRectF(-16, -6, 14, 12))

    # Capacitor plates
    painter.setPen(QPen(QColor("#374151"), 2.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(4, -10), QPointF(4, 10))
    painter.drawLine(QPointF(10, -10), QPointF(10, 10))

    # Leads
    painter.setPen(QPen(QColor("#666666"), 2))
    painter.drawLine(QPointF(-22, 0), QPointF(-16, 0))
    painter.drawLine(QPointF(10, 0), QPointF(22, 0))


class ComponentCard(QFrame):
    """A draggable card representing a component."""

    clicked = Signal(ComponentType)
    double_clicked = Signal(ComponentType)

    def __init__(self, comp_type: ComponentType, name: str, shortcut: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ComponentCard")
        self._comp_type = comp_type
        self._name = name
        self._shortcut = shortcut
        self._hovered = False
        self._icon_color = "#374151"
        self._icon_dark_mode = False
        self._theme: Theme | None = None
        self._hover_fill = "rgba(59, 130, 246, 0.1)"
        self._hover_border = "rgba(59, 130, 246, 0.3)"
        self._name_color = "#374151"
        self._badge_bg = "rgba(107, 114, 128, 0.16)"
        self._badge_text = "#6b7280"

        self.setFixedSize(76, 92)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

        self._setup_ui()
        self._update_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 5)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setFixedSize(48, 48)
        self._update_icon()
        layout.addWidget(self._icon_label)

        # Name
        self._name_label = QLabel(self._name)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._name_label.font()
        font.setPointSize(9)
        self._name_label.setFont(font)
        self._name_label.setWordWrap(True)
        layout.addWidget(self._name_label)

        self._shortcut_label = QLabel(self._shortcut)
        self._shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._shortcut_label.setVisible(bool(self._shortcut))
        self._shortcut_label.setObjectName("ComponentShortcutBadge")
        badge_font = self._shortcut_label.font()
        badge_font.setPointSize(7)
        badge_font.setBold(True)
        self._shortcut_label.setFont(badge_font)
        self._shortcut_label.setStyleSheet(
            "color: #6b7280; background: rgba(107, 114, 128, 0.16); "
            "border-radius: 6px; padding: 1px 6px;"
        )
        layout.addWidget(self._shortcut_label)

    def _update_icon(self):
        pixmap = create_component_icon(
            self._comp_type,
            48,
            self._icon_color,
            dark_mode=self._icon_dark_mode,
        )
        self._icon_label.setPixmap(pixmap)

    def _update_style(self):
        if self._hovered:
            self.setStyleSheet(f"""
                QFrame#ComponentCard {{
                    background-color: {self._hover_fill};
                    border: 1px solid {self._hover_border};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet("""
                QFrame#ComponentCard {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 8px;
                }
            """)

    def set_icon_color(self, color: str):
        self._icon_color = color
        self._update_icon()

    def set_icon_theme_mode(self, dark_mode: bool) -> None:
        """Set icon rendering mode to match active UI theme."""
        self._icon_dark_mode = dark_mode
        self._update_icon()

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme-aware card visuals."""
        self._theme = theme
        self._icon_dark_mode = theme.is_dark
        c = theme.colors
        selected = QColor(c.tree_item_selected)
        primary = QColor(c.primary)
        hover_alpha = 72 if theme.is_dark else 48
        border_alpha = 170 if theme.is_dark else 110
        self._hover_fill = (
            f"rgba({selected.red()}, {selected.green()}, {selected.blue()}, {hover_alpha})"
        )
        self._hover_border = (
            f"rgba({primary.red()}, {primary.green()}, {primary.blue()}, {border_alpha})"
        )
        self._name_color = c.foreground
        self._name_label.setStyleSheet(f"color: {self._name_color};")
        badge_bg = QColor(c.tree_item_selected)
        badge_fg = QColor(c.foreground_muted)
        badge_alpha = 115 if theme.is_dark else 150
        self._badge_bg = (
            f"rgba({badge_bg.red()}, {badge_bg.green()}, {badge_bg.blue()}, {badge_alpha})"
        )
        self._badge_text = badge_fg.name()
        self._shortcut_label.setStyleSheet(
            f"color: {self._badge_text}; background: {self._badge_bg}; "
            "border-radius: 6px; padding: 1px 6px;"
        )
        self._update_icon()
        self._update_style()

    def enterEvent(self, event):
        self._hovered = True
        self._update_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._update_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if hasattr(self, '_drag_start_pos'):
                distance = (event.pos() - self._drag_start_pos).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, '_drag_start_pos'):
                distance = (event.pos() - self._drag_start_pos).manhattanLength()
                if distance < QApplication.startDragDistance():
                    self.clicked.emit(self._comp_type)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._comp_type)
        super().mouseDoubleClickEvent(event)

    def _start_drag(self):
        mime_data = QMimeData()
        mime_data.setData(
            "application/x-pulsim-component",
            QByteArray(self._comp_type.name.encode()),
        )

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Create drag pixmap
        pixmap = create_component_icon(
            self._comp_type,
            48,
            self._icon_color,
            dark_mode=self._icon_dark_mode,
        )
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.DropAction.CopyAction)


class CategorySection(QWidget):
    """A collapsible section for a component category."""

    component_clicked = Signal(ComponentType)
    component_double_clicked = Signal(ComponentType)

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self._name = name
        self._color = color
        self._expanded = True
        self._theme: Theme | None = None
        self._cards: list[ComponentCard] = []
        self._icon_color = "#374151"
        self._icon_dark_mode = False
        self._header: QWidget | None = None
        self._color_bar: QFrame | None = None
        self._toggle_btn: QToolButton | None = None
        self._count_label: QLabel | None = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)

        # Header
        self._header = QWidget()
        self._header.setObjectName("CategoryHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 5, 8, 5)
        header_layout.setSpacing(7)

        # Color indicator
        self._color_bar = QFrame()
        self._color_bar.setFixedSize(4, 20)
        header_layout.addWidget(self._color_bar)

        # Category name
        self._title_label = QLabel(self._name)
        self._title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        font = self._title_label.font()
        font.setBold(True)
        font.setPointSize(10)
        self._title_label.setFont(font)
        header_layout.addWidget(self._title_label)

        self._count_label = QLabel("0")
        self._count_label.setObjectName("CategoryCount")
        self._count_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_label.setMinimumWidth(20)
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("CategoryToggle")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setText("▾")
        self._toggle_btn.setAutoRaise(True)
        self._toggle_btn.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self._toggle_btn)

        layout.addWidget(self._header)
        for clickable in (self._header, self._title_label, self._count_label, self._color_bar):
            clickable.installEventFilter(self)

        # Grid container
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(4, 2, 4, 0)
        self._grid_layout.setSpacing(6)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._grid_container)
        self._refresh_header_style()

    def add_component(self, comp_type: ComponentType, name: str, shortcut: str):
        card = ComponentCard(comp_type, name, shortcut)
        card.set_icon_color(self._icon_color)
        card.set_icon_theme_mode(self._icon_dark_mode)
        card.clicked.connect(self.component_clicked.emit)
        card.double_clicked.connect(self.component_double_clicked.emit)

        self._cards.append(card)
        if self._count_label is not None:
            self._count_label.setText(str(len(self._cards)))

        # Add to grid (3 columns)
        row = (len(self._cards) - 1) // 3
        col = (len(self._cards) - 1) % 3
        self._grid_layout.addWidget(card, row, col)

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._grid_container.setVisible(self._expanded)
        if self._toggle_btn is not None:
            self._toggle_btn.setText("▾" if self._expanded else "▸")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonRelease and watched in {
            self._header,
            self._title_label,
            self._count_label,
            self._color_bar,
        }:
            if event.button() == Qt.MouseButton.LeftButton:
                self._toggle_expanded()
                return True
        return super().eventFilter(watched, event)

    def set_icon_color(self, color: str):
        self._icon_color = color
        for card in self._cards:
            card.set_icon_color(color)

    def set_icon_theme_mode(self, dark_mode: bool) -> None:
        self._icon_dark_mode = dark_mode
        for card in self._cards:
            card.set_icon_theme_mode(dark_mode)

    def _refresh_header_style(self, theme: Theme | None = None) -> None:
        """Apply styles to section header and color accent bar."""
        if self._color_bar is not None:
            self._color_bar.setStyleSheet(
                f"background-color: {self._color}; border-radius: 2px;"
            )
        if theme is None or self._header is None:
            self._title_label.setStyleSheet("")
            return

        c = theme.colors
        self._theme = theme
        self._header.setStyleSheet(
            f"background-color: {c.panel_header}; border: 1px solid {c.panel_border}; border-radius: 6px;"
        )
        self._title_label.setStyleSheet(f"color: {c.foreground};")
        if self._count_label is not None:
            self._count_label.setStyleSheet(
                f"color: {c.foreground_muted}; background-color: {c.tree_item_hover}; "
                "border-radius: 5px; padding: 0 5px; font-size: 10px;"
            )
        if self._toggle_btn is not None:
            self._toggle_btn.setStyleSheet(
                f"QToolButton {{ color: {c.foreground_muted}; border: none; padding: 0 2px; }}"
                f"QToolButton:hover {{ color: {c.foreground}; }}"
            )

    def apply_theme(self, theme: Theme, accent_color: str, icon_color: str) -> None:
        """Apply theme to section and nested component cards."""
        self._color = accent_color
        self._icon_color = icon_color
        self._icon_dark_mode = theme.is_dark
        self._refresh_header_style(theme)
        for card in self._cards:
            card.set_icon_theme_mode(theme.is_dark)
            card.set_icon_color(icon_color)
            card.apply_theme(theme)

    def filter_components(self, search_text: str) -> bool:
        """Filter components by search text. Returns True if any visible."""
        search_lower = search_text.lower()
        any_visible = False
        visible_count = 0

        for card in self._cards:
            visible = not search_text or search_lower in card._name.lower()
            card.setVisible(visible)
            if visible:
                any_visible = True
                visible_count += 1

        if search_text and any_visible and not self._expanded:
            self._expanded = True
            self._grid_container.setVisible(True)
            if self._toggle_btn is not None:
                self._toggle_btn.setText("▾")
        if self._count_label is not None:
            if search_text:
                self._count_label.setText(f"{visible_count}/{len(self._cards)}")
            else:
                self._count_label.setText(str(len(self._cards)))
        self.setVisible(any_visible or not search_text)
        return any_visible


class LibraryPanel(QWidget):
    """Panel displaying component library with grid cards."""

    component_selected = Signal(ComponentType)
    component_double_clicked = Signal(ComponentType)

    def __init__(self, theme_service: ThemeService | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryPanelRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._theme_service = theme_service
        self._theme: Theme | None = None
        self._icon_color = "#374151"
        self._sections: list[CategorySection] = []
        self._recent: list[ComponentType] = []
        self._max_recent = 5
        self._scroll: QScrollArea | None = None
        self._search_action = None
        self._summary_label: QLabel | None = None
        self._total_components = 0

        self._setup_ui()
        self._populate_components()

        if self._theme_service:
            self._theme_service.theme_changed.connect(self._on_theme_changed)
            self.apply_theme(self._theme_service.current_theme)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title_row = QWidget()
        title_row.setObjectName("LibraryTitleRow")
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(6)

        title = QLabel("Component Library")
        title.setObjectName("LibraryPanelTitle")
        title_layout.addWidget(title)
        title_layout.addStretch()

        self._summary_label = QLabel("")
        self._summary_label.setObjectName("LibrarySummaryLabel")
        title_layout.addWidget(self._summary_label)
        layout.addWidget(title_row)

        # Search bar
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search component or function...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        search_icon = IconService.get_icon("search", "#9ca3af", 16)
        self._search_action = self._search_edit.addAction(
            search_icon, QLineEdit.ActionPosition.LeadingPosition
        )
        layout.addWidget(self._search_edit)

        # Scroll area for categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content.setObjectName("LibraryContentRoot")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)
        self._scroll = scroll

    def _populate_components(self):
        for category, components in COMPONENT_LIBRARY.items():
            color = CATEGORY_COLORS.get(category, "#6b7280")
            section = CategorySection(category, color)
            section.set_icon_color(self._icon_color)
            section.component_clicked.connect(self._on_component_clicked)
            section.component_double_clicked.connect(self._on_component_double_clicked)

            for comp in components:
                section.add_component(comp["type"], comp["name"], comp["shortcut"])
                self._total_components += 1

            self._sections.append(section)
            self._content_layout.insertWidget(self._content_layout.count() - 1, section)
        self._update_summary_label()

    def _on_search_changed(self, text: str):
        visible_count = 0
        for section in self._sections:
            if section.filter_components(text):
                visible_count += sum(1 for card in section._cards if card.isVisible())
        self._update_summary_label(visible_count if text else self._total_components)

    def _update_summary_label(self, visible_count: int | None = None) -> None:
        if self._summary_label is None:
            return
        count = self._total_components if visible_count is None else visible_count
        if self._search_edit is not None and self._search_edit.text():
            self._summary_label.setText(f"{count} matching")
        else:
            self._summary_label.setText(f"{count} components")

    def _on_component_clicked(self, comp_type: ComponentType):
        self.component_selected.emit(comp_type)

    def _on_component_double_clicked(self, comp_type: ComponentType):
        self.add_to_recent(comp_type)
        self.component_double_clicked.emit(comp_type)

    def add_to_recent(self, comp_type: ComponentType):
        if comp_type in self._recent:
            self._recent.remove(comp_type)
        self._recent.insert(0, comp_type)
        self._recent = self._recent[:self._max_recent]

    @staticmethod
    def _category_color_for_theme(category: str, theme: Theme) -> str:
        """Normalize category accent brightness for active theme."""
        base = QColor(CATEGORY_COLORS.get(category, "#6b7280"))
        return base.lighter(135).name() if theme.is_dark else base.darker(105).name()

    def _on_theme_changed(self, theme: Theme) -> None:
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to library panel and all category sections."""
        self._theme = theme
        c = theme.colors
        self._icon_color = c.foreground_muted
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(c.panel_background))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        if self._search_action is not None:
            self._search_action.setIcon(IconService.get_icon("search", c.input_placeholder, 16))
        if self._scroll is not None:
            self._scroll.viewport().setStyleSheet(f"background-color: {c.panel_background};")

        self.setStyleSheet(f"""
            QWidget#LibraryPanelRoot {{
                background-color: {c.panel_background};
            }}
            QWidget#LibraryTitleRow {{
                background-color: {c.panel_header};
                border: 1px solid {c.panel_border};
                border-radius: 6px;
                padding: 4px 6px;
            }}
            QLabel#LibraryPanelTitle {{
                color: {c.foreground};
                font-weight: 600;
                font-size: 12px;
            }}
            QLabel#LibrarySummaryLabel {{
                color: {c.foreground_muted};
                background-color: {c.tree_item_hover};
                border-radius: 5px;
                padding: 1px 7px;
                font-size: 10px;
                font-weight: 500;
            }}
            QWidget#LibraryContentRoot {{
                background-color: {c.panel_background};
            }}
            QLineEdit {{
                background-color: {c.input_background};
                border: 1px solid {c.input_border};
                border-radius: 6px;
                padding: 7px 8px;
                color: {c.foreground};
            }}
            QLineEdit:focus {{
                border-color: {c.input_focus_border};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QWidget {{
                color: {c.foreground};
            }}
        """)

        for section in self._sections:
            accent = self._category_color_for_theme(section._name, theme)
            section.apply_theme(theme, accent_color=accent, icon_color=self._icon_color)
