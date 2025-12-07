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

    # Grid settings - 20px is good for schematics
    GRID_SIZE = 20.0  # pixels
    GRID_DOT_SIZE = 3.0  # dot diameter in pixels

    def __init__(self, parent=None):
        super().__init__(parent)

        self._circuit: Circuit | None = None
        self._show_grid = True
        self._grid_size = self.GRID_SIZE
        self._dark_mode = False
        self._grid_color = QColor(180, 180, 180)  # Slightly darker for visibility
        self._background_color = QColor(255, 255, 255)  # White background
        self._show_dc_overlay = False

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
        """Set dark mode for grid colors and update all components."""
        self._dark_mode = dark
        if dark:
            self._background_color = QColor(30, 30, 30)
            self._grid_color = QColor(60, 60, 60)
        else:
            self._background_color = QColor(255, 255, 255)
            self._grid_color = QColor(180, 180, 180)

        # Update all component items
        from pulsimgui.views.schematic.items import ComponentItem, WireItem
        for item in self.items():
            if isinstance(item, ComponentItem):
                item.set_dark_mode(dark)
            elif isinstance(item, WireItem):
                item.set_dark_mode(dark)

        self.update()

    def set_grid_color(self, color: QColor) -> None:
        """Set the grid dot color from theme."""
        self._grid_color = color
        self.update()

    @property
    def background_color(self) -> QColor:
        """Get the current background color."""
        return self._background_color

    def set_background_color(self, color: QColor) -> None:
        """Set the background color from theme."""
        self._background_color = color
        self.update()

    def snap_to_grid(self, point: QPointF) -> QPointF:
        """Snap a point to the nearest grid intersection."""
        x = round(point.x() / self._grid_size) * self._grid_size
        y = round(point.y() / self._grid_size) * self._grid_size
        return QPointF(x, y)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the grid background."""
        # Draw solid background color first
        painter.fillRect(rect, self._background_color)

        if not self._show_grid:
            return

        # Calculate grid bounds - align to grid
        left = int(rect.left() / self._grid_size) * self._grid_size
        top = int(rect.top() / self._grid_size) * self._grid_size

        # Set up painter for dots
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._grid_color))

        # Draw grid dots
        dot_radius = self.GRID_DOT_SIZE / 2.0
        x = left
        while x <= rect.right():
            y = top
            while y <= rect.bottom():
                painter.drawEllipse(QPointF(x, y), dot_radius, dot_radius)
                y += self._grid_size
            x += self._grid_size

    def _rebuild_scene(self) -> None:
        """Rebuild scene from circuit model."""
        # Clear existing items (except background)
        self.clear()

        if self._circuit is None:
            return

        # Add component items
        from pulsimgui.views.schematic.items import create_component_item, WireItem

        for component in self._circuit.components.values():
            item = create_component_item(component)
            item.set_dark_mode(self._dark_mode)
            self.addItem(item)

        for wire in self._circuit.wires.values():
            wire_item = WireItem(wire)
            wire_item.set_dark_mode(self._dark_mode)
            self.addItem(wire_item)

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

    def find_nearest_pin(self, pos: QPointF, max_distance: float = 15.0) -> tuple[QPointF, object, int] | None:
        """
        Find the nearest component pin within max_distance.

        Returns:
            Tuple of (pin_position, component_item, pin_index) or None if no pin nearby
        """
        from pulsimgui.views.schematic.items import ComponentItem

        nearest_pin = None
        nearest_distance = max_distance

        for item in self.items():
            if isinstance(item, ComponentItem):
                component = item.component
                for pin_index, pin in enumerate(component.pins):
                    pin_pos = item.get_pin_position(pin_index)
                    dx = pin_pos.x() - pos.x()
                    dy = pin_pos.y() - pos.y()
                    distance = (dx * dx + dy * dy) ** 0.5

                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_pin = (pin_pos, item, pin_index)

        return nearest_pin

    # DC Overlay methods

    @property
    def show_dc_overlay(self) -> bool:
        """Get DC overlay visibility."""
        return self._show_dc_overlay

    @show_dc_overlay.setter
    def show_dc_overlay(self, show: bool) -> None:
        """Set DC overlay visibility for all components."""
        self._show_dc_overlay = show
        from pulsimgui.views.schematic.items import ComponentItem

        for item in self.items():
            if isinstance(item, ComponentItem):
                item.set_show_dc_overlay(show)

    def set_dc_results(self, dc_result) -> None:
        """
        Apply DC operating point results to all components.

        Args:
            dc_result: DCResult object with node_voltages, branch_currents, power_dissipation
        """
        from pulsimgui.views.schematic.items import ComponentItem

        for item in self.items():
            if isinstance(item, ComponentItem):
                comp_name = item.component.name

                # Get current (I(component_name))
                current_key = f"I({comp_name})"
                current = dc_result.branch_currents.get(current_key)

                # Get power (P(component_name))
                power_key = f"P({comp_name})"
                power = dc_result.power_dissipation.get(power_key)

                item.set_dc_values(current=current, power=power)

        # Auto-show overlay when results are set
        self.show_dc_overlay = True

    def clear_dc_results(self) -> None:
        """Clear all DC results from components."""
        from pulsimgui.views.schematic.items import ComponentItem

        for item in self.items():
            if isinstance(item, ComponentItem):
                item.clear_dc_values()

        self._show_dc_overlay = False
