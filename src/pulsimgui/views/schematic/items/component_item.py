"""Base class for component graphics items."""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QBrush,
    QFont,
    QTransform,
    QRadialGradient,
    QLinearGradient,
    QPainterPath,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QGraphicsDropShadowEffect,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pulsimgui.models.component import Component, ComponentType


class ComponentItem(QGraphicsItem):
    """
    Base graphics item for circuit components.

    Handles:
    - Selection highlighting with glow effect
    - Hover highlighting
    - Rotation and mirroring
    - Pin markers
    - Name and value labels
    - DC operating point overlay
    """

    # Drawing settings
    LINE_WIDTH = 2.0
    LINE_COLOR = QColor(0, 0, 0)
    LINE_COLOR_DARK = QColor(220, 220, 220)
    SELECTED_COLOR = QColor(59, 130, 246)  # Bright blue for selection
    SELECTED_FILL = QColor(59, 130, 246, 30)  # Semi-transparent blue fill
    HOVER_COLOR = QColor(147, 197, 253)  # Light blue on hover
    HOVER_FILL = QColor(147, 197, 253, 20)  # Very subtle hover fill
    PIN_RADIUS = 3.5  # Slightly larger pins
    PIN_COLOR = QColor(220, 38, 38)  # Brighter red
    PIN_HOVER_COLOR = QColor(255, 100, 100)  # Brighter red on hover
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
        self._hovered = False

        # Enable item features
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)  # Enable hover events

        # Set position from component
        self.setPos(component.x, component.y)

        # Apply rotation
        self.setRotation(component.rotation)

        # Create labels as child items
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

    def update_transform(self) -> None:
        """Update the item transform based on component mirror state."""
        # Force repaint to apply mirror
        self.prepareGeometryChange()
        self._update_labels()
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
        # Draw hover/selection backgrounds first (behind component)
        if self._hovered and not self.isSelected():
            self._draw_hover(painter)

        self._setup_painter(painter)

        # Apply mirror transformation
        painter.save()
        scale_x = -1 if self._component.mirrored_h else 1
        scale_y = -1 if self._component.mirrored_v else 1
        painter.scale(scale_x, scale_y)

        self._draw_symbol(painter)
        painter.restore()

        # Draw pins without mirror (they're already handled)
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
        rect = self.boundingRect()

        # Draw semi-transparent fill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.SELECTED_FILL))
        painter.drawRoundedRect(rect, 4, 4)

        # Draw solid border
        painter.setPen(QPen(self.SELECTED_COLOR, 2, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 4, 4)

    def _draw_hover(self, painter: QPainter) -> None:
        """Draw hover highlight (subtle)."""
        if self.isSelected():
            return  # Don't draw hover if already selected

        rect = self.boundingRect()

        # Draw subtle fill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.HOVER_FILL))
        painter.drawRoundedRect(rect, 3, 3)

        # Draw subtle border
        painter.setPen(QPen(self.HOVER_COLOR, 1, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 3, 3)

    def hoverEnterEvent(self, event) -> None:
        """Handle hover enter."""
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        """Handle hover leave."""
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

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
            # Notify scene to update connected wires
            scene = self.scene()
            if scene is not None and hasattr(scene, 'update_connected_wires'):
                scene.update_connected_wires(self)
        return super().itemChange(change, value)


class ResistorItem(ComponentItem):
    """Graphics item for resistor - modern rectangular style."""

    # Color bands inspired design
    BODY_COLOR = QColor(210, 180, 140)  # Tan/beige body
    BODY_DARK = QColor(180, 150, 110)
    BAND_COLORS = [
        QColor(139, 69, 19),   # Brown
        QColor(220, 20, 60),   # Red
        QColor(255, 140, 0),   # Orange
        QColor(255, 215, 0),   # Gold
    ]

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -12, 70, 24)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern rectangular resistor with color bands."""
        # Lead wires
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-35, 0), QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), QPointF(35, 0))

        # Resistor body with gradient
        body_rect = QRectF(-18, -10, 36, 20)
        body_gradient = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
        body_gradient.setColorAt(0, self.BODY_COLOR)
        body_gradient.setColorAt(0.5, self.BODY_DARK)
        body_gradient.setColorAt(1, self.BODY_COLOR)

        painter.setPen(QPen(QColor(120, 100, 80), 1.5))
        painter.setBrush(body_gradient)
        painter.drawRoundedRect(body_rect, 3, 3)

        # Color bands
        band_width = 4
        band_positions = [-12, -4, 4, 12]
        for i, pos in enumerate(band_positions):
            band_rect = QRectF(pos - band_width/2, -8, band_width, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.BAND_COLORS[i % len(self.BAND_COLORS)])
            painter.drawRect(band_rect)

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        resistance = self._component.parameters.get("resistance", 0)
        return format_si_value(resistance, "Ω")


class CapacitorItem(ComponentItem):
    """Graphics item for capacitor - modern electrolytic style."""

    PLATE_COLOR = QColor(70, 130, 180)  # Steel blue plates
    PLATE_GRADIENT_LIGHT = QColor(100, 160, 210)

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -18, 50, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern capacitor with metallic plates."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Lead wires
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-25, 0), QPointF(-6, 0))
        painter.drawLine(QPointF(6, 0), QPointF(25, 0))

        # Left plate (solid metallic look)
        left_plate = QRectF(-6, -14, 4, 28)
        plate_grad = QLinearGradient(left_plate.topLeft(), left_plate.topRight())
        plate_grad.setColorAt(0, self.PLATE_GRADIENT_LIGHT)
        plate_grad.setColorAt(0.5, self.PLATE_COLOR)
        plate_grad.setColorAt(1, self.PLATE_GRADIENT_LIGHT)

        painter.setPen(QPen(QColor(50, 100, 140), 1))
        painter.setBrush(plate_grad)
        painter.drawRect(left_plate)

        # Right plate (slightly curved for polarized look)
        painter.setPen(QPen(line_color, 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Draw curved plate using arc
        path = QPainterPath()
        path.moveTo(6, -14)
        path.quadTo(10, 0, 6, 14)
        painter.drawPath(path)

        # Plus sign indicator (for polarized)
        painter.setPen(QPen(line_color, 1.5))
        painter.drawLine(QPointF(-16, -6), QPointF(-12, -6))
        painter.drawLine(QPointF(-14, -8), QPointF(-14, -4))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        capacitance = self._component.parameters.get("capacitance", 0)
        return format_si_value(capacitance, "F")


class InductorItem(ComponentItem):
    """Graphics item for inductor - modern coil with core style."""

    COIL_COLOR = QColor(180, 100, 50)  # Copper color
    COIL_HIGHLIGHT = QColor(220, 150, 80)
    CORE_COLOR = QColor(80, 80, 85)  # Ferrite core

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -14, 70, 28)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern inductor with copper coil appearance."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Lead wires
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-35, 0), QPointF(-22, 0))
        painter.drawLine(QPointF(22, 0), QPointF(35, 0))

        # Draw coil loops with 3D effect
        painter.setBrush(Qt.BrushStyle.NoBrush)
        num_loops = 4
        loop_width = 11
        start_x = -22

        for i in range(num_loops):
            x = start_x + i * loop_width
            # Back of coil (darker)
            painter.setPen(QPen(self.COIL_COLOR, 3))
            arc_rect = QRectF(x, -10, loop_width, 20)
            painter.drawArc(arc_rect, 0, 180 * 16)

            # Front of coil (lighter/highlight)
            painter.setPen(QPen(self.COIL_HIGHLIGHT, 2.5))
            painter.drawArc(arc_rect, 180 * 16, 180 * 16)

        # Core line (ferrite)
        painter.setPen(QPen(self.CORE_COLOR, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(-18, 0), QPointF(18, 0))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        inductance = self._component.parameters.get("inductance", 0)
        return format_si_value(inductance, "H")


class VoltageSourceItem(ComponentItem):
    """Graphics item for voltage source - modern battery/DC style."""

    POSITIVE_COLOR = QColor(220, 60, 60)  # Red for positive
    NEGATIVE_COLOR = QColor(60, 60, 180)  # Blue for negative

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -30, 40, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern voltage source with gradient circle."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Lead wires
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(0, -30), QPointF(0, -16))
        painter.drawLine(QPointF(0, 16), QPointF(0, 30))

        # Circle with gradient fill
        circle_grad = QRadialGradient(QPointF(0, 0), 16)
        circle_grad.setColorAt(0, QColor(255, 255, 255, 80))
        circle_grad.setColorAt(0.7, QColor(240, 240, 240, 40))
        circle_grad.setColorAt(1, QColor(200, 200, 200, 60))

        painter.setPen(QPen(line_color, 2))
        painter.setBrush(circle_grad)
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        # Plus sign (top) - red
        painter.setPen(QPen(self.POSITIVE_COLOR, 2.5))
        painter.drawLine(QPointF(-5, -7), QPointF(5, -7))
        painter.drawLine(QPointF(0, -12), QPointF(0, -2))

        # Minus sign (bottom) - blue
        painter.setPen(QPen(self.NEGATIVE_COLOR, 2.5))
        painter.drawLine(QPointF(-5, 7), QPointF(5, 7))


class CurrentSourceItem(ComponentItem):
    """Graphics item for current source - modern style with arrow."""

    ARROW_COLOR = QColor(60, 150, 60)  # Green arrow

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -30, 40, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern current source with bold arrow."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Lead wires
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(0, -30), QPointF(0, -16))
        painter.drawLine(QPointF(0, 16), QPointF(0, 30))

        # Circle with subtle gradient
        circle_grad = QRadialGradient(QPointF(0, 0), 16)
        circle_grad.setColorAt(0, QColor(255, 255, 255, 80))
        circle_grad.setColorAt(0.7, QColor(240, 240, 240, 40))
        circle_grad.setColorAt(1, QColor(200, 200, 200, 60))

        painter.setPen(QPen(line_color, 2))
        painter.setBrush(circle_grad)
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        # Bold arrow (pointing up) - green
        painter.setPen(QPen(self.ARROW_COLOR, 2.5))
        painter.drawLine(QPointF(0, 9), QPointF(0, -9))

        # Arrow head (filled)
        arrow_head = QPolygonF([
            QPointF(0, -10),
            QPointF(-5, -3),
            QPointF(5, -3),
        ])
        painter.setBrush(self.ARROW_COLOR)
        painter.setPen(QPen(self.ARROW_COLOR, 1))
        painter.drawPolygon(arrow_head)


class GroundItem(ComponentItem):
    """Graphics item for ground symbol - modern chassis style."""

    GROUND_COLOR = QColor(70, 70, 70)  # Dark gray

    def boundingRect(self) -> QRectF:
        return QRectF(-15, -15, 30, 25)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern ground symbol with gradient bars."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Vertical lead
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(0, -15), QPointF(0, 0))

        # Ground bars with gradient effect
        bars = [(12, 0, 3), (8, 5, 2.5), (4, 10, 2)]
        for half_width, y, thickness in bars:
            bar_grad = QLinearGradient(QPointF(-half_width, y), QPointF(half_width, y))
            gray = self.GROUND_COLOR
            bar_grad.setColorAt(0, gray.lighter(120))
            bar_grad.setColorAt(0.5, gray)
            bar_grad.setColorAt(1, gray.lighter(120))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bar_grad)
            bar_rect = QRectF(-half_width, y - thickness/2, half_width * 2, thickness)
            painter.drawRoundedRect(bar_rect, 1, 1)


class DiodeItem(ComponentItem):
    """Graphics item for diode - modern semiconductor style."""

    ANODE_COLOR = QColor(80, 80, 80)  # Dark silicon
    CATHODE_COLOR = QColor(150, 150, 160)  # Metallic band

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern diode with filled triangle and metallic band."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Lead wires
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(28, 0))

        # Triangle (anode) with gradient fill
        triangle = QPolygonF([
            QPointF(-10, -12),
            QPointF(-10, 12),
            QPointF(8, 0),
        ])

        tri_grad = QLinearGradient(QPointF(-10, -12), QPointF(-10, 12))
        tri_grad.setColorAt(0, self.ANODE_COLOR.lighter(130))
        tri_grad.setColorAt(0.5, self.ANODE_COLOR)
        tri_grad.setColorAt(1, self.ANODE_COLOR.lighter(130))

        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(tri_grad)
        painter.drawPolygon(triangle)

        # Cathode bar (metallic band)
        bar_rect = QRectF(8, -12, 4, 24)
        bar_grad = QLinearGradient(bar_rect.topLeft(), bar_rect.topRight())
        bar_grad.setColorAt(0, self.CATHODE_COLOR.lighter(120))
        bar_grad.setColorAt(0.5, self.CATHODE_COLOR)
        bar_grad.setColorAt(1, self.CATHODE_COLOR.lighter(120))

        painter.setPen(QPen(QColor(100, 100, 110), 1))
        painter.setBrush(bar_grad)
        painter.drawRect(bar_rect)


class MOSFETItem(ComponentItem):
    """Graphics item for MOSFET (N or P channel) - modern encapsulated style."""

    BODY_COLOR = QColor(60, 60, 65)  # Dark package
    GATE_COLOR = QColor(100, 100, 180)  # Blue gate
    NMOS_ARROW = QColor(50, 150, 50)  # Green for NMOS
    PMOS_ARROW = QColor(180, 50, 50)  # Red for PMOS

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -28, 50, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern MOSFET with enhanced visibility."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        is_nmos = self._component.type == ComponentType.MOSFET_N

        # Gate terminal
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-25, 0), QPointF(-10, 0))

        # Gate plate (with highlight)
        painter.setPen(QPen(self.GATE_COLOR, 3))
        painter.drawLine(QPointF(-10, -12), QPointF(-10, 12))

        # Oxide layer (gap)
        painter.setPen(QPen(line_color, 1))
        painter.drawLine(QPointF(-6, -14), QPointF(-6, 14))

        # Channel segments
        painter.setPen(QPen(line_color, 2.5))
        painter.drawLine(QPointF(-6, -14), QPointF(-6, -8))
        painter.drawLine(QPointF(-6, -4), QPointF(-6, 4))
        painter.drawLine(QPointF(-6, 8), QPointF(-6, 14))

        # Drain connection (top)
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-6, -12), QPointF(15, -12))
        painter.drawLine(QPointF(15, -12), QPointF(15, -28))

        # Source connection (bottom)
        painter.drawLine(QPointF(-6, 12), QPointF(15, 12))
        painter.drawLine(QPointF(15, 12), QPointF(15, 28))

        # Body connection
        painter.drawLine(QPointF(-6, 0), QPointF(15, 0))
        painter.drawLine(QPointF(15, 0), QPointF(15, 12))

        # Arrow with filled head (direction indicates N or P)
        arrow_color = self.NMOS_ARROW if is_nmos else self.PMOS_ARROW
        if is_nmos:
            # Arrow pointing into channel
            arrow_head = QPolygonF([
                QPointF(6, 0),
                QPointF(0, -4),
                QPointF(0, 4),
            ])
        else:
            # Arrow pointing out of channel
            arrow_head = QPolygonF([
                QPointF(-2, 0),
                QPointF(4, -4),
                QPointF(4, 4),
            ])

        painter.setPen(QPen(arrow_color, 1.5))
        painter.setBrush(arrow_color)
        painter.drawPolygon(arrow_head)


class SwitchItem(ComponentItem):
    """Graphics item for ideal switch - modern toggle style."""

    CONTACT_COLOR = QColor(200, 160, 60)  # Gold contacts
    ARM_COLOR = QColor(100, 100, 110)  # Metallic arm

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern switch with metallic contacts."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Lead wires
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(28, 0))

        # Left contact (gold with gradient)
        contact_grad = QRadialGradient(QPointF(-10, 0), 5)
        contact_grad.setColorAt(0, self.CONTACT_COLOR.lighter(140))
        contact_grad.setColorAt(0.7, self.CONTACT_COLOR)
        contact_grad.setColorAt(1, self.CONTACT_COLOR.darker(120))

        painter.setPen(QPen(self.CONTACT_COLOR.darker(130), 1))
        painter.setBrush(contact_grad)
        painter.drawEllipse(QPointF(-10, 0), 4, 4)

        # Right contact
        contact_grad2 = QRadialGradient(QPointF(10, 0), 5)
        contact_grad2.setColorAt(0, self.CONTACT_COLOR.lighter(140))
        contact_grad2.setColorAt(0.7, self.CONTACT_COLOR)
        contact_grad2.setColorAt(1, self.CONTACT_COLOR.darker(120))

        painter.setBrush(contact_grad2)
        painter.drawEllipse(QPointF(10, 0), 4, 4)

        # Switch arm (metallic look)
        painter.setPen(QPen(self.ARM_COLOR, 3))
        painter.drawLine(QPointF(-10, 0), QPointF(8, -12))


class IGBTItem(ComponentItem):
    """Graphics item for IGBT (Insulated Gate Bipolar Transistor) - modern power style."""

    GATE_COLOR = QColor(100, 100, 180)  # Blue gate
    ARROW_COLOR = QColor(180, 80, 40)  # Orange arrow

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -28, 50, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern IGBT with enhanced gate and arrow."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Gate terminal
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-25, 0), QPointF(-12, 0))

        # Gate plate (highlighted)
        painter.setPen(QPen(self.GATE_COLOR, 3))
        painter.drawLine(QPointF(-12, -12), QPointF(-12, 12))

        # Insulation gap (oxide layer)
        painter.setPen(QPen(line_color, 2.5))
        painter.drawLine(QPointF(-8, -14), QPointF(-8, 14))

        # Emitter connection (bottom)
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-8, 10), QPointF(12, 10))
        painter.drawLine(QPointF(12, 10), QPointF(12, 28))

        # Collector connection (top)
        painter.drawLine(QPointF(-8, -10), QPointF(12, -10))
        painter.drawLine(QPointF(12, -10), QPointF(12, -28))

        # Arrow on emitter (filled, pointing outward)
        arrow_head = QPolygonF([
            QPointF(6, 14),
            QPointF(0, 8),
            QPointF(4, 10),
        ])
        painter.setPen(QPen(self.ARROW_COLOR, 2))
        painter.drawLine(QPointF(-8, 5), QPointF(6, 14))

        # Filled arrow head
        arrow_tip = QPolygonF([
            QPointF(6, 14),
            QPointF(1, 10),
            QPointF(3, 14),
        ])
        painter.setBrush(self.ARROW_COLOR)
        painter.setPen(QPen(self.ARROW_COLOR, 1))
        painter.drawPolygon(arrow_tip)


class TransformerItem(ComponentItem):
    """Graphics item for transformer - modern magnetic core style."""

    COIL_PRIMARY = QColor(180, 100, 50)  # Copper primary
    COIL_SECONDARY = QColor(160, 80, 40)  # Copper secondary
    CORE_COLOR = QColor(60, 60, 65)  # Ferrite core

    def boundingRect(self) -> QRectF:
        return QRectF(-38, -28, 76, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw modern transformer with copper coils and ferrite core."""
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

        # Primary leads
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(-38, -18), QPointF(-20, -18))
        painter.drawLine(QPointF(-38, 18), QPointF(-20, 18))

        # Primary winding (copper colored coils)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(3):
            y = -12 + i * 12
            painter.setPen(QPen(self.COIL_PRIMARY, 2.5))
            arc_rect = QRectF(-20, y - 6, 12, 12)
            painter.drawArc(arc_rect, 90 * 16, 180 * 16)
            painter.setPen(QPen(self.COIL_PRIMARY.lighter(130), 2))
            painter.drawArc(arc_rect, 270 * 16, 180 * 16)

        # Core (ferrite bars with gradient)
        core_grad = QLinearGradient(QPointF(-4, -22), QPointF(4, -22))
        core_grad.setColorAt(0, self.CORE_COLOR.lighter(130))
        core_grad.setColorAt(0.5, self.CORE_COLOR)
        core_grad.setColorAt(1, self.CORE_COLOR.lighter(130))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core_grad)
        painter.drawRect(QRectF(-5, -22, 3, 44))
        painter.drawRect(QRectF(2, -22, 3, 44))

        # Secondary winding
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(3):
            y = -12 + i * 12
            painter.setPen(QPen(self.COIL_SECONDARY, 2.5))
            arc_rect = QRectF(8, y - 6, 12, 12)
            painter.drawArc(arc_rect, 270 * 16, 180 * 16)
            painter.setPen(QPen(self.COIL_SECONDARY.lighter(130), 2))
            painter.drawArc(arc_rect, 90 * 16, 180 * 16)

        # Secondary leads
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(QPointF(20, -18), QPointF(38, -18))
        painter.drawLine(QPointF(20, 18), QPointF(38, 18))

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
    """Base class for rectangular control block style components - clean modern style."""

    BLOCK_FILL = QColor(255, 255, 255)  # White fill
    BLOCK_BORDER = QColor(60, 60, 60)  # Dark border
    ACCENT_COLOR = QColor(70, 130, 200)  # Blue accent stripe

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -25, 80, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        rect = self.boundingRect()

        # White fill with border
        painter.setPen(QPen(line_color, 2))
        painter.setBrush(self.BLOCK_FILL)
        painter.drawRoundedRect(rect, 4, 4)

        # Left accent stripe
        accent_rect = QRectF(rect.left() + 2, rect.top() + 4, 4, rect.height() - 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.ACCENT_COLOR)
        painter.drawRoundedRect(accent_rect, 2, 2)

        # Block label
        painter.setPen(line_color)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.block_label())

    def block_label(self) -> str:
        return self._component.type.name


