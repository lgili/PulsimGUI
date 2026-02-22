"""Base class for component graphics items."""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QBrush,
    QFont,
    QFontMetricsF,
    QTransform,
    QRadialGradient,
    QLinearGradient,
    QPainterPath,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QGraphicsSimpleTextItem,
    QGraphicsDropShadowEffect,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pulsimgui.models.component import Component, ComponentType


class LabelWithBackground(QGraphicsItem):
    """A text label with semi-transparent background."""

    def __init__(self, text: str = "", parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self._text = text
        self._font = QFont()
        self._font.setPointSize(9)
        self._text_color = QColor(60, 60, 60)
        self._bg_color = QColor(255, 255, 255, 180)  # Semi-transparent white
        self._padding = 3.0
        self._metrics = QFontMetricsF(self._font)

    def setText(self, text: str) -> None:
        """Set the label text."""
        self.prepareGeometryChange()
        self._text = text
        self.update()

    def text(self) -> str:
        """Get the label text."""
        return self._text

    def setFont(self, font: QFont) -> None:
        """Set the label font."""
        self.prepareGeometryChange()
        self._font = font
        self._metrics = QFontMetricsF(self._font)
        self.update()

    def font(self) -> QFont:
        """Get the label font."""
        return self._font

    def setTextColor(self, color: QColor) -> None:
        """Set the text color."""
        self._text_color = color
        self.update()

    def setBackgroundColor(self, color: QColor) -> None:
        """Set the background color."""
        self._bg_color = color
        self.update()

    def boundingRect(self) -> QRectF:
        if not self._text:
            return QRectF()
        width = self._metrics.horizontalAdvance(self._text) + self._padding * 2
        height = self._metrics.height() + self._padding * 2
        return QRectF(0, 0, width, height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if not self._text:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect()

        # Draw semi-transparent background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(rect, 2, 2)

        # Draw text
        painter.setPen(self._text_color)
        painter.setFont(self._font)
        text_rect = rect.adjusted(self._padding, self._padding, -self._padding, -self._padding)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._text)


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
    LINE_COLOR = QColor(33, 42, 56)
    LINE_COLOR_DARK = QColor(225, 232, 242)
    SELECTED_COLOR = QColor(59, 130, 246)  # Bright blue for selection
    SELECTED_FILL = QColor(59, 130, 246, 30)  # Semi-transparent blue fill
    HOVER_COLOR = QColor(147, 197, 253)  # Light blue on hover
    HOVER_FILL = QColor(147, 197, 253, 20)  # Very subtle hover fill
    PIN_RADIUS = 3.0  # Compact but still easy to target
    PIN_COLOR = QColor(228, 72, 72)
    PIN_HOVER_COLOR = QColor(255, 100, 100)  # Brighter red on hover
    DC_OVERLAY_COLOR = QColor(0, 128, 0)  # Green for DC values
    DC_OVERLAY_COLOR_DARK = QColor(100, 220, 100)

    def __init__(self, component: Component, parent: QGraphicsItem | None = None):
        super().__init__(parent)

        self._component = component
        self._dark_mode = False
        self._show_labels = True
        self._show_value_labels = True  # Show component values (e.g., 10kΩ)
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

        # Create labels as child items with semi-transparent background
        self._name_label = LabelWithBackground(component.name, self)
        self._name_label.setTextColor(self.LINE_COLOR)

        self._value_label = LabelWithBackground("", self)
        self._value_label.setTextColor(QColor(80, 80, 80))
        value_font = self._value_label.font()
        value_font.setPointSize(8)
        self._value_label.setFont(value_font)

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
        self._name_label.setTextColor(color)
        # Update value label colors for dark mode
        value_color = QColor(180, 180, 180) if dark else QColor(80, 80, 80)
        self._value_label.setTextColor(value_color)
        # Update label backgrounds for dark mode
        bg_color = QColor(40, 40, 40, 180) if dark else QColor(255, 255, 255, 180)
        self._name_label.setBackgroundColor(bg_color)
        self._value_label.setBackgroundColor(bg_color)
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
        self._value_label.setVisible(show and self._show_value_labels)

    def set_show_value_labels(self, show: bool) -> None:
        """Set value label visibility."""
        self._show_value_labels = show
        self._value_label.setVisible(self._show_labels and show)
        self._update_labels()

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
        painter.setPen(self._symbol_pen(self.LINE_WIDTH))

    def _line_color(self) -> QColor:
        return self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR

    def _muted_color(self) -> QColor:
        return QColor(150, 164, 182) if self._dark_mode else QColor(97, 112, 130)

    def _surface_color(self) -> QColor:
        return QColor(44, 54, 66) if self._dark_mode else QColor(249, 251, 254)

    def _surface_alt_color(self) -> QColor:
        return QColor(37, 46, 57) if self._dark_mode else QColor(236, 241, 248)

    def _accent_blue(self) -> QColor:
        return QColor(110, 170, 255) if self._dark_mode else QColor(40, 120, 220)

    def _accent_green(self) -> QColor:
        return QColor(111, 236, 166) if self._dark_mode else QColor(36, 161, 102)

    def _accent_orange(self) -> QColor:
        return QColor(248, 187, 113) if self._dark_mode else QColor(196, 122, 46)

    def _accent_red(self) -> QColor:
        return QColor(255, 143, 143) if self._dark_mode else QColor(210, 78, 78)

    def _lead_pen(self, width: float = 2.0) -> QPen:
        pen = QPen(self._line_color(), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _symbol_pen(self, width: float = 2.0, color: QColor | None = None) -> QPen:
        pen = QPen(color or self._line_color(), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

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
        from pulsimgui.utils.si_prefix import format_component_value

        rect = self.boundingRect()

        # Update name label
        self._name_label.setText(self._component.name)
        name_rect = self._name_label.boundingRect()
        # Center name above component
        name_x = rect.center().x() - name_rect.width() / 2
        name_y = rect.top() - name_rect.height() - 2
        self._name_label.setPos(name_x, name_y)

        # Update value label using the helper function
        if self._show_value_labels:
            # Try to get value from _get_value_text() first (for specialized items)
            value_text = self._get_value_text()
            # If empty, use the generic format_component_value helper
            if not value_text:
                value_text = format_component_value(
                    self._component.type.name,
                    self._component.parameters
                )
            self._value_label.setText(value_text)
            value_rect = self._value_label.boundingRect()
            # Center value below component
            value_x = rect.center().x() - value_rect.width() / 2
            value_y = rect.bottom() + 2
            self._value_label.setPos(value_x, value_y)
            self._value_label.setVisible(self._show_labels and bool(value_text))
        else:
            self._value_label.setVisible(False)

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
    """Graphics item for resistor with clean industrial look."""

    BAND_COLORS = [
        QColor(118, 88, 62),
        QColor(171, 66, 66),
        QColor(196, 124, 61),
        QColor(187, 153, 78),
    ]

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -12, 70, 24)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-35, 0), QPointF(-20, 0))
        painter.drawLine(QPointF(20, 0), QPointF(35, 0))

        body_rect = QRectF(-20, -9, 40, 18)
        body_top = QColor(222, 196, 158) if not self._dark_mode else QColor(146, 120, 88)
        body_bottom = QColor(194, 162, 120) if not self._dark_mode else QColor(123, 100, 74)
        body_gradient = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
        body_gradient.setColorAt(0, body_top)
        body_gradient.setColorAt(1, body_bottom)

        painter.setPen(self._symbol_pen(1.6, QColor(112, 92, 74) if not self._dark_mode else QColor(170, 143, 108)))
        painter.setBrush(body_gradient)
        painter.drawRoundedRect(body_rect, 4, 4)

        for idx, x in enumerate((-13, -4, 5, 13)):
            band_color = QColor(self.BAND_COLORS[idx % len(self.BAND_COLORS)])
            if self._dark_mode:
                band_color = band_color.lighter(118)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(band_color)
            painter.drawRoundedRect(QRectF(x - 1.8, -8, 3.6, 16), 1.2, 1.2)

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        resistance = self._component.parameters.get("resistance", 0)
        return format_si_value(resistance, "Ω")


