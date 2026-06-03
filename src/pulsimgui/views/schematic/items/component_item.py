"""Base class for component graphics items."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    MOTOR_SIGNAL_BUS_CHANNELS,
    MOTOR_SIGNAL_BUS_PIN_NAME,
    Component,
    ComponentType,
    component_connection_domain,
    pin_connection_domain,
    supports_motor_signal_bus,
)
from pulsimgui.models.component_catalog import get_descriptive_name
from pulsimgui.views.schematic.items import symbol_style as style


def _component_tooltip(component: Component) -> str:
    """Return a hover tooltip describing the component.

    For dynamic machines the tooltip also lists the SIG signal-bus channel
    order — the same lane → signal mapping the user needs when wiring a
    SIGNAL_DEMUX → scope chain. The tooltip stays one short paragraph so
    Qt's native tooltip renderer doesn't blow up the bubble.
    """
    base = get_descriptive_name(component.type)
    if supports_motor_signal_bus(component.type):
        motor_name = component.name or "M1"
        lanes = "\n".join(
            f"  OUT{i + 1}  →  {label}    ({motor_name}.{suffix})"
            for i, (suffix, label) in enumerate(MOTOR_SIGNAL_BUS_CHANNELS)
        )
        return (
            f"{base}\n\n"
            f"{MOTOR_SIGNAL_BUS_PIN_NAME} signal bus — wire to a SIGNAL_DEMUX; "
            "each output lane (in order) carries:\n"
            f"{lanes}"
        )
    if component.type == ComponentType.FOC_CONTROLLER:
        params = component.parameters or {}
        ref = params.get("speed_ref_rpm", 1800.0) or 1800.0
        try:
            ref_text = f"{float(ref):g} rpm"
        except (TypeError, ValueError):
            ref_text = "1800 rpm"
        return (
            f"{base}\n\n"
            "Cascaded speed → d/q current PI loops with inverse Park/Clarke\n"
            "driving a native 3φ VSI. Auto-detects the controlled VSI + the\n"
            "PMSM observed via the FB wire.\n\n"
            "Pins:\n"
            f"  SP  ←  speed-setpoint reference (rpm). Wire a CONSTANT to override\n"
            f"          the parameter default ({ref_text}).\n"
            "  FB  ←  motor feedback bus. Wire the PMSM's SIG pin so the\n"
            "          converter knows which motor to observe.\n\n"
            "Tune the loop gains in the properties dialog (Help)."
        )
    if component.type == ComponentType.PFC_BOOST_CONTROLLER:
        params = component.parameters or {}
        mode = str(params.get("mode", "CCM") or "CCM").upper()
        v_ref = params.get("v_bus_ref", 400.0) or 400.0
        try:
            v_text = f"{float(v_ref):g} V"
        except (TypeError, ValueError):
            v_text = "400 V"
        return (
            f"{base}\n\n"
            f"Cascaded outer voltage / inner current PI loops ({mode} mode).\n"
            "Outer loop regulates V_bus to its target; inner loop shapes i_L\n"
            "to a sine reference (i_L_ref = I_pk_ref · |V_rect|/Vac_pk) so the\n"
            "input current tracks the line voltage. The converter auto-detects\n"
            "the boost MOSFET by topology (L/D junction) and drives its gate\n"
            "at f_sw (default 65 kHz).\n\n"
            "Pins (all signal-domain, wire to voltage/current probes):\n"
            f"  VBUS ←  bus-voltage feedback (target: {v_text}).\n"
            "  IL   ←  boost-inductor current feedback (i_L).\n"
            "  VAC  ←  rectified-input voltage (|V_rect|) for shape ref.\n\n"
            "CCM is the recommended mode for 240–1000 W (lower I_peak / EMI\n"
            "vs. DCM). Tune loop gains in the properties dialog (Help)."
        )
    return base


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
        """Return the local-space rectangle used for painting and hit-testing."""
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
        """Paint the item using the active palette and scene state."""
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

    # Drawing settings — see symbol_style.py for the canonical tokens.
    LINE_WIDTH = style.STROKE_BODY
    LINE_COLOR = QColor(33, 42, 56)
    LINE_COLOR_DARK = QColor(225, 232, 242)
    SELECTED_COLOR = QColor(59, 130, 246)  # Bright blue for selection
    SELECTED_FILL = QColor(59, 130, 246, 30)  # Semi-transparent blue fill
    HOVER_COLOR = QColor(147, 197, 253)  # Light blue on hover
    HOVER_FILL = QColor(147, 197, 253, 20)  # Very subtle hover fill
    PIN_RADIUS = style.PIN_RADIUS
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

        # Schematic-canvas hover tooltip surfaces the long-form type
        # name (e.g. ``PMSM (dynamic)``) since the palette card only
        # has room for a short label. For dynamic machines we also list
        # the SIG signal-bus channel order so the user knows what each
        # demux output lane carries before even opening the help dialog.
        self.setToolTip(_component_tooltip(component))

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
        """Draw pin markers (halo + ring + bubble)."""
        glow_alpha = style.PIN_GLOW_ALPHA_DARK if self._dark_mode else style.PIN_GLOW_ALPHA_LIGHT
        bubble_fill = QColor(24, 30, 38) if self._dark_mode else QColor(250, 252, 255)
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
            glow.setAlpha(glow_alpha)
            painter.setBrush(glow)
            halo_r = self.PIN_RADIUS + style.PIN_GLOW_EXTRA
            painter.drawEllipse(center, halo_r, halo_r)

            painter.setPen(QPen(pin_color, style.PIN_RING_STROKE))
            painter.setBrush(QBrush(bubble_fill))
            ring_r = self.PIN_RADIUS + style.PIN_RING_EXTRA
            painter.drawEllipse(center, ring_r, ring_r)

    def _draw_selection(self, painter: QPainter) -> None:
        """Draw selection highlight."""
        rect = self.boundingRect()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.SELECTED_FILL))
        painter.drawRoundedRect(rect, style.SELECTION_RADIUS, style.SELECTION_RADIUS)

        painter.setPen(QPen(self.SELECTED_COLOR, style.SELECTION_STROKE, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, style.SELECTION_RADIUS, style.SELECTION_RADIUS)

    def _draw_hover(self, painter: QPainter) -> None:
        """Draw hover highlight (subtle)."""
        if self.isSelected():
            return  # Don't draw hover if already selected

        rect = self.boundingRect()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.HOVER_FILL))
        painter.drawRoundedRect(rect, style.HOVER_RADIUS, style.HOVER_RADIUS)

        painter.setPen(QPen(self.HOVER_COLOR, style.HOVER_STROKE, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, style.HOVER_RADIUS, style.HOVER_RADIUS)

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
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-34, -16, 68, 32))

    def _draw_symbol(self, painter: QPainter) -> None:
        left_pin = self._pin_position_by_index(0, QPointF(-40, 0))
        right_pin = self._pin_position_by_index(1, QPointF(40, 0))
        lead_left = -16.0
        lead_right = 16.0

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(left_pin, QPointF(lead_left, 0))
        painter.drawLine(QPointF(lead_right, 0), right_pin)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
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
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-24, -18, 48, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-6, 0))
        painter.drawLine(QPointF(6, 0), QPointF(20, 0))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(-6, -14), QPointF(-6, 14))
        painter.drawLine(QPointF(6, -14), QPointF(6, 14))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        capacitance = self._component.parameters.get("capacitance", 0)
        return format_si_value(capacitance, "F")


class InductorItem(ComponentItem):
    """Graphics item for inductor with copper coil emphasis."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-34, -14, 68, 28))

    def _draw_symbol(self, painter: QPainter) -> None:
        left_pin = self._pin_position_by_index(0, QPointF(-40, 0))
        right_pin = self._pin_position_by_index(1, QPointF(40, 0))

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(left_pin, QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), right_pin)

        coil = self._line_color()
        for i in range(4):
            x = -18 + i * 9
            arc_rect = QRectF(x, -10, 9, 20)
            painter.setPen(self._symbol_pen(style.STROKE_BODY, coil))
            painter.drawArc(arc_rect, 0, 180 * 16)

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        inductance = self._component.parameters.get("inductance", 0)
        return format_si_value(inductance, "H")


class VoltageSourceItem(ComponentItem):
    """Graphics item for voltage source in modern neutral style."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-20, -28, 40, 56))

    def _draw_symbol(self, painter: QPainter) -> None:
        top_pin = self._pin_position_by_name("+", QPointF(0, -20))
        bottom_pin = self._pin_position_by_name("-", QPointF(0, 20))
        radius = 11.0

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(top_pin, QPointF(0, -radius))
        painter.drawLine(QPointF(0, radius), bottom_pin)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL))
        painter.drawLine(QPointF(-4, -6), QPointF(4, -6))
        painter.drawLine(QPointF(0, -9), QPointF(0, -3))
        painter.drawLine(QPointF(-4, 6), QPointF(4, 6))


class CurrentSourceItem(ComponentItem):
    """Graphics item for current source with directional arrow."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-20, -28, 40, 56))

    def _draw_symbol(self, painter: QPainter) -> None:
        top_pin = self._pin_position_by_name("+", QPointF(0, -20))
        bottom_pin = self._pin_position_by_name("-", QPointF(0, 20))
        radius = 11.0

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(top_pin, QPointF(0, -radius))
        painter.drawLine(QPointF(0, radius), bottom_pin)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        arrow = self._line_color()
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, arrow))
        painter.drawLine(QPointF(0, -6), QPointF(0, 6))
        painter.setBrush(arrow)
        painter.drawPolygon(QPolygonF([QPointF(0, 8), QPointF(-3.5, 1), QPointF(3.5, 1)]))


class GroundItem(ComponentItem):
    """Graphics item for ground symbol."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-14, -12, 28, 28))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin = self._pin_position_by_index(0, QPointF(0, -20))
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(pin, QPointF(0, 0))
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
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
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-22, -15, 44, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        triangle = QPolygonF([QPointF(-8, -11), QPointF(-8, 11), QPointF(8, 0)])
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._line_color())  # Filled triangle for solid anode arrow
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))


class MOSFETItem(ComponentItem):
    """Graphics item for MOSFET (N or P channel)."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-24, -24, 48, 48)

    def _draw_symbol(self, painter: QPainter) -> None:
        is_nmos = self._component.type == ComponentType.MOSFET_N

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))      # Gate lead
        painter.drawLine(QPointF(20, -20), QPointF(20, -10))   # Drain lead
        painter.drawLine(QPointF(20, 20), QPointF(20, 10))     # Source lead

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))    # Gate plate
        painter.drawLine(QPointF(4, -10), QPointF(4, 10))      # Channel
        painter.drawLine(QPointF(4, -10), QPointF(20, -10))
        painter.drawLine(QPointF(4, 10), QPointF(20, 10))

        arrow_color = self._line_color()
        if is_nmos:
            arrow_head = QPolygonF([QPointF(10, 4), QPointF(5, 0), QPointF(10, -4)])
        else:
            arrow_head = QPolygonF([QPointF(6, 4), QPointF(11, 0), QPointF(6, -4)])
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, arrow_color))
        painter.setBrush(arrow_color)
        painter.drawPolygon(arrow_head)


class SwitchItem(ComponentItem):
    """Graphics item for ideal switch."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        if len(self._component.pins) >= 3:
            return QRectF(-24, -30, 48, 50)
        return QRectF(-24, -15, 48, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(-8, 0), 2.6, 2.6)
        painter.drawEllipse(QPointF(8, 0), 2.6, 2.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-8, 0), QPointF(6, -10))

        if len(self._component.pins) >= 3:
            painter.setPen(self._lead_pen(style.STROKE_LEAD))
            painter.drawLine(QPointF(0, -20), QPointF(0, -10))
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL))
            painter.drawLine(QPointF(-4, -10), QPointF(4, -10))


class IGBTItem(ComponentItem):
    """Graphics item for IGBT."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-24, -24, 48, 48)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))      # Gate lead
        painter.drawLine(QPointF(20, -20), QPointF(20, -10))   # Collector lead
        painter.drawLine(QPointF(20, 20), QPointF(20, 10))     # Emitter lead

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))
        painter.drawLine(QPointF(5, -10), QPointF(5, 10))
        painter.drawLine(QPointF(5, -10), QPointF(20, -10))
        painter.drawLine(QPointF(5, 10), QPointF(20, 10))

        # Filled emitter arrow — solid wedge matches the MOSFET arrow style.
        arrow_color = self._line_color()
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, arrow_color))
        painter.setBrush(arrow_color)
        painter.drawPolygon(QPolygonF([
            QPointF(8, -4), QPointF(13, 0), QPointF(8, 4),
        ]))