class PIControllerItem(BlockComponentItem):
    """Item for PI controller block - green accent."""

    ACCENT_COLOR = QColor(60, 160, 80)  # Green for PI

    def block_label(self) -> str:
        return "PI"

    def _get_value_text(self) -> str:
        kp = self._component.parameters.get("kp", 0.0)
        ki = self._component.parameters.get("ki", 0.0)
        return f"Kp={kp:g} Ki={ki:g}"


class PIDControllerItem(BlockComponentItem):
    """Item for PID controller block - cyan accent."""

    ACCENT_COLOR = QColor(50, 150, 180)  # Cyan for PID

    def block_label(self) -> str:
        return "PID"

    def _get_value_text(self) -> str:
        kp = self._component.parameters.get("kp", 0.0)
        ki = self._component.parameters.get("ki", 0.0)
        kd = self._component.parameters.get("kd", 0.0)
        return f"Kp={kp:g} Ki={ki:g} Kd={kd:g}"


class MathBlockItem(BlockComponentItem):
    """Item for generic math block - purple accent."""

    ACCENT_COLOR = QColor(130, 90, 180)  # Purple for math

    def block_label(self) -> str:
        operation = self._component.parameters.get("operation", "Σ")
        return operation.upper() if len(operation) <= 3 else operation[:3].upper()

    def _get_value_text(self) -> str:
        operation = self._component.parameters.get("operation", "sum")
        gain = self._component.parameters.get("gain", 1.0)
        return f"{operation} · {gain:g}"


