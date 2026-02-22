"""Schematic view with pan and zoom."""

from enum import Enum, auto
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, QPointF, QEvent, QRectF
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QDragEnterEvent, QDragMoveEvent, QDropEvent, QContextMenuEvent, QPen, QColor, QBrush, QPalette
from PySide6.QtWidgets import QGraphicsView, QLineEdit, QMenu, QGraphicsItem, QApplication
from shiboken6 import isValid

from pulsimgui.models.component import (
    Component,
    ComponentType,
    can_connect_measurement_pins,
)
from pulsimgui.resources.icons import IconService
from pulsimgui.services.theme_service import Theme
from pulsimgui.views.schematic.scene import SchematicScene
from pulsimgui.views.schematic.items.wire_item import WirePreviewItem, WireInProgressItem, WireItem


class PinHighlightItem(QGraphicsItem):
    """Visual indicator showing a highlighted pin when mouse is nearby."""

    PIN_GLOW_COLOR = QColor(0, 180, 80)  # Green glow for connectable pins
    PIN_GLOW_RADIUS = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(999)  # Above components but below preview
        self._visible = False

    def boundingRect(self) -> QRectF:
        r = self.PIN_GLOW_RADIUS + 2
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._visible:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw outer glow (multiple rings for soft effect)
        for i in range(3):
            radius = self.PIN_GLOW_RADIUS - i * 3
            alpha = 60 - i * 15
            color = QColor(self.PIN_GLOW_COLOR)
            color.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(0, 0), radius, radius)

        # Draw center dot
        painter.setBrush(QBrush(self.PIN_GLOW_COLOR))
        painter.drawEllipse(QPointF(0, 0), 4, 4)

    def set_visible(self, visible: bool) -> None:
        """Set visibility and trigger update."""
        if self._visible != visible:
            self._visible = visible
            self.update()

    def is_highlight_visible(self) -> bool:
        return self._visible


class AlignmentGuidesItem(QGraphicsItem):
    """Visual guides showing alignment with other components."""

    GUIDE_COLOR = QColor(255, 100, 100, 180)  # Red-ish for visibility
    GUIDE_WIDTH = 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(998)  # Below pin highlight but above components
        self._h_lines: list[float] = []  # Y coordinates for horizontal lines
        self._v_lines: list[float] = []  # X coordinates for vertical lines
        self._scene_rect = QRectF(-5000, -5000, 10000, 10000)

    def boundingRect(self) -> QRectF:
        return self._scene_rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._h_lines and not self._v_lines:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(self.GUIDE_COLOR, self.GUIDE_WIDTH, Qt.PenStyle.DashLine)
        painter.setPen(pen)

        # Draw horizontal guides
        for y in self._h_lines:
            painter.drawLine(QPointF(self._scene_rect.left(), y),
                           QPointF(self._scene_rect.right(), y))

        # Draw vertical guides
        for x in self._v_lines:
            painter.drawLine(QPointF(x, self._scene_rect.top()),
                           QPointF(x, self._scene_rect.bottom()))

    def set_guides(self, h_lines: list[float], v_lines: list[float]) -> None:
        """Set the alignment guide positions."""
        if self._h_lines != h_lines or self._v_lines != v_lines:
            self._h_lines = h_lines
            self._v_lines = v_lines
            self.update()

    def clear_guides(self) -> None:
        """Clear all guides."""
        if self._h_lines or self._v_lines:
            self._h_lines = []
            self._v_lines = []
            self.update()