class TransformerItem(ComponentItem):
    """Graphics item for transformer with compact modern silhouette."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-34, -26, 68, 52))

    def _draw_symbol(self, painter: QPainter) -> None:
        p1 = self._pin_position_by_name("P1", QPointF(-40, -20))
        p2 = self._pin_position_by_name("P2", QPointF(-40, 20))
        s1 = self._pin_position_by_name("S1", QPointF(40, -20))
        s2 = self._pin_position_by_name("S2", QPointF(40, 20))
        left_attach_x = -13.0
        right_attach_x = 13.0

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(p1, QPointF(left_attach_x, p1.y()))
        painter.drawLine(p2, QPointF(left_attach_x, p2.y()))
        painter.drawLine(QPointF(right_attach_x, s1.y()), s1)
        painter.drawLine(QPointF(right_attach_x, s2.y()), s2)

        primary = self._line_color()
        secondary = self._line_color()
        for i in range(3):
            y = -12 + i * 12
            arc_rect = QRectF(-18, y - 6, 10, 12)
            painter.setPen(self._symbol_pen(style.STROKE_BODY, primary))
            painter.drawArc(arc_rect, 90 * 16, 180 * 16)

        for i in range(3):
            y = -12 + i * 12
            arc_rect = QRectF(8, y - 6, 10, 12)
            painter.setPen(self._symbol_pen(style.STROKE_BODY, secondary))
            painter.drawArc(arc_rect, 270 * 16, 180 * 16)

        # Close visual gaps between leads and first/last coil turns.
        painter.setPen(self._symbol_pen(style.STROKE_BODY, primary))
        painter.drawLine(QPointF(left_attach_x, -20), QPointF(left_attach_x, -18))
        painter.drawLine(QPointF(left_attach_x, 18), QPointF(left_attach_x, 20))
        painter.setPen(self._symbol_pen(style.STROKE_BODY, secondary))
        painter.drawLine(QPointF(right_attach_x, -20), QPointF(right_attach_x, -18))
        painter.drawLine(QPointF(right_attach_x, 18), QPointF(right_attach_x, 20))

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.drawLine(QPointF(-4, -22), QPointF(-4, 22))
        painter.drawLine(QPointF(4, -22), QPointF(4, 22))

    def _get_value_text(self) -> str:
        turns_ratio = self._component.parameters.get("turns_ratio", 1.0)
        return f"1:{turns_ratio}"


class SubcircuitItem(ComponentItem):
    """Graphics item for subcircuit instances.

    Renders a hierarchical block:
      • Doubled rounded outline (visual cue that it's a hierarchical
        block, not a primitive) — matches the IEEE schematic
        convention for sub-sheets.
      • Component name centred inside the body.
      • Each port's name drawn next to its pin so users can tell
        which terminal is which without opening the definition.
      • "⊞" glyph in the top-right corner — a universal "descend
        into" hint that telegraphs the double-click affordance.
    """

    def __init__(self, component: Component, parent: QGraphicsItem | None = None):
        self._symbol_width = float(component.parameters.get("symbol_width", 120.0))
        self._symbol_height = float(component.parameters.get("symbol_height", 80.0))
        super().__init__(component, parent)
        self._name_label.setVisible(False)
        self._value_label.setVisible(False)

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        half_w = self._symbol_width / 2
        half_h = self._symbol_height / 2
        # Pad slightly so port-name labels drawn just outside the
        # rounded rect aren't clipped.
        return QRectF(-half_w - 4, -half_h - 4,
                      self._symbol_width + 8, self._symbol_height + 8)

    def _draw_symbol(self, painter: QPainter) -> None:
        half_w = self._symbol_width / 2
        half_h = self._symbol_height / 2
        rect = QRectF(-half_w, -half_h, self._symbol_width, self._symbol_height)

        # Outer rounded rect (the visible body)
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(rect, style.BLOCK_RADIUS, style.BLOCK_RADIUS)
        # Inner rect — "hierarchical block" hint, IEEE-ish convention
        inner = rect.adjusted(3, 3, -3, -3)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(inner,
                                 max(style.BLOCK_RADIUS - 2, 1),
                                 max(style.BLOCK_RADIUS - 2, 1))

        # Title placed at the TOP of the body (header-bar style) so it
        # doesn't collide with port-name labels drawn next to side pins.
        painter.save()
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        title_font = style.block_label_font(self._name_label.font())
        title_font.setPointSize(max(title_font.pointSize() - 1, 7))
        painter.setFont(title_font)
        title_rect = QRectF(rect.left() + 8, rect.top() + 4,
                             rect.width() - 22, 14)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft
                         | Qt.AlignmentFlag.AlignVCenter,
                         self._component.name or "Subcircuit")
        painter.restore()

        # "Descend into" hint in the top-right corner (uses ⊞ which
        # most CAD/EDA tools associate with hierarchical sub-sheets).
        painter.save()
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        hint_font = QFont()
        hint_font.setBold(True)
        hint_font.setPointSize(9)
        painter.setFont(hint_font)
        hint_rect = QRectF(rect.right() - 16, rect.top() + 2, 14, 12)
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, "⊞")
        painter.restore()

        # Port-name labels next to each pin so users can identify
        # which pin is which without descending into the definition.
        if self._component.pins:
            painter.save()
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL,
                                              self._muted_color()))
            label_font = QFont()
            label_font.setPointSize(7)
            painter.setFont(label_font)
            for p in self._component.pins:
                if not p.name:
                    continue
                # Place the label INSIDE the body, offset away from
                # the pin position toward the center.
                pin_x, pin_y = float(p.x), float(p.y)
                # Snap each label to the nearest body edge:
                #   left edge  → label is to the right of pin (inside)
                #   right edge → label is to the left
                #   top edge   → label below
                #   bottom edge → label above
                # Labels sit close to the pin (40 px wide) so they
                # don't reach the centered title in the body.
                if abs(pin_x + half_w) < 4:        # pin on LEFT edge
                    label_rect = QRectF(pin_x + 4, pin_y - 6, 40, 12)
                    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                elif abs(pin_x - half_w) < 4:      # pin on RIGHT edge
                    label_rect = QRectF(pin_x - 44, pin_y - 6, 40, 12)
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                elif abs(pin_y + half_h) < 4:      # pin on TOP edge
                    label_rect = QRectF(pin_x - 20, pin_y + 2, 40, 10)
                    align = Qt.AlignmentFlag.AlignCenter
                elif abs(pin_y - half_h) < 4:      # pin on BOTTOM edge
                    label_rect = QRectF(pin_x - 20, pin_y - 12, 40, 10)
                    align = Qt.AlignmentFlag.AlignCenter
                else:
                    continue  # pin floating somewhere unusual — skip
                painter.drawText(label_rect, align, p.name)
            painter.restore()


class BlockComponentItem(ComponentItem):
    """Base class for rectangular control blocks with modern CAD styling."""

    ACCENT_COLOR = QColor(60, 132, 225)
    # Visible pin-name labels — small text drawn just inside the block body
    # next to each pin. Helps the user identify e.g. PFC.VBUS vs PFC.IL vs
    # PFC.VAC, or FOC.SP vs FOC.FB, without opening the Help dialog. Each
    # subclass can disable via ``show_pin_labels()`` if its symbol already
    # makes the pin role obvious (e.g. a single-input GAIN).
    PIN_LABEL_FONT_PT = 7.5
    PIN_LABEL_PAD = 2.0   # px from the block edge to the label

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-28, -24, 56, 48))

    def show_pin_labels(self) -> bool:
        """Return True to render pin-name labels inside the block body.

        Default: True for any block with ≥ 3 pins OR with a non-trivial pin
        name (anything other than the bare ``"IN"``/``"OUT"`` pair). A plain
        IN→OUT block (GAIN, INTEGRATOR, etc.) skips the labels — the symbol
        already says "signal in left, signal out right".
        """
        pins = self._component.pins
        if len(pins) >= 3:
            return True
        names = {p.name.strip().upper() for p in pins}
        return not names.issubset({"IN", "OUT", ""})

    def _draw_block_pin_leads(self, painter: QPainter, rect: QRectF) -> None:
        """Draw short leads from every pin to the nearest block edge."""
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
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

    def _body_rect(self) -> QRectF:
        """Return the rounded-rectangle BODY of the block (without the pin
        extension that ``boundingRect`` adds for hit-testing). Pin-name
        labels anchor to the body so they sit *inside* the visible card
        rather than overlapping the pin bubbles which extend further out.
        """
        return QRectF(-28, -24, 56, 48)

    def _draw_pin_name_labels(self, painter: QPainter, rect: QRectF) -> None:
        """Draw small pin-name labels just inside the block body, aligned to
        each pin.

        Left-side pins → label sits inside the body, right of the accent
        stripe (which occupies the leftmost band). Right-side pins → mirror.
        Top/bottom pins anchor against the matching edge. Skips empty /
        single-char generic names so the decoration is informative rather
        than noisy. Pin names are bold + accent-coloured so they stand out
        from the centred block glyph without competing visually.

        Anchored to ``_body_rect`` (NOT the passed-in ``rect``, which is the
        extended ``boundingRect``) so labels sit *inside* the rounded body
        and don't paint over the pin bubbles outside it.
        """
        if not self.show_pin_labels():
            return
        body = self._body_rect()
        font = QFont()
        font.setPointSizeF(self.PIN_LABEL_FONT_PT)
        font.setBold(True)
        painter.setFont(font)
        # Use the block's accent so labels read as "part of the block"
        # rather than as floating text — and ensure they pop on top of
        # the surface tint underneath them.
        accent = QColor(self.ACCENT_COLOR)
        if self._dark_mode:
            accent = accent.lighter(135)
        painter.setPen(QPen(accent))
        metrics = QFontMetricsF(font)
        # Left-edge offset = stripe inset + stripe width + small gap so the
        # text starts after (not under) the coloured accent stripe.
        left_text_x = (
            body.left() + style.BLOCK_STRIPE_INSET
            + style.BLOCK_STRIPE_WIDTH + self.PIN_LABEL_PAD
        )
        right_text_pad = self.PIN_LABEL_PAD
        for pin in self._component.pins:
            name = (pin.name or "").strip()
            if not name or len(name) <= 1:
                continue
            px, py = float(pin.x), float(pin.y)
            text_w = metrics.horizontalAdvance(name)
            text_h = metrics.height()
            if px <= body.left():
                # Left-side input — label inside, right of the accent stripe.
                y = py + text_h * 0.32
                painter.drawText(QPointF(left_text_x, y), name)
            elif px >= body.right():
                # Right-side output — label inside, left of the body edge.
                x = body.right() - right_text_pad - text_w
                y = py + text_h * 0.32
                painter.drawText(QPointF(x, y), name)
            elif py <= body.top():
                # Top — label inside body, below the edge, centred on pin x.
                x = px - text_w * 0.5
                y = body.top() + self.PIN_LABEL_PAD + text_h * 0.8
                painter.drawText(QPointF(x, y), name)
            elif py >= body.bottom():
                # Bottom — label inside body, above the edge, centred on pin x.
                x = px - text_w * 0.5
                y = body.bottom() - self.PIN_LABEL_PAD
                painter.drawText(QPointF(x, y), name)

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()

        # Filled card body with the active surface tint so the block reads
        # as a solid object rather than an outline cage.
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(rect, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # Accent stripe on the left edge — semantic colour per block type.
        accent = QColor(self.ACCENT_COLOR)
        if self._dark_mode:
            accent = accent.lighter(125)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        stripe_rect = QRectF(
            rect.left() + style.BLOCK_STRIPE_INSET,
            rect.top() + style.BLOCK_STRIPE_MARGIN_Y,
            style.BLOCK_STRIPE_WIDTH,
            rect.height() - 2 * style.BLOCK_STRIPE_MARGIN_Y,
        )
        painter.drawRoundedRect(stripe_rect, style.BLOCK_STRIPE_RADIUS, style.BLOCK_STRIPE_RADIUS)

        # Centred glyph (bold block-label font). Omitted when pin labels
        # are shown AND the block has a pin sitting on the centred-glyph
        # row (y ≈ 0) — otherwise the type label collides with the pin
        # name (e.g. PFC.IL or MATH.OUT at y=0). The component's name
        # tag rendered above the block ("PFC1") already conveys the type,
        # so removing the inner glyph in those cases keeps the body clean.
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setFont(style.block_label_font(painter.font()))
        if self._should_draw_centred_glyph():
            label_rect = rect.adjusted(
                style.BLOCK_STRIPE_INSET + style.BLOCK_STRIPE_WIDTH + 2, 0, -2, 0,
            )
            painter.drawText(
                label_rect, Qt.AlignmentFlag.AlignCenter, self.block_label(),
            )

        self._draw_block_pin_leads(painter, rect)
        self._draw_pin_name_labels(painter, rect)

    def _should_draw_centred_glyph(self) -> bool:
        """True when the bold centred type glyph (``PFC`` / ``FOC`` / …) can
        be drawn without colliding with a pin-name label on the middle row.

        Skips the glyph when:
          - Pin labels are shown (``show_pin_labels()`` True) AND
          - At least one pin sits on the centred glyph's row (|y| ≤ 6 px).
        That row hosts the centred type text, so a label there (e.g.
        ``IL`` on PFC, ``OUT`` on a 3-pin MATH block) would overlap.
        """
        if not self.show_pin_labels():
            return True
        for pin in self._component.pins:
            if abs(float(pin.y)) <= 6.0:
                return False
        return True

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return self._component.type.name


class PIControllerItem(BlockComponentItem):
    """Item for PI controller block - green accent."""

    ACCENT_COLOR = QColor(60, 160, 80)  # Green for PI

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return "PI"

    def _get_value_text(self) -> str:
        kp = self._component.parameters.get("kp", 0.0)
        ki = self._component.parameters.get("ki", 0.0)
        return f"Kp={kp:g} Ki={ki:g}"


class PIDControllerItem(BlockComponentItem):
    """Item for PID controller block - cyan accent."""

    ACCENT_COLOR = QColor(50, 150, 180)  # Cyan for PID

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
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
        """Return the short label shown in the block body."""
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
        """Return the short label shown in the block body."""
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
        """Return the short label shown in the block body."""
        return "K"

    def _get_value_text(self) -> str:
        gain = self._component.parameters.get("gain", 1.0)
        return f"k={gain:g}"


class CBlockItem(BlockComponentItem):
    """Item for user-defined C-Block control kernels."""

    ACCENT_COLOR = QColor(78, 124, 205)

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return "C"

    def _get_value_text(self) -> str:
        try:
            n_inputs = int(self._component.parameters.get("n_inputs", 1) or 1)
        except (TypeError, ValueError):
            n_inputs = 1
        try:
            n_outputs = int(self._component.parameters.get("n_outputs", 1) or 1)
        except (TypeError, ValueError):
            n_outputs = 1
        return f"{n_inputs}->{n_outputs}"


class FOCControllerItem(BlockComponentItem):
    """Item for the Field-Oriented Control drive controller block.

    Two visible inputs (SP = speed-setpoint reference, FB = motor feedback
    bus), with all loop gains exposed as editable parameters. The converter
    auto-detects the controlled VSI + observed PMSM by tracing the FB wire
    and the single VSI in the circuit.
    """

    ACCENT_COLOR = QColor(210, 86, 168)  # Magenta — distinct from PI/PID/C

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return "FOC"

    def _get_value_text(self) -> str:
        params = self._component.parameters
        ref = params.get("speed_ref_rpm", 0.0) or 0.0
        ramp = params.get("speed_ramp_s", 0.0) or 0.0
        try:
            return f"{float(ref):g} rpm · ramp {float(ramp):g}s"
        except (TypeError, ValueError):
            return "FOC"


class PFCBoostControllerItem(BlockComponentItem):
    """Item for the closed-loop PFC boost controller block.

    Three visible inputs (VBUS, IL, VAC), with cascaded voltage/current PI
    gains exposed as editable parameters. The converter auto-detects the
    boost MOSFET by topology (single MOSFET whose drain is the L/D junction).
    """

    ACCENT_COLOR = QColor(220, 130, 50)  # Orange — distinct from FOC magenta

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return "PFC"

    def _get_value_text(self) -> str:
        params = self._component.parameters
        mode = str(params.get("mode", "CCM") or "CCM").upper()
        v_ref = params.get("v_bus_ref", 400.0) or 400.0
        try:
            return f"{mode} · Vbus {float(v_ref):g}V"
        except (TypeError, ValueError):
            return f"{mode} · PFC"


class SumBaseItem(BlockComponentItem):
    """Base item for SUM/SUBTRACTOR blocks with per-input signs."""

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return "Σ"

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)
        signs = list(self._component.parameters.get("signs") or [])
        input_pins = [pin for pin in self._component.pins if pin.name.startswith("IN")]
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
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


class ConstantItem(BlockComponentItem):
    """Item for constant source block – displays the numeric value in its body."""

    ACCENT_COLOR = QColor(103, 58, 183)  # Deep purple

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        value = self._component.parameters.get("value", 0.0)
        try:
            fval = float(value)
        except (TypeError, ValueError):
            fval = 0.0
        return f"{fval:g}"

    def _get_value_text(self) -> str:
        return ""


class ScopeItemBase(ComponentItem):
    """Base class for electrical/thermal scope blocks."""

    SCOPE_BODY_COLOR = QColor(46, 54, 66)
    SCOPE_BODY_LIGHT = QColor(62, 72, 86)
    SCOPE_SCREEN_BG = QColor(14, 19, 26)
    SCOPE_GRID_COLOR = QColor(49, 67, 64)
    SCOPE_SIGNAL_COLOR = QColor(72, 218, 131)
    SCOPE_BEZEL_COLOR = QColor(24, 31, 40)
    BODY_LEFT = -24.0
    BODY_WIDTH = 74.0
    BODY_MIN_HEIGHT = 70.0
    BODY_PIN_MARGIN = 15.0

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        body = self._scope_body_rect()
        return self._with_pin_bounds(body.adjusted(-26, 0, 26, 0))

    def _scope_body_rect(self) -> QRectF:
        """Return scope body rect, expanding vertically as channel count grows."""
        y_values = [float(pin.y) for pin in self._component.pins]
        if not y_values:
            return QRectF(self.BODY_LEFT, -self.BODY_MIN_HEIGHT / 2, self.BODY_WIDTH, self.BODY_MIN_HEIGHT)

        top = min(y_values) - self.BODY_PIN_MARGIN
        bottom = max(y_values) + self.BODY_PIN_MARGIN
        height = bottom - top
        if height < self.BODY_MIN_HEIGHT:
            extra = (self.BODY_MIN_HEIGHT - height) / 2
            top -= extra
            bottom += extra

        return QRectF(self.BODY_LEFT, top, self.BODY_WIDTH, bottom - top)

    def _draw_symbol(self, painter: QPainter) -> None:
        body = self._scope_body_rect()
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # Draw channel leads outside body, ending exactly at pin centers.
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        for pin in self._component.pins:
            painter.drawLine(QPointF(pin.x, pin.y), QPointF(body.left(), pin.y))

        screen = body.adjusted(9, 10, -10, -16)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.setBrush(self.SCOPE_SCREEN_BG)  # Dark screen background for CRT feel
        painter.drawRoundedRect(screen, 3, 3)

        painter.setPen(self._symbol_pen(0.8, self.SCOPE_GRID_COLOR))
        for i in range(1, 4):
            y = screen.top() + (screen.height() * i / 4)
            painter.drawLine(QPointF(screen.left(), y), QPointF(screen.right(), y))
        for i in range(1, 6):
            x = screen.left() + (screen.width() * i / 6)
            painter.drawLine(QPointF(x, screen.top()), QPointF(x, screen.bottom()))

        mid_y = screen.center().y()
        mid_x = screen.center().x()
        painter.drawLine(QPointF(screen.left(), mid_y), QPointF(screen.right(), mid_y))
        painter.drawLine(QPointF(mid_x, screen.top()), QPointF(mid_x, screen.bottom()))

        painter.setPen(self._symbol_pen(style.STROKE_LEAD, self.SCOPE_SIGNAL_COLOR))
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

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._line_color()))
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
        """Return the label text displayed in the scope body."""
        return "SCOPE"

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("channel_count", 1)
        return f"{count} ch"


class ElectricalScopeItem(ScopeItemBase):
    """Graphics item that renders electrical scope visuals."""
    SCOPE_SIGNAL_COLOR = QColor(50, 205, 100)  # Green for electrical

    def scope_label(self) -> str:
        """Return the label text displayed in the scope body."""
        return "SCOPE"


class ThermalScopeItem(ScopeItemBase):
    """Graphics item that renders thermal scope visuals."""
    SCOPE_SIGNAL_COLOR = QColor(255, 120, 50)  # Orange for thermal
    SCOPE_GRID_COLOR = QColor(60, 45, 40)  # Warm grid

    def scope_label(self) -> str:
        """Return the label text displayed in the scope body."""
        return "THERM"

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)


class SignalMuxItem(ComponentItem):
    """Item for signal mux blocks - Simulink/PLECS style (vertical bar with inputs)."""

    PIN_SPACING = 20.0

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
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
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._line_color())  # Solid bar — signal-bundle visual
        painter.drawRoundedRect(bar_rect, 2, 2)

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        for pin in input_pins:
            painter.drawLine(QPointF(pin.x, pin.y), QPointF(-4, pin.y))
        painter.drawLine(QPointF(4, output_pin.y), QPointF(output_pin.x, output_pin.y))

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("input_count", 3)
        return f"{count}->1"


class SignalDemuxItem(ComponentItem):
    """Item for signal demux blocks - Simulink/PLECS style (vertical bar with outputs)."""

    PIN_SPACING = 20.0
    LANE_LABEL_OFFSET = 6.0  # px right of each output pin

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        y_values = [pin.y for pin in self._component.pins if pin.name.startswith("OUT")]
        if not y_values:
            return self._with_pin_bounds(QRectF(-24, -25, 48, 50))
        top = min(y_values) - 12
        bottom = max(y_values) + 12
        # Lane labels (e.g. ``i_a``) extend ~60px to the right of the OUT pin.
        return self._with_pin_bounds(QRectF(-24, top, 48 + 60, bottom - top))

    def _draw_symbol(self, painter: QPainter) -> None:
        output_pins = [pin for pin in self._component.pins if pin.name.startswith("OUT")]
        input_pin = next((pin for pin in self._component.pins if pin.name == "IN"), None)
        if not output_pins or input_pin is None:
            return

        top = min(pin.y for pin in output_pins) - 8
        bottom = max(pin.y for pin in output_pins) + 8
        bar_rect = QRectF(-4, top, 8, bottom - top)
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._line_color())  # Solid bar — signal-bundle visual
        painter.drawRoundedRect(bar_rect, 2, 2)

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(input_pin.x, input_pin.y), QPointF(-4, input_pin.y))
        for pin in output_pins:
            painter.drawLine(QPointF(4, pin.y), QPointF(pin.x, pin.y))

        # Per-lane channel labels when the demux is wired to a motor's SIG bus.
        # Draws the bus channel name (e.g. ``i_a``) right of each OUT pin, so the
        # user can read what each output carries without opening any dialog.
        # The label sits just *above* the wire (offset −9 on Y), out of the wire
        # line, with a small opaque background so it stays readable even when
        # something draws underneath.
        lane_labels = self._motor_bus_lane_labels(output_pins)
        if not lane_labels:
            return
        font = QFont()
        font.setPointSizeF(7.5)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        bg = self._surface_color()
        bg.setAlpha(220)
        for pin, label in lane_labels:
            text_rect = metrics.boundingRect(label)
            x = pin.x + self.LANE_LABEL_OFFSET
            y = pin.y - 4  # baseline above the wire so glyphs aren't crossed
            pad = 2.0
            bg_rect = QRectF(
                x - pad, y - text_rect.height() + 2,
                text_rect.width() + 2 * pad, text_rect.height(),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(bg_rect, 2.0, 2.0)
            painter.setPen(QPen(self._line_color()))
            painter.drawText(QPointF(x, y), label)

    def _motor_bus_lane_labels(self, output_pins: list) -> list[tuple[object, str]]:
        """Return ``(pin, channel_label)`` for each output when the demux's IN
        is wired to a dynamic machine's SIG bus pin. Empty otherwise."""
        scene = self.scene()
        # Need scene access to walk the wire graph; degrade gracefully outside.
        if scene is None or not hasattr(scene, "circuit"):
            return []
        circuit = scene.circuit  # type: ignore[attr-defined]
        if circuit is None:
            return []
        # Find a wire connecting this demux's IN pin to a motor's SIG pin.
        from pulsimgui.models.component import (
            MOTOR_SIGNAL_BUS_CHANNELS,
            MOTOR_SIGNAL_BUS_PIN_NAME,
            supports_motor_signal_bus,
        )
        demux_id = self._component.id
        in_pin_idx = next(
            (i for i, p in enumerate(self._component.pins) if p.name == "IN"), None
        )
        if in_pin_idx is None:
            return []
        for wire in circuit.wires.values():
            ends = (wire.start_connection, wire.end_connection)
            for end_a, end_b in (ends, ends[::-1]):
                if end_a is None or end_b is None:
                    continue
                if end_a.component_id != demux_id or end_a.pin_index != in_pin_idx:
                    continue
                other = circuit.components.get(end_b.component_id)
                if other is None or not supports_motor_signal_bus(other.type):
                    continue
                if end_b.pin_index >= len(other.pins):
                    continue
                if other.pins[end_b.pin_index].name != MOTOR_SIGNAL_BUS_PIN_NAME:
                    continue
                # Found a motor.SIG → demux.IN wire. Label each OUT lane.
                pairs: list[tuple[object, str]] = []
                for lane, pin in enumerate(output_pins):
                    if lane >= len(MOTOR_SIGNAL_BUS_CHANNELS):
                        break
                    _suffix, label = MOTOR_SIGNAL_BUS_CHANNELS[lane]
                    pairs.append((pin, label))
                return pairs
        return []

    def _get_value_text(self) -> str:
        count = self._component.parameters.get("output_count", 3)
        return f"1->{count}"