class PWMGeneratorItem(BlockComponentItem):
    """Item for PWM generator block - orange accent."""

    ACCENT_COLOR = QColor(220, 120, 40)  # Orange for PWM

    def block_label(self) -> str:
        return "PWM"

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value

        freq = self._component.parameters.get("frequency", 0.0)
        duty = self._component.parameters.get("duty_cycle", 0.0) * 100.0
        freq_text = format_si_value(freq, "Hz") if freq else "0 Hz"
        return f"{freq_text} / {duty:.0f}%"


class ScopeItemBase(ComponentItem):
    """Base class for electrical/thermal scope blocks - modern oscilloscope design."""

    # Modern scope colors
    SCOPE_BODY_COLOR = QColor(45, 52, 64)  # Dark charcoal body
    SCOPE_BODY_LIGHT = QColor(60, 68, 82)  # Lighter for gradient
    SCOPE_SCREEN_BG = QColor(15, 20, 25)   # Dark screen background
    SCOPE_GRID_COLOR = QColor(40, 60, 50)  # Subtle green grid
    SCOPE_SIGNAL_COLOR = QColor(50, 205, 100)  # Bright green signal
    SCOPE_BEZEL_COLOR = QColor(30, 35, 42)  # Dark bezel

    def boundingRect(self) -> QRectF:
        return QRectF(-50, -35, 100, 70)

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()

        # Outer body with gradient
        body_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body_gradient.setColorAt(0, self.SCOPE_BODY_LIGHT)
        body_gradient.setColorAt(1, self.SCOPE_BODY_COLOR)

        painter.setPen(QPen(QColor(25, 30, 38), 2))
        painter.setBrush(body_gradient)
        painter.drawRoundedRect(rect, 8, 8)

        # Screen area with bezel
        screen_outer = rect.adjusted(8, 8, -8, -18)
        painter.setPen(QPen(self.SCOPE_BEZEL_COLOR, 3))
        painter.setBrush(self.SCOPE_SCREEN_BG)
        painter.drawRoundedRect(screen_outer, 4, 4)

        # Screen inner (actual display)
        screen = screen_outer.adjusted(3, 3, -3, -3)

        # Draw grid lines
        painter.setPen(QPen(self.SCOPE_GRID_COLOR, 0.5))
        # Horizontal grid lines
        for i in range(1, 4):
            y = screen.top() + (screen.height() * i / 4)
            painter.drawLine(QPointF(screen.left(), y), QPointF(screen.right(), y))
        # Vertical grid lines
        for i in range(1, 6):
            x = screen.left() + (screen.width() * i / 6)
            painter.drawLine(QPointF(x, screen.top()), QPointF(x, screen.bottom()))

        # Draw center crosshair (brighter)
        painter.setPen(QPen(QColor(60, 80, 70), 0.8))
        mid_y = screen.center().y()
        mid_x = screen.center().x()
        painter.drawLine(QPointF(screen.left(), mid_y), QPointF(screen.right(), mid_y))
        painter.drawLine(QPointF(mid_x, screen.top()), QPointF(mid_x, screen.bottom()))

        # Draw sample waveform (sine wave)
        painter.setPen(QPen(self.SCOPE_SIGNAL_COLOR, 1.5))
        path = QPainterPath()
        import math
        wave_points = 40
        for i in range(wave_points + 1):
            x = screen.left() + (screen.width() * i / wave_points)
            # Sine wave centered on screen
            y = mid_y - math.sin(i * 2 * math.pi / wave_points * 2) * (screen.height() * 0.3)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.drawPath(path)

        # LED indicator (green glow)
        led_x = rect.right() - 14
        led_y = rect.bottom() - 10
        led_glow = QRadialGradient(QPointF(led_x, led_y), 6)
        led_glow.setColorAt(0, QColor(100, 255, 100, 200))
        led_glow.setColorAt(0.5, QColor(50, 200, 50, 100))
        led_glow.setColorAt(1, QColor(0, 100, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(led_glow)
        painter.drawEllipse(QPointF(led_x, led_y), 6, 6)
        # LED center
        painter.setBrush(QColor(100, 255, 100))
        painter.drawEllipse(QPointF(led_x, led_y), 2, 2)

        # Label at bottom
        painter.setPen(QColor(180, 185, 195))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left(), rect.bottom() - 14, rect.width() - 20, 12),
            Qt.AlignmentFlag.AlignCenter,
            self.scope_label(),
        )

    def scope_label(self) -> str:
        return "SCOPE"

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("channel_count", 1)
        return f"{count} ch"


