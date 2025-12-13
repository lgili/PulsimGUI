"""Wire graphics item with orthogonal routing."""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush, QFontMetricsF
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from pulsimgui.models.wire import Wire


class WireItem(QGraphicsPathItem):
    """
    Graphics item for electrical wires.

    Features:
    - Orthogonal (right-angle) routing
    - Junction dots where wires connect
    - Selection highlighting with glow
    - Hover effects
    """

    LINE_WIDTH = 2.5  # Slightly thicker for better visibility
    LINE_WIDTH_HOVER = 3.5
    LINE_WIDTH_SELECTED = 3.0
    LINE_COLOR = QColor(16, 185, 129)  # Emerald green - modern and visible
    LINE_COLOR_DARK = QColor(52, 211, 153)  # Light emerald for dark mode
    HOVER_COLOR = QColor(5, 150, 105)  # Darker on hover
    HOVER_COLOR_DARK = QColor(110, 231, 183)
    SELECTED_COLOR = QColor(59, 130, 246)  # Blue to match component selection
    SELECTED_GLOW = QColor(59, 130, 246, 60)  # Semi-transparent for glow
    JUNCTION_RADIUS = 6.0
    JUNCTION_RADIUS_HOVER = 7.0

    def __init__(self, wire: Wire, parent=None):
        super().__init__(parent)

        self._wire = wire
        self._dark_mode = False
        self._hovered = False

        # Segment dragging state
        self._dragging_segment: int | None = None  # Index of segment being dragged
        self._drag_start_pos: QPointF | None = None
        self._drag_orientation: str | None = None  # 'horizontal' or 'vertical'

        # Enable selection and hover events (NOT ItemIsMovable - we handle movement ourselves)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # Set default pen for proper bounding rect calculation
        self.setPen(QPen(self.LINE_COLOR, self.LINE_WIDTH))

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
        self.update()
        super().hoverLeaveEvent(event)

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

        # Choose color and width based on state
        if is_selected:
            color = self.SELECTED_COLOR
            line_width = self.LINE_WIDTH_SELECTED
        elif is_hovered:
            color = self.HOVER_COLOR_DARK if self._dark_mode else self.HOVER_COLOR
            line_width = self.LINE_WIDTH_HOVER
        elif self._dark_mode:
            color = self.LINE_COLOR_DARK
            line_width = self.LINE_WIDTH
        else:
            color = self.LINE_COLOR
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
                self._dragging_segment = seg_idx
                self._drag_start_pos = pos
                seg = self._wire.segments[seg_idx]
                # Determine if segment is horizontal or vertical
                if abs(seg.x2 - seg.x1) > abs(seg.y2 - seg.y1):
                    self._drag_orientation = 'horizontal'
                else:
                    self._drag_orientation = 'vertical'
                self.setCursor(Qt.CursorShape.SizeAllCursor)
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
                self._rebuild_path()
        super().mouseReleaseEvent(event)

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

    def _move_segment_fluid(self, seg_idx: int, delta: QPointF) -> None:
        """
        Move a segment fluidly (no grid snapping) and stretch adjacent segments.

        The segment moves in the direction the user drags:
        - Horizontal segments move vertically (up/down)
        - Vertical segments move horizontally (left/right)
        Adjacent segments stretch to stay connected.
        """
        if seg_idx < 0 or seg_idx >= len(self._wire.segments):
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

    def update_endpoint_position(self, endpoint: str, new_pos: QPointF) -> None:
        """
        Update a wire endpoint position when connected component moves.
        Maintains orthogonal routing by adjusting adjacent segments.

        Args:
            endpoint: 'start' or 'end'
            new_pos: New position for the endpoint
        """
        if not self._wire.segments:
            return

        if endpoint == 'start':
            first_seg = self._wire.segments[0]
            old_x, old_y = first_seg.x1, first_seg.y1
            new_x, new_y = new_pos.x(), new_pos.y()

            # Update start point
            first_seg.x1 = new_x
            first_seg.y1 = new_y

            # Determine if first segment is horizontal or vertical
            is_horizontal = abs(first_seg.x2 - old_x) > abs(first_seg.y2 - old_y)

            if is_horizontal:
                # First segment is horizontal - update its Y to match new start
                first_seg.y2 = new_y
                # If there's a next segment, update its start Y
                if len(self._wire.segments) > 1:
                    self._wire.segments[1].y1 = new_y
            else:
                # First segment is vertical - update its X to match new start
                first_seg.x2 = new_x
                # If there's a next segment, update its start X
                if len(self._wire.segments) > 1:
                    self._wire.segments[1].x1 = new_x

        elif endpoint == 'end':
            last_seg = self._wire.segments[-1]
            old_x, old_y = last_seg.x2, last_seg.y2
            new_x, new_y = new_pos.x(), new_pos.y()

            # Update end point
            last_seg.x2 = new_x
            last_seg.y2 = new_y

            # Determine if last segment is horizontal or vertical
            is_horizontal = abs(old_x - last_seg.x1) > abs(old_y - last_seg.y1)

            if is_horizontal:
                # Last segment is horizontal - update its Y to match new end
                last_seg.y1 = new_y
                # If there's a previous segment, update its end Y
                if len(self._wire.segments) > 1:
                    self._wire.segments[-2].y2 = new_y
            else:
                # Last segment is vertical - update its X to match new end
                last_seg.x1 = new_x
                # If there's a previous segment, update its end X
                if len(self._wire.segments) > 1:
                    self._wire.segments[-2].x2 = new_x

        self._ensure_orthogonal()
        self._rebuild_path()

    def _ensure_orthogonal(self) -> None:
        """Ensure all segments are strictly horizontal or vertical."""
        for seg in self._wire.segments:
            # If segment is more horizontal, make it perfectly horizontal
            if abs(seg.x2 - seg.x1) >= abs(seg.y2 - seg.y1):
                # Horizontal - average Y coordinates
                avg_y = (seg.y1 + seg.y2) / 2
                seg.y1 = avg_y
                seg.y2 = avg_y
            else:
                # Vertical - average X coordinates
                avg_x = (seg.x1 + seg.x2) / 2
                seg.x1 = avg_x
                seg.x2 = avg_x

        # Fix connectivity between segments
        for i in range(len(self._wire.segments) - 1):
            curr_seg = self._wire.segments[i]
            next_seg = self._wire.segments[i + 1]
            # End of current should match start of next
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
        # Need corners
        if go_horizontal_first:
            # L-shape: horizontal then vertical
            mid_x = start.x() + dx / 2
            points.append(QPointF(mid_x, start.y()))
            points.append(QPointF(mid_x, end.y()))
        else:
            # L-shape: vertical then horizontal
            mid_y = start.y() + dy / 2
            points.append(QPointF(start.x(), mid_y))
            points.append(QPointF(end.x(), mid_y))

    points.append(end)
    return points


class WireInProgressItem(QGraphicsPathItem):
    """Item showing confirmed wire segments while still drawing."""

    CONFIRMED_COLOR = QColor(5, 150, 105)  # Darker emerald for confirmed segments
    CONFIRMED_WIDTH = 2.5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[tuple[float, float, float, float]] = []
        pen = QPen(self.CONFIRMED_COLOR, self.CONFIRMED_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

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

        pen = QPen(self.PREVIEW_COLOR, self.PREVIEW_WIDTH, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setDashPattern([4, 3])  # Shorter dashes for cleaner look
        self.setPen(pen)
        self._update_path()

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
