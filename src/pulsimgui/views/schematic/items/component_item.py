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

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    Component,
    ComponentType,
    component_connection_domain,
    pin_connection_domain,
)


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
    PIN_RADIUS = 2.4  # Slightly smaller pin bubble for cleaner visuals
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
        self._drag_start_pos: QPointF | None = None

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
        self._name_label.setTextColor(self._line_color())

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
        color = self._line_color()
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

    def _domain(self) -> str:
        return component_connection_domain(self._component.type)

    @staticmethod
    def _blend_color(base: QColor, overlay: QColor, ratio: float) -> QColor:
        ratio = max(0.0, min(1.0, float(ratio)))
        inv = 1.0 - ratio
        return QColor(
            int(base.red() * inv + overlay.red() * ratio),
            int(base.green() * inv + overlay.green() * ratio),
            int(base.blue() * inv + overlay.blue() * ratio),
        )

    def _domain_base_color(self, domain: str | None = None) -> QColor:
        domain = domain or self._domain()
        if domain == CONNECTION_DOMAIN_SIGNAL:
            return QColor(110, 185, 255) if self._dark_mode else QColor(37, 124, 220)
        if domain == CONNECTION_DOMAIN_THERMAL:
            return QColor(255, 191, 124) if self._dark_mode else QColor(213, 116, 34)
        return QColor(self.LINE_COLOR_DARK if self._dark_mode else self.LINE_COLOR)

    def _line_color(self) -> QColor:
        return self._domain_base_color()

    def _muted_color(self) -> QColor:
        base = self._domain_base_color()
        if self._dark_mode:
            return self._blend_color(base, QColor(216, 223, 235), 0.25)
        return self._blend_color(base, QColor(72, 84, 98), 0.35)

    def _surface_color(self) -> QColor:
        neutral = QColor(44, 54, 66) if self._dark_mode else QColor(249, 251, 254)
        accent = self._domain_base_color()
        return self._blend_color(neutral, accent, 0.18 if self._dark_mode else 0.08)

    def _surface_alt_color(self) -> QColor:
        neutral = QColor(37, 46, 57) if self._dark_mode else QColor(236, 241, 248)
        accent = self._domain_base_color()
        return self._blend_color(neutral, accent, 0.24 if self._dark_mode else 0.12)

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

    def _with_pin_bounds(self, rect: QRectF, padding: float = 6.0) -> QRectF:
        """Expand a local symbol rectangle so pin bubbles never get clipped."""
        if not self._component.pins:
            return rect
        min_x = min(pin.x for pin in self._component.pins) - padding
        max_x = max(pin.x for pin in self._component.pins) + padding
        min_y = min(pin.y for pin in self._component.pins) - padding
        max_y = max(pin.y for pin in self._component.pins) + padding
        pin_rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        return rect.united(pin_rect)

    def _pin_position_by_name(self, name: str, fallback: QPointF) -> QPointF:
        """Return local pin position by name."""
        pin = next((pin for pin in self._component.pins if pin.name == name), None)
        if pin is None:
            return fallback
        return QPointF(float(pin.x), float(pin.y))

    def _pin_position_by_index(self, index: int, fallback: QPointF) -> QPointF:
        """Return local pin position by index."""
        if 0 <= index < len(self._component.pins):
            pin = self._component.pins[index]
            return QPointF(float(pin.x), float(pin.y))
        return fallback

    def _draw_pins(self, painter: QPainter) -> None:
        """Draw pin markers."""
        for pin_index, pin in enumerate(self._component.pins):
            pin_color = self._domain_base_color(pin_connection_domain(self._component, pin_index))
            x, y = pin.x, pin.y
            if self._component.mirrored_h:
                x = -x
            if self._component.mirrored_v:
                y = -y
            center = QPointF(x, y)
            painter.setPen(Qt.PenStyle.NoPen)
            glow = QColor(pin_color)
            glow.setAlpha(75 if self._dark_mode else 58)
            painter.setBrush(glow)
            painter.drawEllipse(center, self.PIN_RADIUS + 1.5, self.PIN_RADIUS + 1.5)

            painter.setPen(QPen(pin_color, 1.6))
            painter.setBrush(QBrush(QColor(250, 252, 255) if not self._dark_mode else QColor(24, 30, 38)))
            painter.drawEllipse(center, self.PIN_RADIUS + 0.4, self.PIN_RADIUS + 0.4)

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

    def mousePressEvent(self, event) -> None:
        """Track pre-drag position for undoable move commands."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = QPointF(self.pos())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Emit movement information after a drag completes."""
        start_pos = self._drag_start_pos
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

        if event.button() != Qt.MouseButton.LeftButton or start_pos is None:
            return

        end_pos = self.pos()
        if abs(end_pos.x() - start_pos.x()) < 0.01 and abs(end_pos.y() - start_pos.y()) < 0.01:
            return

        scene = self.scene()
        if scene is not None and hasattr(scene, "component_moved"):
            scene.component_moved.emit(
                self._component,
                start_pos.x(),
                start_pos.y(),
                end_pos.x(),
                end_pos.y(),
            )

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
                if hasattr(scene, "resolve_component_position"):
                    return scene.resolve_component_position(self, snapped_pos)
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
    """Graphics item for resistor in monoline style."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-34, -16, 68, 32))

    def _draw_symbol(self, painter: QPainter) -> None:
        left_pin = self._pin_position_by_index(0, QPointF(-40, 0))
        right_pin = self._pin_position_by_index(1, QPointF(40, 0))
        lead_left = -16.0
        lead_right = 16.0

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(left_pin, QPointF(lead_left, 0))
        painter.drawLine(QPointF(lead_right, 0), right_pin)

        painter.setPen(self._symbol_pen(2.4))
        zigzag = [
            QPointF(lead_left, 0),
            QPointF(-10, -8),
            QPointF(-5, 8),
            QPointF(0, -8),
            QPointF(5, 8),
            QPointF(10, -8),
            QPointF(lead_right, 0),
        ]
        for idx in range(len(zigzag) - 1):
            painter.drawLine(zigzag[idx], zigzag[idx + 1])

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        resistance = self._component.parameters.get("resistance", 0)
        return format_si_value(resistance, "Ω")


class CapacitorItem(ComponentItem):
    """Graphics item for capacitor with clean symmetric geometry."""

    def boundingRect(self) -> QRectF:
        return QRectF(-24, -18, 48, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-20, 0), QPointF(-6, 0))
        painter.drawLine(QPointF(6, 0), QPointF(20, 0))

        painter.setPen(self._symbol_pen(2.6))
        painter.drawLine(QPointF(-6, -14), QPointF(-6, 14))
        painter.drawLine(QPointF(6, -14), QPointF(6, 14))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        capacitance = self._component.parameters.get("capacitance", 0)
        return format_si_value(capacitance, "F")


class InductorItem(ComponentItem):
    """Graphics item for inductor with copper coil emphasis."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-34, -14, 68, 28))

    def _draw_symbol(self, painter: QPainter) -> None:
        left_pin = self._pin_position_by_index(0, QPointF(-40, 0))
        right_pin = self._pin_position_by_index(1, QPointF(40, 0))

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(left_pin, QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), right_pin)

        coil = self._line_color()
        for i in range(4):
            x = -18 + i * 9
            arc_rect = QRectF(x, -10, 9, 20)
            painter.setPen(self._symbol_pen(2.4, coil))
            painter.drawArc(arc_rect, 0, 180 * 16)

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        inductance = self._component.parameters.get("inductance", 0)
        return format_si_value(inductance, "H")


