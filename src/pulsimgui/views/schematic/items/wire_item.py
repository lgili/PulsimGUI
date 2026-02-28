"""Wire graphics item with orthogonal routing."""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush, QFontMetricsF
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    pin_connection_domain,
)
from pulsimgui.models.wire import Wire, WireSegment


class WireItem(QGraphicsPathItem):
    """
    Graphics item for electrical wires.

    Features:
    - Orthogonal (right-angle) routing
    - Junction dots where wires connect
    - Connection indicators at component pins
    - Selection highlighting with glow
    - Hover effects
    """

    LINE_WIDTH = 2.5  # Slightly thicker for better visibility
    LINE_WIDTH_HOVER = 3.5
    LINE_WIDTH_SELECTED = 3.0
    DOMAIN_LINE_COLORS = {
        CONNECTION_DOMAIN_CIRCUIT: QColor(16, 185, 129),
        CONNECTION_DOMAIN_SIGNAL: QColor(52, 126, 232),
        CONNECTION_DOMAIN_THERMAL: QColor(234, 108, 34),
    }
    DOMAIN_LINE_COLORS_DARK = {
        CONNECTION_DOMAIN_CIRCUIT: QColor(52, 211, 153),
        CONNECTION_DOMAIN_SIGNAL: QColor(130, 188, 255),
        CONNECTION_DOMAIN_THERMAL: QColor(255, 182, 120),
    }
    DOMAIN_HOVER_COLORS = {
        CONNECTION_DOMAIN_CIRCUIT: QColor(5, 150, 105),
        CONNECTION_DOMAIN_SIGNAL: QColor(35, 102, 212),
        CONNECTION_DOMAIN_THERMAL: QColor(211, 91, 24),
    }
    DOMAIN_HOVER_COLORS_DARK = {
        CONNECTION_DOMAIN_CIRCUIT: QColor(110, 231, 183),
        CONNECTION_DOMAIN_SIGNAL: QColor(171, 212, 255),
        CONNECTION_DOMAIN_THERMAL: QColor(255, 205, 156),
    }
    SELECTED_COLOR = QColor(59, 130, 246)  # Blue to match component selection
    SELECTED_GLOW = QColor(59, 130, 246, 60)  # Semi-transparent for glow
    JUNCTION_RADIUS = 4.2
    JUNCTION_RADIUS_HOVER = 5.2
    CONNECTION_RADIUS = 3.8  # Connection indicator circles
    CONNECTION_RADIUS_HOVER = 4.8

    def __init__(self, wire: Wire, parent=None):
        super().__init__(parent)

        self._wire = wire
        self._dark_mode = False
        self._hovered = False

        # Connected endpoints - positions where wire connects to component pins
        self._connected_endpoints: set[tuple[float, float]] = set()

        # Segment dragging state
        self._dragging_segment: int | None = None  # Index of segment being dragged
        self._drag_start_pos: QPointF | None = None
        self._drag_orientation: str | None = None  # 'horizontal' or 'vertical'
        self._drag_snapshot: list[tuple[float, float, float, float]] | None = None

        # Enable selection and hover events (NOT ItemIsMovable - we handle movement ourselves)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # Set default pen for proper bounding rect calculation
        self.setPen(QPen(self.DOMAIN_LINE_COLORS[CONNECTION_DOMAIN_CIRCUIT], self.LINE_WIDTH))

        # Build path from wire segments
        self._rebuild_path()

    @property
    def wire(self) -> Wire:
        """Get the associated wire model."""
        return self._wire

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode colors."""
        self._dark_mode = dark
        self.update()

    def set_connected_endpoints(self, endpoints: set[tuple[float, float]]) -> None:
        """Set the positions where this wire connects to component pins.

        These positions will be marked with a small circle to indicate
        a valid connection.
        """
        self._connected_endpoints = endpoints
        self.update()

    def add_connected_endpoint(self, x: float, y: float) -> None:
        """Add a single connected endpoint position."""
        self._connected_endpoints.add((x, y))
        self.update()

    def clear_connected_endpoints(self) -> None:
        """Clear all connected endpoint indicators."""
        self._connected_endpoints.clear()
        self.update()

    def _wire_domain(self) -> str:
        """Resolve wire domain from connected endpoint pin metadata."""
        domains: set[str] = set()
        for connection in (self._wire.start_connection, self._wire.end_connection):
            domain = self._connection_domain(connection)
            if domain:
                domains.add(domain)

        if CONNECTION_DOMAIN_THERMAL in domains:
            return CONNECTION_DOMAIN_THERMAL
        if CONNECTION_DOMAIN_SIGNAL in domains:
            return CONNECTION_DOMAIN_SIGNAL
        return CONNECTION_DOMAIN_CIRCUIT

    def _connection_domain(self, connection) -> str | None:
        if connection is None:
            return None
        scene = self.scene()
        circuit = getattr(scene, "circuit", None) if scene is not None else None
        if circuit is None:
            return None
        component = circuit.components.get(connection.component_id)
        if component is None:
            return None
        if connection.pin_index < 0 or connection.pin_index >= len(component.pins):
            return None
        return pin_connection_domain(component, connection.pin_index)

    def _rebuild_path(self) -> None:
        """Rebuild the QPainterPath from wire segments."""
        path = QPainterPath()

        if not self._wire.segments:
            self.setPath(path)
            return

        # Move to start of first segment
        first_seg = self._wire.segments[0]
        path.moveTo(first_seg.x1, first_seg.y1)

        # Add all segments
        for seg in self._wire.segments:
            path.lineTo(seg.x2, seg.y2)

        self.setPath(path)

    def hoverEnterEvent(self, event) -> None:
        """Handle hover enter."""
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        """Handle hover leave."""
        self._hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().hoverLeaveEvent(event)

    def boundingRect(self) -> QRectF:
        """Return bounding rect that includes connection indicators and junctions.

        The default QGraphicsPathItem bounding rect only covers the path itself.
        We need to expand it to include the circles drawn at connection points
        and junctions, plus the glow effects.
        """
        base_rect = super().boundingRect()
        if base_rect.isEmpty():
            return base_rect

        # Calculate maximum radius we might draw (connection indicator + shadow)
        max_radius = max(
            self.CONNECTION_RADIUS_HOVER + 2,  # Connection + shadow
            self.JUNCTION_RADIUS_HOVER + 2,     # Junction + shadow
            self.LINE_WIDTH_HOVER + 6           # Selection glow
        )

        # Expand rect to include circles and glows
        return base_rect.adjusted(-max_radius, -max_radius, max_radius, max_radius)

    def shape(self) -> QPainterPath:
        """Return a wider shape for easier selection."""
        # Create a stroker to make the hit area wider
        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(10.0)  # 10px wide hit area
        return stroker.createStroke(self.path())

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the wire with hover and selection effects."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Determine state and colors
        is_selected = self.isSelected()
        is_hovered = self._hovered and not is_selected
        domain = self._wire_domain()

        # Choose color and width based on state
        if is_selected:
            color = self.SELECTED_COLOR
            line_width = self.LINE_WIDTH_SELECTED
        elif is_hovered:
            color = (
                self.DOMAIN_HOVER_COLORS_DARK.get(domain, self.DOMAIN_HOVER_COLORS[CONNECTION_DOMAIN_CIRCUIT])
                if self._dark_mode
                else self.DOMAIN_HOVER_COLORS.get(domain, self.DOMAIN_HOVER_COLORS[CONNECTION_DOMAIN_CIRCUIT])
            )
            line_width = self.LINE_WIDTH_HOVER
        elif self._dark_mode:
            color = self.DOMAIN_LINE_COLORS_DARK.get(domain, self.DOMAIN_LINE_COLORS_DARK[CONNECTION_DOMAIN_CIRCUIT])
            line_width = self.LINE_WIDTH
        else:
            color = self.DOMAIN_LINE_COLORS.get(domain, self.DOMAIN_LINE_COLORS[CONNECTION_DOMAIN_CIRCUIT])
            line_width = self.LINE_WIDTH

        # Draw selection glow effect (behind the wire)
        if is_selected:
            glow_pen = QPen(self.SELECTED_GLOW, line_width + 6)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawPath(self.path())

        # Draw hover glow (subtle)
        if is_hovered:
            hover_glow = QColor(color)
            hover_glow.setAlpha(40)
            glow_pen = QPen(hover_glow, line_width + 4)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawPath(self.path())

        # Draw the main wire path
        main_pen = QPen(color, line_width)
        main_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        main_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(main_pen)
        painter.drawPath(self.path())

        # Draw junction dots with shadow effect
        junction_radius = self.JUNCTION_RADIUS_HOVER if (is_hovered or is_selected) else self.JUNCTION_RADIUS
        for junction in self._wire.junctions:
            jpt = QPointF(junction[0], junction[1])
            # Draw subtle shadow/outline (darker color behind)
            shadow_color = QColor(color)
            shadow_color.setAlpha(80)
            painter.setBrush(QBrush(shadow_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(jpt, junction_radius + 2, junction_radius + 2)
            # Draw main junction dot
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1.5))
            painter.drawEllipse(jpt, junction_radius, junction_radius)

        # Draw connection indicators at wire-to-pin connections (always visible)
        self._draw_connection_indicators(painter, color, is_hovered or is_selected)

        # Draw endpoint dots for better visibility
        if is_hovered or is_selected:
            self._draw_endpoints(painter, color)

        alias = (self._wire.alias or "").strip()
        if alias:
            self._draw_alias_label(painter, color, alias)

    def _draw_endpoints(self, painter: QPainter, color: QColor) -> None:
        """Draw small dots at wire endpoints."""
        path = self.path()
        if path.isEmpty():
            return

        # Get start and end points
        start = path.pointAtPercent(0.0)
        end = path.pointAtPercent(1.0)

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        radius = 3.0
        painter.drawEllipse(start, radius, radius)
        painter.drawEllipse(end, radius, radius)

    def _draw_connection_indicators(
        self, painter: QPainter, color: QColor, is_highlighted: bool
    ) -> None:
        """Draw connection indicator circles at points where wire connects to component pins.

        These indicators help users see when a wire is actually connected to a component
        versus just passing near it. Uses a distinctive white center with colored ring
        style for maximum visibility.
        """
        if not self._connected_endpoints:
            return

        radius = self.CONNECTION_RADIUS_HOVER if is_highlighted else self.CONNECTION_RADIUS

        for endpoint in self._connected_endpoints:
            pt = QPointF(endpoint[0], endpoint[1])

            # Draw outer glow/shadow for depth
            glow_color = QColor(color)
            glow_color.setAlpha(80)
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt, radius + 3, radius + 3)

            # Draw colored ring (the main visible element)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 2.5))
            painter.drawEllipse(pt, radius, radius)

            # Draw white/bright center dot for contrast
            inner_radius = max(2.0, radius - 2.5)
            center_color = QColor(255, 255, 255) if not self._dark_mode else QColor(240, 240, 240)
            painter.setBrush(QBrush(center_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt, inner_radius, inner_radius)

    def add_junction(self, x: float, y: float) -> None:
        """Add a junction point to the wire."""
        self._wire.junctions.append((x, y))
        self.update()

    def mousePressEvent(self, event) -> None:
        """Start dragging a wire segment."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            # Find which segment was clicked
            seg_idx = self._find_segment_at(pos)
            if seg_idx is not None:
                # Respect the same pin-lock rules used during fluid movement
                last_idx = len(self._wire.segments) - 1
                is_first_locked = (
                    seg_idx == 0 and self._wire.start_connection is not None
                )
                is_last_locked = (
                    seg_idx == last_idx and self._wire.end_connection is not None
                )
                if is_first_locked or is_last_locked:
                    # Let Qt handle selection but do not start a drag
                    super().mousePressEvent(event)
                    return

                self._drag_snapshot = [
                    (seg.x1, seg.y1, seg.x2, seg.y2)
                    for seg in self._wire.segments
                ]
                self._dragging_segment = seg_idx
                self._drag_start_pos = pos
                seg = self._wire.segments[seg_idx]
                # Determine if segment is horizontal or vertical
                if abs(seg.x2 - seg.x1) > abs(seg.y2 - seg.y1):
                    self._drag_orientation = 'horizontal'
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                else:
                    self._drag_orientation = 'vertical'
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Drag the wire segment - fluid movement without grid snapping."""
        if self._dragging_segment is not None and self._drag_start_pos is not None:
            pos = event.pos()
            delta = pos - self._drag_start_pos

            # Move segment fluidly (no grid snapping during drag)
            self._move_segment_fluid(self._dragging_segment, delta)
            self._drag_start_pos = pos
            self._rebuild_path()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finish dragging - snap to grid on release."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging_segment is not None:
                self._dragging_segment = None
                self._drag_start_pos = None
                self._drag_orientation = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                # Snap all points to grid on release
                self._snap_all_to_grid()
                # Clean up any zero-length segments
                self._cleanup_segments()
                scene = self.scene()
                if (
                    scene is not None
                    and hasattr(scene, "is_wire_path_clear")
                    and not scene.is_wire_path_clear(self._wire.segments)
                ):
                    self._restore_drag_snapshot()
                self._rebuild_path()
                if scene is not None and hasattr(scene, "refresh_wire_connection_overlays"):
                    scene.refresh_wire_connection_overlays()
                self._drag_snapshot = None
        super().mouseReleaseEvent(event)

    def _restore_drag_snapshot(self) -> None:
        """Restore wire geometry saved before drag operation."""
        if self._drag_snapshot is None:
            return
        self._wire.segments = [
            WireSegment(x1=x1, y1=y1, x2=x2, y2=y2)
            for x1, y1, x2, y2 in self._drag_snapshot
        ]

    def _find_segment_at(self, pos: QPointF) -> int | None:
        """Find which segment index is at the given position."""
        tolerance = 8.0
        for i, seg in enumerate(self._wire.segments):
            if self._point_near_segment(pos, seg, tolerance):
                return i
        return None

    def _point_near_segment(self, pos: QPointF, seg, tolerance: float) -> bool:
        """Check if a point is near a line segment."""
        x, y = pos.x(), pos.y()
        x1, y1, x2, y2 = seg.x1, seg.y1, seg.x2, seg.y2

        # Check bounding box first (with tolerance)
        min_x, max_x = min(x1, x2) - tolerance, max(x1, x2) + tolerance
        min_y, max_y = min(y1, y2) - tolerance, max(y1, y2) + tolerance
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return False

        # Calculate distance from point to line segment
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            # Segment is a point
            return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5 <= tolerance

        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        dist = ((x - proj_x) ** 2 + (y - proj_y) ** 2) ** 0.5
        return dist <= tolerance

    def hoverMoveEvent(self, event) -> None:
        """Update cursor shape based on which segment is hovered."""
        seg_idx = self._find_segment_at(event.pos())
        if seg_idx is not None:
            seg = self._wire.segments[seg_idx]
            is_h = abs(seg.x2 - seg.x1) >= abs(seg.y2 - seg.y1)

            # Pin-locked segments cannot be dragged – show plain arrow
            is_first_locked = (
                seg_idx == 0 and self._wire.start_connection is not None
            )
            is_last_locked = (
                seg_idx == len(self._wire.segments) - 1
                and self._wire.end_connection is not None
            )
            if is_first_locked or is_last_locked:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            elif is_h:
                # Horizontal segment → user slides it up/down
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                # Vertical segment → user slides it left/right
                self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def _move_segment_fluid(self, seg_idx: int, delta: QPointF) -> None:
        """
        Move a segment fluidly (no grid snapping) and stretch adjacent segments.

        The segment moves in the direction the user drags:
        - Horizontal segments move vertically (up/down)
        - Vertical segments move horizontally (left/right)
        Adjacent segments stretch to stay connected.

        Pin-connected first / last segments cannot be dragged to prevent
        disconnecting the wire endpoint from its component pin.
        """        
        if seg_idx < 0 or seg_idx >= len(self._wire.segments):
            return

        # Do not allow dragging a pin-connected first or last segment – the
        # endpoint is locked to the component pin and moving it would create
        # a disconnected diagonal stub.
        last_idx = len(self._wire.segments) - 1
        if seg_idx == 0 and self._wire.start_connection is not None:
            return
        if seg_idx == last_idx and self._wire.end_connection is not None:
            return

        seg = self._wire.segments[seg_idx]
        is_horizontal = abs(seg.x2 - seg.x1) > abs(seg.y2 - seg.y1)

        if is_horizontal:
            # Horizontal segment - move in Y direction
            dy = delta.y()
            seg.y1 += dy
            seg.y2 += dy

            # Stretch previous segment (if exists)
            if seg_idx > 0:
                prev_seg = self._wire.segments[seg_idx - 1]
                prev_seg.y2 = seg.y1

            # Stretch next segment (if exists)
            if seg_idx < len(self._wire.segments) - 1:
                next_seg = self._wire.segments[seg_idx + 1]
                next_seg.y1 = seg.y2
        else:
            # Vertical segment - move in X direction
            dx = delta.x()
            seg.x1 += dx
            seg.x2 += dx

            # Stretch previous segment (if exists)
            if seg_idx > 0:
                prev_seg = self._wire.segments[seg_idx - 1]
                prev_seg.x2 = seg.x1

            # Stretch next segment (if exists)
            if seg_idx < len(self._wire.segments) - 1:
                next_seg = self._wire.segments[seg_idx + 1]
                next_seg.x1 = seg.x2

    def _snap_all_to_grid(self) -> None:
        """Snap all segment points to the grid."""
        scene = self.scene()
        grid_size = 20.0
        if scene is not None and hasattr(scene, 'grid_size'):
            grid_size = scene.grid_size

        start_pin_pos = self._connected_pin_position("start")
        end_pin_pos = self._connected_pin_position("end")

        for seg in self._wire.segments:
            seg.x1 = round(seg.x1 / grid_size) * grid_size
            seg.y1 = round(seg.y1 / grid_size) * grid_size
            seg.x2 = round(seg.x2 / grid_size) * grid_size
            seg.y2 = round(seg.y2 / grid_size) * grid_size

        # Fix connectivity after snapping
        for i in range(len(self._wire.segments) - 1):
            curr_seg = self._wire.segments[i]
            next_seg = self._wire.segments[i + 1]
            next_seg.x1 = curr_seg.x2
            next_seg.y1 = curr_seg.y2

        # After snapping + connectivity fix, re-orthogonalize so floating point
        # rounding deltas don't leave any segment slightly diagonal.
        self._ensure_orthogonal()

        # Keep endpoints locked to component pins when connection metadata exists.
        if self._wire.segments and start_pin_pos is not None:
            self._wire.segments[0].x1 = start_pin_pos[0]
            self._wire.segments[0].y1 = start_pin_pos[1]
        if self._wire.segments and end_pin_pos is not None:
            self._wire.segments[-1].x2 = end_pin_pos[0]
            self._wire.segments[-1].y2 = end_pin_pos[1]

    def _connected_pin_position(self, endpoint: str) -> tuple[float, float] | None:
        """Resolve pin position for a connected wire endpoint."""
        connection = self._wire.start_connection if endpoint == "start" else self._wire.end_connection
        if connection is None:
            return None

        scene = self.scene()
        circuit = getattr(scene, "circuit", None) if scene is not None else None
        if circuit is None:
            return None
        component = circuit.components.get(connection.component_id)
        if component is None:
            return None
        pin_index = connection.pin_index
        if pin_index < 0 or pin_index >= len(component.pins):
            return None
        return component.get_pin_position(pin_index)

    def _cleanup_segments(self) -> None:
        """Remove zero-length segments and merge collinear segments."""
        if not self._wire.segments:
            return

        # First ensure all segments are orthogonal
        self._ensure_orthogonal()

        cleaned = []
        for seg in self._wire.segments:
            # Skip zero-length segments
            if abs(seg.x2 - seg.x1) < 0.1 and abs(seg.y2 - seg.y1) < 0.1:
                continue
            cleaned.append(seg)

        # Merge collinear consecutive segments
        if len(cleaned) > 1:
            merged = [cleaned[0]]
            for seg in cleaned[1:]:
                prev = merged[-1]
                # Check if both are horizontal and at same Y
                if (abs(prev.y1 - prev.y2) < 0.1 and abs(seg.y1 - seg.y2) < 0.1 and
                    abs(prev.y2 - seg.y1) < 0.1):
                    # Extend previous segment
                    prev.x2 = seg.x2
                    prev.y2 = seg.y2
                # Check if both are vertical and at same X
                elif (abs(prev.x1 - prev.x2) < 0.1 and abs(seg.x1 - seg.x2) < 0.1 and
                      abs(prev.x2 - seg.x1) < 0.1):
                    # Extend previous segment
                    prev.x2 = seg.x2
                    prev.y2 = seg.y2
                else:
                    merged.append(seg)
            cleaned = merged

        self._wire.segments = cleaned

    # ------------------------------------------------------------------
    # Smart endpoint rerouting (used when a connected component is moved)
    # ------------------------------------------------------------------

    def _route_two_points(
        self,
        start: QPointF,
        end: QPointF,
        prefer_h_first: bool,
        grid_size: float = 20.0,
    ) -> "list[WireSegment]":
        """Return 1 or 2 strictly orthogonal segments from *start* to *end*.

        Both endpoints are first snapped to the grid.  When an L-shape is
        needed the *prefer_h_first* flag chooses between
        horizontal-then-vertical (True) or vertical-then-horizontal (False).
        """
        sx = round(start.x() / grid_size) * grid_size
        sy = round(start.y() / grid_size) * grid_size
        ex = round(end.x() / grid_size) * grid_size
        ey = round(end.y() / grid_size) * grid_size

        dx = abs(ex - sx)
        dy = abs(ey - sy)

        if dx < 0.1 and dy < 0.1:
            # Coincident – return a zero-length stub (will be cleaned up)
            return [WireSegment(sx, sy, ex, ey)]

        if dx < 0.1:
            # Same column → single vertical segment
            return [WireSegment(sx, sy, ex, ey)]

        if dy < 0.1:
            # Same row → single horizontal segment
            return [WireSegment(sx, sy, ex, ey)]

        # Need an L-bend
        if prefer_h_first:
            return [
                WireSegment(sx, sy, ex, sy),  # horizontal leg
                WireSegment(ex, sy, ex, ey),  # vertical leg
            ]
        else:
            return [
                WireSegment(sx, sy, sx, ey),  # vertical leg
                WireSegment(sx, ey, ex, ey),  # horizontal leg
            ]

    def update_endpoint_position(self, endpoint: str, new_pos: QPointF) -> None:
        """
        Update a wire endpoint position when a connected component moves.

        The first two (or last two) segments are replaced with a freshly
        computed orthogonal route so the wire can never become diagonal,
        even after large component displacements.  Segments beyond the
        rerouted pair are preserved intact.

        Args:
            endpoint: ``'start'`` or ``'end'``
            new_pos:  New scene position for the endpoint (will be grid-snapped)
        """
        if not self._wire.segments:
            return

        scene = self.scene()
        grid_size = 20.0
        if scene is not None and hasattr(scene, 'grid_size'):
            grid_size = scene.grid_size

        # Snap the incoming position so routing math stays on-grid
        snapped = QPointF(
            round(new_pos.x() / grid_size) * grid_size,
            round(new_pos.y() / grid_size) * grid_size,
        )

        n = len(self._wire.segments)

        if endpoint == 'start':
            # How many segments at the beginning to replace with the new route
            replace_count = min(2, n)

            # The "anchor" is the first point that stays fixed:
            # - 3+ segments: start of segment[2]
            # - 1-2 segments: end of the last segment
            if n >= 3:
                anchor = QPointF(
                    self._wire.segments[2].x1,
                    self._wire.segments[2].y1,
                )
            else:
                anchor = QPointF(
                    self._wire.segments[-1].x2,
                    self._wire.segments[-1].y2,
                )

            # Preserve the original bend orientation of the first segment
            orig = self._wire.segments[0]
            prefer_h = abs(orig.x2 - orig.x1) >= abs(orig.y2 - orig.y1)

            new_segs = self._route_two_points(snapped, anchor, prefer_h, grid_size)
            self._wire.segments = new_segs + self._wire.segments[replace_count:]

        elif endpoint == 'end':
            replace_count = min(2, n)

            if n >= 3:
                anchor = QPointF(
                    self._wire.segments[-3].x2,
                    self._wire.segments[-3].y2,
                )
            else:
                anchor = QPointF(
                    self._wire.segments[0].x1,
                    self._wire.segments[0].y1,
                )

            orig = self._wire.segments[-1]
            prefer_h = abs(orig.x2 - orig.x1) >= abs(orig.y2 - orig.y1)

            new_segs = self._route_two_points(anchor, snapped, prefer_h, grid_size)
            self._wire.segments = self._wire.segments[:-replace_count] + new_segs

        # Remove any zero-length artifacts and re-render
        self._cleanup_segments()
        self._rebuild_path()

    def _ensure_orthogonal(self) -> None:
        """Ensure all segments are strictly horizontal or vertical.

        After forcing H/V orientation the snapped coordinate is also rounded to
        the nearest grid cell so floating-point drift cannot accumulate into
        visible diagonals.
        """
        scene = self.scene()
        grid_size = 20.0
        if scene is not None and hasattr(scene, 'grid_size'):
            grid_size = scene.grid_size

        for seg in self._wire.segments:
            if abs(seg.x2 - seg.x1) >= abs(seg.y2 - seg.y1):
                # Horizontal – snap the shared Y to the nearest grid row
                avg_y = (seg.y1 + seg.y2) / 2
                snapped_y = round(avg_y / grid_size) * grid_size
                seg.y1 = snapped_y
                seg.y2 = snapped_y
            else:
                # Vertical – snap the shared X to the nearest grid column
                avg_x = (seg.x1 + seg.x2) / 2
                snapped_x = round(avg_x / grid_size) * grid_size
                seg.x1 = snapped_x
                seg.x2 = snapped_x

        # Restore point-to-point continuity after orthogonalization
        for i in range(len(self._wire.segments) - 1):
            curr_seg = self._wire.segments[i]
            next_seg = self._wire.segments[i + 1]
            next_seg.x1 = curr_seg.x2
            next_seg.y1 = curr_seg.y2

    def move_endpoint(self, endpoint: str, new_pos: QPointF) -> None:
        """
        Move a wire endpoint to a new position and update intermediate segments.
        This is for manual dragging - maintains orthogonal routing.

        Args:
            endpoint: 'start' or 'end'
            new_pos: New position for the endpoint
        """
        if not self._wire.segments:
            return

        if endpoint == 'start':
            # Move start point of first segment
            first_seg = self._wire.segments[0]
            first_seg.x1 = new_pos.x()
            first_seg.y1 = new_pos.y()

            # If there are multiple segments, adjust the connection point
            if len(self._wire.segments) > 1:
                # Determine if first segment should be horizontal or vertical
                second_seg = self._wire.segments[1]
                # Keep the intermediate point's other coordinate
                if abs(second_seg.x2 - second_seg.x1) > abs(second_seg.y2 - second_seg.y1):
                    # Second segment is horizontal, so first should be vertical
                    first_seg.x2 = first_seg.x1
                else:
                    # Second segment is vertical, so first should be horizontal
                    first_seg.y2 = first_seg.y1

        elif endpoint == 'end':
            # Move end point of last segment
            last_seg = self._wire.segments[-1]
            last_seg.x2 = new_pos.x()
            last_seg.y2 = new_pos.y()

            # If there are multiple segments, adjust the connection point
            if len(self._wire.segments) > 1:
                second_last = self._wire.segments[-2]
                if abs(second_last.x2 - second_last.x1) > abs(second_last.y2 - second_last.y1):
                    # Second-last is horizontal, so last should be vertical
                    last_seg.x1 = last_seg.x2
                else:
                    # Second-last is vertical, so last should be horizontal
                    last_seg.y1 = last_seg.y2

        self._rebuild_path()

    def get_start_point(self) -> QPointF | None:
        """Get the start point of the wire."""
        if self._wire.segments:
            seg = self._wire.segments[0]
            return QPointF(seg.x1, seg.y1)
        return None

    def get_end_point(self) -> QPointF | None:
        """Get the end point of the wire."""
        if self._wire.segments:
            seg = self._wire.segments[-1]
            return QPointF(seg.x2, seg.y2)
        return None

    def _draw_alias_label(self, painter: QPainter, pen_color: QColor, alias: str) -> None:
        path = self.path()
        if path.isEmpty():
            return

        position = path.pointAtPercent(0.5)
        painter.save()

        font = painter.font()
        font.setPointSizeF(max(font.pointSizeF() - 1, 8))
        painter.setFont(font)

        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(alias) + 8
        height = metrics.height() + 4
        rect = QRectF(
            position.x() - width / 2,
            position.y() - height / 2,
            width,
            height,
        )

        bg_color = QColor(255, 255, 255, 230)
        text_color = pen_color
        if self._dark_mode:
            bg_color = QColor(20, 20, 20, 230)
            text_color = QColor(220, 255, 220)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rect, 4, 4)

        painter.setPen(QPen(text_color, 1))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, alias)
        painter.restore()


def calculate_orthogonal_path(
    start: QPointF,
    end: QPointF,
    start_direction: str = "auto",
) -> list[QPointF]:
    """
    Calculate an orthogonal (right-angle) path between two points.

    Args:
        start: Starting point
        end: Ending point
        start_direction: Initial direction ("horizontal", "vertical", or "auto")

    Returns:
        List of points forming the path
    """
    dx = end.x() - start.x()
    dy = end.y() - start.y()

    points = [start]

    # Determine initial direction
    if start_direction == "auto":
        go_horizontal_first = abs(dx) > abs(dy)
    else:
        go_horizontal_first = start_direction == "horizontal"

    if abs(dx) < 0.1 and abs(dy) < 0.1:
        # Points are the same
        pass
    elif abs(dx) < 0.1:
        # Vertical line only
        pass
    elif abs(dy) < 0.1:
        # Horizontal line only
        pass
    else:
        # Need a single corner (clean L-shape)
        if go_horizontal_first:
            # Horizontal then vertical: corner is at (end.x, start.y)
            points.append(QPointF(end.x(), start.y()))
        else:
            # Vertical then horizontal: corner is at (start.x, end.y)
            points.append(QPointF(start.x(), end.y()))

    points.append(end)
    return points


class WireInProgressItem(QGraphicsPathItem):
    """Item showing confirmed wire segments while still drawing."""

    CONFIRMED_COLOR = QColor(5, 150, 105)  # Darker emerald for confirmed segments
    CONFIRMED_WIDTH = 2.5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[tuple[float, float, float, float]] = []
        self._domain = CONNECTION_DOMAIN_CIRCUIT
        self._apply_pen()

    def _apply_pen(self) -> None:
        color = WireItem.DOMAIN_HOVER_COLORS.get(self._domain, self.CONFIRMED_COLOR)
        pen = QPen(color, self.CONFIRMED_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def set_domain(self, domain: str) -> None:
        """Set active domain for in-progress segment color."""
        if domain == self._domain:
            return
        self._domain = domain
        self._apply_pen()

    def add_segments(self, segments: list[tuple[float, float, float, float]]) -> None:
        """Add confirmed segments."""
        self._segments.extend(segments)
        self._rebuild_path()

    def _rebuild_path(self) -> None:
        """Rebuild path from segments."""
        path = QPainterPath()
        if self._segments:
            first = self._segments[0]
            path.moveTo(first[0], first[1])
            path.lineTo(first[2], first[3])
            for seg in self._segments[1:]:
                path.lineTo(seg[2], seg[3])
        self.setPath(path)

    def get_all_segments(self) -> list[tuple[float, float, float, float]]:
        """Get all confirmed segments."""
        return self._segments.copy()


class WireRoutingSuggestion(QGraphicsPathItem):
    """Shows alternative routing suggestions as ghost paths."""

    SUGGESTION_COLOR = QColor(150, 150, 150, 100)  # Semi-transparent gray
    SUGGESTION_WIDTH = 1.5

    def __init__(self, points: list[QPointF], parent=None):
        super().__init__(parent)
        self._points = points

        pen = QPen(self.SUGGESTION_COLOR, self.SUGGESTION_WIDTH, Qt.PenStyle.DotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setZValue(-10)  # Behind main preview
        self._build_path()

    def _build_path(self) -> None:
        """Build path from points."""
        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for point in self._points[1:]:
                path.lineTo(point)
        self.setPath(path)


def calculate_all_route_options(
    start: QPointF,
    end: QPointF,
) -> list[list[QPointF]]:
    """
    Calculate all reasonable orthogonal routing options between two points.

    Returns:
        List of point lists, each representing a different route option
    """
    dx = end.x() - start.x()
    dy = end.y() - start.y()

    routes = []

    # Option 1: Horizontal first (L-shape)
    if abs(dx) > 0.1 and abs(dy) > 0.1:
        route1 = [start, QPointF(end.x(), start.y()), end]
        routes.append(route1)

        # Option 2: Vertical first (L-shape)
        route2 = [start, QPointF(start.x(), end.y()), end]
        routes.append(route2)

        # Option 3: Z-shape horizontal-vertical-horizontal
        mid_x = start.x() + dx / 2
        route3 = [
            start,
            QPointF(mid_x, start.y()),
            QPointF(mid_x, end.y()),
            end
        ]
        routes.append(route3)

        # Option 4: Z-shape vertical-horizontal-vertical
        mid_y = start.y() + dy / 2
        route4 = [
            start,
            QPointF(start.x(), mid_y),
            QPointF(end.x(), mid_y),
            end
        ]
        routes.append(route4)
    else:
        # Simple straight line
        routes.append([start, end])

    return routes


class WirePreviewItem(QGraphicsPathItem):
    """Preview item shown while drawing a wire."""

    PREVIEW_COLOR = QColor(16, 185, 129)  # Match wire emerald green
    PREVIEW_WIDTH = 2.5

    def __init__(self, start: QPointF, parent=None):
        super().__init__(parent)

        self._start = start
        self._end = start
        self._horizontal_first = True
        self._route_index = 0
        self._available_routes: list[list[QPointF]] = []
        self._suggestion_items: list[WireRoutingSuggestion] = []
        self._domain = CONNECTION_DOMAIN_CIRCUIT
        self._apply_pen()
        self._update_path()

    def _apply_pen(self) -> None:
        color = WireItem.DOMAIN_LINE_COLORS.get(self._domain, self.PREVIEW_COLOR)
        pen = QPen(color, self.PREVIEW_WIDTH, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setDashPattern([4, 3])  # Shorter dashes for cleaner look
        self.setPen(pen)

    def set_domain(self, domain: str) -> None:
        """Set active domain for preview segment color."""
        if domain == self._domain:
            return
        self._domain = domain
        self._apply_pen()

    def set_end(self, end: QPointF) -> None:
        """Update the end point."""
        self._end = end
        self._available_routes = calculate_all_route_options(self._start, self._end)
        # Keep route index valid
        if self._route_index >= len(self._available_routes):
            self._route_index = 0
        self._update_path()

    def toggle_direction(self) -> None:
        """Cycle through available routing options."""
        if self._available_routes:
            self._route_index = (self._route_index + 1) % len(self._available_routes)
        else:
            self._horizontal_first = not self._horizontal_first
        self._update_path()

    def _update_path(self) -> None:
        """Rebuild the preview path using selected route."""
        # Get current route points
        if self._available_routes and self._route_index < len(self._available_routes):
            points = self._available_routes[self._route_index]
        else:
            direction = "horizontal" if self._horizontal_first else "vertical"
            points = calculate_orthogonal_path(self._start, self._end, direction)

        # Build main path
        path = QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)

        self.setPath(path)

    def get_suggestion_items(self) -> list["WireRoutingSuggestion"]:
        """Get suggestion items for alternative routes (for adding to scene)."""
        suggestions = []
        for i, route in enumerate(self._available_routes):
            if i != self._route_index:  # Skip current selection
                suggestions.append(WireRoutingSuggestion(route))
        return suggestions

    def get_segments(self) -> list[tuple[float, float, float, float]]:
        """Get the wire segments as (x1, y1, x2, y2) tuples."""
        # Get current route points
        if self._available_routes and self._route_index < len(self._available_routes):
            points = self._available_routes[self._route_index]
        else:
            direction = "horizontal" if self._horizontal_first else "vertical"
            points = calculate_orthogonal_path(self._start, self._end, direction)

        segments = []
        for i in range(len(points) - 1):
            segments.append((
                points[i].x(),
                points[i].y(),
                points[i + 1].x(),
                points[i + 1].y(),
            ))
        return segments

    def get_route_info(self) -> str:
        """Get description of current route for status display."""
        if not self._available_routes:
            return "Direct"
        total = len(self._available_routes)
        current = self._route_index + 1
        return f"Route {current}/{total} (Space to cycle)"