class CapacitorItem(ComponentItem):
    """Graphics item for capacitor with clean symmetric geometry."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -18, 50, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(25, 0))

        plate_color = self._muted_color().lighter(112) if self._dark_mode else self._muted_color()
        painter.setPen(self._symbol_pen(2.8, plate_color))
        painter.drawLine(QPointF(-6, -14), QPointF(-6, 14))
        painter.drawLine(QPointF(6, -14), QPointF(6, 14))

        painter.setPen(self._symbol_pen(1.4, self._line_color()))
        painter.drawLine(QPointF(-15, -6), QPointF(-11, -6))
        painter.drawLine(QPointF(-13, -8), QPointF(-13, -4))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        capacitance = self._component.parameters.get("capacitance", 0)
        return format_si_value(capacitance, "F")


class InductorItem(ComponentItem):
    """Graphics item for inductor with copper coil emphasis."""

    def boundingRect(self) -> QRectF:
        return QRectF(-35, -14, 70, 28)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-35, 0), QPointF(-22, 0))
        painter.drawLine(QPointF(22, 0), QPointF(35, 0))

        coil = QColor(194, 128, 72) if not self._dark_mode else QColor(233, 175, 116)
        highlight = coil.lighter(124)
        for i in range(4):
            x = -22 + i * 11
            arc_rect = QRectF(x, -10, 11, 20)
            painter.setPen(self._symbol_pen(2.7, coil))
            painter.drawArc(arc_rect, 0, 180 * 16)
            painter.setPen(self._symbol_pen(1.8, highlight))
            painter.drawArc(arc_rect.adjusted(0.4, 0.8, -0.4, -0.8), 22 * 16, 130 * 16)

        painter.setPen(QPen(self._muted_color(), 1.2, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(-18, 0), QPointF(18, 0))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        inductance = self._component.parameters.get("inductance", 0)
        return format_si_value(inductance, "H")


class VoltageSourceItem(ComponentItem):
    """Graphics item for voltage source in modern neutral style."""

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -30, 40, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(0, -30), QPointF(0, -16))
        painter.drawLine(QPointF(0, 16), QPointF(0, 30))

        fill = QRadialGradient(QPointF(0, -2), 16)
        fill.setColorAt(0, self._surface_color().lighter(108))
        fill.setColorAt(1, self._surface_alt_color())
        painter.setPen(self._symbol_pen(2.2))
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        painter.setPen(self._symbol_pen(2.2, self._accent_red()))
        painter.drawLine(QPointF(-5, -7), QPointF(5, -7))
        painter.drawLine(QPointF(0, -12), QPointF(0, -2))
        painter.setPen(self._symbol_pen(2.0, self._accent_blue()))
        painter.drawLine(QPointF(-5, 7), QPointF(5, 7))


class CurrentSourceItem(ComponentItem):
    """Graphics item for current source with directional arrow."""

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -30, 40, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(0, -30), QPointF(0, -16))
        painter.drawLine(QPointF(0, 16), QPointF(0, 30))

        fill = QRadialGradient(QPointF(0, -2), 16)
        fill.setColorAt(0, self._surface_color().lighter(108))
        fill.setColorAt(1, self._surface_alt_color())
        painter.setPen(self._symbol_pen(2.2))
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        arrow = self._accent_green()
        painter.setPen(self._symbol_pen(2.3, arrow))
        painter.drawLine(QPointF(0, 9), QPointF(0, -8))
        painter.setBrush(arrow)
        painter.drawPolygon(QPolygonF([QPointF(0, -11), QPointF(-4.8, -4), QPointF(4.8, -4)]))


class GroundItem(ComponentItem):
    """Graphics item for ground symbol."""

    def boundingRect(self) -> QRectF:
        return QRectF(-15, -15, 30, 25)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(0, -15), QPointF(0, 0))
        painter.setPen(self._symbol_pen(2.4, self._muted_color()))
        painter.drawLine(QPointF(-12, 0), QPointF(12, 0))
        painter.drawLine(QPointF(-8, 5), QPointF(8, 5))
        painter.drawLine(QPointF(-4, 10), QPointF(4, 10))


class DiodeItem(ComponentItem):
    """Graphics item for diode with PLECS-like silhouette."""

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(28, 0))

        triangle = QPolygonF([QPointF(-10, -12), QPointF(-10, 12), QPointF(8, 0)])
        fill = QLinearGradient(QPointF(-10, -12), QPointF(-10, 12))
        fill.setColorAt(0, self._surface_color().lighter(105))
        fill.setColorAt(1, self._surface_alt_color())
        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(fill)
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.8, self._muted_color()))
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))


class MOSFETItem(ComponentItem):
    """Graphics item for MOSFET (N or P channel)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -28, 50, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        is_nmos = self._component.type == ComponentType.MOSFET_N

        # Gate
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(-10, 0))
        painter.setPen(self._symbol_pen(2.4, self._accent_blue()))
        painter.drawLine(QPointF(-10, -12), QPointF(-10, 12))
        painter.setPen(self._symbol_pen(1.2, self._muted_color()))
        painter.drawLine(QPointF(-6.5, -14), QPointF(-6.5, 14))

        # Channel and D/S
        painter.setPen(self._symbol_pen(2.1))
        painter.drawLine(QPointF(-4, -14), QPointF(-4, -8))
        painter.drawLine(QPointF(-4, -4), QPointF(-4, 4))
        painter.drawLine(QPointF(-4, 8), QPointF(-4, 14))
        painter.drawLine(QPointF(-4, -12), QPointF(15, -12))
        painter.drawLine(QPointF(15, -12), QPointF(15, -28))
        painter.drawLine(QPointF(-6, 12), QPointF(15, 12))
        painter.drawLine(QPointF(15, 12), QPointF(15, 28))
        painter.drawLine(QPointF(-6, 0), QPointF(15, 0))
        painter.drawLine(QPointF(15, 0), QPointF(15, 12))

        arrow_color = self._accent_green() if is_nmos else self._accent_red()
        if is_nmos:
            arrow_head = QPolygonF([QPointF(6, 0), QPointF(0, -4), QPointF(0, 4)])
        else:
            arrow_head = QPolygonF([QPointF(-2, 0), QPointF(4, -4), QPointF(4, 4)])
        painter.setPen(self._symbol_pen(1.3, arrow_color))
        painter.setBrush(arrow_color)
        painter.drawPolygon(arrow_head)