class ElectricalScopeItem(ScopeItemBase):
    SCOPE_SIGNAL_COLOR = QColor(50, 205, 100)  # Green for electrical

    def scope_label(self) -> str:
        return "SCOPE"


class ThermalScopeItem(ScopeItemBase):
    SCOPE_SIGNAL_COLOR = QColor(255, 120, 50)  # Orange for thermal
    SCOPE_GRID_COLOR = QColor(60, 45, 40)  # Warm grid

    def scope_label(self) -> str:
        return "THERM"

    def _draw_symbol(self, painter: QPainter) -> None:
        # Override to use thermal colors
        rect = self.boundingRect()

        # Outer body with gradient (warmer tone)
        body_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body_gradient.setColorAt(0, QColor(65, 55, 50))
        body_gradient.setColorAt(1, QColor(50, 42, 38))

        painter.setPen(QPen(QColor(35, 28, 25), 2))
        painter.setBrush(body_gradient)
        painter.drawRoundedRect(rect, 8, 8)

        # Screen area with bezel
        screen_outer = rect.adjusted(8, 8, -8, -18)
        painter.setPen(QPen(QColor(40, 32, 28), 3))
        painter.setBrush(QColor(20, 15, 12))
        painter.drawRoundedRect(screen_outer, 4, 4)

        # Screen inner
        screen = screen_outer.adjusted(3, 3, -3, -3)

        # Draw grid lines (warm color)
        painter.setPen(QPen(self.SCOPE_GRID_COLOR, 0.5))
        for i in range(1, 4):
            y = screen.top() + (screen.height() * i / 4)
            painter.drawLine(QPointF(screen.left(), y), QPointF(screen.right(), y))
        for i in range(1, 6):
            x = screen.left() + (screen.width() * i / 6)
            painter.drawLine(QPointF(x, screen.top()), QPointF(x, screen.bottom()))

        # Center crosshair
        painter.setPen(QPen(QColor(80, 60, 50), 0.8))
        mid_y = screen.center().y()
        mid_x = screen.center().x()
        painter.drawLine(QPointF(screen.left(), mid_y), QPointF(screen.right(), mid_y))
        painter.drawLine(QPointF(mid_x, screen.top()), QPointF(mid_x, screen.bottom()))

        # Draw temperature waveform (rising curve)
        painter.setPen(QPen(self.SCOPE_SIGNAL_COLOR, 1.5))
        path = QPainterPath()
        import math
        wave_points = 40
        for i in range(wave_points + 1):
            x = screen.left() + (screen.width() * i / wave_points)
            # Exponential rise then plateau
            t = i / wave_points
            y = mid_y - (1 - math.exp(-t * 4)) * (screen.height() * 0.35) + (screen.height() * 0.2)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.drawPath(path)

        # LED indicator (orange glow)
        led_x = rect.right() - 14
        led_y = rect.bottom() - 10
        led_glow = QRadialGradient(QPointF(led_x, led_y), 6)
        led_glow.setColorAt(0, QColor(255, 180, 100, 200))
        led_glow.setColorAt(0.5, QColor(255, 120, 50, 100))
        led_glow.setColorAt(1, QColor(200, 80, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(led_glow)
        painter.drawEllipse(QPointF(led_x, led_y), 6, 6)
        painter.setBrush(QColor(255, 180, 100))
        painter.drawEllipse(QPointF(led_x, led_y), 2, 2)

        # Label at bottom
        painter.setPen(QColor(200, 180, 165))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left(), rect.bottom() - 14, rect.width() - 20, 12),
            Qt.AlignmentFlag.AlignCenter,
            self.scope_label(),
        )