# === NEW COMPONENTS ===

class ZenerDiodeItem(ComponentItem):
    """Graphics item for Zener diode - bent cathode style."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-22, -15, 44, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        triangle = QPolygonF([QPointF(-8, -11), QPointF(-8, 11), QPointF(8, 0)])
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._line_color())
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(8, -12), QPointF(8, 12))
        painter.drawLine(QPointF(8, -12), QPointF(4.5, -12))
        painter.drawLine(QPointF(8, 12), QPointF(11.5, 12))

    def _get_value_text(self) -> str:
        vz = self._component.parameters.get("vz", 0)
        return f"{vz:.1f}V"


class LEDItem(ComponentItem):
    """Graphics item for LED - diode with light arrows."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
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

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
        painter.drawLine(QPointF(8, 0), QPointF(20, 0))

        triangle = QPolygonF([QPointF(-8, -10), QPointF(-8, 10), QPointF(6, 0)])
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(led_color)  # Body filled with LED colour for instant recognition
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(6, -10), QPointF(6, 10))

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, led_color))
        for dy in [-8, -2]:
            painter.drawLine(QPointF(0, dy), QPointF(8, dy - 8))
            painter.drawLine(QPointF(8, dy - 8), QPointF(5, dy - 6))
            painter.drawLine(QPointF(8, dy - 8), QPointF(6, dy - 5))


class BJTItem(ComponentItem):
    """Graphics item for BJT transistors (NPN and PNP)."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-25, -28, 50, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        is_npn = self._component.type == ComponentType.BJT_NPN

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-25, 0), QPointF(-8, 0))
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(-8, -12), QPointF(-8, 12))
        painter.setPen(self._symbol_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-8, -8), QPointF(15, -20))
        painter.drawLine(QPointF(15, -20), QPointF(15, -28))
        painter.drawLine(QPointF(-8, 8), QPointF(15, 20))
        painter.drawLine(QPointF(15, 20), QPointF(15, 28))

        arrow_color = self._line_color()
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, arrow_color))
        painter.setBrush(arrow_color)

        if is_npn:
            arrow = QPolygonF([QPointF(12, 16), QPointF(6, 12), QPointF(8, 18)])
        else:
            arrow = QPolygonF([QPointF(-4, 6), QPointF(2, 10), QPointF(0, 4)])
        painter.drawPolygon(arrow)


class ThyristorItem(ComponentItem):
    """Graphics item for thyristor (SCR)."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-25, -25, 50, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(0, -25), QPointF(0, -10))
        painter.drawLine(QPointF(0, 10), QPointF(0, 25))
        painter.drawLine(QPointF(-25, 10), QPointF(-8, 10))
        painter.drawLine(QPointF(-8, 10), QPointF(-8, 4))

        triangle = QPolygonF([QPointF(-10, -10), QPointF(10, -10), QPointF(0, 6)])
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._line_color())  # Filled anode triangle matches diode family
        painter.drawPolygon(triangle)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(-10, 6), QPointF(10, 6))


class TriacItem(ComponentItem):
    """Graphics item for TRIAC."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-25, -25, 50, 50)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(0, -25), QPointF(0, -12))
        painter.drawLine(QPointF(0, 12), QPointF(0, 25))
        painter.drawLine(QPointF(-25, 10), QPointF(-10, 10))
        painter.drawLine(QPointF(-10, 10), QPointF(-10, 0))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._line_color())  # Bidirectional triangles filled (anti-parallel SCR pair)
        tri1 = QPolygonF([QPointF(-8, -12), QPointF(8, -12), QPointF(0, 0)])
        painter.drawPolygon(tri1)
        tri2 = QPolygonF([QPointF(-8, 12), QPointF(8, 12), QPointF(0, 0)])
        painter.drawPolygon(tri2)


class OpAmpItem(ComponentItem):
    """Graphics item for operational amplifier."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-40, -30, 80, 60)

    def _draw_symbol(self, painter: QPainter) -> None:
        # Triangle body — sized so its left edge straddles the IN+/IN-
        # pins at y=±20 (the post-snap pin positions). Apex points right
        # at the OUT pin.
        in_plus = self._pin_position_by_name("IN+", QPointF(-40, -20))
        in_minus = self._pin_position_by_name("IN-", QPointF(-40, 20))
        out_pin = self._pin_position_by_name("OUT", QPointF(40, 0))
        v_plus = self._pin_position_by_name("V+", QPointF(0, -20))
        v_minus = self._pin_position_by_name("V-", QPointF(0, 20))

        triangle = QPolygonF([QPointF(-25, -25), QPointF(-25, 25), QPointF(25, 0)])
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawPolygon(triangle)

        # Leads run from each pin straight to the triangle edge so the
        # bubble and the body actually touch.
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(in_plus, QPointF(-25, in_plus.y()))
        painter.drawLine(in_minus, QPointF(-25, in_minus.y()))
        painter.drawLine(QPointF(25, 0), out_pin)
        # V+/V- enter the diagonal top/bottom edge of the triangle at
        # x=0 → y=±12.5 by similar triangles.
        painter.drawLine(v_plus, QPointF(0, -12.5))
        painter.drawLine(v_minus, QPointF(0, 12.5))

        # Polarity marks beside the input leads (just inside the body).
        mark_y = 18.0  # close to the lead-y but safely inside the triangle
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._line_color()))
        painter.drawLine(QPointF(-22, -mark_y), QPointF(-16, -mark_y))
        painter.drawLine(QPointF(-19, -mark_y - 3), QPointF(-19, -mark_y + 3))
        painter.drawLine(QPointF(-22, mark_y), QPointF(-16, mark_y))


class ComparatorItem(OpAmpItem):
    """Graphics item for comparator (similar to op-amp with indicator)."""

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)

        # Add output indicator (digital output symbol)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL))
        painter.setBrush(self._line_color())
        painter.drawRect(QRectF(15, -4, 6, 8))