class SwitchItem(ComponentItem):
    """Graphics item for ideal switch."""

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(28, 0))

        contact = self._accent_orange()
        painter.setPen(self._symbol_pen(1.3, contact.darker(120)))
        painter.setBrush(contact)
        painter.drawEllipse(QPointF(-10, 0), 3.8, 3.8)
        painter.drawEllipse(QPointF(10, 0), 3.8, 3.8)

        painter.setPen(self._symbol_pen(2.6, self._muted_color()))
        painter.drawLine(QPointF(-10, 0), QPointF(8, -12))


class IGBTItem(ComponentItem):
    """Graphics item for IGBT."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -28, 50, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(-12, 0))
        painter.setPen(self._symbol_pen(2.4, self._accent_blue()))
        painter.drawLine(QPointF(-12, -12), QPointF(-12, 12))
        painter.setPen(self._symbol_pen(1.3, self._muted_color()))
        painter.drawLine(QPointF(-8.5, -14), QPointF(-8.5, 14))

        painter.setPen(self._symbol_pen(2.1))
        painter.drawLine(QPointF(-8, -10), QPointF(12, -10))
        painter.drawLine(QPointF(12, -10), QPointF(12, -28))
        painter.drawLine(QPointF(-8, 10), QPointF(12, 10))
        painter.drawLine(QPointF(12, 10), QPointF(12, 28))
        painter.drawLine(QPointF(-8, 0), QPointF(12, 0))

        arrow = self._accent_orange()
        painter.setPen(self._symbol_pen(1.8, arrow))
        painter.drawLine(QPointF(-8, 5), QPointF(6, 14))
        painter.setBrush(arrow)
        painter.drawPolygon(QPolygonF([QPointF(6, 14), QPointF(1, 10), QPointF(3.5, 14)]))


class TransformerItem(ComponentItem):
    """Graphics item for transformer with compact modern silhouette."""

    def boundingRect(self) -> QRectF:
        return QRectF(-38, -28, 76, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-38, -18), QPointF(-20, -18))
        painter.drawLine(QPointF(-38, 18), QPointF(-20, 18))
        painter.drawLine(QPointF(20, -18), QPointF(38, -18))
        painter.drawLine(QPointF(20, 18), QPointF(38, 18))

        primary = QColor(194, 128, 72) if not self._dark_mode else QColor(232, 176, 116)
        secondary = QColor(176, 110, 62) if not self._dark_mode else QColor(216, 160, 104)
        for i in range(3):
            y = -12 + i * 12
            arc_rect = QRectF(-20, y - 6, 12, 12)
            painter.setPen(self._symbol_pen(2.3, primary))
            painter.drawArc(arc_rect, 90 * 16, 180 * 16)
            painter.setPen(self._symbol_pen(1.6, primary.lighter(122)))
            painter.drawArc(arc_rect.adjusted(0.4, 0.6, -0.2, -0.6), 235 * 16, 90 * 16)

        for i in range(3):
            y = -12 + i * 12
            arc_rect = QRectF(8, y - 6, 12, 12)
            painter.setPen(self._symbol_pen(2.3, secondary))
            painter.drawArc(arc_rect, 270 * 16, 180 * 16)
            painter.setPen(self._symbol_pen(1.6, secondary.lighter(122)))
            painter.drawArc(arc_rect.adjusted(0.2, 0.6, -0.4, -0.6), 55 * 16, 90 * 16)

        painter.setPen(self._symbol_pen(2.0, self._muted_color()))
        painter.drawLine(QPointF(-4, -22), QPointF(-4, 22))
        painter.drawLine(QPointF(4, -22), QPointF(4, 22))

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
    """Base class for rectangular control blocks with modern CAD styling."""

    ACCENT_COLOR = QColor(60, 132, 225)

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -25, 80, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()
        top = self._surface_color().lighter(108)
        bottom = self._surface_alt_color()
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0, top)
        fill.setColorAt(1, bottom)

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 5, 5)

        accent = QColor(self.ACCENT_COLOR)
        if self._dark_mode:
            accent = accent.lighter(125)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(rect.left() + 2.5, rect.top() + 4.5, 4.5, rect.height() - 9), 2, 2)

        painter.setPen(self._symbol_pen(1.0, self._muted_color()))
        painter.drawLine(QPointF(rect.left() + 9, rect.top() + 4), QPointF(rect.left() + 9, rect.bottom() - 4))

        painter.setPen(self._symbol_pen(1.8))
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
    """Base class for electrical/thermal scope blocks."""

    SCOPE_BODY_COLOR = QColor(46, 54, 66)
    SCOPE_BODY_LIGHT = QColor(62, 72, 86)
    SCOPE_SCREEN_BG = QColor(14, 19, 26)
    SCOPE_GRID_COLOR = QColor(49, 67, 64)
    SCOPE_SIGNAL_COLOR = QColor(72, 218, 131)
    SCOPE_BEZEL_COLOR = QColor(24, 31, 40)

    def boundingRect(self) -> QRectF:
        return QRectF(-50, -35, 100, 70)

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()

        body_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body_gradient.setColorAt(0, self.SCOPE_BODY_LIGHT)
        body_gradient.setColorAt(1, self.SCOPE_BODY_COLOR)

        painter.setPen(QPen(QColor(24, 30, 38), 2))
        painter.setBrush(body_gradient)
        painter.drawRoundedRect(rect, 8, 8)

        screen_outer = rect.adjusted(8, 8, -8, -18)
        painter.setPen(QPen(self.SCOPE_BEZEL_COLOR, 3))
        painter.setBrush(self.SCOPE_SCREEN_BG)
        painter.drawRoundedRect(screen_outer, 4, 4)

        screen = screen_outer.adjusted(3, 3, -3, -3)
        painter.setPen(QPen(self.SCOPE_GRID_COLOR, 0.6))
        for i in range(1, 4):
            y = screen.top() + (screen.height() * i / 4)
            painter.drawLine(QPointF(screen.left(), y), QPointF(screen.right(), y))
        for i in range(1, 6):
            x = screen.left() + (screen.width() * i / 6)
            painter.drawLine(QPointF(x, screen.top()), QPointF(x, screen.bottom()))

        painter.setPen(QPen(QColor(72, 92, 88), 0.8))
        mid_y = screen.center().y()
        mid_x = screen.center().x()
        painter.drawLine(QPointF(screen.left(), mid_y), QPointF(screen.right(), mid_y))
        painter.drawLine(QPointF(mid_x, screen.top()), QPointF(mid_x, screen.bottom()))

        painter.setPen(QPen(self.SCOPE_SIGNAL_COLOR, 1.6))
        path = QPainterPath()
        import math
        wave_points = 40
        for i in range(wave_points + 1):
            x = screen.left() + (screen.width() * i / wave_points)
            y = mid_y - math.sin(i * 2 * math.pi / wave_points * 2) * (screen.height() * 0.3)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.drawPath(path)

        led_x = rect.right() - 14
        led_y = rect.bottom() - 10
        led_glow = QRadialGradient(QPointF(led_x, led_y), 6)
        led_glow.setColorAt(0, QColor(100, 255, 100, 200))
        led_glow.setColorAt(0.5, QColor(50, 200, 50, 100))
        led_glow.setColorAt(1, QColor(0, 100, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(led_glow)
        painter.drawEllipse(QPointF(led_x, led_y), 6, 6)
        painter.setBrush(QColor(100, 255, 100))
        painter.drawEllipse(QPointF(led_x, led_y), 2, 2)

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
        input_count = self._component.parameters.get("input_count", 3)
        offset = (input_count - 1) * self.PIN_SPACING / 2.0
        bar_height = (input_count - 1) * self.PIN_SPACING + 16
        bar_width = 8
        bar_rect = QRectF(-bar_width/2, -bar_height/2, bar_width, bar_height)

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(self._surface_alt_color())
        painter.drawRoundedRect(bar_rect, 2, 2)
        painter.setPen(self._symbol_pen(2.1, self._accent_blue()))
        painter.drawLine(QPointF(0, bar_rect.top() + 4), QPointF(0, bar_rect.bottom() - 4))

        painter.setPen(self._lead_pen(2.0))
        for i in range(input_count):
            y = -offset + i * self.PIN_SPACING
            painter.drawLine(QPointF(-self.PIN_X, y), QPointF(-bar_width/2, y))

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
        output_count = self._component.parameters.get("output_count", 3)
        offset = (output_count - 1) * self.PIN_SPACING / 2.0
        bar_height = (output_count - 1) * self.PIN_SPACING + 16
        bar_width = 8
        bar_rect = QRectF(-bar_width/2, -bar_height/2, bar_width, bar_height)

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(self._surface_alt_color())
        painter.drawRoundedRect(bar_rect, 2, 2)
        painter.setPen(self._symbol_pen(2.1, self._accent_blue()))
        painter.drawLine(QPointF(0, bar_rect.top() + 4), QPointF(0, bar_rect.bottom() - 4))

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-self.PIN_X, 0), QPointF(-bar_width/2, 0))

        for i in range(output_count):
            y = -offset + i * self.PIN_SPACING
            painter.drawLine(QPointF(bar_width/2, y), QPointF(self.PIN_X, y))

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("output_count", 3)
        return f"1->{count}"


# === NEW COMPONENTS ===

class ZenerDiodeItem(ComponentItem):
    """Graphics item for Zener diode - bent cathode style."""

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(28, 0))

        triangle = QPolygonF([QPointF(-10, -12), QPointF(-10, 12), QPointF(8, 0)])
        fill = QLinearGradient(QPointF(-10, -12), QPointF(-10, 12))
        fill.setColorAt(0, self._surface_color().lighter(105))
        fill.setColorAt(1, self._surface_alt_color())
        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(fill)
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.6, self._muted_color()))
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))
        painter.drawLine(QPointF(8, -12), QPointF(4.5, -12))
        painter.drawLine(QPointF(8, 12), QPointF(11.5, 12))

    def _get_value_text(self) -> str:
        vz = self._component.parameters.get("vz", 0)
        return f"{vz:.1f}V"


class LEDItem(ComponentItem):
    """Graphics item for LED - diode with light arrows."""

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -18, 56, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        color = self._component.parameters.get("color", "red")
        led_color = {
            "red": QColor(235, 83, 83),
            "green": QColor(83, 210, 128),
            "blue": QColor(90, 152, 238),
            "yellow": QColor(230, 196, 92),
            "white": QColor(230, 234, 240),
        }.get(color, QColor(235, 83, 83))
        if self._dark_mode:
            led_color = led_color.lighter(120)

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(28, 0))

        triangle = QPolygonF([QPointF(-10, -10), QPointF(-10, 10), QPointF(6, 0)])
        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(led_color)
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.6, self._muted_color()))
        painter.drawLine(QPointF(6, -10), QPointF(6, 10))

        painter.setPen(self._symbol_pen(1.7, led_color))
        for dy in [-8, -2]:
            painter.drawLine(QPointF(0, dy), QPointF(8, dy - 8))
            painter.drawLine(QPointF(8, dy - 8), QPointF(5, dy - 6))
            painter.drawLine(QPointF(8, dy - 8), QPointF(6, dy - 5))


class BJTItem(ComponentItem):
    """Graphics item for BJT transistors (NPN and PNP)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -28, 50, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        is_npn = self._component.type == ComponentType.BJT_NPN

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(-8, 0))
        painter.setPen(self._symbol_pen(2.8))
        painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))
        painter.setPen(self._symbol_pen(2.0))
        painter.drawLine(QPointF(-8, -8), QPointF(15, -20))
        painter.drawLine(QPointF(15, -20), QPointF(15, -28))
        painter.drawLine(QPointF(-8, 8), QPointF(15, 20))
        painter.drawLine(QPointF(15, 20), QPointF(15, 28))

        arrow_color = self._accent_green() if is_npn else self._accent_red()
        painter.setPen(self._symbol_pen(1.4, arrow_color))
        painter.setBrush(arrow_color)

        if is_npn:
            arrow = QPolygonF([QPointF(12, 16), QPointF(6, 12), QPointF(8, 18)])
        else:
            arrow = QPolygonF([QPointF(-4, 6), QPointF(2, 10), QPointF(0, 4)])
        painter.drawPolygon(arrow)


