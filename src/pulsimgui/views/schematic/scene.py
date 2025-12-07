"""Schematic scene for circuit editing."""

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from PySide6.QtWidgets import QGraphicsScene

from pulsimgui.models.circuit import Circuit


class SchematicScene(QGraphicsScene):
    """
    Scene for displaying and editing circuit schematics.

    Signals:
        component_added: Emitted when a component is added
        component_removed: Emitted when a component is removed
        wire_added: Emitted when a wire is added
        selection_changed_custom: Emitted when selection changes with count
    """

    component_added = Signal(object)
    component_removed = Signal(object)
    wire_added = Signal(object)
    selection_changed_custom = Signal(int)

    # Grid settings
    GRID_SIZE = 10.0  # pixels
    GRID_COLOR = QColor(200, 200, 200)
    GRID_COLOR_DARK = QColor(60, 60, 60)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._circuit: Circuit | None = None
        self._show_grid = True
        self._grid_size = self.GRID_SIZE
        self._dark_mode = False

        # Set scene rect (large canvas)
        self.setSceneRect(-5000, -5000, 10000, 10000)

        # Connect selection changed
        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def circuit(self) -> Circuit | None:
        """Get the current circuit."""
        return self._circuit

    @circuit.setter
    def circuit(self, circuit: Circuit | None) -> None:
        """Set the circuit and update display."""
        self._circuit = circuit
        self._rebuild_scene()

    @property
    def grid_size(self) -> float:
        """Get grid size in pixels."""
        return self._grid_size

    @grid_size.setter
    def grid_size(self, size: float) -> None:
        """Set grid size and redraw."""
        self._grid_size = max(5.0, size)
        self.update()

    @property
    def show_grid(self) -> bool:
        """Get grid visibility."""
        return self._show_grid

    @show_grid.setter
    def show_grid(self, show: bool) -> None:
        """Set grid visibility."""
        self._show_grid = show
        self.update()

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode for grid colors."""
        self._dark_mode = dark
        self.update()

    def snap_to_grid(self, point: QPointF) -> QPointF:
        """Snap a point to the nearest grid intersection."""
        x = round(point.x() / self._grid_size) * self._grid_size
        y = round(point.y() / self._grid_size) * self._grid_size
        return QPointF(x, y)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the grid background."""
        super().drawBackground(painter, rect)

        if not self._show_grid:
            return

        # Get grid color based on theme
        grid_color = self.GRID_COLOR_DARK if self._dark_mode else self.GRID_COLOR

        # Calculate grid bounds
        left = int(rect.left()) - (int(rect.left()) % int(self._grid_size))
        top = int(rect.top()) - (int(rect.top()) % int(self._grid_size))

        # Draw grid dots
        painter.setPen(QPen(grid_color, 1))

        points = []
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                points.append(QPointF(x, y))
                y += self._grid_size
            x += self._grid_size

        painter.drawPoints(points)

    def _rebuild_scene(self) -> None:
        """Rebuild scene from circuit model."""
        # Clear existing items (except background)
        self.clear()

        if self._circuit is None:
            return

        # Add component items
        from pulsimgui.views.schematic.items import create_component_item

        for component in self._circuit.components:
            item = create_component_item(component)
            item.set_dark_mode(self._dark_mode)
            self.addItem(item)

        # TODO: Add wire items from circuit

    def add_component(self, component) -> None:
        """Add a component to the scene."""
        from pulsimgui.views.schematic.items import create_component_item

        item = create_component_item(component)
        item.set_dark_mode(self._dark_mode)
        self.addItem(item)
        self.component_added.emit(component)

    def remove_component(self, component) -> None:
        """Remove a component from the scene."""
        from pulsimgui.views.schematic.items import ComponentItem

        for item in self.items():
            if isinstance(item, ComponentItem) and item.component == component:
                self.removeItem(item)
                self.component_removed.emit(component)
                break

    def _on_selection_changed(self) -> None:
        """Handle selection changes."""
        count = len(self.selectedItems())
        self.selection_changed_custom.emit(count)

    def get_items_at(self, pos: QPointF, item_type=None):
        """Get items at a position, optionally filtered by type."""
        items = self.items(pos)
        if item_type is not None:
            items = [item for item in items if isinstance(item, item_type)]
        return items