class RelayItem(ComponentItem):
    """Graphics item for relay."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-40, -28, 80, 56)

    def _draw_symbol(self, painter: QPainter) -> None:
        # Coil terminal pins (left) and switch contact pins (right) — all
        # derived from the actual model pin so leads reach the bubbles.
        coil_p = self._pin_position_by_name("COIL+", QPointF(-40, -20))
        coil_n = self._pin_position_by_name("COIL-", QPointF(-40, 20))
        com = self._pin_position_by_name("COM", QPointF(40, 0))
        no = self._pin_position_by_name("NO", QPointF(40, -20))
        nc = self._pin_position_by_name("NC", QPointF(40, 20))

        # Coil body: rectangle that *encloses* the two coil leads, so the
        # leads cleanly enter the box at their pin y.
        top_y = min(coil_p.y(), coil_n.y())
        bot_y = max(coil_p.y(), coil_n.y())
        coil_rect = QRectF(-25, top_y - 2, 20, (bot_y - top_y) + 4)
        coil_fill = QColor(205, 170, 128) if not self._dark_mode else QColor(151, 124, 95)

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(coil_p, QPointF(-25, coil_p.y()))
        painter.drawLine(coil_n, QPointF(-25, coil_n.y()))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(coil_fill)
        painter.drawRoundedRect(coil_rect, 2, 2)

        # Coil winding arcs spread evenly across the inner height.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        inner_top = int(top_y + 4)
        inner_bot = int(bot_y - 4)
        for y in range(inner_top, inner_bot + 1, 4):
            painter.drawArc(QRectF(-20, y - 2, 10, 4), 90 * 16, 180 * 16)

        # Magnetic-coupling dashed line spans coil → switch contacts.
        painter.setPen(QPen(self._muted_color(), style.STROKE_DETAIL, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(0, top_y), QPointF(0, bot_y))

        # Switch contacts (right): COM goes to a pivot point; NO/NC are the
        # two throws. Lead direction follows each pin's actual y.
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(com, QPointF(20, com.y()))
        painter.drawLine(no, QPointF(25, no.y()))
        painter.drawLine(nc, QPointF(25, nc.y()))

        # Throw arms — draw from the pivot toward the closed contact (NO).
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._muted_color()))
        pivot = QPointF(20, com.y())
        painter.drawLine(QPointF(25, no.y()), pivot)
        painter.drawLine(QPointF(25, nc.y()), QPointF(20, nc.y() * 0.25))

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_orange().darker(120)))
        painter.setBrush(self._accent_orange())
        painter.drawEllipse(QPointF(20, 0), 3, 3)
        painter.drawEllipse(QPointF(25, -15), 2, 2)
        painter.drawEllipse(QPointF(25, 15), 2, 2)


class FuseItem(ComponentItem):
    """Graphics item for fuse."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-25, -12, 50, 24)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-25, 0), QPointF(-15, 0))
        painter.drawLine(QPointF(15, 0), QPointF(25, 0))

        body = QRectF(-15, -8, 30, 16)
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(body, 3, 3)

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._line_color()))
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
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-28, -15, 56, 30)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-28, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), QPointF(28, 0))

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_orange().darker(120)))
        painter.setBrush(self._accent_orange())
        painter.drawEllipse(QPointF(-12, 0), 3, 3)
        painter.drawEllipse(QPointF(12, 0), 3, 3)

        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        painter.drawLine(QPointF(-12, 0), QPointF(8, -12))

        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._accent_red()))
        painter.setBrush(self._accent_red())
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
            # Three-phase / vector control
            ComponentType.CLARKE_TRANSFORM: "Clarke",
            ComponentType.INVERSE_CLARKE_TRANSFORM: "Clarke⁻¹",
            ComponentType.PARK_TRANSFORM: "Park",
            ComponentType.INVERSE_PARK_TRANSFORM: "Park⁻¹",
            ComponentType.PLL: "PLL",
            ComponentType.SVM: "SVM",
        }
        return labels.get(self._component.type, "?")

    def block_label(self) -> str:
        """Return the short label shown in the block body."""
        return self._label


class IntegratorItem(SimpleBlockItem):
    """Graphics item that renders integrator visuals."""
    ACCENT_COLOR = QColor(100, 150, 200)


class DifferentiatorItem(SimpleBlockItem):
    """Graphics item that renders differentiator visuals."""
    ACCENT_COLOR = QColor(200, 150, 100)


class LimiterItem(SimpleBlockItem):
    """Graphics item that renders limiter visuals."""
    ACCENT_COLOR = QColor(200, 100, 100)


class RateLimiterItem(SimpleBlockItem):
    """Graphics item that renders rate limiter visuals."""
    ACCENT_COLOR = QColor(180, 120, 100)


class HysteresisItem(SimpleBlockItem):
    """Graphics item that renders hysteresis visuals."""
    ACCENT_COLOR = QColor(150, 100, 180)


class LookupTableItem(SimpleBlockItem):
    """Graphics item that renders lookup table visuals."""
    ACCENT_COLOR = QColor(100, 180, 150)


class TransferFunctionItem(SimpleBlockItem):
    """Graphics item that renders transfer function visuals."""
    ACCENT_COLOR = QColor(180, 150, 200)


class DelayBlockItem(SimpleBlockItem):
    """Graphics item that renders delay block visuals."""
    ACCENT_COLOR = QColor(150, 180, 100)


class SampleHoldItem(SimpleBlockItem):
    """Graphics item that renders sample hold visuals."""
    ACCENT_COLOR = QColor(200, 180, 100)


class StateMachineItem(SimpleBlockItem):
    """Graphics item that renders state machine visuals."""
    ACCENT_COLOR = QColor(180, 100, 150)


# =============================================================================
# Three-phase / vector control (Pulsim Phase 28)
# =============================================================================


class ClarkeTransformItem(SimpleBlockItem):
    """Clarke transform (abc → αβγ)."""

    ACCENT_COLOR = QColor(124, 58, 237)  # Purple


class InverseClarkeTransformItem(SimpleBlockItem):
    """Inverse Clarke transform (αβγ → abc)."""

    ACCENT_COLOR = QColor(139, 92, 246)


class ParkTransformItem(SimpleBlockItem):
    """Park transform (αβ → dq with θ)."""

    ACCENT_COLOR = QColor(91, 33, 182)

    def _get_value_text(self) -> str:
        theta = self._component.parameters.get("theta_from_channel", "")
        return f"θ={theta}" if theta else "θ=?"


class InversePArkTransformItem(SimpleBlockItem):  # legacy typo guard
    pass


class InverseParkTransformItem(SimpleBlockItem):
    """Inverse Park transform (dq → αβ with θ)."""

    ACCENT_COLOR = QColor(109, 40, 217)

    def _get_value_text(self) -> str:
        theta = self._component.parameters.get("theta_from_channel", "")
        return f"θ={theta}" if theta else "θ=?"


class PLLItem(SimpleBlockItem):
    """Single-phase PLL (sine → θ, ω, lock_error)."""

    ACCENT_COLOR = QColor(67, 56, 202)  # Indigo

    def _get_value_text(self) -> str:
        f_nom = self._component.parameters.get("f_nominal_hz", 60.0)
        return f"f={f_nom:g} Hz"


class SVMItem(SimpleBlockItem):
    """Space-Vector Modulation (αβ → 3 half-bridge duties)."""

    ACCENT_COLOR = QColor(190, 24, 93)  # Pink

    def _get_value_text(self) -> str:
        v_dc = self._component.parameters.get("v_dc", 1.0)
        return f"V_DC={v_dc:g} V"


class VoltageProbeItem(ComponentItem):
    """Graphics item for voltage probe."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-20, -25, 50, 50))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin_plus = self._pin_position_by_name("+", QPointF(0, -20))
        pin_minus = self._pin_position_by_name("-", QPointF(0, 20))
        pin_out = self._pin_position_by_name("OUT", QPointF(20, 0))
        radius = 11.0

        circuit_color = self._domain_base_color(CONNECTION_DOMAIN_CIRCUIT)
        signal_color = self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, circuit_color))
        painter.drawLine(pin_plus, QPointF(0, -radius))
        painter.drawLine(QPointF(0, radius), pin_minus)
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, signal_color))
        painter.drawLine(QPointF(radius, 0), pin_out)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_red()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(-10, -10, 20, 20), Qt.AlignmentFlag.AlignCenter, "V")


class VoltageProbeGndItem(ComponentItem):
    """Graphics item for single-ended voltage probe (node referenced to GND)."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-24, -20, 48, 40))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin_in = self._pin_position_by_name("IN", QPointF(-25, 0))
        pin_out = self._pin_position_by_name("OUT", QPointF(25, 0))
        radius = 10.0

        circuit_color = self._domain_base_color(CONNECTION_DOMAIN_CIRCUIT)
        signal_color = self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, circuit_color))
        painter.drawLine(pin_in, QPointF(-radius, 0))
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, signal_color))
        painter.drawLine(QPointF(radius, 0), pin_out)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_red()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(QRectF(-9, -9, 18, 18), Qt.AlignmentFlag.AlignCenter, "V")

        ground_y = radius + 5.0
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.drawLine(QPointF(0, radius), QPointF(0, ground_y))
        painter.drawLine(QPointF(-6, ground_y), QPointF(6, ground_y))
        painter.drawLine(QPointF(-4, ground_y + 3), QPointF(4, ground_y + 3))
        painter.drawLine(QPointF(-2, ground_y + 6), QPointF(2, ground_y + 6))


class _NetLabelItem(ComponentItem):
    """Shared drawing logic for Goto/From net labels."""

    _ARROW_RIGHT = True

    def __init__(self, component: Component, parent: QGraphicsItem | None = None):
        super().__init__(component, parent)
        self._name_label.setVisible(False)
        self._value_label.setVisible(False)
        self.setToolTip("")

    def _update_labels(self) -> None:
        # Net labels are rendered inside the symbol body.
        self._name_label.setVisible(False)
        self._value_label.setVisible(False)

    def _label_text(self) -> str:
        text = str(self._component.parameters.get("net_label", "") or "").strip()
        if text:
            return text
        return self._component.name or "NET"

    def _display_label_text(self) -> str:
        text = self._label_text()
        max_chars = 14
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    def _is_linked_pair(self) -> bool:
        scene = self.scene()
        circuit = getattr(scene, "circuit", None)
        if circuit is None:
            return False

        if self._component.type == ComponentType.GOTO_LABEL:
            target_type = ComponentType.FROM_LABEL
        elif self._component.type == ComponentType.FROM_LABEL:
            target_type = ComponentType.GOTO_LABEL
        else:
            return False

        source_label = self._label_text().strip()
        if not source_label:
            return False

        for candidate in circuit.components.values():
            if candidate.id == self._component.id:
                continue
            if candidate.type != target_type:
                continue
            candidate_label = str(candidate.parameters.get("net_label", "") or "").strip()
            if not candidate_label:
                candidate_label = str(candidate.name or "").strip()
            if candidate_label == source_label:
                return True
        return False

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        text = self._display_label_text()
        width = max(58.0, min(168.0, 24.0 + float(len(text)) * 6.0))
        x = -6.0 if self._ARROW_RIGHT else -width + 6.0
        return self._with_pin_bounds(QRectF(x, -13.0, width, 26.0))

    def _draw_symbol(self, painter: QPainter) -> None:
        rect = self.boundingRect()
        pin_pos = self._pin_position_by_index(0, QPointF(0, 0))
        text = self._display_label_text()
        linked = self._is_linked_pair()
        self.setToolTip(f"Net label: {self._label_text()}")

        edge_color = self._accent_green() if linked else self._line_color()
        fill_color = self._surface_color().lighter(102)
        if linked:
            fill_color = self._blend_color(fill_color, self._accent_green(), 0.22 if self._dark_mode else 0.16)

        head_width = 14.0
        path = QPainterPath()
        top = rect.top() + 1.0
        bottom = rect.bottom() - 1.0

        if self._ARROW_RIGHT:
            body_end = rect.right() - head_width
            path.moveTo(QPointF(rect.left(), top))
            path.lineTo(QPointF(body_end, top))
            path.lineTo(QPointF(rect.right(), 0.0))
            path.lineTo(QPointF(body_end, bottom))
            path.lineTo(QPointF(rect.left(), bottom))
            path.closeSubpath()
            lead_end_x = rect.left()
            text_rect = QRectF(rect.left() + 7.0, rect.top() + 1.0, rect.width() - 31.0, rect.height() - 2.0)
            chevron = (
                QPointF(rect.right() - 15.0, -5.0),
                QPointF(rect.right() - 10.0, 0.0),
                QPointF(rect.right() - 15.0, 5.0),
            )
        else:
            body_start = rect.left() + head_width
            path.moveTo(QPointF(rect.right(), top))
            path.lineTo(QPointF(body_start, top))
            path.lineTo(QPointF(rect.left(), 0.0))
            path.lineTo(QPointF(body_start, bottom))
            path.lineTo(QPointF(rect.right(), bottom))
            path.closeSubpath()
            lead_end_x = rect.right()
            text_rect = QRectF(rect.left() + 24.0, rect.top() + 1.0, rect.width() - 31.0, rect.height() - 2.0)
            chevron = (
                QPointF(rect.left() + 15.0, -5.0),
                QPointF(rect.left() + 10.0, 0.0),
                QPointF(rect.left() + 15.0, 5.0),
            )

        painter.setPen(self._symbol_pen(style.STROKE_BODY, edge_color))
        painter.setBrush(fill_color)
        painter.drawPath(path)

        painter.setPen(self._symbol_pen(style.STROKE_LEAD, edge_color))
        painter.drawLine(pin_pos, QPointF(lead_end_x, 0.0))

        # PLECS-like directional cue near the arrow head.
        signal_color = self._accent_green() if linked else self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, signal_color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(list(chevron)))

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._line_color()))
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter, text)


class GotoLabelItem(_NetLabelItem):
    """Graphics item for Goto label."""

    _ARROW_RIGHT = True


class FromLabelItem(_NetLabelItem):
    """Graphics item for From label."""

    _ARROW_RIGHT = False