class SignalMuxItem(ComponentItem):
    """Item for signal mux blocks - Simulink/PLECS style (vertical bar with inputs)."""

    PIN_SPACING = 18.0  # Match pin spacing from component.py
    PIN_X = 20  # Distance from center to pins

    def boundingRect(self) -> QRectF:
        input_count = self._component.parameters.get("input_count", 3)
        height = max(50, input_count * self.PIN_SPACING + 20)
        return QRectF(-25, -height/2, 50, height)

    def _draw_symbol(self, painter: QPainter) -> None:
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        input_count = self._component.parameters.get("input_count", 3)

        # Calculate pin positions (same as _generate_stacked_pins in component.py)
        offset = (input_count - 1) * self.PIN_SPACING / 2.0

        # Central vertical bar height to cover all inputs
        bar_height = (input_count - 1) * self.PIN_SPACING + 16
        bar_width = 8
        bar_rect = QRectF(-bar_width/2, -bar_height/2, bar_width, bar_height)

        painter.setPen(QPen(line_color, 2))
        painter.setBrush(line_color)
        painter.drawRect(bar_rect)

        # Input lines (left side) - aligned with pin positions
        painter.setPen(QPen(line_color, 2))
        for i in range(input_count):
            y = -offset + i * self.PIN_SPACING
            # Horizontal input line from pin position to bar
            painter.drawLine(QPointF(-self.PIN_X, y), QPointF(-bar_width/2, y))

        # Output line (right side, center)
        painter.drawLine(QPointF(bar_width/2, 0), QPointF(self.PIN_X, 0))

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("input_count", 3)
        return f"{count}->1"


