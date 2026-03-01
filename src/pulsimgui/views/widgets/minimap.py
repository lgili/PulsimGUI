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

from pulsimgui.services.theme_service import Theme


class MinimapWidget(QFrame):
    """Minimap showing overview of schematic with viewport indicator."""

    # Signal emitted when user clicks on minimap to navigate
    navigation_requested = Signal(float, float)  # Scene x, y coordinates

    # Minimap settings
    SIZE = 160  # Widget size in pixels
    PADDING = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MinimapWidgetRoot")
        self._source_view: QGraphicsView | None = None
        self._scene_rect = QRectF()
        self._viewport_rect = QRectF()
        self._scale = 1.0
        self._offset = QPointF()
        self._dragging = False
        self._dark_mode = False
        self._theme: Theme | None = None

        # Theme-aware colors (will be updated)
        self._update_colors()

        self.setFixedSize(self.SIZE, self.SIZE)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._apply_styles()

    def _update_colors(self) -> None:
        """Update colors based on dark mode setting."""
        if self._theme is not None:
            c = self._theme.colors
            self.VIEWPORT_COLOR = QColor(c.overlay_minimap_viewport_fill)
            self.VIEWPORT_BORDER = QColor(c.overlay_minimap_viewport_border)
            self.COMPONENT_COLOR = QColor(c.foreground_muted)
            self.WIRE_COLOR = QColor(c.schematic_wire)
            self.WIRE_COLOR.setAlpha(160)
            self.BACKGROUND = QColor(c.plot_background)
            self.BORDER_COLOR = QColor(c.panel_border)
            self.PLACEHOLDER_TEXT = QColor(c.foreground_muted)
            return

        if self._dark_mode:
            self.VIEWPORT_COLOR = QColor(88, 166, 255, 60)
            self.VIEWPORT_BORDER = QColor(88, 166, 255, 180)
            self.COMPONENT_COLOR = QColor(180, 180, 180)
            self.WIRE_COLOR = QColor(63, 185, 80, 150)
            self.BACKGROUND = QColor(22, 27, 34)
            self.BORDER_COLOR = QColor(48, 54, 61)
        else:
            self.VIEWPORT_COLOR = QColor(37, 99, 235, 50)
            self.VIEWPORT_BORDER = QColor(37, 99, 235, 180)
            self.COMPONENT_COLOR = QColor(120, 120, 120)
            self.WIRE_COLOR = QColor(5, 150, 105, 150)
            self.BACKGROUND = QColor(255, 255, 255)
            self.BORDER_COLOR = QColor(229, 231, 235)
        self.PLACEHOLDER_TEXT = QColor(180, 180, 180) if self._dark_mode else QColor(120, 120, 120)

    def apply_theme(self, theme: Theme) -> None:
        """Apply the active theme directly to minimap visuals."""
        self._theme = theme
        self._dark_mode = theme.is_dark
        self._update_colors()
        self._apply_styles()
        self.update()

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode and update colors."""
        self._theme = None
        self._dark_mode = dark
        self._update_colors()
        self._apply_styles()
        self.update()

    def _apply_styles(self) -> None:
        """Apply modern styling."""
        if self._theme is not None:
            bg = self._theme.colors.plot_background
            border = self._theme.colors.panel_border
        else:
            bg = "#161b22" if self._dark_mode else "#ffffff"
            border = "#30363d" if self._dark_mode else "#e5e7eb"
        self.setStyleSheet(f"""
            QFrame#MinimapWidgetRoot {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
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
            painter.setPen(QPen(self.PLACEHOLDER_TEXT))
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

        # Adjust size to account for shadow/border
        self.setFixedSize(MinimapWidget.SIZE + 4, MinimapWidget.SIZE + 4)

    def set_source_view(self, view: QGraphicsView) -> None:
        """Set the source graphics view."""
        self._minimap.set_source_view(view)

    def update_minimap(self) -> None:
        """Update the minimap display."""
        self._minimap.update_minimap()

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode for the minimap."""
        self._minimap.set_dark_mode(dark)

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme to the embedded minimap widget."""
        self._minimap.apply_theme(theme)
