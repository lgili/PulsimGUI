"""Schematic view with pan and zoom."""

from enum import Enum, auto

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QGraphicsView

from pulsimgui.views.schematic.scene import SchematicScene


class Tool(Enum):
    """Available editing tools."""

    SELECT = auto()
    WIRE = auto()
    COMPONENT = auto()


class SchematicView(QGraphicsView):
    """
    View for displaying and interacting with schematic scenes.

    Features:
    - Mouse wheel zoom centered on cursor
    - Middle-button pan
    - Keyboard shortcuts for zoom
    - Tool switching

    Signals:
        zoom_changed: Emitted when zoom level changes (percentage)
        mouse_moved: Emitted when mouse moves (scene coordinates)
        tool_changed: Emitted when active tool changes
    """

    zoom_changed = Signal(float)
    mouse_moved = Signal(float, float)
    tool_changed = Signal(Tool)

    # Zoom settings
    ZOOM_MIN = 0.1
    ZOOM_MAX = 10.0
    ZOOM_STEP = 1.15

    def __init__(self, scene: SchematicScene | None = None, parent=None):
        super().__init__(parent)

        self._zoom_level = 1.0
        self._panning = False
        self._pan_start = QPointF()
        self._current_tool = Tool.SELECT
        self._snap_to_grid = True

        # Set up view
        self.setScene(scene or SchematicScene())
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)

        # Set background
        self.setBackgroundBrush(Qt.GlobalColor.white)

    @property
    def schematic_scene(self) -> SchematicScene:
        """Get the schematic scene."""
        return self.scene()

    @property
    def zoom_level(self) -> float:
        """Get current zoom level (1.0 = 100%)."""
        return self._zoom_level

    @property
    def zoom_percent(self) -> float:
        """Get zoom level as percentage."""
        return self._zoom_level * 100

    @property
    def current_tool(self) -> Tool:
        """Get the current editing tool."""
        return self._current_tool

    @current_tool.setter
    def current_tool(self, tool: Tool) -> None:
        """Set the current editing tool."""
        if self._current_tool != tool:
            self._current_tool = tool
            self._update_cursor()
            self.tool_changed.emit(tool)

    @property
    def snap_to_grid(self) -> bool:
        """Get snap-to-grid setting."""
        return self._snap_to_grid

    @snap_to_grid.setter
    def snap_to_grid(self, enabled: bool) -> None:
        """Set snap-to-grid setting."""
        self._snap_to_grid = enabled

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode appearance."""
        if dark:
            self.setBackgroundBrush(QColor(30, 30, 30))
        else:
            self.setBackgroundBrush(Qt.GlobalColor.white)

        if isinstance(self.scene(), SchematicScene):
            self.scene().set_dark_mode(dark)

    def zoom_in(self) -> None:
        """Zoom in by one step."""
        self._set_zoom(self._zoom_level * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        """Zoom out by one step."""
        self._set_zoom(self._zoom_level / self.ZOOM_STEP)

    def zoom_to_fit(self) -> None:
        """Zoom to fit all items in view."""
        scene = self.scene()
        if scene is None:
            return

        items_rect = scene.itemsBoundingRect()
        if items_rect.isEmpty():
            # No items, reset to default view
            self._set_zoom(1.0)
            self.centerOn(0, 0)
            return

        # Add margin
        margin = 50
        items_rect.adjust(-margin, -margin, margin, margin)

        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = self.transform().m11()
        self.zoom_changed.emit(self.zoom_percent)

    def zoom_to_selection(self) -> None:
        """Zoom to fit selected items."""
        scene = self.scene()
        if scene is None:
            return

        selected = scene.selectedItems()
        if not selected:
            return

        # Calculate bounding rect of selection
        rect = selected[0].sceneBoundingRect()
        for item in selected[1:]:
            rect = rect.united(item.sceneBoundingRect())

        # Add margin
        margin = 50
        rect.adjust(-margin, -margin, margin, margin)

        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = self.transform().m11()
        self.zoom_changed.emit(self.zoom_percent)

    def reset_zoom(self) -> None:
        """Reset zoom to 100%."""
        self._set_zoom(1.0)

    def _set_zoom(self, level: float) -> None:
        """Set zoom level with bounds checking."""
        level = max(self.ZOOM_MIN, min(self.ZOOM_MAX, level))

        if abs(level - self._zoom_level) < 0.001:
            return

        # Calculate scale factor
        factor = level / self._zoom_level
        self.scale(factor, factor)
        self._zoom_level = level
        self.zoom_changed.emit(self.zoom_percent)

    def _update_cursor(self) -> None:
        """Update cursor based on current tool."""
        if self._current_tool == Tool.SELECT:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif self._current_tool == Tool.WIRE:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._current_tool == Tool.COMPONENT:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for zooming."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+wheel = zoom
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            # Normal wheel = scroll
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for panning."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for panning and coordinate updates."""
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)

        # Emit mouse position in scene coordinates
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(scene_pos.x(), scene_pos.y())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to stop panning."""
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self._update_cursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()
        modifiers = event.modifiers()

        # Zoom shortcuts
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
                self.zoom_in()
                return
            elif key == Qt.Key.Key_Minus:
                self.zoom_out()
                return
            elif key == Qt.Key.Key_0:
                self.zoom_to_fit()
                return

        # Tool shortcuts (without modifiers)
        if not modifiers:
            if key == Qt.Key.Key_Escape:
                self.current_tool = Tool.SELECT
                self.scene().clearSelection()
                return
            elif key == Qt.Key.Key_W:
                self.current_tool = Tool.WIRE
                return

        super().keyPressEvent(event)


# Import QColor for dark mode
from PySide6.QtGui import QColor