class ThyristorItem(ComponentItem):
    """Graphics item for thyristor (SCR)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -25, 50, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(0, -25), QPointF(0, -10))
        painter.drawLine(QPointF(0, 10), QPointF(0, 25))
        painter.drawLine(QPointF(-25, 10), QPointF(-8, 10))
        painter.drawLine(QPointF(-8, 10), QPointF(-8, 4))

        triangle = QPolygonF([QPointF(-10, -10), QPointF(10, -10), QPointF(0, 6)])
        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(self._surface_alt_color())
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.6, self._muted_color()))
        painter.drawLine(QPointF(-10, 6), QPointF(10, 6))


class TriacItem(ComponentItem):
    """Graphics item for TRIAC."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -25, 50, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(0, -25), QPointF(0, -12))
        painter.drawLine(QPointF(0, 12), QPointF(0, 25))
        painter.drawLine(QPointF(-25, 10), QPointF(-10, 10))
        painter.drawLine(QPointF(-10, 10), QPointF(-10, 0))

        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(self._surface_alt_color())
        tri1 = QPolygonF([QPointF(-8, -12), QPointF(8, -12), QPointF(0, 0)])
        painter.drawPolygon(tri1)
        tri2 = QPolygonF([QPointF(-8, 12), QPointF(8, 12), QPointF(0, 0)])
        painter.drawPolygon(tri2)