class VoltageSourceItem(ComponentItem):
    """Graphics item for voltage source in modern neutral style."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-20, -28, 40, 56))

    def _draw_symbol(self, painter: QPainter) -> None:
        top_pin = self._pin_position_by_name("+", QPointF(0, -20))
        bottom_pin = self._pin_position_by_name("-", QPointF(0, 20))
        radius = 11.0

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(top_pin, QPointF(0, -radius))
        painter.drawLine(QPointF(0, radius), bottom_pin)

        painter.setPen(self._symbol_pen(2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        painter.setPen(self._symbol_pen(2.0))
        painter.drawLine(QPointF(-4, -6), QPointF(4, -6))
        painter.drawLine(QPointF(0, -9), QPointF(0, -3))
        painter.drawLine(QPointF(-4, 6), QPointF(4, 6))


class CurrentSourceItem(ComponentItem):
    """Graphics item for current source with directional arrow."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-20, -28, 40, 56))

    def _draw_symbol(self, painter: QPainter) -> None:
        top_pin = self._pin_position_by_name("+", QPointF(0, -20))
        bottom_pin = self._pin_position_by_name("-", QPointF(0, 20))
        radius = 11.0

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(top_pin, QPointF(0, -radius))
        painter.drawLine(QPointF(0, radius), bottom_pin)

        painter.setPen(self._symbol_pen(2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        arrow = self._line_color()
        painter.setPen(self._symbol_pen(2.0, arrow))
        painter.drawLine(QPointF(0, -6), QPointF(0, 6))
        painter.setBrush(arrow)
        painter.drawPolygon(QPolygonF([QPointF(0, 8), QPointF(-3.5, 1), QPointF(3.5, 1)]))


class GroundItem(ComponentItem):
    """Graphics item for ground symbol."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-14, -12, 28, 28))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin = self._pin_position_by_index(0, QPointF(0, -20))
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(pin, QPointF(0, 0))
        painter.setPen(self._symbol_pen(2.2, self._line_color()))
        painter.drawLine(QPointF(-12, 0), QPointF(12, 0))
        painter.drawLine(QPointF(-8, 5), QPointF(8, 5))
        painter.drawLine(QPointF(-4, 10), QPointF(4, 10))

    def _update_labels(self) -> None:
        super()._update_labels()
        rect = self.boundingRect()
        name_rect = self._name_label.boundingRect()
        self._name_label.setPos(rect.right() + 6, rect.center().y() - name_rect.height() / 2)


class DiodeItem(ComponentItem):
    """Graphics item for diode with PLECS-like silhouette."""

    def boundingRect(self) -> QRectF:
        return QRectF(-22, -15, 44, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        triangle = QPolygonF([QPointF(-8, -11), QPointF(-8, 11), QPointF(8, 0)])
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.6))
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))


class MOSFETItem(ComponentItem):
    """Graphics item for MOSFET (N or P channel)."""

    def boundingRect(self) -> QRectF:
        return QRectF(-24, -24, 48, 48)

    def _draw_symbol(self, painter: QPainter) -> None:
        is_nmos = self._component.type == ComponentType.MOSFET_N

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))      # Gate lead
        painter.drawLine(QPointF(20, -20), QPointF(20, -10))   # Drain lead
        painter.drawLine(QPointF(20, 20), QPointF(20, 10))     # Source lead

        painter.setPen(self._symbol_pen(2.2))
        painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))    # Gate plate
        painter.drawLine(QPointF(4, -10), QPointF(4, 10))      # Channel
        painter.drawLine(QPointF(4, -10), QPointF(20, -10))
        painter.drawLine(QPointF(4, 10), QPointF(20, 10))

        arrow_color = self._line_color()
        if is_nmos:
            arrow_head = QPolygonF([QPointF(10, 4), QPointF(5, 0), QPointF(10, -4)])
        else:
            arrow_head = QPolygonF([QPointF(6, 4), QPointF(11, 0), QPointF(6, -4)])
        painter.setPen(self._symbol_pen(1.3, arrow_color))
        painter.setBrush(arrow_color)
        painter.drawPolygon(arrow_head)


class SwitchItem(ComponentItem):
    """Graphics item for ideal switch."""

    def boundingRect(self) -> QRectF:
        if len(self._component.pins) >= 3:
            return QRectF(-24, -30, 48, 50)
        return QRectF(-24, -15, 48, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))
        painter.setPen(self._symbol_pen(2.4))
        painter.drawEllipse(QPointF(-8, 0), 2.6, 2.6)
        painter.drawEllipse(QPointF(8, 0), 2.6, 2.6)
        painter.drawLine(QPointF(-8, 0), QPointF(6, -10))

        if len(self._component.pins) >= 3:
            painter.setPen(self._lead_pen(2.0))
            painter.drawLine(QPointF(0, -20), QPointF(0, -10))
            painter.setPen(self._symbol_pen(1.8))
            painter.drawLine(QPointF(-4, -10), QPointF(4, -10))


class IGBTItem(ComponentItem):
    """Graphics item for IGBT."""

    def boundingRect(self) -> QRectF:
        return QRectF(-24, -24, 48, 48)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))      # Gate lead
        painter.drawLine(QPointF(20, -20), QPointF(20, -10))   # Collector lead
        painter.drawLine(QPointF(20, 20), QPointF(20, 10))     # Emitter lead

        painter.setPen(self._symbol_pen(2.2))
        painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))
        painter.drawLine(QPointF(5, -10), QPointF(5, 10))
        painter.drawLine(QPointF(5, -10), QPointF(20, -10))
        painter.drawLine(QPointF(5, 10), QPointF(20, 10))

        painter.setPen(self._symbol_pen(1.8))
        painter.drawLine(QPointF(8, -4), QPointF(13, 0))
        painter.drawLine(QPointF(8, 4), QPointF(13, 0))


class TransformerItem(ComponentItem):
    """Graphics item for transformer with compact modern silhouette."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-34, -26, 68, 52))

    def _draw_symbol(self, painter: QPainter) -> None:
        p1 = self._pin_position_by_name("P1", QPointF(-40, -20))
        p2 = self._pin_position_by_name("P2", QPointF(-40, 20))
        s1 = self._pin_position_by_name("S1", QPointF(40, -20))
        s2 = self._pin_position_by_name("S2", QPointF(40, 20))
        left_attach_x = -13.0
        right_attach_x = 13.0

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(p1, QPointF(left_attach_x, p1.y()))
        painter.drawLine(p2, QPointF(left_attach_x, p2.y()))
        painter.drawLine(QPointF(right_attach_x, s1.y()), s1)
        painter.drawLine(QPointF(right_attach_x, s2.y()), s2)

        primary = self._line_color()
        secondary = self._line_color()
        for i in range(3):
            y = -12 + i * 12
            arc_rect = QRectF(-18, y - 6, 10, 12)
            painter.setPen(self._symbol_pen(2.2, primary))
            painter.drawArc(arc_rect, 90 * 16, 180 * 16)

        for i in range(3):
            y = -12 + i * 12
            arc_rect = QRectF(8, y - 6, 10, 12)
            painter.setPen(self._symbol_pen(2.2, secondary))
            painter.drawArc(arc_rect, 270 * 16, 180 * 16)

        # Close visual gaps between leads and first/last coil turns.
        painter.setPen(self._symbol_pen(2.2, primary))
        painter.drawLine(QPointF(left_attach_x, -20), QPointF(left_attach_x, -18))
        painter.drawLine(QPointF(left_attach_x, 18), QPointF(left_attach_x, 20))
        painter.setPen(self._symbol_pen(2.2, secondary))
        painter.drawLine(QPointF(right_attach_x, -20), QPointF(right_attach_x, -18))
        painter.drawLine(QPointF(right_attach_x, 18), QPointF(right_attach_x, 20))

        painter.setPen(self._symbol_pen(2.0))
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
        return self._with_pin_bounds(QRectF(-28, -24, 56, 48))

    def _draw_block_pin_leads(self, painter: QPainter, rect: QRectF) -> None:
        """Draw short leads from every pin to the nearest block edge."""
        painter.setPen(self._lead_pen(2.0))
        for pin in self._component.pins:
            px, py = float(pin.x), float(pin.y)
            if px <= rect.left():
                painter.drawLine(QPointF(px, py), QPointF(rect.left(), py))
            elif px >= rect.right():
                painter.drawLine(QPointF(rect.right(), py), QPointF(px, py))
            elif py <= rect.top():
                painter.drawLine(QPointF(px, py), QPointF(px, rect.top()))
            elif py >= rect.bottom():
                painter.drawLine(QPointF(px, rect.bottom()), QPointF(px, py))

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
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
        self._draw_block_pin_leads(painter, rect)

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


class GainItem(BlockComponentItem):
    """Item for gain block (1 input, 1 output)."""

    ACCENT_COLOR = QColor(54, 152, 226)

    def block_label(self) -> str:
        return "K"

    def _get_value_text(self) -> str:
        gain = self._component.parameters.get("gain", 1.0)
        return f"k={gain:g}"


class SumBaseItem(BlockComponentItem):
    """Base item for SUM/SUBTRACTOR blocks with per-input signs."""

    def block_label(self) -> str:
        return "Σ"

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)
        signs = list(self._component.parameters.get("signs") or [])
        input_pins = [pin for pin in self._component.pins if pin.name.startswith("IN")]
        painter.setPen(self._symbol_pen(1.4, self._muted_color()))
        font = QFont(painter.font())
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        for idx, pin in enumerate(input_pins):
            sign = signs[idx] if idx < len(signs) else "+"
            painter.drawText(QRectF(-34, pin.y - 7, 8, 14), Qt.AlignmentFlag.AlignCenter, sign)

    def _get_value_text(self) -> str:
        count = max(0, len([pin for pin in self._component.pins if pin.name.startswith("IN")]))
        return f"{count} in"


class SumItem(SumBaseItem):
    """Item for adder block."""

    ACCENT_COLOR = QColor(72, 186, 122)


class SubtractorItem(SumBaseItem):
    """Item for subtractor block."""

    ACCENT_COLOR = QColor(224, 110, 72)


class ScopeItemBase(ComponentItem):
    """Base class for electrical/thermal scope blocks."""

    SCOPE_BODY_COLOR = QColor(46, 54, 66)
    SCOPE_BODY_LIGHT = QColor(62, 72, 86)
    SCOPE_SCREEN_BG = QColor(14, 19, 26)
    SCOPE_GRID_COLOR = QColor(49, 67, 64)
    SCOPE_SIGNAL_COLOR = QColor(72, 218, 131)
    SCOPE_BEZEL_COLOR = QColor(24, 31, 40)

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-50, -35, 100, 70))

    def _draw_symbol(self, painter: QPainter) -> None:
        body = QRectF(-24, -35, 74, 70)
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, 7, 7)

        # Draw channel leads outside body, ending exactly at pin centers.
        for pin in self._component.pins:
            painter.setPen(self._lead_pen(2.0))
            painter.drawLine(QPointF(pin.x, pin.y), QPointF(body.left(), pin.y))

        screen = body.adjusted(9, 10, -10, -16)
        painter.setPen(self._symbol_pen(1.6, self._muted_color()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(screen, 3, 3)

        painter.setPen(self._symbol_pen(0.8, self._muted_color()))
        for i in range(1, 4):
            y = screen.top() + (screen.height() * i / 4)
            painter.drawLine(QPointF(screen.left(), y), QPointF(screen.right(), y))
        for i in range(1, 6):
            x = screen.left() + (screen.width() * i / 6)
            painter.drawLine(QPointF(x, screen.top()), QPointF(x, screen.bottom()))

        painter.setPen(self._symbol_pen(0.8, self._muted_color()))
        mid_y = screen.center().y()
        mid_x = screen.center().x()
        painter.drawLine(QPointF(screen.left(), mid_y), QPointF(screen.right(), mid_y))
        painter.drawLine(QPointF(mid_x, screen.top()), QPointF(mid_x, screen.bottom()))

        painter.setPen(self._symbol_pen(1.8, self.SCOPE_SIGNAL_COLOR))
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

        painter.setPen(self._symbol_pen(1.2, self._line_color()))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.left(), body.bottom() - 14, body.width() - 20, 12),
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
        super()._draw_symbol(painter)


class SignalMuxItem(ComponentItem):
    """Item for signal mux blocks - Simulink/PLECS style (vertical bar with inputs)."""

    PIN_SPACING = 20.0

    def boundingRect(self) -> QRectF:
        y_values = [pin.y for pin in self._component.pins if pin.name.startswith("IN")]
        if not y_values:
            return self._with_pin_bounds(QRectF(-24, -25, 48, 50))
        top = min(y_values) - 12
        bottom = max(y_values) + 12
        return self._with_pin_bounds(QRectF(-24, top, 48, bottom - top))

    def _draw_symbol(self, painter: QPainter) -> None:
        input_pins = [pin for pin in self._component.pins if pin.name.startswith("IN")]
        output_pin = next((pin for pin in self._component.pins if pin.name == "OUT"), None)
        if not input_pins or output_pin is None:
            return

        top = min(pin.y for pin in input_pins) - 8
        bottom = max(pin.y for pin in input_pins) + 8
        bar_rect = QRectF(-4, top, 8, bottom - top)
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bar_rect, 2, 2)
        painter.setPen(self._symbol_pen(1.8, self._line_color()))
        painter.drawLine(QPointF(0, bar_rect.top() + 4), QPointF(0, bar_rect.bottom() - 4))

        painter.setPen(self._lead_pen(2.0))
        for pin in input_pins:
            painter.drawLine(QPointF(pin.x, pin.y), QPointF(-4, pin.y))
        painter.drawLine(QPointF(4, output_pin.y), QPointF(output_pin.x, output_pin.y))

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("input_count", 3)
        return f"{count}->1"


