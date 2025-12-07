"""Base class for component graphics items."""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pulsimgui.models.component import Component, ComponentType


class ComponentItem(QGraphicsItem):
    """
    Base graphics item for circuit components.

    Handles:
    - Selection highlighting
    - Rotation and mirroring
    - Pin markers
    - Name and value labels
    - DC operating point overlay
    """

    # Drawing settings
    LINE_WIDTH = 2.0
    LINE_COLOR = QColor(0, 0, 0)
    LINE_COLOR_DARK = QColor(220, 220, 220)
    SELECTED_COLOR = QColor(0, 120, 215)
    PIN_RADIUS = 3.0
    PIN_COLOR = QColor(200, 0, 0)
    DC_OVERLAY_COLOR = QColor(0, 128, 0)  # Green for DC values
    DC_OVERLAY_COLOR_DARK = QColor(100, 220, 100)

    def __init__(self, component: Component, parent: QGraphicsItem | None = None):
        super().__init__(parent)

        self._component = component
        self._dark_mode = False
        self._show_labels = True
        self._show_dc_overlay = False
        self._dc_voltage: float | None = None
        self._dc_current: float | None = None
        self._dc_power: float | None = None

        # Enable item features
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Set position from component
        self.setPos(component.x, component.y)

        # Apply rotation
        self.setRotation(component.rotation)

        # Create labels
        self._name_label = QGraphicsTextItem(component.name, self)
        self._name_label.setDefaultTextColor(self.LINE_COLOR)
        self._value_label = QGraphicsTextItem("", self)
        self._value_label.setDefaultTextColor(QColor(100, 100, 100))

        # Create DC overlay label
        self._dc_label = QGraphicsTextItem("", self)
        self._dc_label.setDefaultTextColor(self.DC_OVERLAY_COLOR)
        font = self._dc_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() - 1)
        self._dc_label.setFont(font)
        self._dc_label.setVisible(False)

        self._update_labels()

    @property
    def component(self) -> Component:
        """Get the associated component model."""
        return self._component

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode colors."""
        self._dark_mode = dark
        color = self.LINE_COLOR_DARK if dark else self.LINE_COLOR
        self._name_label.setDefaultTextColor(color)
        dc_color = self.DC_OVERLAY_COLOR_DARK if dark else self.DC_OVERLAY_COLOR
        self._dc_label.setDefaultTextColor(dc_color)
        self.update()

    def set_show_labels(self, show: bool) -> None:
        """Set label visibility."""
        self._show_labels = show
        self._name_label.setVisible(show)
        self._value_label.setVisible(show)

    def set_show_dc_overlay(self, show: bool) -> None:
        """Set DC overlay visibility."""
        self._show_dc_overlay = show
        self._update_dc_label()

    def set_dc_values(
        self,
        voltage: float | None = None,
        current: float | None = None,
        power: float | None = None,
    ) -> None:
        """Set DC operating point values for this component."""
        self._dc_voltage = voltage
        self._dc_current = current
        self._dc_power = power
        self._update_dc_label()

    def clear_dc_values(self) -> None:
        """Clear DC operating point values."""
        self._dc_voltage = None
        self._dc_current = None
        self._dc_power = None
        self._update_dc_label()

    def _update_dc_label(self) -> None:
        """Update the DC overlay label content and visibility."""
        from pulsimgui.utils.si_prefix import format_si_value

        if not self._show_dc_overlay:
            self._dc_label.setVisible(False)
            return

        # Build label text from available values
        parts = []
        if self._dc_current is not None:
            parts.append(format_si_value(self._dc_current, "A"))
        if self._dc_power is not None:
            parts.append(format_si_value(self._dc_power, "W"))

        if parts:
            self._dc_label.setPlainText(" | ".join(parts))
            self._dc_label.setVisible(True)
            # Position to the right of the component
            rect = self.boundingRect()
            self._dc_label.setPos(rect.right() + 5, rect.center().y() - 8)
        else:
            self._dc_label.setVisible(False)

    def get_pin_position(self, pin_index: int) -> QPointF:
        """Get scene position of a pin."""
        if pin_index >= len(self._component.pins):
            return self.scenePos()

        pin = self._component.pins[pin_index]
        local_pos = QPointF(pin.x, pin.y)

        # Apply mirroring
        if self._component.mirrored_h:
            local_pos.setX(-local_pos.x())
        if self._component.mirrored_v:
            local_pos.setY(-local_pos.y())

        return self.mapToScene(local_pos)

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle - to be overridden by subclasses."""
        return QRectF(-40, -30, 80, 60)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the component - to be overridden by subclasses."""
        self._setup_painter(painter)
        self._draw_symbol(painter)
        self._draw_pins(painter)

        if self.isSelected():
            self._draw_selection(painter)

    def _setup_painter(self, painter: QPainter) -> None:
        """Set up painter with standard settings."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        painter.setPen(QPen(color, self.LINE_WIDTH))

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw the component symbol - override in subclasses."""
        # Default: draw a rectangle
        painter.drawRect(-20, -15, 40, 30)

    def _draw_pins(self, painter: QPainter) -> None:
        """Draw pin markers."""
        painter.setPen(QPen(self.PIN_COLOR, 1))
        painter.setBrush(QBrush(self.PIN_COLOR))

        for pin in self._component.pins:
            x, y = pin.x, pin.y
            if self._component.mirrored_h:
                x = -x
            if self._component.mirrored_v:
                y = -y
            painter.drawEllipse(QPointF(x, y), self.PIN_RADIUS, self.PIN_RADIUS)

    def _draw_selection(self, painter: QPainter) -> None:
        """Draw selection highlight."""
        painter.setPen(QPen(self.SELECTED_COLOR, 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = self.boundingRect()
        painter.drawRect(rect.adjusted(-2, -2, 2, 2))

    def _update_labels(self) -> None:
        """Update label positions and content."""
        rect = self.boundingRect()

        # Position name above component
        self._name_label.setPos(rect.center().x() - 15, rect.top() - 20)

        # Position value below component
        value_text = self._get_value_text()
        self._value_label.setPlainText(value_text)
        self._value_label.setPos(rect.center().x() - 15, rect.bottom() + 2)

    def _get_value_text(self) -> str:
        """Get the value text for display - override in subclasses."""
        return ""

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        """Handle item changes."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Snap position to grid before applying
            scene = self.scene()
            if scene is not None:
                new_pos = value  # QPointF
                snapped_pos = scene.snap_to_grid(new_pos)
                return snapped_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update component model position
            pos = self.pos()
            self._component.x = pos.x()
            self._component.y = pos.y()
        return super().itemChange(change, value)