class OpAmpItem(ComponentItem):
    """Graphics item for operational amplifier."""

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -30, 80, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        triangle = QPolygonF([QPointF(-25, -25), QPointF(-25, 25), QPointF(25, 0)])
        gradient = QLinearGradient(QPointF(-25, -25), QPointF(-25, 25))
        gradient.setColorAt(0, self._surface_color().lighter(108))
        gradient.setColorAt(1, self._surface_alt_color())

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(gradient)
        painter.drawPolygon(triangle)

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-40, -12), QPointF(-25, -12))  # IN+
        painter.drawLine(QPointF(-40, 12), QPointF(-25, 12))   # IN-
        painter.drawLine(QPointF(25, 0), QPointF(40, 0))
        painter.drawLine(QPointF(0, -30), QPointF(0, -18))  # V+
        painter.drawLine(QPointF(0, 18), QPointF(0, 30))    # V-

        painter.setPen(self._symbol_pen(1.9, self._accent_green()))
        painter.drawLine(QPointF(-22, -12), QPointF(-16, -12))
        painter.drawLine(QPointF(-19, -15), QPointF(-19, -9))

        painter.setPen(self._symbol_pen(1.9, self._accent_red()))
        painter.drawLine(QPointF(-22, 12), QPointF(-16, 12))