class ComponentDropPreviewItem(QGraphicsItem):
    """Semi-transparent preview showing component symbol during drag."""

    PREVIEW_COLOR = QColor(0, 120, 215, 80)  # Accent for placement hints
    PREVIEW_BORDER = QColor(0, 120, 215, 180)
    PREVIEW_LINE_WIDTH = 1.5
    DARK_MODE = False

    def __init__(self, comp_type: ComponentType, parent=None):
        super().__init__(parent)
        self._comp_type = comp_type
        from pulsimgui.views.schematic.items import create_component_item

        self._preview_item = create_component_item(Component(type=comp_type, name=""))
        self._preview_item.set_show_labels(False)
        self._preview_item.set_show_value_labels(False)
        self._preview_item.set_dark_mode(self.DARK_MODE)
        self._bounds = self._preview_item.boundingRect()
        self.setZValue(1000)  # Always on top

    def set_dark_mode(self, dark: bool) -> None:
        self._preview_item.set_dark_mode(dark)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds.adjusted(-6, -6, 6, 6)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a light glow around the component bounds for placement feedback.
        glow_color = QColor(self.PREVIEW_BORDER)
        glow_color.setAlpha(26)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_color))
        painter.drawRoundedRect(self._bounds.adjusted(-4, -4, 4, 4), 6, 6)

        # Draw the exact same symbol language as schematic/library, semi-transparent.
        painter.save()
        painter.setOpacity(0.72)
        self._preview_item.paint(painter, option, widget)
        painter.restore()

        # Draw an alignment frame so preview remains readable over dense wires.
        painter.setPen(QPen(self.PREVIEW_BORDER, self.PREVIEW_LINE_WIDTH, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self._bounds.adjusted(-2, -2, 2, 2), 4, 4)

        center_color = QColor(self.PREVIEW_COLOR)
        center_color.setAlpha(140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(center_color)
        painter.drawEllipse(QPointF(0, 0), 2.5, 2.5)

        # Draw crosshairs at center to show exact placement point
        painter.setPen(QPen(self.PREVIEW_BORDER, 1))
        cross_size = 8
        painter.drawLine(QPointF(-cross_size, 0), QPointF(cross_size, 0))
        painter.drawLine(QPointF(0, -cross_size), QPointF(0, cross_size))


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
    component_dropped = Signal(str, float, float)  # component_type_name, x, y
    wire_created = Signal(list)  # list of (x1, y1, x2, y2) segments
    wire_alias_changed = Signal(object)  # Wire model reference
    grid_toggle_requested = Signal()  # emitted when G key is pressed
    subcircuit_open_requested = Signal(object)  # Component instance
    scope_open_requested = Signal(object)  # Component instance
    component_properties_requested = Signal(object)  # Component instance
    quick_add_component = Signal(object)  # ComponentType for keyboard shortcuts
    scroll_changed = Signal()  # emitted when view scrolls
    component_delete_requested = Signal(str)  # component UUID string
    wire_delete_requested = Signal(str)  # wire UUID string
    component_rotate_requested = Signal(str, int)  # component UUID string, degrees
    component_flip_requested = Signal(str, bool)  # component UUID string, horizontal

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

        # Wire drawing state
        self._wire_preview: WirePreviewItem | None = None
        self._wire_in_progress: WireInProgressItem | None = None  # Shows confirmed segments
        self._wire_start: QPointF | None = None
        self._wire_start_pin: tuple[Component, int] | None = None
        self._alias_editor: QLineEdit | None = None
        self._alias_wire_item: WireItem | None = None

        # Component drop preview state
        self._drop_preview: ComponentDropPreviewItem | None = None
        self._drop_comp_type: ComponentType | None = None

        # Pin highlight for wire drawing feedback
        self._pin_highlight: PinHighlightItem | None = None

        # Alignment guides for component dragging
        self._alignment_guides: AlignmentGuidesItem | None = None

        # Clipboard for copy/paste operations
        self._clipboard_component_data: dict | None = None

        # Set up view
        self.setScene(scene or SchematicScene())
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Use FullViewportUpdate to avoid rendering artifacts when moving items
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)
        # Enable caching for better scrolling performance
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)

        # Don't set background brush here - let scene's drawBackground handle it
        # The scene will draw the background with grid dots

        # Enable drag-and-drop
        self.setAcceptDrops(True)

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
        # Don't set background brush - let scene's drawBackground handle it
        if isinstance(self.scene(), SchematicScene):
            self.scene().set_dark_mode(dark)
        ComponentDropPreviewItem.DARK_MODE = dark
        if self._drop_preview is not None:
            self._drop_preview.set_dark_mode(dark)
        # Background is cached; force invalidation so theme changes repaint immediately.
        self.resetCachedContent()
        self.viewport().update()

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors for canvas overlays and dark-mode rendering."""
        self.set_dark_mode(theme.is_dark)
        PinHighlightItem.PIN_GLOW_COLOR = QColor(theme.colors.overlay_pin_highlight)
        AlignmentGuidesItem.GUIDE_COLOR = QColor(theme.colors.overlay_alignment_guides)
        ComponentDropPreviewItem.PREVIEW_COLOR = QColor(theme.colors.overlay_drop_preview_fill)
        ComponentDropPreviewItem.PREVIEW_BORDER = QColor(theme.colors.overlay_drop_preview_border)
        if self._drop_preview is not None:
            self._drop_preview.update()

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
        self._position_alias_editor()

    @staticmethod
    def _is_alive_graphics_item(item: QGraphicsItem | None) -> bool:
        """Check whether a Qt graphics item still has a live C++ object."""
        return item is not None and isValid(item)

    def _get_wire_preview(self) -> WirePreviewItem | None:
        """Return wire preview only when the underlying C++ item is still valid."""
        if not self._is_alive_graphics_item(self._wire_preview):
            self._wire_preview = None
            return None
        return self._wire_preview

    def _get_wire_in_progress(self) -> WireInProgressItem | None:
        """Return in-progress wire overlay only when item is still valid."""
        if not self._is_alive_graphics_item(self._wire_in_progress):
            self._wire_in_progress = None
            return None
        return self._wire_in_progress

    def _get_pin_highlight(self) -> PinHighlightItem | None:
        """Return pin highlight only when item is still valid."""
        if not self._is_alive_graphics_item(self._pin_highlight):
            self._pin_highlight = None
            return None
        return self._pin_highlight

    def _remove_wire_preview(self) -> None:
        """Safely remove wire preview item from scene."""
        preview = self._get_wire_preview()
        if preview is not None:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(preview)
        self._wire_preview = None

    def _remove_wire_in_progress(self) -> None:
        """Safely remove in-progress wire overlay from scene."""
        in_progress = self._get_wire_in_progress()
        if in_progress is not None:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(in_progress)
        self._wire_in_progress = None

    def _wire_endpoint_pin_filter(self) -> Callable[[object, int], bool] | None:
        """Return a pin filter that enforces scope/probe connection rules."""
        if self._wire_start_pin is None:
            return None

        start_component, start_pin_index = self._wire_start_pin

        def _pin_filter(item: object, pin_index: int) -> bool:
            candidate_component = getattr(item, "component", None)
            if candidate_component is None:
                return False
            return can_connect_measurement_pins(
                start_component,
                start_pin_index,
                candidate_component,
                pin_index,
            )

        return _pin_filter

    def resizeEvent(self, event):  # noqa: D401 - Qt override
        super().resizeEvent(event)
        self._position_alias_editor()

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
        self._position_alias_editor()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Handle scroll events and emit scroll_changed signal."""
        super().scrollContentsBy(dx, dy)
        self.scroll_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for panning and wire drawing."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton and self._current_tool == Tool.WIRE:
            # Wire tool: start, add point, or complete wire
            scene_pos = self.mapToScene(event.position().toPoint())
            preview = self._get_wire_preview()
            in_progress = self._get_wire_in_progress()
            nearest_pin = None

            # Check if clicking on a pin (magnetic snap) - pins take priority
            # Wires ALWAYS snap to grid or pin for clean schematics
            clicked_on_pin = False
            if isinstance(self.scene(), SchematicScene):
                pin_filter = self._wire_endpoint_pin_filter() if preview is not None else None
                nearest_pin = self.scene().find_nearest_pin(scene_pos, pin_filter=pin_filter)
                if nearest_pin is not None:
                    scene_pos = nearest_pin[0]
                    clicked_on_pin = True
                else:
                    # Always snap wires to grid
                    scene_pos = self.scene().snap_to_grid(scene_pos)

            if preview is None:
                # Start new wire
                self._wire_start = scene_pos
                self._wire_preview = WirePreviewItem(scene_pos)
                self._wire_in_progress = WireInProgressItem()
                self.scene().addItem(self._wire_in_progress)
                self.scene().addItem(self._wire_preview)
                if clicked_on_pin and nearest_pin is not None:
                    self._wire_start_pin = (nearest_pin[1].component, nearest_pin[2])
                else:
                    self._wire_start_pin = None
            elif clicked_on_pin:
                # Clicked on a pin - auto-finish the wire
                # Update preview end to pin position
                preview.set_end(scene_pos)

                # Add final segments from preview
                final_segments = preview.get_segments()
                if final_segments and in_progress is not None:
                    in_progress.add_segments(final_segments)

                # Get all accumulated segments and emit
                all_segments = in_progress.get_all_segments() if in_progress is not None else []
                if all_segments:
                    self.wire_created.emit(all_segments)

                # Clean up
                self._remove_wire_preview()
                self._remove_wire_in_progress()
                self._wire_start = None
                self._wire_start_pin = None
            else:
                # Add current segment to confirmed segments and continue
                if in_progress is None:
                    self._wire_in_progress = WireInProgressItem()
                    in_progress = self._wire_in_progress
                    self.scene().addItem(in_progress)
                current_segments = preview.get_segments()
                if current_segments:
                    in_progress.add_segments(current_segments)

                # Update start point for next segment
                self._wire_start = scene_pos

                # Reset preview from new point
                self._remove_wire_preview()
                self._wire_preview = WirePreviewItem(scene_pos)
                self.scene().addItem(self._wire_preview)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for panning, wire preview, and coordinate updates."""
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            self._position_alias_editor()
            event.accept()
        elif self._get_wire_preview() is not None:
            # Wires ALWAYS snap to grid or pin for clean schematics
            if isinstance(self.scene(), SchematicScene):
                nearest_pin = self.scene().find_nearest_pin(
                    scene_pos,
                    pin_filter=self._wire_endpoint_pin_filter(),
                )
                if nearest_pin is not None:
                    # Snap to pin position and show highlight
                    scene_pos = nearest_pin[0]
                    self._show_pin_highlight(scene_pos)
                else:
                    # Always snap wires to grid, hide pin highlight
                    scene_pos = self.scene().snap_to_grid(scene_pos)
                    self._hide_pin_highlight()
            preview = self._get_wire_preview()
            if preview is not None:
                preview.set_end(scene_pos)
            event.accept()
        else:
            # When not drawing wire, still show pin highlight in wire mode
            if self._current_tool == Tool.WIRE and isinstance(self.scene(), SchematicScene):
                nearest_pin = self.scene().find_nearest_pin(scene_pos)
                if nearest_pin is not None:
                    self._show_pin_highlight(nearest_pin[0])
                else:
                    self._hide_pin_highlight()
            else:
                self._hide_pin_highlight()

            super().mouseMoveEvent(event)

        # Emit mouse position in scene coordinates
        self.mouse_moved.emit(scene_pos.x(), scene_pos.y())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to stop panning."""
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self._update_cursor()
            self._position_alias_editor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double-click to complete wire."""
        if event.button() == Qt.MouseButton.LeftButton and self._current_tool == Tool.WIRE:
            preview = self._get_wire_preview()
            in_progress = self._get_wire_in_progress()
            if preview is not None and in_progress is not None:
                # Get final segment
                scene_pos = self.mapToScene(event.position().toPoint())
                if self._snap_to_grid and isinstance(self.scene(), SchematicScene):
                    scene_pos = self.scene().snap_to_grid(scene_pos)

                # Add final segments from preview
                final_segments = preview.get_segments()
                if final_segments:
                    in_progress.add_segments(final_segments)

                # Get all accumulated segments and emit
                all_segments = in_progress.get_all_segments()
                if all_segments:
                    self.wire_created.emit(all_segments)

                # Clean up
                self._remove_wire_preview()
                self._remove_wire_in_progress()
                self._wire_start = None
                self._wire_start_pin = None
                event.accept()
                return
        elif event.button() == Qt.MouseButton.LeftButton and self._current_tool == Tool.SELECT:
            item = self.itemAt(event.position().toPoint())
            if item is not None:
                from pulsimgui.views.schematic.items import ComponentItem

                if isinstance(item, ComponentItem):
                    comp_type = item.component.type
                    if comp_type == ComponentType.SUBCIRCUIT:
                        self.subcircuit_open_requested.emit(item.component)
                        event.accept()
                        return
                    if comp_type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
                        self.scope_open_requested.emit(item.component)
                        event.accept()
                        return
                    self.component_properties_requested.emit(item.component)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()
        modifiers = event.modifiers()

        # Zoom and edit shortcuts with Ctrl modifier
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
            elif key == Qt.Key.Key_C:
                # Copy selected component
                self.copy_selected()
                return
            elif key == Qt.Key.Key_V:
                # Paste component at cursor
                self.paste_at_cursor()
                return
            elif key == Qt.Key.Key_X:
                # Cut selected component
                self.cut_selected()
                return
            elif key == Qt.Key.Key_D:
                # Duplicate selected component
                from pulsimgui.views.schematic.items import ComponentItem
                scene = self.scene()
                if scene:
                    for item in scene.selectedItems():
                        if isinstance(item, ComponentItem):
                            self._duplicate_component(item)
                            break
                return

        # Tool shortcuts (without modifiers)
        if not modifiers:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._request_properties_for_selected_component():
                    return
            if key == Qt.Key.Key_F2:
                if self._maybe_start_alias_edit():
                    return
            if key == Qt.Key.Key_Escape:
                # Cancel wire drawing if in progress
                if self._get_wire_preview() is not None:
                    self.cancel_wire()
                else:
                    self.current_tool = Tool.SELECT
                    self.scene().clearSelection()
                return
            elif key == Qt.Key.Key_W:
                self.current_tool = Tool.WIRE
                return
            elif key == Qt.Key.Key_G:
                # Toggle grid visibility
                self.grid_toggle_requested.emit()
                return
            elif key == Qt.Key.Key_Space:
                # Toggle wire direction while drawing
                preview = self._get_wire_preview()
                if preview is not None:
                    preview.toggle_direction()
                return
            # Component shortcuts
            elif key == Qt.Key.Key_R:
                self.quick_add_component.emit(ComponentType.RESISTOR)
                return
            elif key == Qt.Key.Key_C:
                self.quick_add_component.emit(ComponentType.CAPACITOR)
                return
            elif key == Qt.Key.Key_L:
                self.quick_add_component.emit(ComponentType.INDUCTOR)
                return
            elif key == Qt.Key.Key_V:
                self.quick_add_component.emit(ComponentType.VOLTAGE_SOURCE)
                return
            elif key == Qt.Key.Key_I:
                self.quick_add_component.emit(ComponentType.CURRENT_SOURCE)
                return
            elif key == Qt.Key.Key_D:
                self.quick_add_component.emit(ComponentType.DIODE)
                return
            elif key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
                # Delete selected items
                self._delete_selected_items()
                return

        super().keyPressEvent(event)

    def _delete_selected_items(self) -> None:
        """Delete all selected items (wires and components)."""
        from pulsimgui.views.schematic.items import ComponentItem

        scene = self.scene()
        if scene is None or not isinstance(scene, SchematicScene):
            return

        selected = scene.selectedItems()
        if not selected:
            return

        wire_ids: list[str] = []
        component_ids: list[str] = []
        for item in selected:
            if isinstance(item, WireItem):
                wire_ids.append(str(item.wire.id))
            elif isinstance(item, ComponentItem):
                component_ids.append(str(item.component.id))

        # Delete wires first
        for wire_id in wire_ids:
            self.wire_delete_requested.emit(wire_id)

        # Delete components
        for component_id in component_ids:
            self.component_delete_requested.emit(component_id)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        from pulsimgui.views.schematic.items import ComponentItem

        item = self.itemAt(event.pos())
        icon_color = self.palette().color(QPalette.ColorRole.Text).name()

        if isinstance(item, WireItem):
            menu = QMenu(self)

            rename_action = menu.addAction(
                IconService.get_icon("edit", icon_color), "Rename Signal..."
            )
            rename_action.setShortcut("F2")

            copy_action = menu.addAction(
                IconService.get_icon("copy", icon_color), "Copy Signal Name"
            )

            menu.addSeparator()

            delete_action = menu.addAction(
                IconService.get_icon("trash", icon_color), "Delete Wire"
            )
            delete_action.setShortcut("Del")

            chosen = menu.exec(event.globalPos())
            if chosen == rename_action:
                self._begin_wire_alias_edit(item)
            elif chosen == copy_action:
                name = item.wire.alias or item.wire.node_name or ""
                if name:
                    QApplication.clipboard().setText(name)
            elif chosen == delete_action:
                self._delete_wire(item)
            event.accept()
            return

        elif isinstance(item, ComponentItem):
            menu = QMenu(self)

            # Properties at top
            props_action = menu.addAction(
                IconService.get_icon("sliders", icon_color), "Edit Properties..."
            )
            props_action.setShortcut("Enter")

            menu.addSeparator()

            # Edit submenu
            edit_menu = menu.addMenu(
                IconService.get_icon("edit", icon_color), "Edit"
            )
            cut_action = edit_menu.addAction(
                IconService.get_icon("scissors", icon_color), "Cut"
            )
            cut_action.setShortcut("Ctrl+X")
            copy_action = edit_menu.addAction(
                IconService.get_icon("copy", icon_color), "Copy"
            )
            copy_action.setShortcut("Ctrl+C")
            paste_action = edit_menu.addAction(
                IconService.get_icon("clipboard", icon_color), "Paste"
            )
            paste_action.setShortcut("Ctrl+V")
            edit_menu.addSeparator()
            duplicate_action = edit_menu.addAction(
                IconService.get_icon("copy", icon_color), "Duplicate"
            )
            duplicate_action.setShortcut("Ctrl+D")
            edit_menu.addSeparator()
            delete_action = edit_menu.addAction(
                IconService.get_icon("trash", icon_color), "Delete"
            )
            delete_action.setShortcut("Del")

            # Transform submenu
            transform_menu = menu.addMenu(
                IconService.get_icon("refresh", icon_color), "Transform"
            )
            rotate_cw = transform_menu.addAction(
                IconService.get_icon("rotate-cw", icon_color), "Rotate 90° CW"
            )
            rotate_cw.setShortcut("R")
            rotate_ccw = transform_menu.addAction(
                IconService.get_icon("rotate-ccw", icon_color), "Rotate 90° CCW"
            )
            rotate_ccw.setShortcut("Shift+R")
            transform_menu.addSeparator()
            flip_h = transform_menu.addAction(
                IconService.get_icon("flip-horizontal", icon_color), "Flip Horizontal"
            )
            flip_h.setShortcut("H")
            flip_v = transform_menu.addAction(
                IconService.get_icon("flip-vertical", icon_color), "Flip Vertical"
            )
            flip_v.setShortcut("V")

            chosen = menu.exec(event.globalPos())
            if chosen == props_action:
                self.component_properties_requested.emit(item.component)
            elif chosen == rotate_cw:
                self._rotate_component(item, 90)
            elif chosen == rotate_ccw:
                self._rotate_component(item, -90)
            elif chosen == flip_h:
                self._flip_component(item, horizontal=True)
            elif chosen == flip_v:
                self._flip_component(item, horizontal=False)
            elif chosen == delete_action:
                self._delete_component(item)
            elif chosen == duplicate_action:
                self._duplicate_component(item)
            elif chosen == cut_action:
                self._cut_component(item)
            elif chosen == copy_action:
                self._copy_component(item)
            elif chosen == paste_action:
                self._paste_component(QPointF(item.pos().x() + 40, item.pos().y() + 40))
            event.accept()
            return

        super().contextMenuEvent(event)

    def _request_properties_for_selected_component(self) -> bool:
        """Emit properties request for a single selected component."""
        from pulsimgui.views.schematic.items import ComponentItem

        scene = self.scene()
        if scene is None:
            return False

        selected = [item for item in scene.selectedItems() if isinstance(item, ComponentItem)]
        if len(selected) != 1:
            return False

        self.component_properties_requested.emit(selected[0].component)
        return True

    def _delete_wire(self, wire_item: WireItem) -> None:
        """Request deletion of a wire from the owning controller."""
        wire = getattr(wire_item, "wire", None)
        if wire is None:
            return
        self.wire_delete_requested.emit(str(wire.id))

    def _delete_component(self, comp_item) -> None:
        """Request deletion of a component from the owning controller."""
        from pulsimgui.views.schematic.items import ComponentItem

        if isinstance(comp_item, ComponentItem):
            self.component_delete_requested.emit(str(comp_item.component.id))

    def _rotate_component(self, comp_item, angle: int) -> None:
        """Request component rotation from owning controller."""
        from pulsimgui.views.schematic.items import ComponentItem

        if not isinstance(comp_item, ComponentItem):
            return
        self.component_rotate_requested.emit(str(comp_item.component.id), int(angle))

    def _flip_component(self, comp_item, horizontal: bool = True) -> None:
        """Request component flip from owning controller."""
        from pulsimgui.views.schematic.items import ComponentItem

        if not isinstance(comp_item, ComponentItem):
            return
        self.component_flip_requested.emit(str(comp_item.component.id), bool(horizontal))

    def _duplicate_component(self, comp_item) -> None:
        """Duplicate a component at a slight offset."""
        from pulsimgui.views.schematic.items import ComponentItem

        if not isinstance(comp_item, ComponentItem):
            return
        # Get original component data
        orig = comp_item.component
        # Create offset position
        new_x = orig.x + 40
        new_y = orig.y + 40
        # Emit signal to create new component (handled by main window)
        self.component_dropped.emit(orig.type.name, new_x, new_y)

    def _copy_component(self, comp_item) -> None:
        """Copy a component to clipboard with all its configuration."""
        from pulsimgui.views.schematic.items import ComponentItem

        if not isinstance(comp_item, ComponentItem):
            return

        # Serialize the component data
        self._clipboard_component_data = comp_item.component.to_dict()

    def _paste_component(self, position: QPointF | None = None) -> None:
        """Paste a component from clipboard at the given position."""
        from copy import deepcopy
        from uuid import uuid4
        from pulsimgui.models.component import Component
        from pulsimgui.views.schematic.items import create_component_item

        if self._clipboard_component_data is None:
            return

        scene = self.scene()
        if scene is None:
            return

        # Make a deep copy of the clipboard data
        data = deepcopy(self._clipboard_component_data)

        # Generate new ID
        data["id"] = str(uuid4())

        # Generate new name (increment number suffix)
        base_name = data["name"]
        existing_names = set()
        for item in scene.items():
            from pulsimgui.views.schematic.items import ComponentItem
            if isinstance(item, ComponentItem):
                existing_names.add(item.component.name)

        # Find unique name
        new_name = base_name
        counter = 1
        while new_name in existing_names:
            # Try to extract base and increment
            import re
            match = re.match(r"^(.+?)(\d+)$", base_name)
            if match:
                prefix = match.group(1)
                num = int(match.group(2)) + counter
                new_name = f"{prefix}{num}"
            else:
                new_name = f"{base_name}{counter}"
            counter += 1

        data["name"] = new_name

        # Determine paste position
        if position is not None:
            # Snap position to grid
            snapped = scene.snap_to_grid(position)
            data["x"] = snapped.x()
            data["y"] = snapped.y()
        else:
            # Offset from original position
            data["x"] = data["x"] + 40
            data["y"] = data["y"] + 40

        # Create the component from the data
        component = Component.from_dict(data)

        # Create the graphics item
        comp_item = create_component_item(component)
        scene.addItem(comp_item)

        # Select the new component
        scene.clearSelection()
        comp_item.setSelected(True)

    def _cut_component(self, comp_item) -> None:
        """Cut a component (copy to clipboard and delete)."""
        from pulsimgui.views.schematic.items import ComponentItem

        if not isinstance(comp_item, ComponentItem):
            return

        # Copy first
        self._copy_component(comp_item)

        # Then delete
        self._delete_component(comp_item)

    def copy_selected(self) -> None:
        """Copy selected component(s) to clipboard."""
        from pulsimgui.views.schematic.items import ComponentItem

        scene = self.scene()
        if scene is None:
            return

        selected = scene.selectedItems()
        for item in selected:
            if isinstance(item, ComponentItem):
                self._copy_component(item)
                break  # Only copy first selected component for now

    def paste_at_cursor(self) -> None:
        """Paste component at current cursor position."""
        cursor_pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        self._paste_component(cursor_pos)

    def cut_selected(self) -> None:
        """Cut selected component(s) to clipboard."""
        from pulsimgui.views.schematic.items import ComponentItem

        scene = self.scene()
        if scene is None:
            return

        selected = scene.selectedItems()
        for item in selected:
            if isinstance(item, ComponentItem):
                self._cut_component(item)
                break  # Only cut first selected component for now

    def eventFilter(self, watched, event):  # noqa: D401 - Qt override
        if watched is self._alias_editor and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._finish_wire_alias_edit(save=False)
                return True
        return super().eventFilter(watched, event)

    def _maybe_start_alias_edit(self) -> bool:
        scene = self.scene()
        if scene is None:
            return False

        for item in scene.selectedItems():
            if isinstance(item, WireItem):
                self._begin_wire_alias_edit(item)
                return True
        return False

    def _begin_wire_alias_edit(self, wire_item: WireItem) -> None:
        if wire_item is None:
            return

        self._finish_wire_alias_edit(save=False)
        editor = QLineEdit(self)
        initial_text = wire_item.wire.alias or wire_item.wire.node_name or ""
        editor.setText(initial_text)
        editor.setFixedWidth(160)
        editor.selectAll()
        editor.installEventFilter(self)
        editor.returnPressed.connect(lambda: self._finish_wire_alias_edit(True))
        editor.editingFinished.connect(lambda: self._finish_wire_alias_edit(True))

        self._alias_editor = editor
        self._alias_wire_item = wire_item
        self._position_alias_editor()
        editor.show()
        editor.setFocus()

    def _position_alias_editor(self) -> None:
        if not (self._alias_editor and self._alias_wire_item):
            return

        path = self._alias_wire_item.path()
        if path.isEmpty():
            return

        scene_point = self._alias_wire_item.mapToScene(path.pointAtPercent(0.5))
        view_point = self.mapFromScene(scene_point)
        editor = self._alias_editor
        editor.move(
            int(view_point.x() - editor.width() / 2),
            int(view_point.y() - editor.height() / 2),
        )

    def _finish_wire_alias_edit(self, save: bool) -> None:
        if not self._alias_editor:
            return

        editor = self._alias_editor
        wire_item = self._alias_wire_item
        self._alias_editor = None
        self._alias_wire_item = None

        editor.removeEventFilter(self)
        text = editor.text().strip()
        editor.deleteLater()

        if save and wire_item and wire_item.wire.alias != text:
            wire_item.wire.alias = text
            wire_item.update()
            self.wire_alias_changed.emit(wire_item.wire)

    def cancel_wire(self) -> None:
        """Cancel current wire drawing operation."""
        self._remove_wire_preview()
        self._remove_wire_in_progress()
        self._wire_start = None
        self._wire_start_pin = None
        self._hide_pin_highlight()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter to accept component drops and show preview."""
        if event.mimeData().hasFormat("application/x-pulsim-component"):
            # Get component type
            data = event.mimeData().data("application/x-pulsim-component")
            comp_type_name = bytes(data).decode()

            try:
                comp_type = ComponentType[comp_type_name]
                self._drop_comp_type = comp_type

                # Create preview item
                self._drop_preview = ComponentDropPreviewItem(comp_type)
                self.scene().addItem(self._drop_preview)

                # Position at current drag location (snapped to grid)
                scene_pos = self.mapToScene(event.position().toPoint())
                if self._snap_to_grid and isinstance(self.scene(), SchematicScene):
                    scene_pos = self.scene().snap_to_grid(scene_pos)
                self._drop_preview.setPos(scene_pos)

            except (KeyError, ValueError):
                pass  # Invalid component type

            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move to update preview location."""
        if event.mimeData().hasFormat("application/x-pulsim-component"):
            # Update preview position
            if self._drop_preview is not None:
                scene_pos = self.mapToScene(event.position().toPoint())
                if self._snap_to_grid and isinstance(self.scene(), SchematicScene):
                    scene_pos = self.scene().snap_to_grid(scene_pos)
                self._drop_preview.setPos(scene_pos)

            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        """Handle drag leave to remove preview."""
        self._remove_drop_preview()
        super().dragLeaveEvent(event)

    def _remove_drop_preview(self) -> None:
        """Remove the drop preview item from the scene."""
        if self._is_alive_graphics_item(self._drop_preview):
            scene = self.scene()
            if scene is not None and isValid(scene):
                scene.removeItem(self._drop_preview)
        self._drop_preview = None
        self._drop_comp_type = None

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop to add component at location."""
        if event.mimeData().hasFormat("application/x-pulsim-component"):
            # Get component type from mime data
            data = event.mimeData().data("application/x-pulsim-component")
            comp_type_name = bytes(data).decode()

            # Get drop position in scene coordinates
            scene_pos = self.mapToScene(event.position().toPoint())

            # Snap to grid if enabled
            if self._snap_to_grid and isinstance(self.scene(), SchematicScene):
                scene_pos = self.scene().snap_to_grid(scene_pos)

            # Remove preview before adding the real component
            self._remove_drop_preview()

            # Emit signal to add component
            self.component_dropped.emit(comp_type_name, scene_pos.x(), scene_pos.y())
            event.acceptProposedAction()
        else:
            event.ignore()

    def _show_pin_highlight(self, pos: QPointF) -> None:
        """Show pin highlight glow at the given position."""
        scene = self.scene()
        if scene is None or not isValid(scene):
            return

        highlight = self._get_pin_highlight()
        if highlight is None:
            self._pin_highlight = PinHighlightItem()
            scene.addItem(self._pin_highlight)
            highlight = self._pin_highlight

        highlight.setPos(pos)
        highlight.set_visible(True)

    def _hide_pin_highlight(self) -> None:
        """Hide the pin highlight glow."""
        highlight = self._get_pin_highlight()
        if highlight is not None:
            highlight.set_visible(False)

    def _show_alignment_guides(self, moving_item) -> None:
        """Show alignment guides when moving a component."""
        from pulsimgui.views.schematic.items import ComponentItem

        if not isinstance(moving_item, ComponentItem):
            return

        scene = self.scene()
        if not isinstance(scene, SchematicScene):
            return

        # Create guides item if needed
        if self._alignment_guides is None:
            self._alignment_guides = AlignmentGuidesItem()
            scene.addItem(self._alignment_guides)

        # Get center position of moving item
        moving_center = moving_item.pos()
        moving_x = moving_center.x()
        moving_y = moving_center.y()

        # Find alignments with other components
        h_guides: list[float] = []
        v_guides: list[float] = []
        tolerance = 5.0  # Alignment tolerance in pixels

        for item in scene.items():
            if isinstance(item, ComponentItem) and item is not moving_item:
                other_pos = item.pos()

                # Check horizontal alignment (same Y)
                if abs(other_pos.y() - moving_y) < tolerance:
                    h_guides.append(other_pos.y())

                # Check vertical alignment (same X)
                if abs(other_pos.x() - moving_x) < tolerance:
                    v_guides.append(other_pos.x())

        # Update guides
        self._alignment_guides.set_guides(h_guides, v_guides)

    def _hide_alignment_guides(self) -> None:
        """Hide the alignment guides."""
        if self._alignment_guides is not None:
            self._alignment_guides.clear_guides()