class ResistorItem(ComponentItem):
    """Graphics item for resistor."""

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -15, 70, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw resistor zigzag symbol."""
        # Draw zigzag
        points = [
            (-30, 0), (-20, 0), (-17, -10), (-11, 10), (-5, -10),
            (1, 10), (7, -10), (13, 10), (17, 0), (30, 0)
        ]
        for i in range(len(points) - 1):
            painter.drawLine(
                QPointF(points[i][0], points[i][1]),
                QPointF(points[i + 1][0], points[i + 1][1])
            )

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        resistance = self._component.parameters.get("resistance", 0)
        return format_si_value(resistance, "Ω")


class CapacitorItem(ComponentItem):
    """Graphics item for capacitor."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -20, 50, 40)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw capacitor symbol (two parallel plates)."""
        # Lead lines
        painter.drawLine(QPointF(-20, 0), QPointF(-5, 0))
        painter.drawLine(QPointF(5, 0), QPointF(20, 0))

        # Plates
        painter.drawLine(QPointF(-5, -15), QPointF(-5, 15))
        painter.drawLine(QPointF(5, -15), QPointF(5, 15))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        capacitance = self._component.parameters.get("capacitance", 0)
        return format_si_value(capacitance, "F")


class InductorItem(ComponentItem):
    """Graphics item for inductor."""

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -15, 70, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw inductor coil symbol."""
        from PySide6.QtCore import QRectF as QR

        # Lead lines
        painter.drawLine(QPointF(-30, 0), QPointF(-20, 0))
        painter.drawLine(QPointF(20, 0), QPointF(30, 0))

        # Coil arcs
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(4):
            x = -15 + i * 10
            painter.drawArc(QR(x, -8, 10, 16), 0, 180 * 16)

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        inductance = self._component.parameters.get("inductance", 0)
        return format_si_value(inductance, "H")


class VoltageSourceItem(ComponentItem):
    """Graphics item for voltage source."""

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -30, 40, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw voltage source circle with +/- symbols."""
        # Circle
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        # Lead lines
        painter.drawLine(QPointF(0, -25), QPointF(0, -15))
        painter.drawLine(QPointF(0, 15), QPointF(0, 25))

        # Plus sign (top)
        painter.drawLine(QPointF(-5, -8), QPointF(5, -8))
        painter.drawLine(QPointF(0, -13), QPointF(0, -3))

        # Minus sign (bottom)
        painter.drawLine(QPointF(-5, 8), QPointF(5, 8))


