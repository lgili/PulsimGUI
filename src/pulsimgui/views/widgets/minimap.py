"""Minimap widget for navigating large schematics."""

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (
    QWidget,
    QGraphicsView,
    QGraphicsScene,
    QFrame,
    QVBoxLayout,
)


class MinimapWidget(QFrame):
    """Minimap showing overview of schematic with viewport indicator."""

    # Signal emitted when user clicks on minimap to navigate
    navigation_requested = Signal(float, float)  # Scene x, y coordinates

    # Minimap settings
    SIZE = 150  # Widget size in pixels
    PADDING = 4
    VIEWPORT_COLOR = QColor(0, 120, 215, 80)
    VIEWPORT_BORDER = QColor(0, 120, 215, 200)
    COMPONENT_COLOR = QColor(100, 100, 100)
    WIRE_COLOR = QColor(0, 120, 80, 150)
    BACKGROUND = QColor(250, 250, 250)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_view: QGraphicsView | None = None
        self._scene_rect = QRectF()
        self._viewport_rect = QRectF()
        self._scale = 1.0
        self._offset = QPointF()
        self._dragging = False

        self.setFixedSize(self.SIZE, self.SIZE)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._apply_styles()

    def _apply_styles(self) -> None:
        """Apply modern styling."""
        self.setStyleSheet("""
            MinimapWidget {
                background-color: #fafafa;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
        """)

    def set_source_view(self, view: QGraphicsView) -> None:
        """Set the source graphics view to mirror."""
        self._source_view = view
        self.update_minimap()

    def update_minimap(self) -> None:
        """Update the minimap display."""
        if not self._source_view or not self._source_view.scene():
            return

        scene = self._source_view.scene()

        # Get scene bounding rect with some padding
        self._scene_rect = scene.itemsBoundingRect()
        if self._scene_rect.isEmpty():
            self._scene_rect = QRectF(-500, -500, 1000, 1000)
        else:
            # Add padding
            pad = 50
            self._scene_rect.adjust(-pad, -pad, pad, pad)

        # Calculate scale to fit scene in minimap
        available = self.SIZE - 2 * self.PADDING
        scale_x = available / max(self._scene_rect.width(), 1)
        scale_y = available / max(self._scene_rect.height(), 1)
        self._scale = min(scale_x, scale_y)

        # Center offset
        scaled_width = self._scene_rect.width() * self._scale
        scaled_height = self._scene_rect.height() * self._scale
        self._offset = QPointF(
            (self.SIZE - scaled_width) / 2,
            (self.SIZE - scaled_height) / 2,
        )

        # Get viewport rect in scene coordinates
        viewport_rect = self._source_view.mapToScene(
            self._source_view.viewport().rect()
        ).boundingRect()
        self._viewport_rect = viewport_rect

        self.update()

    def paintEvent(self, event) -> None:
        """Paint the minimap."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), self.BACKGROUND)

        if not self._source_view or not self._source_view.scene():
            # Draw placeholder
            painter.setPen(QPen(QColor(200, 200, 200)))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No schematic"
            )
            return

        scene = self._source_view.scene()

        # Draw simplified scene items
        painter.save()
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)
        painter.translate(-self._scene_rect.topLeft())

        # Draw wires as simple lines
        painter.setPen(QPen(self.WIRE_COLOR, 1 / self._scale))
        for item in scene.items():
            if hasattr(item, 'path') and callable(item.path):
                path = item.path()
                if not path.isEmpty():
                    painter.drawPath(path)

        # Draw components as rectangles
        painter.setPen(QPen(self.COMPONENT_COLOR, 1 / self._scale))
        painter.setBrush(QBrush(QColor(200, 200, 200, 100)))
        for item in scene.items():
            if hasattr(item, 'component'):  # ComponentItem
                rect = item.boundingRect()
                scene_rect = item.mapRectToScene(rect)
                painter.drawRect(scene_rect)

        painter.restore()

        # Draw viewport indicator
        viewport_mapped = self._map_scene_to_minimap(self._viewport_rect)
        painter.setPen(QPen(self.VIEWPORT_BORDER, 2))
        painter.setBrush(QBrush(self.VIEWPORT_COLOR))
        painter.drawRect(viewport_mapped)

    def _map_scene_to_minimap(self, rect: QRectF) -> QRectF:
        """Map a scene rectangle to minimap coordinates."""
        x = self._offset.x() + (rect.x() - self._scene_rect.x()) * self._scale
        y = self._offset.y() + (rect.y() - self._scene_rect.y()) * self._scale
        w = rect.width() * self._scale
        h = rect.height() * self._scale
        return QRectF(x, y, w, h)

    def _map_minimap_to_scene(self, pos: QPointF) -> QPointF:
        """Map minimap coordinates to scene coordinates."""
        x = (pos.x() - self._offset.x()) / self._scale + self._scene_rect.x()
        y = (pos.y() - self._offset.y()) / self._scale + self._scene_rect.y()
        return QPointF(x, y)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press - start dragging or navigate."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._navigate_to(event.position())

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move - drag to navigate."""
        if self._dragging:
            self._navigate_to(event.position())

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release - stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def _navigate_to(self, pos: QPointF) -> None:
        """Navigate the source view to the clicked position."""
        scene_pos = self._map_minimap_to_scene(pos)
        self.navigation_requested.emit(scene_pos.x(), scene_pos.y())


class MinimapOverlay(QWidget):
    """Floating minimap overlay for corner of view."""

    navigation_requested = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._minimap = MinimapWidget()
        self._minimap.navigation_requested.connect(self.navigation_requested)
        layout.addWidget(self._minimap)

    def set_source_view(self, view: QGraphicsView) -> None:
        """Set the source graphics view."""
        self._minimap.set_source_view(view)

    def update_minimap(self) -> None:
        """Update the minimap display."""
        self._minimap.update_minimap()