class SubcircuitPortItem(ComponentItem):
    """Marker placed inside a subcircuit definition that declares a
    named input/output. Renders as a pentagonal flag pointing toward
    the outer edge of the symbol (i.e., outward from the subcircuit).
    The pin always faces inward, so wires from other inner components
    attach naturally.

    Parameters consumed:
        port_name (str): label shown inside the flag and used as the
            outer-symbol pin name when the definition is synced.
        direction (input|output|bidir): tints the flag and chooses
            the arrow-head direction (input → into body, output →
            out of body, bidir → diamond/no chevron).
        side (left|right|top|bottom): which edge of the marker the
            flag points to. The matching pin location is computed by
            ``_synchronize_subcircuit_port_pin`` in the model layer.
    """

    _BODY_LENGTH = 56.0
    _BODY_THICKNESS = 22.0
    _HEAD_LENGTH = 12.0

    def _params(self) -> tuple[str, str, str]:
        params = getattr(self._component, "parameters", {}) or {}
        port_name = str(params.get("port_name", "port")).strip() or "port"
        direction = str(params.get("direction", "bidir")).lower().strip()
        if direction not in ("input", "output", "bidir"):
            direction = "bidir"
        side = str(params.get("side", "left")).lower().strip()
        if side not in ("left", "right", "top", "bottom"):
            side = "left"
        return port_name, direction, side

    def boundingRect(self) -> QRectF:
        _, _, side = self._params()
        body = self._BODY_LENGTH
        thick = self._BODY_THICKNESS
        # Flag extends from the pin outward. For left side the pin is
        # on the right (+40), flag stretches to the left.
        margin = 4.0
        if side == "left":
            rect = QRectF(-body - margin, -thick / 2 - margin,
                          body + margin * 2, thick + margin * 2)
        elif side == "right":
            rect = QRectF(-margin, -thick / 2 - margin,
                          body + margin * 2, thick + margin * 2)
        elif side == "top":
            rect = QRectF(-thick / 2 - margin, -body - margin,
                          thick + margin * 2, body + margin * 2)
        else:  # bottom
            rect = QRectF(-thick / 2 - margin, -margin,
                          thick + margin * 2, body + margin * 2)
        return self._with_pin_bounds(rect)

    def _flag_color(self, direction: str) -> QColor:
        if direction == "input":
            return self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        if direction == "output":
            return self._accent_green()
        return self._line_color()

    def _draw_symbol(self, painter: QPainter) -> None:
        port_name, direction, side = self._params()
        edge_color = self._flag_color(direction)
        fill_color = self._surface_color().lighter(105)
        fill_color = self._blend_color(fill_color, edge_color,
                                       0.25 if self._dark_mode else 0.18)

        self.setToolTip(f"Subcircuit port: {port_name} ({direction}, {side})")

        # The pin lives on the inward-facing side. Build the flag
        # pointing from the pin outward.
        pin_pt = self._pin_position_by_index(0, QPointF(0.0, 0.0))
        body = self._BODY_LENGTH
        thick = self._BODY_THICKNESS
        head = self._HEAD_LENGTH

        path = QPainterPath()
        if side == "left":
            # pin on the right, flag stretches left, point at x=-body
            top_y, bot_y = -thick / 2, thick / 2
            body_x = -body + head
            path.moveTo(QPointF(pin_pt.x(), top_y))
            path.lineTo(QPointF(body_x, top_y))
            path.lineTo(QPointF(-body, 0.0))
            path.lineTo(QPointF(body_x, bot_y))
            path.lineTo(QPointF(pin_pt.x(), bot_y))
            path.closeSubpath()
            text_rect = QRectF(-body + head + 2, top_y, body - head - 4, thick)
            arrow_pts = self._direction_chevron(direction, side, body, thick, head)
        elif side == "right":
            top_y, bot_y = -thick / 2, thick / 2
            body_x = body - head
            path.moveTo(QPointF(pin_pt.x(), top_y))
            path.lineTo(QPointF(body_x, top_y))
            path.lineTo(QPointF(body, 0.0))
            path.lineTo(QPointF(body_x, bot_y))
            path.lineTo(QPointF(pin_pt.x(), bot_y))
            path.closeSubpath()
            text_rect = QRectF(2, top_y, body - head - 4, thick)
            arrow_pts = self._direction_chevron(direction, side, body, thick, head)
        elif side == "top":
            left_x, right_x = -thick / 2, thick / 2
            body_y = -body + head
            path.moveTo(QPointF(left_x, pin_pt.y()))
            path.lineTo(QPointF(left_x, body_y))
            path.lineTo(QPointF(0.0, -body))
            path.lineTo(QPointF(right_x, body_y))
            path.lineTo(QPointF(right_x, pin_pt.y()))
            path.closeSubpath()
            text_rect = QRectF(left_x, -body + head + 2, thick, body - head - 4)
            arrow_pts = self._direction_chevron(direction, side, body, thick, head)
        else:  # bottom
            left_x, right_x = -thick / 2, thick / 2
            body_y = body - head
            path.moveTo(QPointF(left_x, pin_pt.y()))
            path.lineTo(QPointF(left_x, body_y))
            path.lineTo(QPointF(0.0, body))
            path.lineTo(QPointF(right_x, body_y))
            path.lineTo(QPointF(right_x, pin_pt.y()))
            path.closeSubpath()
            text_rect = QRectF(left_x, 2, thick, body - head - 4)
            arrow_pts = self._direction_chevron(direction, side, body, thick, head)

        painter.setPen(self._symbol_pen(style.STROKE_BODY, edge_color))
        painter.setBrush(fill_color)
        painter.drawPath(path)

        # Direction chevron — input/output only; bidir omits it.
        if direction in ("input", "output") and arrow_pts:
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL, edge_color))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QPolygonF(list(arrow_pts)))

        # Port name label
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._line_color()))
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        if side in ("top", "bottom"):
            # Rotate text to fit vertical orientation
            painter.save()
            painter.translate(text_rect.center())
            painter.rotate(-90)
            rotated = QRectF(-text_rect.height() / 2, -text_rect.width() / 2,
                             text_rect.height(), text_rect.width())
            painter.drawText(rotated,
                             Qt.AlignmentFlag.AlignCenter, port_name)
            painter.restore()
        else:
            painter.drawText(text_rect,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter,
                             port_name)

    def _direction_chevron(
        self,
        direction: str,
        side: str,
        body: float,
        thick: float,
        head: float,
    ) -> tuple[QPointF, ...]:
        """Build a 3-point chevron pointing along the signal flow.

        - input: signal flows from outside → into the body (toward
          the pin), so chevron points inward
        - output: signal flows from body → outward, chevron points
          outward
        - bidir: empty (no chevron)
        """
        if direction not in ("input", "output"):
            return ()
        inward = direction == "input"  # input: arrow head toward pin
        # Pick a center along the flag where the chevron sits, and a
        # direction unit vector pointing the way the arrow should go.
        if side == "left":
            cx = -body + head + 8.0
            dx = +1.0 if inward else -1.0
            return (
                QPointF(cx - dx * 4, -4),
                QPointF(cx + dx * 4, 0),
                QPointF(cx - dx * 4, +4),
            )
        if side == "right":
            cx = body - head - 8.0
            dx = -1.0 if inward else +1.0
            return (
                QPointF(cx - dx * 4, -4),
                QPointF(cx + dx * 4, 0),
                QPointF(cx - dx * 4, +4),
            )
        if side == "top":
            cy = -body + head + 8.0
            dy = +1.0 if inward else -1.0
            return (
                QPointF(-4, cy - dy * 4),
                QPointF(0, cy + dy * 4),
                QPointF(+4, cy - dy * 4),
            )
        # bottom
        cy = body - head - 8.0
        dy = -1.0 if inward else +1.0
        return (
            QPointF(-4, cy - dy * 4),
            QPointF(0, cy + dy * 4),
            QPointF(+4, cy - dy * 4),
        )


class CurrentProbeItem(ComponentItem):
    """Graphics item for current probe (clamp meter style)."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-22, -25, 44, 45))

    def _draw_symbol(self, painter: QPainter) -> None:
        pin_in = self._pin_position_by_name("IN", QPointF(-20, 0))
        pin_out = self._pin_position_by_name("OUT", QPointF(20, 0))
        pin_meas = self._pin_position_by_name("MEAS", QPointF(0, -20))

        circuit_color = self._domain_base_color(CONNECTION_DOMAIN_CIRCUIT)
        signal_color = self._domain_base_color(CONNECTION_DOMAIN_SIGNAL)
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, circuit_color))
        painter.drawLine(pin_in, QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), pin_out)
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, signal_color))
        painter.drawLine(QPointF(0, -12), pin_meas)

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), 12, 12)

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_green()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(-8, -8, 16, 16), Qt.AlignmentFlag.AlignCenter, "A")


class PowerProbeItem(ComponentItem):
    """Graphics item for power probe."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-30, -22, 60, 44)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-30, -15), QPointF(-15, -15))
        painter.drawLine(QPointF(-30, 15), QPointF(-15, 15))
        painter.drawLine(QPointF(15, -15), QPointF(30, -15))
        painter.drawLine(QPointF(15, 15), QPointF(30, 15))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(QRectF(-15, -18, 30, 36), style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_orange()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(-12, -12, 24, 24), Qt.AlignmentFlag.AlignCenter, "W")


class SaturableInductorItem(InductorItem):
    """Graphics item for saturable inductor.

    Saturation model  → one solid core bar below the coil.
    Hysteresis model  → two parallel dashed bars (laminated-core convention).
    """

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)

        model = str(
            self._component.parameters.get("magnetic_core_model", "saturation") or "saturation"
        ).strip().lower()

        core_color = self._muted_color()

        if model == "hysteresis":
            # Two thin dashed bars — standard symbol for hysteresis / laminated core.
            pen = QPen(core_color, style.STROKE_DETAIL, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(-15, -5), QPointF(15, -5))
            painter.drawLine(QPointF(-15,  5), QPointF(15,  5))
        else:
            # Single solid bar — saturation model.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(core_color)
            painter.drawRect(QRectF(-15, -3, 30, 6))


class HystereticInductorItem(InductorItem):
    """Graphics item for the Jiles-Atherton hysteretic inductor.

    Coil (inherited) + two parallel solid core bars (laminated-core
    convention) + a small ``JA`` badge so it reads distinctly from
    the saturable inductor's dashed-bar hysteresis variant.
    """

    def _draw_symbol(self, painter: QPainter) -> None:
        super()._draw_symbol(painter)

        core_color = self._muted_color()
        # Two solid bars below the coil — magnetic core.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, core_color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-16, -6), QPointF(16, -6))
        painter.drawLine(QPointF(-16, 6), QPointF(16, 6))

        # ``JA`` tag (Jiles-Atherton) — distinguishes from the
        # saturable inductor and signals the hysteresis model.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._accent_orange()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(-16, 8, 32, 10),
            Qt.AlignmentFlag.AlignCenter, "JA",
        )

    def _get_value_text(self) -> str:
        material = str(self._component.parameters.get("material", "") or "")
        # Compact material label, e.g. "si_steel_m19" → "M19".
        short = {
            "si_steel_m19": "M19",
            "annealed_iron": "Fe",
            "ferrite_n87": "N87",
            "permalloy": "Py",
        }.get(material, material)
        return short


class CoupledInductorItem(TransformerItem):
    """Graphics item for coupled inductor (similar to transformer)."""

    def _get_value_text(self) -> str:
        k = self._component.parameters.get("coupling_coefficient", 0)
        return f"k={k:.2f}"


class SnubberRCItem(ComponentItem):
    """Graphics item for RC snubber network."""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return QRectF(-28, -18, 56, 36)

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-25, 0), QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), QPointF(25, 0))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(-18, -6, 14, 12))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.drawLine(QPointF(4, -10), QPointF(4, 10))
        painter.drawLine(QPointF(10, -10), QPointF(10, 10))

        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(-2, 0), QPointF(4, 0))
        painter.drawLine(QPointF(10, 0), QPointF(18, 0))

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        r = self._component.parameters.get("resistance", 0)
        c = self._component.parameters.get("capacitance", 0)
        return f"{format_si_value(r, 'Ω')} {format_si_value(c, 'F')}"


class _RotatingMachineItem(ComponentItem):
    """Shared draw helper for rotating machines (DC motor, PMSM).

    Renders a centred circle body with the standard ``M`` glyph and a
    glyph suffix (e.g. ``~``) that distinguishes the variant. Subclasses
    pick the suffix, the accent colour, and any extra decoration drawn
    on top via ``_draw_machine_extra``.
    """

    BODY_RADIUS = 18.0
    GLYPH_SUFFIX = ""

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(
            QRectF(-self.BODY_RADIUS - 4, -self.BODY_RADIUS - 4,
                   2 * (self.BODY_RADIUS + 4), 2 * (self.BODY_RADIUS + 4))
        )

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        for pin in self._component.pins:
            # Trace a short lead from the body edge straight to each pin.
            px, py = float(pin.x), float(pin.y)
            edge = self._closest_circle_edge(px, py, self.BODY_RADIUS)
            painter.drawLine(edge, QPointF(px, py))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), self.BODY_RADIUS, self.BODY_RADIUS)

        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        glyph = "M" + self.GLYPH_SUFFIX
        painter.drawText(
            QRectF(-self.BODY_RADIUS, -self.BODY_RADIUS,
                   2 * self.BODY_RADIUS, 2 * self.BODY_RADIUS),
            Qt.AlignmentFlag.AlignCenter, glyph,
        )

        self._draw_machine_extra(painter)

    def _draw_machine_extra(self, painter: QPainter) -> None:
        """Override to add per-machine decorations (rotor arrow, ω, etc.)."""

    @staticmethod
    def _closest_circle_edge(x: float, y: float, radius: float) -> QPointF:
        """Project (x,y) onto a circle of ``radius`` centred at the origin."""
        import math
        length = math.hypot(x, y)
        if length <= 1e-6:
            return QPointF(radius, 0.0)
        scale = radius / length
        return QPointF(x * scale, y * scale)


class DCMotorItem(_RotatingMachineItem):
    """DC motor with brush/commutator hint."""

    GLYPH_SUFFIX = ""

    def _draw_machine_extra(self, painter: QPainter) -> None:
        # Subtle commutator marks at top/bottom of the body — visual cue
        # that this is a brushed DC machine (vs. brushless PMSM below).
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.drawArc(QRectF(-6, -self.BODY_RADIUS - 2, 12, 6), 0, 180 * 16)
        painter.drawArc(QRectF(-6, self.BODY_RADIUS - 4, 12, 6), 180 * 16, 180 * 16)

    def _get_value_text(self) -> str:
        speed = self._component.parameters.get("rated_speed_rpm", 0)
        try:
            return f"{int(speed)} rpm"
        except (TypeError, ValueError):
            return ""


class PMSMSteadyItem(_RotatingMachineItem):
    """PMSM running at fixed rotor speed — ``M~`` glyph + sine hint."""

    BODY_RADIUS = 20.0
    GLYPH_SUFFIX = "~"

    def _draw_machine_extra(self, painter: QPainter) -> None:
        # Small "3φ" tag below the glyph so users distinguish from DC.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(-self.BODY_RADIUS, self.BODY_RADIUS - 12, 2 * self.BODY_RADIUS, 10),
            Qt.AlignmentFlag.AlignCenter, "3φ",
        )

    def _get_value_text(self) -> str:
        speed = self._component.parameters.get("rotor_speed_rpm", 0)
        try:
            return f"{int(speed)} rpm"
        except (TypeError, ValueError):
            return ""


class PMSMDynamicItem(_RotatingMachineItem):
    """Dynamic PMSM — same body as steady but with rotor-arrow accent."""

    BODY_RADIUS = 20.0
    GLYPH_SUFFIX = "~"

    def _draw_machine_extra(self, painter: QPainter) -> None:
        # Rotor arrow — quarter-arc with an arrow head, signals dynamic
        # mech state (ω, θ) vs. the steady-state PMSM above.
        arc_color = self._accent_orange()
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, arc_color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(-7, -7, 14, 14), 45 * 16, 180 * 16)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, arc_color))
        painter.setBrush(arc_color)
        painter.drawPolygon(QPolygonF([
            QPointF(-7, 1), QPointF(-3, -2), QPointF(-3, 4),
        ]))

        # Smaller "3φ" tag.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(-self.BODY_RADIUS, self.BODY_RADIUS - 12, 2 * self.BODY_RADIUS, 10),
            Qt.AlignmentFlag.AlignCenter, "3φ",
        )

    def _get_value_text(self) -> str:
        poles = self._component.parameters.get("pole_pairs", 0)
        try:
            return f"{int(poles)} pp"
        except (TypeError, ValueError):
            return ""