class ComparatorItem(OpAmpItem):
    """Graphics item for comparator (similar to op-amp with indicator)."""

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)

        # Add output indicator (digital output symbol)
        line_color = self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR
        painter.setPen(QPen(line_color, 1.5))
        painter.drawRect(QRectF(15, -4, 6, 8))


class RelayItem(ComponentItem):
    """Graphics item for relay."""

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -25, 80, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-40, -15), QPointF(-25, -15))
        painter.drawLine(QPointF(-40, 15), QPointF(-25, 15))
        coil_rect = QRectF(-25, -12, 20, 24)
        coil_fill = QColor(205, 170, 128) if not self._dark_mode else QColor(151, 124, 95)
        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(coil_fill)
        painter.drawRoundedRect(coil_rect, 2, 2)

        painter.setPen(self._symbol_pen(1.0, self._muted_color()))
        for y in range(-8, 12, 4):
            painter.drawArc(QRectF(-20, y - 2, 10, 4), 90 * 16, 180 * 16)

        painter.setPen(QPen(self._muted_color(), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(0, -20), QPointF(0, 20))

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(40, 0), QPointF(20, 0))
        painter.drawLine(QPointF(40, -15), QPointF(25, -15))
        painter.setPen(self._symbol_pen(2.1, self._muted_color()))
        painter.drawLine(QPointF(25, -15), QPointF(18, -5))
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(40, 15), QPointF(25, 15))
        painter.setPen(self._symbol_pen(2.1, self._muted_color()))
        painter.drawLine(QPointF(25, 15), QPointF(20, 5))

        painter.setPen(self._symbol_pen(1.2, self._accent_orange().darker(120)))
        painter.setBrush(self._accent_orange())
        painter.drawEllipse(QPointF(20, 0), 3, 3)
        painter.drawEllipse(QPointF(25, -15), 2, 2)
        painter.drawEllipse(QPointF(25, 15), 2, 2)


