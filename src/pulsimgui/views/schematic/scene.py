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
        """Draw the grid background with major grid markers every 5 cells.

        Optimized for performance by batching draw operations and using
        drawPoints for minor grid dots.
        """
        # Draw solid background color first
        painter.fillRect(rect, self._background_color)

        if not self._show_grid:
            return

        # Calculate grid bounds - align to grid
        left = int(rect.left() / self._grid_size) * self._grid_size
        top = int(rect.top() / self._grid_size) * self._grid_size
        right = rect.right()
        bottom = rect.bottom()

        # Major grid every 5 cells (100px with 20px grid)
        major_interval = 5

        # Dot sizes
        dot_radius = self.GRID_DOT_SIZE / 2.0
        major_dot_radius = self.GRID_DOT_SIZE

        # Create colors for major dots (slightly darker/more visible)
        major_color = QColor(self._grid_color)
        if self._dark_mode:
            major_color = major_color.lighter(140)
        else:
            major_color = major_color.darker(120)

        # Collect points in batches for efficient drawing
        minor_points = []
        major_points = []

        x = left
        grid_x = int(left / self._grid_size)
        while x <= right:
            y = top
            grid_y = int(top / self._grid_size)
            while y <= bottom:
                is_major = (grid_x % major_interval == 0) and (grid_y % major_interval == 0)
                if is_major:
                    major_points.append(QPointF(x, y))
                else:
                    minor_points.append(QPointF(x, y))
                y += self._grid_size
                grid_y += 1
            x += self._grid_size
            grid_x += 1

        # Batch draw minor dots using drawPoints (faster than individual drawEllipse)
        if minor_points:
            pen = QPen(self._grid_color)
            pen.setWidthF(self.GRID_DOT_SIZE)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawPoints(minor_points)

        # Draw major dots (still use ellipse for larger size, but batched)
        if major_points:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(major_color))
            for pt in major_points:
                painter.drawEllipse(pt, major_dot_radius, major_dot_radius)

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

        Optimized with early termination when a very close pin is found.

        Returns:
            Tuple of (pin_position, component_item, pin_index) or None if no pin nearby
        """
        from pulsimgui.views.schematic.items import ComponentItem

        nearest_pin = None
        nearest_distance = max_distance
        max_dist_sq = max_distance * max_distance
        snap_threshold_sq = 25.0  # 5px - if within this, stop searching

        for item in self.items():
            if isinstance(item, ComponentItem):
                component = item.component
                for pin_index, pin in enumerate(component.pins):
                    pin_pos = item.get_pin_position(pin_index)
                    dx = pin_pos.x() - pos.x()
                    dy = pin_pos.y() - pos.y()
                    dist_sq = dx * dx + dy * dy

                    # Skip if clearly outside max distance
                    if dist_sq > max_dist_sq:
                        continue

                    distance = dist_sq ** 0.5
                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_pin = (pin_pos, item, pin_index)

                        # Early termination if very close
                        if dist_sq < snap_threshold_sq:
                            return nearest_pin

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

    def update_connected_wires(self, component_item) -> None:
        """
        Update wire endpoints that are connected to a component's pins.

        Called when a component is moved to keep wires attached.
        Uses the saved connection info in wire model to track connections.
        """
        from pulsimgui.views.schematic.items import WireItem

        component_id = component_item.component.id

        for item in self.items():
            if not isinstance(item, WireItem):
                continue

            wire_item = item
            wire = wire_item.wire

            # Check if wire start is connected to this component
            if (wire.start_connection is not None and
                wire.start_connection.component_id == component_id):
                pin_index = wire.start_connection.pin_index
                new_pin_pos = component_item.get_pin_position(pin_index)
                wire_item.update_endpoint_position('start', new_pin_pos)

            # Check if wire end is connected to this component
            if (wire.end_connection is not None and
                wire.end_connection.component_id == component_id):
                pin_index = wire.end_connection.pin_index
                new_pin_pos = component_item.get_pin_position(pin_index)
                wire_item.update_endpoint_position('end', new_pin_pos)

    def load_circuit(self, circuit) -> None:
        """Load a circuit and rebuild connections."""
        self._circuit = circuit
        self._rebuild_scene()
