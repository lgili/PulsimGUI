"""Wire graphics item with orthogonal routing."""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush
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
    - Selection highlighting
    """

    LINE_WIDTH = 2.0
    LINE_COLOR = QColor(0, 100, 0)  # Dark green
    LINE_COLOR_DARK = QColor(100, 200, 100)  # Light green for dark mode
    SELECTED_COLOR = QColor(0, 120, 215)
    JUNCTION_RADIUS = 4.0

    def __init__(self, wire: Wire, parent=None):
        super().__init__(parent)

        self._wire = wire
        self._dark_mode = False

        # Enable selection
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)

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

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the wire."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Choose color based on selection and theme
        if self.isSelected():
            color = self.SELECTED_COLOR
        elif self._dark_mode:
            color = self.LINE_COLOR_DARK
        else:
            color = self.LINE_COLOR

        # Draw the wire path
        painter.setPen(QPen(color, self.LINE_WIDTH))
        painter.drawPath(self.path())

        # Draw junction dots
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        for junction in self._wire.junctions:
            painter.drawEllipse(
                QPointF(junction[0], junction[1]),
                self.JUNCTION_RADIUS,
                self.JUNCTION_RADIUS,
            )

    def add_junction(self, x: float, y: float) -> None:
        """Add a junction point to the wire."""
        self._wire.junctions.append((x, y))
        self.update()


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


class WirePreviewItem(QGraphicsPathItem):
    """Preview item shown while drawing a wire."""

    PREVIEW_COLOR = QColor(100, 100, 255)
    PREVIEW_WIDTH = 1.5

    def __init__(self, start: QPointF, parent=None):
        super().__init__(parent)

        self._start = start
        self._end = start
        self._horizontal_first = True

        self.setPen(QPen(self.PREVIEW_COLOR, self.PREVIEW_WIDTH, Qt.PenStyle.DashLine))
        self._update_path()

    def set_end(self, end: QPointF) -> None:
        """Update the end point."""
        self._end = end
        self._update_path()

    def toggle_direction(self) -> None:
        """Toggle between horizontal-first and vertical-first routing."""
        self._horizontal_first = not self._horizontal_first
        self._update_path()

    def _update_path(self) -> None:
        """Rebuild the preview path."""
        direction = "horizontal" if self._horizontal_first else "vertical"
        points = calculate_orthogonal_path(self._start, self._end, direction)

        path = QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)

        self.setPath(path)

    def get_segments(self) -> list[tuple[float, float, float, float]]:
        """Get the wire segments as (x1, y1, x2, y2) tuples."""
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