class FuseItem(ComponentItem):
    """Graphics item for fuse."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -12, 50, 24)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(-15, 0))
        painter.drawLine(QPointF(15, 0), QPointF(25, 0))

        body = QRectF(-15, -8, 30, 16)
        painter.setPen(self._symbol_pen(1.8))
        painter.setBrush(self._surface_color().lighter(106))
        painter.drawRoundedRect(body, 2, 2)

        painter.setPen(self._symbol_pen(1.6, self._muted_color()))
        path = QPainterPath()
        path.moveTo(-12, 0)
        path.cubicTo(-6, -5, 0, 5, 6, -3)
        path.lineTo(12, 0)
        painter.drawPath(path)

    def _get_value_text(self) -> str:
        rating = self._component.parameters.get("rating", 0)
        return f"{rating}A"


class CircuitBreakerItem(ComponentItem):
    """Graphics item for circuit breaker."""

    def boundingRect(self) -> QRectF:
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-28, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), QPointF(28, 0))

        painter.setPen(self._symbol_pen(1.2, self._accent_orange().darker(120)))
        painter.setBrush(self._accent_orange())
        painter.drawEllipse(QPointF(-12, 0), 3, 3)
        painter.drawEllipse(QPointF(12, 0), 3, 3)

        painter.setPen(self._symbol_pen(2.6, self._muted_color()))
        painter.drawLine(QPointF(-12, 0), QPointF(8, -12))

        painter.setPen(self._symbol_pen(2.0, self._accent_red()))
        painter.drawRect(QRectF(-4, -12, 8, 4))


class SimpleBlockItem(BlockComponentItem):
    """Generic simple block for signal processing components."""

    def __init__(self, component: Component, parent: QGraphicsItem | None = None):
        super().__init__(component, parent)
        self._label = self._get_block_label()

    def _get_block_label(self) -> str:
        labels = {
            ComponentType.INTEGRATOR: "∫",
            ComponentType.DIFFERENTIATOR: "d/dt",
            ComponentType.LIMITER: "⊏⊐",
            ComponentType.RATE_LIMITER: "dY/dt",
            ComponentType.HYSTERESIS: "⊂⊃",
            ComponentType.LOOKUP_TABLE: "f(x)",
            ComponentType.TRANSFER_FUNCTION: "H(s)",
            ComponentType.DELAY_BLOCK: "T",
            ComponentType.SAMPLE_HOLD: "S/H",
            ComponentType.STATE_MACHINE: "FSM",
        }
        return labels.get(self._component.type, "?")

    def block_label(self) -> str:
        return self._label


class IntegratorItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(100, 150, 200)


class DifferentiatorItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(200, 150, 100)


class LimiterItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(200, 100, 100)


class RateLimiterItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(180, 120, 100)


class HysteresisItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(150, 100, 180)


class LookupTableItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(100, 180, 150)


class TransferFunctionItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(180, 150, 200)


class DelayBlockItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(150, 180, 100)


class SampleHoldItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(200, 180, 100)


class StateMachineItem(SimpleBlockItem):
    ACCENT_COLOR = QColor(180, 100, 150)


class VoltageProbeItem(ComponentItem):
    """Graphics item for voltage probe."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -20, 50, 40)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, -10), QPointF(-12, -10))
        painter.drawLine(QPointF(-25, 10), QPointF(-12, 10))
        painter.drawLine(QPointF(12, 0), QPointF(25, 0))

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(self._surface_color().lighter(106))
        painter.drawEllipse(QPointF(0, 0), 15, 15)

        painter.setPen(self._symbol_pen(2.4, self._accent_red()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(-10, -10, 20, 20), Qt.AlignmentFlag.AlignCenter, "V")


class CurrentProbeItem(ComponentItem):
    """Graphics item for current probe (clamp meter style)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -25, 50, 45)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(25, 0))
        painter.drawLine(QPointF(0, -12), QPointF(0, -20))

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(self._surface_color().lighter(106))
        painter.drawEllipse(QPointF(0, 0), 12, 12)

        painter.setPen(self._symbol_pen(2.3, self._accent_green()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(-8, -8, 16, 16), Qt.AlignmentFlag.AlignCenter, "A")

        painter.setPen(self._symbol_pen(1.5, self._accent_green()))
        painter.drawLine(QPointF(-20, -8), QPointF(-14, -8))
        painter.drawLine(QPointF(-14, -8), QPointF(-16, -10))
        painter.drawLine(QPointF(-14, -8), QPointF(-16, -6))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._accent_green())
        painter.drawEllipse(QPointF(0, -20), 2.4, 2.4)


class PowerProbeItem(ComponentItem):
    """Graphics item for power probe."""

    def boundingRect(self) -> QRectF:
        return QRectF(-30, -22, 60, 44)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-30, -15), QPointF(-15, -15))
        painter.drawLine(QPointF(-30, 15), QPointF(-15, 15))
        painter.drawLine(QPointF(15, -15), QPointF(30, -15))
        painter.drawLine(QPointF(15, 15), QPointF(30, 15))

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(self._surface_color().lighter(106))
        painter.drawRoundedRect(QRectF(-15, -18, 30, 36), 4, 4)

        painter.setPen(self._symbol_pen(2.4, self._accent_orange()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(-12, -12, 24, 24), Qt.AlignmentFlag.AlignCenter, "W")


class SaturableInductorItem(InductorItem):
    """Graphics item for saturable inductor."""

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._muted_color())
        painter.drawRect(QRectF(-15, -3, 30, 6))


class CoupledInductorItem(TransformerItem):
    """Graphics item for coupled inductor (similar to transformer)."""

    def _get_value_text(self) -> str:
        k = self._component.parameters.get("coupling_coefficient", 0)
        return f"k={k:.2f}"


class SnubberRCItem(ComponentItem):
    """Graphics item for RC snubber network."""

    def boundingRect(self) -> QRectF:
        return QRectF(-30, -18, 60, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-30, 0), QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), QPointF(30, 0))

        painter.setPen(self._symbol_pen(1.6, QColor(112, 92, 74) if not self._dark_mode else QColor(170, 143, 108)))
        painter.setBrush(QColor(210, 180, 140) if not self._dark_mode else QColor(146, 120, 88))
        painter.drawRoundedRect(QRectF(-18, -6, 16, 12), 2, 2)

        painter.setPen(self._symbol_pen(2.5, self._muted_color()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(4, -10), QPointF(4, 10))
        painter.drawLine(QPointF(10, -10), QPointF(10, 10))

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-2, 0), QPointF(4, 0))
        painter.drawLine(QPointF(10, 0), QPointF(18, 0))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        r = self._component.parameters.get("resistance", 0)
        c = self._component.parameters.get("capacitance", 0)
        return f"{format_si_value(r, 'Ω')} {format_si_value(c, 'F')}"


# Factory function to create appropriate item type
def create_component_item(component: Component) -> ComponentItem:
    """Create the appropriate graphics item for a component."""
    item_classes = {
        # Basic passive
        ComponentType.RESISTOR: ResistorItem,
        ComponentType.CAPACITOR: CapacitorItem,
        ComponentType.INDUCTOR: InductorItem,

        # Sources
        ComponentType.VOLTAGE_SOURCE: VoltageSourceItem,
        ComponentType.CURRENT_SOURCE: CurrentSourceItem,
        ComponentType.GROUND: GroundItem,

        # Diodes
        ComponentType.DIODE: DiodeItem,
        ComponentType.ZENER_DIODE: ZenerDiodeItem,
        ComponentType.LED: LEDItem,

        # Transistors
        ComponentType.MOSFET_N: MOSFETItem,
        ComponentType.MOSFET_P: MOSFETItem,
        ComponentType.IGBT: IGBTItem,
        ComponentType.BJT_NPN: BJTItem,
        ComponentType.BJT_PNP: BJTItem,
        ComponentType.THYRISTOR: ThyristorItem,
        ComponentType.TRIAC: TriacItem,

        # Switching
        ComponentType.SWITCH: SwitchItem,

        # Transformer
        ComponentType.TRANSFORMER: TransformerItem,

        # Analog
        ComponentType.OP_AMP: OpAmpItem,
        ComponentType.COMPARATOR: ComparatorItem,

        # Protection
        ComponentType.RELAY: RelayItem,
        ComponentType.FUSE: FuseItem,
        ComponentType.CIRCUIT_BREAKER: CircuitBreakerItem,

        # Control blocks - basic
        ComponentType.PI_CONTROLLER: PIControllerItem,
        ComponentType.PID_CONTROLLER: PIDControllerItem,
        ComponentType.MATH_BLOCK: MathBlockItem,
        ComponentType.PWM_GENERATOR: PWMGeneratorItem,

        # Control blocks - signal processing
        ComponentType.INTEGRATOR: IntegratorItem,
        ComponentType.DIFFERENTIATOR: DifferentiatorItem,
        ComponentType.LIMITER: LimiterItem,
        ComponentType.RATE_LIMITER: RateLimiterItem,
        ComponentType.HYSTERESIS: HysteresisItem,

        # Control blocks - advanced
        ComponentType.LOOKUP_TABLE: LookupTableItem,
        ComponentType.TRANSFER_FUNCTION: TransferFunctionItem,
        ComponentType.DELAY_BLOCK: DelayBlockItem,
        ComponentType.SAMPLE_HOLD: SampleHoldItem,
        ComponentType.STATE_MACHINE: StateMachineItem,

        # Measurement
        ComponentType.VOLTAGE_PROBE: VoltageProbeItem,
        ComponentType.CURRENT_PROBE: CurrentProbeItem,
        ComponentType.POWER_PROBE: PowerProbeItem,

        # Scopes
        ComponentType.ELECTRICAL_SCOPE: ElectricalScopeItem,
        ComponentType.THERMAL_SCOPE: ThermalScopeItem,

        # Signal routing
        ComponentType.SIGNAL_MUX: SignalMuxItem,
        ComponentType.SIGNAL_DEMUX: SignalDemuxItem,

        # Magnetic
        ComponentType.SATURABLE_INDUCTOR: SaturableInductorItem,
        ComponentType.COUPLED_INDUCTOR: CoupledInductorItem,

        # Pre-configured networks
        ComponentType.SNUBBER_RC: SnubberRCItem,

        # Hierarchical
        ComponentType.SUBCIRCUIT: SubcircuitItem,
    }

    item_class = item_classes.get(component.type, ComponentItem)
    return item_class(component)