class InductionMotorItem(_RotatingMachineItem):
    """3-phase squirrel-cage induction motor — ``IM`` glyph + rotor
    cage bars. No ``~`` suffix: it's an asynchronous machine, the
    distinguishing visual from the synchronous PMSM."""

    BODY_RADIUS = 20.0
    GLYPH_SUFFIX = ""

    def _draw_symbol(self, painter: QPainter) -> None:
        # Reuse the base leads + circle, but draw an "IM" glyph instead
        # of the inherited "M"+suffix so the asynchronous machine reads
        # clearly. Replicate the base body, then overlay.
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        for pin in self._component.pins:
            px, py = float(pin.x), float(pin.y)
            edge = self._closest_circle_edge(px, py, self.BODY_RADIUS)
            painter.drawLine(edge, QPointF(px, py))

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), self.BODY_RADIUS, self.BODY_RADIUS)

        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(
            QRectF(-self.BODY_RADIUS, -self.BODY_RADIUS - 2,
                   2 * self.BODY_RADIUS, 2 * self.BODY_RADIUS),
            Qt.AlignmentFlag.AlignCenter, "IM",
        )
        self._draw_machine_extra(painter)

    def _draw_machine_extra(self, painter: QPainter) -> None:
        # Squirrel-cage hint: three short vertical rotor bars under the
        # glyph, plus a "3φ" tag at the bottom.
        bar_color = self._muted_color()
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, bar_color))
        for x in (-5.0, 0.0, 5.0):
            painter.drawLine(QPointF(x, 3), QPointF(x, 9))

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(-self.BODY_RADIUS, self.BODY_RADIUS - 11, 2 * self.BODY_RADIUS, 10),
            Qt.AlignmentFlag.AlignCenter, "3φ",
        )

    def _get_value_text(self) -> str:
        poles = self._component.parameters.get("pole_pairs", 0)
        try:
            return f"{int(poles)} pp"
        except (TypeError, ValueError):
            return ""


class ThreePhaseSourceItem(ComponentItem):
    """Three-phase grid source — circle body with big ``3~`` mark.

    Same family as the 1-phase voltage/current sources (round body) so
    the schematic stays visually coherent. The IEC ``3~`` glyph reads at
    a glance and three small colour-coded dots on the right edge tie
    each output pin to its phase.

    Pin layout (model defines): A/B/C on the right at y=±25/0, N on left.
    """

    BODY_RADIUS = 26.0

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-30, -32, 60, 64))

    def _draw_symbol(self, painter: QPainter) -> None:
        a_pin = self._pin_position_by_name("A", QPointF(30, -25))
        b_pin = self._pin_position_by_name("B", QPointF(30, 0))
        c_pin = self._pin_position_by_name("C", QPointF(30, 25))
        n_pin = self._pin_position_by_name("N", QPointF(-30, 0))

        phase_colors = (
            QColor(220, 60, 60),    # A — red
            QColor(60, 170, 80),    # B — green
            QColor(60, 130, 220),   # C — blue
        )

        # Coloured phase leads that meet the body edge at the right side.
        for pin, color in zip((a_pin, b_pin, c_pin), phase_colors):
            painter.setPen(self._symbol_pen(style.STROKE_LEAD, color))
            edge = self._edge_point(pin.y())
            painter.drawLine(edge, pin)
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(n_pin, QPointF(-self.BODY_RADIUS, 0))

        # Body — circle, same family as VoltageSourceItem.
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawEllipse(QPointF(0, 0), self.BODY_RADIUS, self.BODY_RADIUS)

        # Big IEC "3~" mark centred — universal AC source glyph.
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(
            QRectF(-self.BODY_RADIUS, -self.BODY_RADIUS - 1,
                   2 * self.BODY_RADIUS, 2 * self.BODY_RADIUS),
            Qt.AlignmentFlag.AlignCenter, "3~",
        )

        # Tiny phase dots on the right edge tie A/B/C lines to body cleanly.
        for pin, color in zip((a_pin, b_pin, c_pin), phase_colors):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(self._edge_point(pin.y()), 2.4, 2.4)

    def _edge_point(self, y: float) -> QPointF:
        """Project an outgoing right-side lead onto the circle edge."""
        import math
        # Clamp y inside body so leads at extreme y still touch the circle.
        y = max(-self.BODY_RADIUS + 0.1, min(self.BODY_RADIUS - 0.1, y))
        x = math.sqrt(max(self.BODY_RADIUS ** 2 - y ** 2, 0.0))
        return QPointF(x, y)

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        v_rms = self._component.parameters.get("v_line_rms", 0)
        freq = self._component.parameters.get("frequency", 0)
        return f"{format_si_value(v_rms, 'V')} {format_si_value(freq, 'Hz')}"


class ThreePhaseVSIItem(ComponentItem):
    """3-phase 2-level voltage source inverter (IEC inverter symbol).

    Pin layout: VDC+/VDC- on the left, A/B/C on the right. Body uses the
    standard IEC convention — a square split by a diagonal line, with
    ``=`` (DC) on the upper-left half and ``∼`` (AC) on the lower-right
    half. A small ``3φ`` superscript indicates three-phase output.
    """

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-30, -34, 60, 68))

    def _draw_symbol(self, painter: QPainter) -> None:
        vdc_p = self._pin_position_by_name("VDC+", QPointF(-35, -25))
        vdc_n = self._pin_position_by_name("VDC-", QPointF(-35, 25))
        a_pin = self._pin_position_by_name("A", QPointF(35, -25))
        b_pin = self._pin_position_by_name("B", QPointF(35, 0))
        c_pin = self._pin_position_by_name("C", QPointF(35, 25))

        body = QRectF(-26, -30, 52, 60)
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # DC leads on the left (red for +, neutral for −).
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, self._accent_red()))
        painter.drawLine(vdc_p, QPointF(body.left(), vdc_p.y()))
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(vdc_n, QPointF(body.left(), vdc_n.y()))

        # AC leads on the right — phase-coloured (R, G, B).
        phase_colors = (
            QColor(220, 60, 60), QColor(60, 170, 80), QColor(60, 130, 220),
        )
        for pin, color in zip((a_pin, b_pin, c_pin), phase_colors):
            painter.setPen(self._symbol_pen(style.STROKE_LEAD, color))
            painter.drawLine(QPointF(body.right(), pin.y()), pin)

        # IEC inverter mark: diagonal divider from bottom-left to top-right.
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        diag_pad = 8.0
        painter.drawLine(
            QPointF(body.left() + diag_pad, body.bottom() - diag_pad),
            QPointF(body.right() - diag_pad, body.top() + diag_pad),
        )

        # Upper-left half → DC mark ("=").
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        dc_x_center = body.left() + 16
        dc_y_center = body.top() + 18
        painter.drawLine(
            QPointF(dc_x_center - 7, dc_y_center - 3),
            QPointF(dc_x_center + 7, dc_y_center - 3),
        )
        painter.drawLine(
            QPointF(dc_x_center - 7, dc_y_center + 3),
            QPointF(dc_x_center + 7, dc_y_center + 3),
        )

        # Lower-right half → AC mark ("∼") + small superscript "3φ".
        ac_x_center = body.right() - 16
        ac_y_center = body.bottom() - 18
        import math
        path = QPainterPath()
        steps = 22
        amp = 4.0
        half_w = 9.0
        for i in range(steps + 1):
            t = i / steps
            x = ac_x_center - half_w + t * 2 * half_w
            y = ac_y_center + math.sin(t * 2 * math.pi) * amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(self._symbol_pen(style.STROKE_BODY, self._line_color()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # "3φ" superscript next to the AC mark.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(ac_x_center - 12, ac_y_center - 14, 24, 9),
            Qt.AlignmentFlag.AlignCenter, "3φ",
        )

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        f_pwm = self._component.parameters.get("pwm_frequency", 0)
        return format_si_value(f_pwm, "Hz") if f_pwm else ""


class ThreePhaseRLLoadItem(ComponentItem):
    """3-phase RL load — three R+L pairs joined at a neutral point.

    Pin layout: A/B/C on the left, N on the right.
    """

    def boundingRect(self) -> QRectF:
        """Return the local-space rectangle used for painting and hit-testing."""
        return self._with_pin_bounds(QRectF(-26, -34, 52, 68))

    def _draw_symbol(self, painter: QPainter) -> None:
        a_pin = self._pin_position_by_name("A", QPointF(-30, -25))
        b_pin = self._pin_position_by_name("B", QPointF(-30, 0))
        c_pin = self._pin_position_by_name("C", QPointF(-30, 25))
        n_pin = self._pin_position_by_name("N", QPointF(30, 0))

        body = QRectF(-20, -30, 40, 60)
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # Coloured phase leads in (left side).
        phase_colors = (
            QColor(220, 60, 60), QColor(60, 170, 80), QColor(60, 130, 220),
        )
        for pin, color in zip((a_pin, b_pin, c_pin), phase_colors):
            painter.setPen(self._symbol_pen(style.STROKE_LEAD, color))
            painter.drawLine(pin, QPointF(body.left(), pin.y()))

        # Neutral lead out (right side).
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(body.right(), 0), n_pin)

        # Three R+L glyph pairs converging into a Y-junction at the right.
        junction_x = body.right() - 6
        for idx, (color, y) in enumerate(zip(phase_colors, (-20.0, 0.0, 20.0))):
            x0 = body.left() + 3
            # Resistor block
            r_rect = QRectF(x0, y - 3, 9, 6)
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL, color))
            painter.setBrush(self._surface_color())
            painter.drawRect(r_rect)
            # Inductor coils — two small bumps
            for i in range(2):
                painter.drawArc(QRectF(x0 + 11 + i * 5, y - 3, 5, 6), 0, 180 * 16)
            # Tail line to the junction
            painter.drawLine(QPointF(x0 + 22, y), QPointF(junction_x, y))
            # Vertical join to neutral
            painter.drawLine(QPointF(junction_x, y), QPointF(junction_x, 0))

        # Centre dot at the neutral junction.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._line_color())
        painter.drawEllipse(QPointF(junction_x, 0), 2.0, 2.0)

        # Topology label.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        topology = str(self._component.parameters.get("topology", "Y") or "Y").upper()
        painter.drawText(
            QRectF(body.left(), body.bottom() - 11, body.width(), 10),
            Qt.AlignmentFlag.AlignCenter, f"RL · {topology}",
        )

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        r = self._component.parameters.get("resistance", 0)
        l = self._component.parameters.get("inductance", 0)
        return f"{format_si_value(r, 'Ω')} {format_si_value(l, 'H')}"


# ---------------------------------------------------------------------------
# Shared helper — textbook diode glyph (filled triangle + cathode bar)
# ---------------------------------------------------------------------------
def _draw_diode_glyph(
    painter: QPainter,
    anode: QPointF,
    cathode: QPointF,
    *,
    body_color: QColor,
    surface_color: QColor,
    size: float = 5.0,
) -> None:
    """Draw a diode symbol pointing from ``anode`` to ``cathode``.

    The symbol is the classic filled triangle + cathode bar:
        anode ─▶|─ cathode
    Geometry is centred on the midpoint of (anode, cathode) and scales
    with ``size`` (the triangle half-base, in scene units).
    """
    import math
    dx, dy = cathode.x() - anode.x(), cathode.y() - anode.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length          # unit vector anode→cathode
    px, py = -uy, ux                            # perpendicular unit
    cx, cy = (anode.x() + cathode.x()) / 2, (anode.y() + cathode.y()) / 2

    # Triangle: base at midpoint-back, apex at midpoint-forward.
    apex_x = cx + ux * size
    apex_y = cy + uy * size
    base_lx = cx - ux * size + px * size
    base_ly = cy - uy * size + py * size
    base_rx = cx - ux * size - px * size
    base_ry = cy - uy * size - py * size

    triangle = QPainterPath()
    triangle.moveTo(base_lx, base_ly)
    triangle.lineTo(base_rx, base_ry)
    triangle.lineTo(apex_x, apex_y)
    triangle.closeSubpath()

    painter.setPen(QPen(body_color, 1.0))
    painter.setBrush(body_color)
    painter.drawPath(triangle)

    # Cathode bar: perpendicular to anode→cathode, at the apex.
    bar_lx = apex_x + px * size * 0.9
    bar_ly = apex_y + py * size * 0.9
    bar_rx = apex_x - px * size * 0.9
    bar_ry = apex_y - py * size * 0.9
    painter.setPen(QPen(body_color, 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(bar_lx, bar_ly), QPointF(bar_rx, bar_ry))

    # Restore brush state for the caller
    painter.setBrush(surface_color)


def _draw_mosfet_glyph(
    painter: QPainter,
    drain: QPointF,
    source: QPointF,
    *,
    body_color: QColor,
    surface_color: QColor,
    width: float = 9.0,
) -> None:
    """Compact MOSFET-with-body-diode glyph (drain on ``drain`` side).

    Draws a rounded body rectangle straddling the drain↔source segment,
    with a tiny diagonal slash to hint "switch + body diode" without
    cluttering the cell-level schematic.
    """
    import math
    dx, dy = source.x() - drain.x(), source.y() - drain.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length          # along drain→source
    px, py = -uy, ux                            # perpendicular

    # Centre of body
    cx, cy = (drain.x() + source.x()) / 2, (drain.y() + source.y()) / 2
    half_along = min(length / 2 - 2, 6.0)
    half_perp = width / 2

    # 4 corners of the body rectangle (oriented along drain-source axis)
    a = QPointF(cx + ux * half_along + px * half_perp,
                cy + uy * half_along + py * half_perp)
    b = QPointF(cx + ux * half_along - px * half_perp,
                cy + uy * half_along - py * half_perp)
    c = QPointF(cx - ux * half_along - px * half_perp,
                cy - uy * half_along - py * half_perp)
    d = QPointF(cx - ux * half_along + px * half_perp,
                cy - uy * half_along + py * half_perp)

    body_path = QPainterPath()
    body_path.moveTo(a)
    body_path.lineTo(b)
    body_path.lineTo(c)
    body_path.lineTo(d)
    body_path.closeSubpath()

    painter.setPen(QPen(body_color, 1.2))
    painter.setBrush(surface_color)
    painter.drawPath(body_path)

    # Drain-source short lines (leads inside the body)
    painter.setPen(QPen(body_color, 1.4))
    painter.drawLine(drain, QPointF(cx + ux * half_along, cy + uy * half_along))
    painter.drawLine(source, QPointF(cx - ux * half_along, cy - uy * half_along))

    # Diagonal "switch" hint inside the body
    painter.setPen(QPen(body_color, 1.0))
    painter.drawLine(
        QPointF(cx - ux * (half_along - 2) + px * (half_perp - 2),
                cy - uy * (half_along - 2) + py * (half_perp - 2)),
        QPointF(cx + ux * (half_along - 2) - px * (half_perp - 2),
                cy + uy * (half_along - 2) - py * (half_perp - 2)),
    )


def _draw_cap_glyph(
    painter: QPainter,
    top: QPointF,
    bottom: QPointF,
    *,
    body_color: QColor,
    plate_half: float = 5.0,
) -> None:
    """Two parallel plates between two endpoints (capacitor symbol)."""
    import math
    dx, dy = bottom.x() - top.x(), bottom.y() - top.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    # Plates 25% / 75% of the way from top to bottom
    p1 = QPointF(top.x() + ux * length * 0.42, top.y() + uy * length * 0.42)
    p2 = QPointF(top.x() + ux * length * 0.58, top.y() + uy * length * 0.58)

    painter.setPen(QPen(body_color, 1.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(p1.x() + px * plate_half, p1.y() + py * plate_half),
                     QPointF(p1.x() - px * plate_half, p1.y() - py * plate_half))
    painter.drawLine(QPointF(p2.x() + px * plate_half, p2.y() + py * plate_half),
                     QPointF(p2.x() - px * plate_half, p2.y() - py * plate_half))
    # Leads
    painter.setPen(QPen(body_color, 1.2))
    painter.drawLine(top, p1)
    painter.drawLine(p2, bottom)


# ---------------------------------------------------------------------------
# Single-phase Graetz diode bridge (4 diodes)
# ---------------------------------------------------------------------------
class SinglePhaseDiodeBridgeItem(ComponentItem):
    """Single-phase 4-diode Graetz rectifier bridge.

    Pin layout: AC+/AC- on the left, DC+/DC- on the right. Uses the
    "rails-and-pillars" representation (consistent with the 3-phase
    bridge): top rail = DC+, bottom rail = DC-, two vertical phase
    columns (one per AC terminal) each with a proper diode glyph to
    each rail.
    """

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._with_pin_bounds(QRectF(-32, -28, 64, 56))

    def _draw_symbol(self, painter: QPainter) -> None:
        acp = self._pin_position_by_name("AC+", QPointF(-35, -20))
        acn = self._pin_position_by_name("AC-", QPointF(-35, 20))
        dcp = self._pin_position_by_name("DC+", QPointF(35, -20))
        dcn = self._pin_position_by_name("DC-", QPointF(35, 20))

        body = QRectF(-28, -24, 56, 48)
        line_color = self._line_color()
        surface_color = self._surface_color()
        red = self._accent_red()
        muted = self._muted_color()
        ac_color = QColor(60, 130, 220)        # blue tint for AC

        # Body
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(surface_color)
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # External leads
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, red))
        painter.drawLine(QPointF(body.right(), dcp.y()), dcp)
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(body.right(), dcn.y()), dcn)
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, ac_color))
        painter.drawLine(acp, QPointF(body.left(), acp.y()))
        painter.drawLine(acn, QPointF(body.left(), acn.y()))

        # Internal DC rails — horizontal bus bars near the top and bottom.
        rail_top_y = body.top() + 8
        rail_bot_y = body.bottom() - 8
        rail_left_x = body.left() + 9
        rail_right_x = body.right() - 9
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, red))
        painter.drawLine(QPointF(rail_left_x, rail_top_y),
                         QPointF(rail_right_x, rail_top_y))
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
        painter.drawLine(QPointF(rail_left_x, rail_bot_y),
                         QPointF(rail_right_x, rail_bot_y))

        # Connect external DC leads INTO the internal rails (right side).
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, red))
        painter.drawLine(QPointF(body.right(), dcp.y()),
                         QPointF(rail_right_x, dcp.y()))
        painter.drawLine(QPointF(rail_right_x, dcp.y()),
                         QPointF(rail_right_x, rail_top_y))
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
        painter.drawLine(QPointF(body.right(), dcn.y()),
                         QPointF(rail_right_x, dcn.y()))
        painter.drawLine(QPointF(rail_right_x, dcn.y()),
                         QPointF(rail_right_x, rail_bot_y))

        # 2 phase columns (one for AC+, one for AC-). Each column has
        # an upper diode (anode=phase, cathode=DC+ rail) and a lower
        # diode (anode=DC- rail, cathode=phase).
        col_x = [-7, +7]
        ac_pin_ys = (acp.y(), acn.y())
        for i, x in enumerate(col_x):
            pin_y = ac_pin_ys[i]
            # Vertical phase tap (between the two diodes)
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL, ac_color))
            painter.drawLine(QPointF(x, rail_top_y + 8),
                             QPointF(x, rail_bot_y - 8))
            # Stub from AC lead row into the column
            painter.drawLine(QPointF(body.left(), pin_y), QPointF(x, pin_y))
            # Junction dot at the connection point
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ac_color)
            painter.drawEllipse(QPointF(x, pin_y), 1.6, 1.6)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # Upper diode (phase → DC+ rail)
            _draw_diode_glyph(painter,
                              anode=QPointF(x, rail_top_y + 8),
                              cathode=QPointF(x, rail_top_y),
                              body_color=line_color,
                              surface_color=surface_color,
                              size=3.0)
            # Lower diode (DC- rail → phase)
            _draw_diode_glyph(painter,
                              anode=QPointF(x, rail_bot_y),
                              cathode=QPointF(x, rail_bot_y - 8),
                              body_color=line_color,
                              surface_color=surface_color,
                              size=3.0)

        # Polarity hints flush against the right edge.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, red))
        font = QFont()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.right() - 14, rail_top_y - 4, 10, 8),
            Qt.AlignmentFlag.AlignRight, "+",
        )
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
        painter.drawText(
            QRectF(body.right() - 14, rail_bot_y - 4, 10, 8),
            Qt.AlignmentFlag.AlignRight, "−",
        )

        # "1φ" badge in the top-left corner so it doesn't overlap with
        # the diodes or rails.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
        font.setPointSize(6)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.left() + 3, body.top() + 2, 16, 8),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "1φ",
        )

    def _get_value_text(self) -> str:
        return "Graetz"