class SignalDemuxItem(ComponentItem):
    """Item for signal demux blocks - Simulink/PLECS style (vertical bar with outputs)."""

    PIN_SPACING = 18.0  # Match pin spacing from component.py
    PIN_X = 20  # Distance from center to pins

    def boundingRect(self) -> QRectF:
        output_count = self._component.parameters.get("output_count", 3)
        height = max(50, output_count * self.PIN_SPACING + 20)
        return QRectF(-25, -height/2, 50, height)

    def _draw_symbol(self, painter: QPainter) -> None:
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        output_count = self._component.parameters.get("output_count", 3)

        # Calculate pin positions (same as _generate_stacked_pins in component.py)
        offset = (output_count - 1) * self.PIN_SPACING / 2.0

        # Central vertical bar height to cover all outputs
        bar_height = (output_count - 1) * self.PIN_SPACING + 16
        bar_width = 8
        bar_rect = QRectF(-bar_width/2, -bar_height/2, bar_width, bar_height)

        painter.setPen(QPen(line_color, 2))
        painter.setBrush(line_color)
        painter.drawRect(bar_rect)

        # Input line (left side, center)
        painter.drawLine(QPointF(-self.PIN_X, 0), QPointF(-bar_width/2, 0))

        # Output lines (right side) - aligned with pin positions
        for i in range(output_count):
            y = -offset + i * self.PIN_SPACING
            # Horizontal output line from bar to pin position
            painter.drawLine(QPointF(bar_width/2, y), QPointF(self.PIN_X, y))

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("output_count", 3)
        return f"1->{count}"


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
        ComponentType.ELECTRICAL_SCOPE: ElectricalScopeItem,
        ComponentType.THERMAL_SCOPE: ThermalScopeItem,
        ComponentType.SIGNAL_MUX: SignalMuxItem,
        ComponentType.SIGNAL_DEMUX: SignalDemuxItem,
        ComponentType.SUBCIRCUIT: SubcircuitItem,
    }

    item_class = item_classes.get(component.type, ComponentItem)
    return item_class(component)