class SignalDemuxItem(ComponentItem):
    """Item for signal demux blocks - Simulink/PLECS style (vertical bar with outputs)."""

    PIN_SPACING = 20.0

    def boundingRect(self) -> QRectF:
        y_values = [pin.y for pin in self._component.pins if pin.name.startswith("OUT")]
        if not y_values:
            return self._with_pin_bounds(QRectF(-24, -25, 48, 50))
        top = min(y_values) - 12
        bottom = max(y_values) + 12
        return self._with_pin_bounds(QRectF(-24, top, 48, bottom - top))

    def _draw_symbol(self, painter: QPainter) -> None:
        output_pins = [pin for pin in self._component.pins if pin.name.startswith("OUT")]
        input_pin = next((pin for pin in self._component.pins if pin.name == "IN"), None)
        if not output_pins or input_pin is None:
            return

        top = min(pin.y for pin in output_pins) - 8
        bottom = max(pin.y for pin in output_pins) + 8
        bar_rect = QRectF(-4, top, 8, bottom - top)
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bar_rect, 2, 2)
        painter.setPen(self._symbol_pen(1.8, self._line_color()))
        painter.drawLine(QPointF(0, bar_rect.top() + 4), QPointF(0, bar_rect.bottom() - 4))

        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(input_pin.x, input_pin.y), QPointF(-4, input_pin.y))
        for pin in output_pins:
            painter.drawLine(QPointF(4, pin.y), QPointF(pin.x, pin.y))

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("output_count", 3)
        return f"1->{count}"