# ---------------------------------------------------------------------------
# Three-phase 6-pulse diode bridge (6 diodes)
# ---------------------------------------------------------------------------
class ThreePhaseDiodeBridgeItem(ComponentItem):
    """Three-phase 6-diode rectifier bridge (6-pulse).

    Pin layout: A/B/C on the left, DC+/DC- on the right. Uses textbook
    rails-and-pillars: two horizontal DC rails (red top = DC+, neutral
    bottom = DC-) and 3 vertical phase columns each with a proper
    diode glyph to the top rail and from the bottom rail.
    """

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._with_pin_bounds(QRectF(-32, -34, 64, 68))

    def _draw_symbol(self, painter: QPainter) -> None:
        a = self._pin_position_by_name("A", QPointF(-35, -25))
        b = self._pin_position_by_name("B", QPointF(-35, 0))
        c = self._pin_position_by_name("C", QPointF(-35, 25))
        dcp = self._pin_position_by_name("DC+", QPointF(35, -20))
        dcn = self._pin_position_by_name("DC-", QPointF(35, 20))

        body = QRectF(-28, -30, 56, 60)
        line_color = self._line_color()
        surface_color = self._surface_color()
        red = self._accent_red()
        phase_colors = (
            QColor(220, 60, 60),  # A — red
            QColor(60, 170, 80),  # B — green
            QColor(60, 130, 220), # C — blue
        )

        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(surface_color)
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # Phase-coloured AC leads (left).
        for pin, color in zip((a, b, c), phase_colors):
            painter.setPen(self._symbol_pen(style.STROKE_LEAD, color))
            painter.drawLine(pin, QPointF(body.left(), pin.y()))

        # DC leads (right): red for +, neutral for −.
        painter.setPen(self._symbol_pen(style.STROKE_LEAD, red))
        painter.drawLine(QPointF(body.right(), dcp.y()), dcp)
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(QPointF(body.right(), dcn.y()), dcn)

        # Internal DC rails (horizontal bus bars).
        rail_top_y = body.top() + 8
        rail_bot_y = body.bottom() - 8
        rail_left_x = body.left() + 8
        rail_right_x = body.right() - 8
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, red))
        painter.drawLine(QPointF(rail_left_x, rail_top_y),
                         QPointF(rail_right_x, rail_top_y))
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.drawLine(QPointF(rail_left_x, rail_bot_y),
                         QPointF(rail_right_x, rail_bot_y))

        # Three phase columns (one per phase). Each column has a vertical
        # phase tap with a diode glyph to the top rail (upward) and a
        # second diode glyph from the bottom rail (also pointing up toward
        # the phase tap — anode is on the bottom rail).
        col_y_top = rail_top_y + 4
        col_y_bot = rail_bot_y - 4
        col_mid_y = (rail_top_y + rail_bot_y) / 2
        for i, color in enumerate(phase_colors):
            x = body.left() + 12 + i * 11
            # Vertical phase bus across the central region
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL, color))
            painter.drawLine(QPointF(x, col_y_top + 10),
                             QPointF(x, col_y_bot - 10))
            # Stub from the AC lead row into the phase column (so each
            # column visually connects back to its A/B/C lead).
            pin_y = (a, b, c)[i].y()
            painter.drawLine(QPointF(body.left(), pin_y), QPointF(x, pin_y))
            # Junction dot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, pin_y), 1.4, 1.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # Upper diode: anode=phase tap, cathode=DC+ rail
            _draw_diode_glyph(painter,
                              anode=QPointF(x, col_y_top + 10),
                              cathode=QPointF(x, rail_top_y),
                              body_color=line_color, surface_color=surface_color,
                              size=3.0)
            # Lower diode: anode=DC- rail, cathode=phase tap
            _draw_diode_glyph(painter,
                              anode=QPointF(x, rail_bot_y),
                              cathode=QPointF(x, col_y_bot - 10),
                              body_color=line_color, surface_color=surface_color,
                              size=3.0)

        # Polarity hints next to the DC rails
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, red))
        font = QFont()
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            QRectF(rail_right_x - 12, rail_top_y - 5, 10, 8),
            Qt.AlignmentFlag.AlignRight, "+",
        )
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        painter.drawText(
            QRectF(rail_right_x - 12, rail_bot_y - 3, 10, 8),
            Qt.AlignmentFlag.AlignRight, "−",
        )

        # "3φ" badge in the top-left corner (clear of all diodes & rails)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font.setPointSize(6)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.left() + 3, body.top() + 2, 16, 8),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "3φ",
        )

    def _get_value_text(self) -> str:
        return "6-pulse"