class CurrentSourceItem(ComponentItem):
    """Graphics item for current source."""

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -30, 40, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw current source circle with arrow."""
        # Circle
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        # Lead lines
        painter.drawLine(QPointF(0, -25), QPointF(0, -15))
        painter.drawLine(QPointF(0, 15), QPointF(0, 25))

        # Arrow (pointing up)
        painter.drawLine(QPointF(0, 10), QPointF(0, -10))
        painter.drawLine(QPointF(0, -10), QPointF(-4, -4))
        painter.drawLine(QPointF(0, -10), QPointF(4, -4))


class GroundItem(ComponentItem):
    """Graphics item for ground symbol."""

    def boundingRect(self) -> QRectF:
        return QRectF(-15, -15, 30, 25)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw ground symbol (three horizontal lines)."""
        painter.drawLine(QPointF(0, -10), QPointF(0, 0))
        painter.drawLine(QPointF(-12, 0), QPointF(12, 0))
        painter.drawLine(QPointF(-8, 5), QPointF(8, 5))
        painter.drawLine(QPointF(-4, 10), QPointF(4, 10))


class DiodeItem(ComponentItem):
    """Graphics item for diode."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -15, 50, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw diode symbol (triangle with bar)."""
        # Lead lines
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        # Triangle (pointing right)
        from PySide6.QtGui import QPolygonF
        triangle = QPolygonF([
            QPointF(-8, -12),
            QPointF(-8, 12),
            QPointF(8, 0),
        ])
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(triangle)

        # Bar (cathode)
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))


class MOSFETItem(ComponentItem):
    """Graphics item for MOSFET (N or P channel)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -25, 50, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw MOSFET symbol."""
        is_nmos = self._component.type == ComponentType.MOSFET_N

        # Gate line
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(-8, -10), QPointF(-8, 10))

        # Channel
        painter.drawLine(QPointF(-4, -15), QPointF(-4, -8))
        painter.drawLine(QPointF(-4, -3), QPointF(-4, 3))
        painter.drawLine(QPointF(-4, 8), QPointF(-4, 15))

        # Drain/Source connections
        painter.drawLine(QPointF(-4, -12), QPointF(15, -12))  # to D
        painter.drawLine(QPointF(15, -12), QPointF(15, -20))
        painter.drawLine(QPointF(-4, 12), QPointF(15, 12))    # to S
        painter.drawLine(QPointF(15, 12), QPointF(15, 20))

        # Body connection and arrow
        painter.drawLine(QPointF(-4, 0), QPointF(15, 0))
        painter.drawLine(QPointF(15, 0), QPointF(15, 12))

        # Arrow (direction indicates N or P)
        if is_nmos:
            # Arrow pointing into channel
            painter.drawLine(QPointF(-4, 0), QPointF(4, 0))
            painter.drawLine(QPointF(2, -3), QPointF(4, 0))
            painter.drawLine(QPointF(2, 3), QPointF(4, 0))
        else:
            # Arrow pointing out of channel
            painter.drawLine(QPointF(4, 0), QPointF(-4, 0))
            painter.drawLine(QPointF(-2, -3), QPointF(-4, 0))
            painter.drawLine(QPointF(-2, 3), QPointF(-4, 0))


class SwitchItem(ComponentItem):
    """Graphics item for ideal switch."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -15, 50, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw switch symbol."""
        # Lead lines
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        # Switch contacts
        painter.drawEllipse(QPointF(-8, 0), 3, 3)
        painter.drawEllipse(QPointF(8, 0), 3, 3)

        # Switch arm (open position)
        painter.drawLine(QPointF(-8, 0), QPointF(6, -10))