# === NEW COMPONENTS ===

class ZenerDiodeItem(ComponentItem):
    """Graphics item for Zener diode - bent cathode style."""

    def boundingRect(self) -> QRectF:
        return QRectF(-22, -15, 44, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        triangle = QPolygonF([QPointF(-8, -11), QPointF(-8, 11), QPointF(8, 0)])
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.6))
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))
        painter.drawLine(QPointF(8, -12), QPointF(4.5, -12))
        painter.drawLine(QPointF(8, 12), QPointF(11.5, 12))

    def _get_value_text(self) -> str:
        vz = self._component.parameters.get("vz", 0)
        return f"{vz:.1f}V"


class LEDItem(ComponentItem):
    """Graphics item for LED - diode with light arrows."""

    def boundingRect(self) -> QRectF:
        return QRectF(-22, -18, 44, 36)

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
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        triangle = QPolygonF([QPointF(-8, -10), QPointF(-8, 10), QPointF(6, 0)])
        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(2.6))
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
        return self._with_pin_bounds(QRectF(-20, -25, 50, 50))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin_plus = self._pin_position_by_name("+", QPointF(0, -20))
        pin_minus = self._pin_position_by_name("-", QPointF(0, 20))
        pin_out = self._pin_position_by_name("OUT", QPointF(20, 0))
        radius = 11.0

        circuit_color = self._domain_base_color(CONNECTION_DOMAIN_CIRCUIT)
        signal_color = self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        painter.setPen(self._symbol_pen(2.0, circuit_color))
        painter.drawLine(pin_plus, QPointF(0, -radius))
        painter.drawLine(QPointF(0, radius), pin_minus)
        painter.setPen(self._symbol_pen(2.0, signal_color))
        painter.drawLine(QPointF(radius, 0), pin_out)

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        painter.setPen(self._symbol_pen(2.4, self._accent_red()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(-10, -10, 20, 20), Qt.AlignmentFlag.AlignCenter, "V")


class CurrentProbeItem(ComponentItem):
    """Graphics item for current probe (clamp meter style)."""

    def boundingRect(self) -> QRectF:
        return self._with_pin_bounds(QRectF(-22, -25, 44, 45))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin_in = self._pin_position_by_name("IN", QPointF(-20, 0))
        pin_out = self._pin_position_by_name("OUT", QPointF(20, 0))
        pin_meas = self._pin_position_by_name("MEAS", QPointF(0, -20))

        circuit_color = self._domain_base_color(CONNECTION_DOMAIN_CIRCUIT)
        signal_color = self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        painter.setPen(self._symbol_pen(2.0, circuit_color))
        painter.drawLine(pin_in, QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), pin_out)
        painter.setPen(self._symbol_pen(2.0, signal_color))
        painter.drawLine(QPointF(0, -12), pin_meas)

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 12, 12)

        painter.setPen(self._symbol_pen(2.3, self._accent_green()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(-8, -8, 16, 16), Qt.AlignmentFlag.AlignCenter, "A")


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
        return QRectF(-28, -18, 56, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(2.0))
        painter.drawLine(QPointF(-25, 0), QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), QPointF(25, 0))

        painter.setPen(self._symbol_pen(2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(-18, -6, 14, 12))

        painter.setPen(self._symbol_pen(2.5))
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
        ComponentType.GAIN: GainItem,
        ComponentType.SUM: SumItem,
        ComponentType.SUBTRACTOR: SubtractorItem,

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