# ---------------------------------------------------------------------------
# MMC sub-module cell — unified item with topology branch
# ---------------------------------------------------------------------------
class MMCCellItem(ComponentItem):
    """MMC sub-module cell — both half-bridge and full-bridge in one item.

    The ``cell_topology`` parameter ("Half-Bridge" or "Full-Bridge")
    selects the inner symbol; pin count is updated by
    ``_synchronize_mmc_cell`` in the model layer.

    Pin layout:
        Half-Bridge: TOP, BOT (power) + S1_G, S2_G (gates)
        Full-Bridge: TOP, BOT (power) + S1_G..S4_G (gates)
    """

    def _topology(self) -> str:
        return str(self._component.parameters.get("cell_topology")
                   or "Half-Bridge")

    def boundingRect(self) -> QRectF:  # noqa: N802
        if self._topology() == "Full-Bridge":
            return self._with_pin_bounds(QRectF(-32, -38, 64, 76))
        return self._with_pin_bounds(QRectF(-32, -34, 64, 68))

    def _draw_symbol(self, painter: QPainter) -> None:
        if self._topology() == "Full-Bridge":
            self._draw_full_bridge(painter)
        else:
            self._draw_half_bridge(painter)

    # ----- shared chrome -------------------------------------------------
    def _draw_cell_chrome(self, painter: QPainter, body: QRectF,
                           label: str) -> None:
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(self._surface_color())
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # Corner topology badge (top-right)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, self._muted_color()))
        font = QFont()
        font.setBold(True)
        font.setPointSize(6)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.right() - 26, body.top() + 2, 24, 9),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, label,
        )

    def _draw_power_and_gate_leads(self, painter: QPainter,
                                     body: QRectF,
                                     top: QPointF, bot: QPointF,
                                     gates: list[QPointF]) -> None:
        # Power leads (left) — solid heavier stroke.
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(top, QPointF(body.left(), top.y()))
        painter.drawLine(bot, QPointF(body.left(), bot.y()))
        # Gate leads (right) — thinner muted lines so they read as control.
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL,
                                         self._muted_color()))
        for g in gates:
            painter.drawLine(QPointF(body.right(), g.y()), g)

    # ----- half-bridge variant -------------------------------------------
    def _draw_half_bridge(self, painter: QPainter) -> None:
        top = self._pin_position_by_name("TOP", QPointF(-30, -25))
        bot = self._pin_position_by_name("BOT", QPointF(-30, 25))
        g1 = self._pin_position_by_name("S1_G", QPointF(30, -15))
        g2 = self._pin_position_by_name("S2_G", QPointF(30, 15))

        body = QRectF(-28, -30, 56, 60)
        self._draw_cell_chrome(painter, body, "½H")
        self._draw_power_and_gate_leads(painter, body, top, bot, [g1, g2])

        line = self._line_color()
        surface = self._surface_color()
        red = self._accent_red()
        muted = self._muted_color()

        # Geometry
        sw_x = -2                              # switch column (slightly left of centre)
        cap_x = body.right() - 12              # cap column (right side)
        rail_top_y = body.top() + 8            # cap-positive rail
        rail_bot_y = body.bottom() - 8         # cap-negative rail
        routing_x = body.left() + 8            # TOP/BOT pin routing column

        # Cap (vertical)
        _draw_cap_glyph(painter, QPointF(cap_x, rail_top_y),
                        QPointF(cap_x, rail_bot_y),
                        body_color=line, plate_half=5.0)

        # Top rail (red, cap+ to upper switch drain)
        painter.setPen(QPen(red, 1.4))
        painter.drawLine(QPointF(sw_x, rail_top_y),
                         QPointF(cap_x, rail_top_y))

        # Bot rail (neutral, cap- to lower switch source and BOT pin)
        painter.setPen(QPen(line, 1.4))
        painter.drawLine(QPointF(routing_x, rail_bot_y),
                         QPointF(cap_x, rail_bot_y))
        # BOT pin trace: from body.left at bot.y → routing_x → rail
        painter.drawLine(QPointF(body.left(), bot.y()),
                         QPointF(routing_x, bot.y()))
        painter.drawLine(QPointF(routing_x, bot.y()),
                         QPointF(routing_x, rail_bot_y))

        # Two MOSFETs stacked on the switch column
        sw_hi_top = QPointF(sw_x, rail_top_y)
        sw_hi_bot = QPointF(sw_x, -5)
        sw_lo_top = QPointF(sw_x, 5)
        sw_lo_bot = QPointF(sw_x, rail_bot_y)
        _draw_mosfet_glyph(painter, sw_hi_top, sw_hi_bot,
                           body_color=line, surface_color=surface, width=9.0)
        _draw_mosfet_glyph(painter, sw_lo_top, sw_lo_bot,
                           body_color=line, surface_color=surface, width=9.0)

        # Bot rail continues to lower switch source
        painter.setPen(QPen(line, 1.4))
        painter.drawLine(sw_lo_bot, QPointF(sw_x, rail_bot_y))

        # AC midpoint: between the two switches, at y=0
        ac_mid = QPointF(sw_x, 0)
        painter.drawLine(sw_hi_bot, ac_mid)
        painter.drawLine(ac_mid, sw_lo_top)

        # TOP pin trace: body.left at top.y → routing_x → down to ac_mid.y → right to ac_mid
        painter.drawLine(QPointF(body.left(), top.y()),
                         QPointF(routing_x, top.y()))
        painter.drawLine(QPointF(routing_x, top.y()),
                         QPointF(routing_x, ac_mid.y()))
        painter.drawLine(QPointF(routing_x, ac_mid.y()), ac_mid)

        # Junction dots: AC midpoint + routing tee
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(line)
        painter.drawEllipse(ac_mid, 1.5, 1.5)
        painter.drawEllipse(QPointF(routing_x, ac_mid.y()), 1.2, 1.2)
        painter.drawEllipse(QPointF(routing_x, bot.y()), 1.2, 1.2)
        painter.setBrush(red)
        painter.drawEllipse(QPointF(cap_x, rail_top_y), 1.6, 1.6)
        painter.setBrush(line)
        painter.drawEllipse(QPointF(cap_x, rail_bot_y), 1.6, 1.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Gate stubs (dashed, muted) from switch bodies to gate pins
        painter.setPen(QPen(muted, 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(sw_x + 5, (sw_hi_top.y() + sw_hi_bot.y()) / 2),
                         QPointF(g1.x() - 2, g1.y()))
        painter.drawLine(QPointF(sw_x + 5, (sw_lo_top.y() + sw_lo_bot.y()) / 2),
                         QPointF(g2.x() - 2, g2.y()))

    # ----- full-bridge variant -------------------------------------------
    def _draw_full_bridge(self, painter: QPainter) -> None:
        # Pin map: TOP/BOT on the left (power), S1..S4_G on the right.
        # We draw the full-bridge as TWO STACKED HALF-BRIDGE LEGS — the
        # upper leg (S1/S2) feeds the TOP terminal; the lower leg
        # (S3/S4) feeds the BOT terminal. Both legs share the same
        # cap, which sits between them at the right side. This stays
        # true to the kernel topology (4 switches, common cap, 2 AC
        # taps) while routing cleanly to the LEFT-side pin layout.
        top = self._pin_position_by_name("TOP", QPointF(-30, -30))
        bot = self._pin_position_by_name("BOT", QPointF(-30, 30))
        g1 = self._pin_position_by_name("S1_G", QPointF(30, -25))
        g2 = self._pin_position_by_name("S2_G", QPointF(30, -10))
        g3 = self._pin_position_by_name("S3_G", QPointF(30, 10))
        g4 = self._pin_position_by_name("S4_G", QPointF(30, 25))

        body = QRectF(-28, -34, 56, 68)
        self._draw_cell_chrome(painter, body, "H")
        self._draw_power_and_gate_leads(painter, body, top, bot,
                                         [g1, g2, g3, g4])

        line = self._line_color()
        surface = self._surface_color()
        red = self._accent_red()
        muted = self._muted_color()

        # Geometry
        sw_x = -2
        cap_x = body.right() - 12
        rail_top_y = body.top() + 7    # cap+ rail
        rail_bot_y = body.bottom() - 7  # cap- rail
        routing_x = body.left() + 8     # TOP/BOT pin routing column
        upper_mid_y = -17               # AC mid of upper leg → TOP pin
        lower_mid_y = 17                # AC mid of lower leg → BOT pin

        # Cap (vertical, spans both legs)
        _draw_cap_glyph(painter, QPointF(cap_x, rail_top_y),
                        QPointF(cap_x, rail_bot_y),
                        body_color=line, plate_half=6.0)

        # Top rail (red): connects upper-leg upper switch drain + lower-leg
        # upper switch drain + cap+
        painter.setPen(QPen(red, 1.4))
        painter.drawLine(QPointF(sw_x, rail_top_y),
                         QPointF(cap_x, rail_top_y))
        # Bot rail (neutral): cap- + lower-leg lower switch source + upper-leg
        # lower switch source
        painter.setPen(QPen(line, 1.4))
        painter.drawLine(QPointF(sw_x, rail_bot_y),
                         QPointF(cap_x, rail_bot_y))

        # Upper leg switches (S1 = upper-upper, S2 = upper-lower)
        s1_top = QPointF(sw_x, rail_top_y)
        s1_bot = QPointF(sw_x, upper_mid_y - 4)
        s2_top = QPointF(sw_x, upper_mid_y + 4)
        s2_bot = QPointF(sw_x, -3)           # ends just above center

        # Lower leg switches (S3 = lower-upper, S4 = lower-lower)
        s3_top = QPointF(sw_x, 3)             # starts just below center
        s3_bot = QPointF(sw_x, lower_mid_y - 4)
        s4_top = QPointF(sw_x, lower_mid_y + 4)
        s4_bot = QPointF(sw_x, rail_bot_y)

        for (a, b) in ((s1_top, s1_bot), (s2_top, s2_bot),
                       (s3_top, s3_bot), (s4_top, s4_bot)):
            _draw_mosfet_glyph(painter, a, b,
                               body_color=line, surface_color=surface, width=9.0)

        # Inter-leg rail tie (centre): connects upper-leg source rail to
        # lower-leg drain rail. Both upper-S2's source and lower-S3's
        # drain land at y≈0. In the H-bridge topology this is where the
        # cap's MIDDLE would conceptually be — but our cap is on the
        # right, so this central node is just a structural shorthand.
        # Skip drawing it (each leg is independent of the other through
        # the shared cap on the right).

        # AC mid-taps with junction dots
        ac_upper = QPointF(sw_x, upper_mid_y)
        ac_lower = QPointF(sw_x, lower_mid_y)
        painter.setPen(QPen(line, 1.4))
        painter.drawLine(s1_bot, ac_upper)
        painter.drawLine(ac_upper, s2_top)
        painter.drawLine(s3_bot, ac_lower)
        painter.drawLine(ac_lower, s4_top)

        # TOP pin trace: body.left at top.y → routing_x → down to upper AC mid → right to AC tap
        painter.drawLine(QPointF(body.left(), top.y()),
                         QPointF(routing_x, top.y()))
        painter.drawLine(QPointF(routing_x, top.y()),
                         QPointF(routing_x, ac_upper.y()))
        painter.drawLine(QPointF(routing_x, ac_upper.y()), ac_upper)

        # BOT pin trace: body.left at bot.y → routing_x → up to lower AC mid → right to AC tap
        painter.drawLine(QPointF(body.left(), bot.y()),
                         QPointF(routing_x, bot.y()))
        painter.drawLine(QPointF(routing_x, bot.y()),
                         QPointF(routing_x, ac_lower.y()))
        painter.drawLine(QPointF(routing_x, ac_lower.y()), ac_lower)

        # Junction dots
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(line)
        painter.drawEllipse(ac_upper, 1.5, 1.5)
        painter.drawEllipse(ac_lower, 1.5, 1.5)
        painter.drawEllipse(QPointF(routing_x, ac_upper.y()), 1.2, 1.2)
        painter.drawEllipse(QPointF(routing_x, ac_lower.y()), 1.2, 1.2)
        painter.setBrush(red)
        painter.drawEllipse(QPointF(cap_x, rail_top_y), 1.6, 1.6)
        painter.setBrush(line)
        painter.drawEllipse(QPointF(cap_x, rail_bot_y), 1.6, 1.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Gate stubs (dashed, muted) from switch bodies to gate pins
        painter.setPen(QPen(muted, 1.0, Qt.PenStyle.DashLine))
        for sw_top_pt, sw_bot_pt, gate_pt in (
            (s1_top, s1_bot, g1),
            (s2_top, s2_bot, g2),
            (s3_top, s3_bot, g3),
            (s4_top, s4_bot, g4),
        ):
            sw_mid = QPointF(sw_x + 5,
                              (sw_top_pt.y() + sw_bot_pt.y()) / 2)
            painter.drawLine(sw_mid, QPointF(gate_pt.x() - 2, gate_pt.y()))

    # ----- value text shown next to the body ----------------------------
    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        c = self._component.parameters.get("c_cell", 0)
        topology = "FB" if self._topology() == "Full-Bridge" else "HB"
        return f"{topology} · {format_si_value(c, 'F')}" if c else topology


# ---------------------------------------------------------------------------
# MMC arm — chain of N sub-modules with selectable fidelity (L0..L3)
# ---------------------------------------------------------------------------
class MMCArmItem(ComponentItem):
    """MMC arm block. Visually a tall rectangle representing a chain
    of N sub-modules; the model-fidelity badge (L0/L1/L2/L3) sits in
    the top-right corner, the N submodule count + SM type in the
    bottom-left, and the M_REF input pin sticks out on the right.

    Pin layout: TOP / BOT (chain endpoints, on the LEFT) + M_REF
    (modulation input, on the RIGHT).
    """

    def _fidelity_short(self) -> str:
        """Return the 2-char fidelity tag (L0..L3)."""
        full = str(self._component.parameters.get("model_fidelity")
                   or "L3 Detailed")
        return full.split(" ", 1)[0] if " " in full else full[:2]

    def _submodule_short(self) -> str:
        smt = str(self._component.parameters.get("submodule_type")
                   or "Half-Bridge")
        return "FB" if smt.startswith("Full") else "HB"

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._with_pin_bounds(QRectF(-38, -52, 76, 104))

    def _draw_symbol(self, painter: QPainter) -> None:
        top = self._pin_position_by_name("TOP", QPointF(-35, -40))
        bot = self._pin_position_by_name("BOT", QPointF(-35, 40))
        mref = self._pin_position_by_name("M_REF", QPointF(35, 0))

        body = QRectF(-34, -48, 68, 96)
        line = self._line_color()
        surface = self._surface_color()
        muted = self._muted_color()
        red = self._accent_red()

        # Body
        painter.setPen(self._symbol_pen(style.STROKE_BODY))
        painter.setBrush(surface)
        painter.drawRoundedRect(body, style.BLOCK_RADIUS, style.BLOCK_RADIUS)

        # Power leads on the LEFT (heavy)
        painter.setPen(self._lead_pen(style.STROKE_LEAD))
        painter.drawLine(top, QPointF(body.left(), top.y()))
        painter.drawLine(bot, QPointF(body.left(), bot.y()))
        # M_REF input on the RIGHT (muted, signal-style)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
        painter.drawLine(QPointF(body.right(), mref.y()), mref)

        # Render the chain as N stacked sub-module mini-boxes inside
        # the body. We cap the visual count at 6 so very long chains
        # don't degenerate into a flat strip.
        try:
            n_sm = max(1, min(6, int(self._component.parameters.get(
                "n_submodules", 4))))
        except (TypeError, ValueError):
            n_sm = 4

        margin_top = body.top() + 8
        margin_bot = body.bottom() - 14   # leave room for label band
        slot_h = (margin_bot - margin_top) / max(n_sm, 1)
        sm_x_left = body.left() + 10
        sm_x_right = body.right() - 22

        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, line))
        painter.setBrush(surface)
        for i in range(n_sm):
            y_top = margin_top + i * slot_h + 1
            y_bot = margin_top + (i + 1) * slot_h - 1
            rect = QRectF(sm_x_left, y_top, sm_x_right - sm_x_left,
                          max(y_bot - y_top, 4))
            painter.drawRect(rect)
            # Tiny "C" marker inside each cell to suggest a capacitor
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
            font_sm = QFont()
            font_sm.setBold(True)
            font_sm.setPointSize(6)
            painter.setFont(font_sm)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "C")
            painter.setPen(self._symbol_pen(style.STROKE_DETAIL, line))

        # Connecting trace down the chain (left edge of mini-boxes)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, red))
        painter.drawLine(QPointF(body.left() + 6, margin_top - 2),
                         QPointF(body.left() + 6, margin_bot + 2))

        # Fidelity badge (top-right)
        painter.setPen(self._symbol_pen(style.STROKE_DETAIL, muted))
        font = QFont()
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.right() - 24, body.top() + 2, 22, 11),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            self._fidelity_short(),
        )

        # Submodule type + count (bottom-left band)
        font.setPointSize(6)
        painter.setFont(font)
        painter.drawText(
            QRectF(body.left() + 3, body.bottom() - 12, body.width() - 6, 10),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self._submodule_short()} × {n_sm}",
        )

        # "MMC ARM" header text
        painter.drawText(
            QRectF(body.left() + 3, body.top() + 2, body.width() - 28, 10),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            "MMC ARM",
        )

    def _get_value_text(self) -> str:
        from pulsimgui.utils.si_prefix import format_si_value
        c = self._component.parameters.get("c_sm", 0)
        n = self._component.parameters.get("n_submodules", 0)
        fid = self._fidelity_short()
        if c and n:
            return f"{fid} · {n} SM · {format_si_value(c, 'F')}"
        return fid


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
        ComponentType.C_BLOCK: CBlockItem,
        ComponentType.FOC_CONTROLLER: FOCControllerItem,
        ComponentType.PFC_BOOST_CONTROLLER: PFCBoostControllerItem,
        ComponentType.GAIN: GainItem,
        ComponentType.SUM: SumItem,
        ComponentType.SUBTRACTOR: SubtractorItem,
        ComponentType.CONSTANT: ConstantItem,

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
        ComponentType.VOLTAGE_PROBE_GND: VoltageProbeGndItem,
        ComponentType.CURRENT_PROBE: CurrentProbeItem,
        ComponentType.POWER_PROBE: PowerProbeItem,

        # Scopes
        ComponentType.ELECTRICAL_SCOPE: ElectricalScopeItem,
        ComponentType.THERMAL_SCOPE: ThermalScopeItem,

        # Signal routing
        ComponentType.SIGNAL_MUX: SignalMuxItem,
        ComponentType.SIGNAL_DEMUX: SignalDemuxItem,
        ComponentType.GOTO_LABEL: GotoLabelItem,
        ComponentType.FROM_LABEL: FromLabelItem,

        # Hierarchical
        ComponentType.SUBCIRCUIT_PORT: SubcircuitPortItem,

        # Magnetic
        ComponentType.SATURABLE_INDUCTOR: SaturableInductorItem,
        ComponentType.HYSTERETIC_INDUCTOR: HystereticInductorItem,
        ComponentType.COUPLED_INDUCTOR: CoupledInductorItem,

        # Three-phase / vector control (Pulsim Phase 28)
        ComponentType.CLARKE_TRANSFORM: ClarkeTransformItem,
        ComponentType.INVERSE_CLARKE_TRANSFORM: InverseClarkeTransformItem,
        ComponentType.PARK_TRANSFORM: ParkTransformItem,
        ComponentType.INVERSE_PARK_TRANSFORM: InverseParkTransformItem,
        ComponentType.PLL: PLLItem,
        ComponentType.SVM: SVMItem,

        # Pre-configured networks
        ComponentType.SNUBBER_RC: SnubberRCItem,

        # Motors & drives (Pulsim Phase 28+)
        ComponentType.DC_MOTOR: DCMotorItem,
        ComponentType.PMSM_STEADY_STATE: PMSMSteadyItem,
        ComponentType.PMSM: PMSMDynamicItem,
        ComponentType.INDUCTION_MOTOR: InductionMotorItem,
        ComponentType.THREE_PHASE_SOURCE: ThreePhaseSourceItem,
        ComponentType.THREE_PHASE_VSI: ThreePhaseVSIItem,
        ComponentType.THREE_PHASE_RL_LOAD: ThreePhaseRLLoadItem,

        # Power conversion — rectifier bridges & MMC sub-modules
        ComponentType.SINGLE_PHASE_DIODE_BRIDGE: SinglePhaseDiodeBridgeItem,
        ComponentType.THREE_PHASE_DIODE_BRIDGE: ThreePhaseDiodeBridgeItem,
        ComponentType.MMC_CELL: MMCCellItem,
        ComponentType.MMC_ARM: MMCArmItem,

        # Hierarchical
        ComponentType.SUBCIRCUIT: SubcircuitItem,
    }

    item_class = item_classes.get(component.type, ComponentItem)
    return item_class(component)