class IGBTItem(ComponentItem):
    """Graphics item for IGBT (Insulated Gate Bipolar Transistor)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -25, 50, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw IGBT symbol (similar to MOSFET but with BJT-style collector)."""
        # Gate line (insulated)
        painter.drawLine(QPointF(-20, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(-10, -10), QPointF(-10, 10))

        # Gate insulation gap
        painter.drawLine(QPointF(-6, -12), QPointF(-6, 12))

        # Emitter connection (bottom)
        painter.drawLine(QPointF(-6, 10), QPointF(10, 10))
        painter.drawLine(QPointF(10, 10), QPointF(10, 20))

        # Collector connection (top)
        painter.drawLine(QPointF(-6, -10), QPointF(10, -10))
        painter.drawLine(QPointF(10, -10), QPointF(10, -20))

        # Arrow on emitter (pointing outward for NPN-like IGBT)
        painter.drawLine(QPointF(-6, 5), QPointF(5, 12))
        painter.drawLine(QPointF(5, 12), QPointF(1, 8))
        painter.drawLine(QPointF(5, 12), QPointF(1, 14))


class TransformerItem(ComponentItem):
    """Graphics item for transformer."""

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -25, 70, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw transformer symbol (two coupled inductors with core)."""
        from PySide6.QtCore import QRectF as QR

        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Primary winding (left side) - 3 arcs
        painter.drawLine(QPointF(-30, -15), QPointF(-15, -15))
        for i in range(3):
            y = -10 + i * 10
            painter.drawArc(QR(-15, y - 5, 10, 10), 90 * 16, 180 * 16)
        painter.drawLine(QPointF(-30, 15), QPointF(-15, 15))

        # Core lines (two vertical parallel lines)
        painter.drawLine(QPointF(-3, -18), QPointF(-3, 18))
        painter.drawLine(QPointF(3, -18), QPointF(3, 18))

        # Secondary winding (right side) - 3 arcs
        painter.drawLine(QPointF(30, -15), QPointF(15, -15))
        for i in range(3):
            y = -10 + i * 10
            painter.drawArc(QR(5, y - 5, 10, 10), 270 * 16, 180 * 16)
        painter.drawLine(QPointF(30, 15), QPointF(15, 15))

    def _get_value_text(self) -> str:
        turns_ratio = self._component.parameters.get("turns_ratio", 1.0)
        return f"1:{turns_ratio}"


class SubcircuitItem(ComponentItem):
    """Graphics item for subcircuit instances."""

    def __init__(self, component: Component, parent: QGraphicsItem | None = None):
        self._symbol_width = float(component.parameters.get("symbol_width", 120.0))
        self._symbol_height = float(component.parameters.get("symbol_height", 80.0))
        super().__init__(component, parent)
        self._name_label.setVisible(False)
        self._value_label.setVisible(False)

    def boundingRect(self) -> QRectF:
        half_w = self._symbol_width / 2
        half_h = self._symbol_height / 2
        return QRectF(-half_w, -half_h, self._symbol_width, self._symbol_height)

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()
        painter.drawRect(rect)

        # Draw title centered inside block
        painter.save()
        painter.setFont(self._name_label.font())
        painter.drawText(rect.adjusted(4, 4, -4, -4), Qt.AlignmentFlag.AlignCenter, self._component.name)
        painter.restore()


class BlockComponentItem(ComponentItem):
    """Base class for rectangular control block style components."""

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -25, 80, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()
        painter.drawRect(rect)
        painter.save()
        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.block_label())
        painter.restore()

    def block_label(self) -> str:
        return self._component.type.name


class PIControllerItem(BlockComponentItem):
    """Item for PI controller block."""

    def block_label(self) -> str:
        return "PI"

    def _get_value_text(self) -> str:
        kp = self._component.parameters.get("kp", 0.0)
        ki = self._component.parameters.get("ki", 0.0)
        return f"Kp={kp:g} Ki={ki:g}"


class PIDControllerItem(BlockComponentItem):
    """Item for PID controller block."""

    def block_label(self) -> str:
        return "PID"

    def _get_value_text(self) -> str:
        kp = self._component.parameters.get("kp", 0.0)
        ki = self._component.parameters.get("ki", 0.0)
        kd = self._component.parameters.get("kd", 0.0)
        return f"Kp={kp:g} Ki={ki:g} Kd={kd:g}"


class MathBlockItem(BlockComponentItem):
    """Item for generic math block."""

    def block_label(self) -> str:
        operation = self._component.parameters.get("operation", "Σ")
        return operation.upper() if len(operation) <= 3 else operation[:3].upper()

    def _get_value_text(self) -> str:
        operation = self._component.parameters.get("operation", "sum")
        gain = self._component.parameters.get("gain", 1.0)
        return f"{operation} · {gain:g}"


class PWMGeneratorItem(BlockComponentItem):
    """Item for PWM generator block."""

    def block_label(self) -> str:
        return "PWM"

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value

        freq = self._component.parameters.get("frequency", 0.0)
        duty = self._component.parameters.get("duty_cycle", 0.0) * 100.0
        freq_text = format_si_value(freq, "Hz") if freq else "0 Hz"
        return f"{freq_text} / {duty:.0f}%"


# Factory function to create appropriate item type
def create_component_item(component: Component) -> ComponentItem:
    """Create the appropriate graphics item for a component."""
    item_classes = {
        ComponentType.RESISTOR: ResistorItem,
        ComponentType.CAPACITOR: CapacitorItem,
        ComponentType.INDUCTOR: InductorItem,
        ComponentType.VOLTAGE_SOURCE: VoltageSourceItem,
        ComponentType.CURRENT_SOURCE: CurrentSourceItem,
        ComponentType.GROUND: GroundItem,
        ComponentType.DIODE: DiodeItem,
        ComponentType.MOSFET_N: MOSFETItem,
        ComponentType.MOSFET_P: MOSFETItem,
        ComponentType.IGBT: IGBTItem,
        ComponentType.SWITCH: SwitchItem,
        ComponentType.TRANSFORMER: TransformerItem,
        ComponentType.PI_CONTROLLER: PIControllerItem,
        ComponentType.PID_CONTROLLER: PIDControllerItem,
        ComponentType.MATH_BLOCK: MathBlockItem,
        ComponentType.PWM_GENERATOR: PWMGeneratorItem,
        ComponentType.SUBCIRCUIT: SubcircuitItem,
    }

    item_class = item_classes.get(component.type, ComponentItem)
    return item_class(component)
