"""Schematic scene for circuit editing."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush, QPainterPath
from PySide6.QtWidgets import QGraphicsScene

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    pin_connection_domain,
)
from pulsimgui.models.wire import WireConnection


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
    component_moved = Signal(object, float, float, float, float)
    selection_changed_custom = Signal(int)

    # Grid settings - 20px is good for schematics
    GRID_SIZE = 20.0  # pixels
    GRID_DOT_SIZE = 2.4  # dot diameter in pixels
    PIN_CAPTURE_DISTANCE = 22.0  # pixels
    COMPONENT_COLLISION_PADDING = 2.0  # minimum spacing between component bodies
    COMPONENT_COLLISION_SEARCH_RADIUS = 16  # in grid cells
    WIRE_COMPONENT_CLEARANCE = 1.0  # shrink obstacle rect slightly to allow pin touches
    WIRE_PIN_SIDE_THRESHOLD = 9.0  # consider a pin near a side if inside this distance
    WIRE_PIN_SIDE_INSET = 8.0  # extra inset on sides that expose pins
    WIRE_PIN_ENTRY_ALLOWANCE = 14.0  # allow short ingress near a valid pin endpoint

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
        self._normalize_circuit_geometry()
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
        """Set dark-mode-dependent rendering behavior for scene items."""
        self._dark_mode = dark

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

    def resolve_component_position(self, component_item, desired_pos: QPointF) -> QPointF:
        """Resolve a collision-free component position near the desired grid point."""
        snapped = self.snap_to_grid(desired_pos)
        if not self._component_overlaps_at(component_item, snapped):
            return snapped

        step = self._grid_size
        for radius in range(1, self.COMPONENT_COLLISION_SEARCH_RADIUS + 1):
            candidates: list[QPointF] = []
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    candidate = QPointF(snapped.x() + dx * step, snapped.y() + dy * step)
                    if not self._component_overlaps_at(component_item, candidate):
                        candidates.append(candidate)
            if candidates:
                return min(
                    candidates,
                    key=lambda p: (p.x() - snapped.x()) ** 2 + (p.y() - snapped.y()) ** 2,
                )

        return component_item.pos()

    def is_wire_path_clear(self, segments: list) -> bool:
        """Return False when any segment crosses through a component body."""
        from pulsimgui.views.schematic.items import ComponentItem

        component_items = [item for item in self.items() if isinstance(item, ComponentItem)]
        if not component_items:
            return True

        for segment in segments:
            x1, y1, x2, y2 = self._segment_coords(segment)
            for component_item in component_items:
                if self._segment_crosses_component_body(x1, y1, x2, y2, component_item):
                    return False
        return True

    def _segment_coords(self, segment) -> tuple[float, float, float, float]:
        """Extract segment coordinates from either tuple or model segment object."""
        if hasattr(segment, "x1"):
            return (
                float(segment.x1),
                float(segment.y1),
                float(segment.x2),
                float(segment.y2),
            )
        return (
            float(segment[0]),
            float(segment[1]),
            float(segment[2]),
            float(segment[3]),
        )

    def _component_overlaps_at(self, component_item, pos: QPointF) -> bool:
        from pulsimgui.views.schematic.items import ComponentItem

        candidate_rect = self._component_body_rect(component_item, pos).adjusted(
            -self.COMPONENT_COLLISION_PADDING,
            -self.COMPONENT_COLLISION_PADDING,
            self.COMPONENT_COLLISION_PADDING,
            self.COMPONENT_COLLISION_PADDING,
        )

        for item in self.items():
            if not isinstance(item, ComponentItem) or item is component_item:
                continue
            other_rect = self._component_body_rect(item)
            if candidate_rect.intersects(other_rect):
                return True
        return False

    def _component_body_rect(self, component_item, pos: QPointF | None = None) -> QRectF:
        """Return component symbol body bounds in scene coordinates (without labels)."""
        mapped_rect = component_item.mapRectToScene(component_item.boundingRect())
        rect = mapped_rect if isinstance(mapped_rect, QRectF) else mapped_rect.boundingRect()
        if pos is None:
            return rect
        delta = pos - component_item.pos()
        return rect.translated(delta.x(), delta.y())

    def _segment_crosses_component_body(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        component_item,
    ) -> bool:
        """Check if a segment crosses the interior of a component bounding box."""
        rect = self._wire_obstacle_rect(component_item)
        if rect.isEmpty():
            return False

        horizontal = abs(y1 - y2) <= 0.1
        vertical = abs(x1 - x2) <= 0.1

        if horizontal:
            y = y1
            if y <= rect.top() or y >= rect.bottom():
                return False
            min_x, max_x = sorted((x1, x2))
            overlap_start = max(min_x, rect.left())
            overlap_end = min(max_x, rect.right())
            overlap_len = overlap_end - overlap_start
            if overlap_len <= 0.5:
                return False
            if overlap_len <= self.WIRE_PIN_ENTRY_ALLOWANCE and (
                self._point_is_component_pin(component_item, x1, y1)
                or self._point_is_component_pin(component_item, x2, y2)
            ):
                return False
            return True

        if vertical:
            x = x1
            if x <= rect.left() or x >= rect.right():
                return False
            min_y, max_y = sorted((y1, y2))
            overlap_start = max(min_y, rect.top())
            overlap_end = min(max_y, rect.bottom())
            overlap_len = overlap_end - overlap_start
            if overlap_len <= 0.5:
                return False
            if overlap_len <= self.WIRE_PIN_ENTRY_ALLOWANCE and (
                self._point_is_component_pin(component_item, x1, y1)
                or self._point_is_component_pin(component_item, x2, y2)
            ):
                return False
            return True

        # Fallback for any non-orthogonal segment (should be rare).
        seg_path = QPainterPath(QPointF(x1, y1))
        seg_path.lineTo(x2, y2)
        rect_path = QPainterPath()
        rect_path.addRect(rect)
        return seg_path.intersects(rect_path)

    def _wire_obstacle_rect(self, component_item) -> QRectF:
        """Return the rectangle used as wire obstacle for a component body."""
        rect = self._component_body_rect(component_item)
        if rect.isEmpty():
            return rect

        left_inset = self.WIRE_COMPONENT_CLEARANCE
        right_inset = self.WIRE_COMPONENT_CLEARANCE
        top_inset = self.WIRE_COMPONENT_CLEARANCE
        bottom_inset = self.WIRE_COMPONENT_CLEARANCE

        pins = self._component_pin_scene_positions(component_item)
        for pin in pins:
            if pin.x() <= rect.left() + self.WIRE_PIN_SIDE_THRESHOLD:
                left_inset = max(left_inset, self.WIRE_PIN_SIDE_INSET)
            if pin.x() >= rect.right() - self.WIRE_PIN_SIDE_THRESHOLD:
                right_inset = max(right_inset, self.WIRE_PIN_SIDE_INSET)
            if pin.y() <= rect.top() + self.WIRE_PIN_SIDE_THRESHOLD:
                top_inset = max(top_inset, self.WIRE_PIN_SIDE_INSET)
            if pin.y() >= rect.bottom() - self.WIRE_PIN_SIDE_THRESHOLD:
                bottom_inset = max(bottom_inset, self.WIRE_PIN_SIDE_INSET)

        max_x_inset = max(0.0, rect.width() / 2.0 - 1.0)
        max_y_inset = max(0.0, rect.height() / 2.0 - 1.0)
        left_inset = min(left_inset, max_x_inset)
        right_inset = min(right_inset, max_x_inset)
        top_inset = min(top_inset, max_y_inset)
        bottom_inset = min(bottom_inset, max_y_inset)

        return rect.adjusted(left_inset, top_inset, -right_inset, -bottom_inset)

    def _component_pin_scene_positions(self, component_item) -> list[QPointF]:
        """Get all pin positions of a component in scene coordinates."""
        component = getattr(component_item, "component", None)
        if component is None:
            return []
        pins: list[QPointF] = []
        for pin_index in range(len(component.pins)):
            pins.append(component_item.get_pin_position(pin_index))
        return pins

    def _point_is_component_pin(
        self,
        component_item,
        x: float,
        y: float,
        tolerance: float = 3.0,
    ) -> bool:
        """Return True when point matches a component pin center within tolerance."""
        for pin in self._component_pin_scene_positions(component_item):
            if abs(pin.x() - x) <= tolerance and abs(pin.y() - y) <= tolerance:
                return True
        return False

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

        # Dot sizes and contrast tuned for smoother "web-like" canvas.
        minor_dot_size = self.GRID_DOT_SIZE
        major_dot_radius = self.GRID_DOT_SIZE * 0.92

        minor_color = QColor(self._grid_color)
        minor_color.setAlpha(122 if self._dark_mode else 108)

        major_color = QColor(self._grid_color)
        if self._dark_mode:
            major_color = major_color.lighter(124)
            major_color.setAlpha(178)
        else:
            major_color = major_color.darker(118)
            major_color.setAlpha(152)

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
            pen = QPen(minor_color)
            pen.setWidthF(minor_dot_size)
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

        # Update connection indicators for all wires
        self._update_wire_connection_indicators()

    def refresh_wire_connection_overlays(self) -> None:
        """Recompute wire endpoint indicators and wire-wire junction dots."""
        self._update_wire_connection_indicators()
        self.update()

    def _update_wire_connection_indicators(self) -> None:
        """Update connection indicators for all wires in the scene.

        Finds wire endpoints that are connected to component pins and marks
        them with visual indicators.
        """
        from pulsimgui.views.schematic.items import WireItem

        if self._circuit is None:
            return

        PIN_HIT_TOLERANCE = 5.0

        # Collect all component pin positions
        pin_positions: list[tuple[float, float]] = []
        for component in self._circuit.components.values():
            for pin_idx in range(len(component.pins)):
                pos = component.get_pin_position(pin_idx)
                pin_positions.append(pos)

        wire_items = [item for item in self.items() if isinstance(item, WireItem)]
        if not wire_items:
            return

        # Recompute wire-wire junction points (for explicit T branches only).
        junctions_by_wire_id: dict[object, set[tuple[float, float]]] = {
            item.wire.id: set() for item in wire_items
        }
        wire_domains = {item.wire.id: self._wire_domain(item.wire) for item in wire_items}
        candidate_points: set[tuple[float, float]] = set()

        # Endpoints are candidates for branched nodes.
        for item in wire_items:
            for seg in item.wire.segments:
                candidate_points.add(self._normalized_point(seg.x1, seg.y1))
                candidate_points.add(self._normalized_point(seg.x2, seg.y2))

        # Draw junction dots only when the node has branching (3+ legs).
        for point in candidate_points:
            legs_by_domain = {
                CONNECTION_DOMAIN_CIRCUIT: 0,
                CONNECTION_DOMAIN_SIGNAL: 0,
                CONNECTION_DOMAIN_THERMAL: 0,
            }
            wires_by_domain = {
                CONNECTION_DOMAIN_CIRCUIT: set(),
                CONNECTION_DOMAIN_SIGNAL: set(),
                CONNECTION_DOMAIN_THERMAL: set(),
            }
            for item in wire_items:
                wire_touches = False
                wire_legs = 0
                for seg in item.wire.segments:
                    relation = self._point_segment_relation(point, seg, tolerance=0.1)
                    if relation <= 0:
                        continue
                    wire_legs += relation
                    wire_touches = True
                if wire_touches:
                    domain = wire_domains.get(item.wire.id, CONNECTION_DOMAIN_CIRCUIT)
                    legs_by_domain[domain] += wire_legs
                    wires_by_domain[domain].add(item.wire.id)

            for domain in (CONNECTION_DOMAIN_CIRCUIT, CONNECTION_DOMAIN_SIGNAL, CONNECTION_DOMAIN_THERMAL):
                if legs_by_domain[domain] < 3 or len(wires_by_domain[domain]) < 2:
                    continue
                for wire_id in wires_by_domain[domain]:
                    junctions_by_wire_id[wire_id].add(point)

        for item in wire_items:
            points = junctions_by_wire_id.get(item.wire.id, set())
            # Keep ordering deterministic for stable project serialization.
            item.wire.junctions = sorted(points, key=lambda point: (point[1], point[0]))

        # For each wire item, find endpoints that are connected to pins.
        for item in wire_items:
            wire = item.wire
            connected: set[tuple[float, float]] = set()

            # Check all wire segment endpoints
            for seg in wire.segments:
                for pos in ((seg.x1, seg.y1), (seg.x2, seg.y2)):
                    # Check if this position is near any pin
                    for pin_pos in pin_positions:
                        dx = abs(pos[0] - pin_pos[0])
                        dy = abs(pos[1] - pin_pos[1])
                        if dx < PIN_HIT_TOLERANCE and dy < PIN_HIT_TOLERANCE:
                            connected.add((pos[0], pos[1]))
                            break

            item.set_connected_endpoints(connected)

    def _wire_domain(self, wire) -> str:
        """Resolve wire domain from its endpoint pin metadata."""
        if self._circuit is None:
            return CONNECTION_DOMAIN_CIRCUIT
        domains: set[str] = set()
        for connection in (wire.start_connection, wire.end_connection):
            if connection is None:
                continue
            component = self._circuit.components.get(connection.component_id)
            if component is None:
                continue
            pin_index = connection.pin_index
            if pin_index < 0 or pin_index >= len(component.pins):
                continue
            domains.add(pin_connection_domain(component, pin_index))

        # Backward compatibility for wires without endpoint metadata.
        if not domains:
            points: list[tuple[float, float]] = []
            for segment in wire.segments:
                points.append((segment.x1, segment.y1))
                points.append((segment.x2, segment.y2))
            points.extend(wire.junctions or [])

            for component in self._circuit.components.values():
                for pin_index in range(len(component.pins)):
                    pin_x, pin_y = component.get_pin_position(pin_index)
                    for px, py in points:
                        if abs(pin_x - px) < 5.0 and abs(pin_y - py) < 5.0:
                            domains.add(pin_connection_domain(component, pin_index))
                            break

        if CONNECTION_DOMAIN_THERMAL in domains:
            return CONNECTION_DOMAIN_THERMAL
        if CONNECTION_DOMAIN_SIGNAL in domains:
            return CONNECTION_DOMAIN_SIGNAL
        return CONNECTION_DOMAIN_CIRCUIT

    def _wire_intersection_points(self, left_wire, right_wire) -> set[tuple[float, float]]:
        """Return normalized wire-wire junction points between two wires."""
        intersections: set[tuple[float, float]] = set()

        for left_seg in left_wire.segments:
            for right_seg in right_wire.segments:
                intersections.update(self._segment_intersection_points(left_seg, right_seg))

        return intersections

    def _segment_intersection_points(self, left_seg, right_seg) -> set[tuple[float, float]]:
        """Return candidate junction points between two segments."""
        tol = 0.1
        points: set[tuple[float, float]] = set()

        left_endpoints = ((left_seg.x1, left_seg.y1), (left_seg.x2, left_seg.y2))
        right_endpoints = ((right_seg.x1, right_seg.y1), (right_seg.x2, right_seg.y2))

        # T-junctions: endpoint of one segment lands on interior of the other.
        for point in left_endpoints:
            if self._point_on_segment(point, right_seg, include_endpoints=False, tolerance=tol):
                points.add(self._normalized_point(point[0], point[1]))
        for point in right_endpoints:
            if self._point_on_segment(point, left_seg, include_endpoints=False, tolerance=tol):
                points.add(self._normalized_point(point[0], point[1]))

        left_horizontal = abs(left_seg.y1 - left_seg.y2) <= tol
        left_vertical = abs(left_seg.x1 - left_seg.x2) <= tol
        right_horizontal = abs(right_seg.y1 - right_seg.y2) <= tol
        right_vertical = abs(right_seg.x1 - right_seg.x2) <= tol

        # Orthogonal crossing.
        if (left_horizontal and right_vertical) or (left_vertical and right_horizontal):
            if left_horizontal:
                ix, iy = right_seg.x1, left_seg.y1
            else:
                ix, iy = left_seg.x1, right_seg.y1

            if (
                self._between(ix, left_seg.x1, left_seg.x2, tol)
                and self._between(iy, left_seg.y1, left_seg.y2, tol)
                and self._between(ix, right_seg.x1, right_seg.x2, tol)
                and self._between(iy, right_seg.y1, right_seg.y2, tol)
            ):
                point = (ix, iy)
                # Skip pure endpoint-to-endpoint touch; keep only true branch/cross points.
                if not (
                    self._is_segment_endpoint(point, left_seg, tol)
                    and self._is_segment_endpoint(point, right_seg, tol)
                ):
                    points.add(self._normalized_point(ix, iy))

        # Collinear overlap: use interior endpoints as junction anchors.
        if left_horizontal and right_horizontal and abs(left_seg.y1 - right_seg.y1) <= tol:
            for point in left_endpoints:
                if self._point_on_segment(point, right_seg, include_endpoints=False, tolerance=tol):
                    points.add(self._normalized_point(point[0], point[1]))
            for point in right_endpoints:
                if self._point_on_segment(point, left_seg, include_endpoints=False, tolerance=tol):
                    points.add(self._normalized_point(point[0], point[1]))
        elif left_vertical and right_vertical and abs(left_seg.x1 - right_seg.x1) <= tol:
            for point in left_endpoints:
                if self._point_on_segment(point, right_seg, include_endpoints=False, tolerance=tol):
                    points.add(self._normalized_point(point[0], point[1]))
            for point in right_endpoints:
                if self._point_on_segment(point, left_seg, include_endpoints=False, tolerance=tol):
                    points.add(self._normalized_point(point[0], point[1]))

        return points

    def _normalized_point(self, x: float, y: float) -> tuple[float, float]:
        """Normalize point coordinates to schematic grid for stable matching."""
        return (
            self._snap_value_to_grid(float(x)),
            self._snap_value_to_grid(float(y)),
        )

    @staticmethod
    def _between(value: float, bound_a: float, bound_b: float, tolerance: float) -> bool:
        low = min(bound_a, bound_b) - tolerance
        high = max(bound_a, bound_b) + tolerance
        return low <= value <= high

    @staticmethod
    def _is_segment_endpoint(point: tuple[float, float], segment, tolerance: float) -> bool:
        px, py = point
        return (
            (abs(px - segment.x1) <= tolerance and abs(py - segment.y1) <= tolerance)
            or (abs(px - segment.x2) <= tolerance and abs(py - segment.y2) <= tolerance)
        )

    def _point_on_segment(
        self,
        point: tuple[float, float],
        segment,
        *,
        include_endpoints: bool,
        tolerance: float,
    ) -> bool:
        """Check if a point is on a segment within tolerance."""
        px, py = point
        x1, y1, x2, y2 = float(segment.x1), float(segment.y1), float(segment.x2), float(segment.y2)

        if not self._between(px, x1, x2, tolerance) or not self._between(py, y1, y2, tolerance):
            return False

        horizontal = abs(y1 - y2) <= tolerance
        vertical = abs(x1 - x2) <= tolerance

        if horizontal:
            if abs(py - y1) > tolerance:
                return False
            if not include_endpoints and (abs(px - x1) <= tolerance or abs(px - x2) <= tolerance):
                return False
            return True

        if vertical:
            if abs(px - x1) > tolerance:
                return False
            if not include_endpoints and (abs(py - y1) <= tolerance or abs(py - y2) <= tolerance):
                return False
            return True

        # Fallback for non-orthogonal segments.
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return abs(px - x1) <= tolerance and abs(py - y1) <= tolerance

        cross = abs((px - x1) * dy - (py - y1) * dx)
        length = (dx**2 + dy**2) ** 0.5
        if length < 1e-12:
            return False
        if cross / length > tolerance:
            return False

        if not include_endpoints and self._is_segment_endpoint(point, segment, tolerance):
            return False
        return True

    def _point_segment_relation(
        self,
        point: tuple[float, float],
        segment,
        *,
        tolerance: float,
    ) -> int:
        """Return how a point touches a segment: 0 none, 1 endpoint, 2 interior."""
        if not self._point_on_segment(point, segment, include_endpoints=True, tolerance=tolerance):
            return 0
        if self._is_segment_endpoint(point, segment, tolerance):
            return 1
        return 2

    def add_component(self, component) -> None:
        """Add a component to the scene."""
        from pulsimgui.views.schematic.items import create_component_item

        self._snap_component_to_grid(component)
        item = create_component_item(component)
        item.set_dark_mode(self._dark_mode)
        self.addItem(item)
        resolved = self.resolve_component_position(item, item.pos())
        if resolved != item.pos():
            item.setPos(resolved)
            component.x = resolved.x()
            component.y = resolved.y()
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

    def find_nearest_pin(
        self,
        pos: QPointF,
        max_distance: float | None = None,
        pin_filter: Callable[[object, int], bool] | None = None,
    ) -> tuple[QPointF, object, int] | None:
        """
        Find the nearest component pin within max_distance.

        Optimized with early termination when a very close pin is found.

        Returns:
            Tuple of (pin_position, component_item, pin_index) or None if no pin nearby
        """
        from pulsimgui.views.schematic.items import ComponentItem

        if max_distance is None:
            max_distance = self.PIN_CAPTURE_DISTANCE

        nearest_pin = None
        nearest_distance = max_distance
        max_dist_sq = max_distance * max_distance
        snap_threshold_sq = 25.0  # 5px - if within this, stop searching

        for item in self.items():
            if isinstance(item, ComponentItem):
                component = item.component
                for pin_index, _pin in enumerate(component.pins):
                    if pin_filter is not None and not pin_filter(item, pin_index):
                        continue
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

        self._update_wire_connection_indicators()

    def load_circuit(self, circuit) -> None:
        """Load a circuit and rebuild connections."""
        self.circuit = circuit

    # ------------------------------------------------------------------
    # Geometry normalization helpers
    # ------------------------------------------------------------------
    def _snap_value_to_grid(self, value: float) -> float:
        return round(value / self._grid_size) * self._grid_size

    def _snap_component_to_grid(self, component) -> None:
        snapped = self.snap_to_grid(QPointF(component.x, component.y))
        component.x = snapped.x()
        component.y = snapped.y()

    def _normalize_circuit_geometry(self) -> None:
        """Keep component/wire geometry aligned so wiring remains connectable."""
        if self._circuit is None:
            return

        for component in self._circuit.components.values():
            self._snap_component_to_grid(component)

        for wire in self._circuit.wires.values():
            for seg in wire.segments:
                seg.x1 = self._snap_value_to_grid(seg.x1)
                seg.y1 = self._snap_value_to_grid(seg.y1)
                seg.x2 = self._snap_value_to_grid(seg.x2)
                seg.y2 = self._snap_value_to_grid(seg.y2)

            # Preserve continuous polyline topology after snapping.
            for idx in range(len(wire.segments) - 1):
                wire.segments[idx + 1].x1 = wire.segments[idx].x2
                wire.segments[idx + 1].y1 = wire.segments[idx].y2

            if wire.junctions:
                wire.junctions = [
                    (
                        self._snap_value_to_grid(float(jx)),
                        self._snap_value_to_grid(float(jy)),
                    )
                    for jx, jy in wire.junctions
                ]

            self._synchronize_wire_endpoint_connection(wire, endpoint="start")
            self._synchronize_wire_endpoint_connection(wire, endpoint="end")

    def _synchronize_wire_endpoint_connection(self, wire, endpoint: str) -> None:
        """Ensure wire endpoint metadata and endpoint coordinates match nearby pins."""
        if not wire.segments:
            return

        is_start = endpoint == "start"
        connection = wire.start_connection if is_start else wire.end_connection
        pin_pos = self._pin_position_for_connection(connection)

        if pin_pos is None:
            point = (
                (wire.segments[0].x1, wire.segments[0].y1)
                if is_start
                else (wire.segments[-1].x2, wire.segments[-1].y2)
            )
            inferred = self._nearest_component_pin(point[0], point[1], max_distance=self.PIN_CAPTURE_DISTANCE)
            if inferred is None:
                if is_start:
                    wire.start_connection = None
                else:
                    wire.end_connection = None
                return

            component, pin_index, pin_x, pin_y = inferred
            if is_start:
                wire.start_connection = WireConnection(component_id=component.id, pin_index=pin_index)
            else:
                wire.end_connection = WireConnection(component_id=component.id, pin_index=pin_index)
            pin_pos = (pin_x, pin_y)

        if pin_pos is None:
            return

        pin_x, pin_y = pin_pos
        if is_start:
            wire.segments[0].x1 = pin_x
            wire.segments[0].y1 = pin_y
        else:
            wire.segments[-1].x2 = pin_x
            wire.segments[-1].y2 = pin_y

    def _pin_position_for_connection(
        self,
        connection: WireConnection | None,
    ) -> tuple[float, float] | None:
        if self._circuit is None or connection is None:
            return None
        component = self._circuit.components.get(connection.component_id)
        if component is None:
            return None
        if connection.pin_index < 0 or connection.pin_index >= len(component.pins):
            return None
        return component.get_pin_position(connection.pin_index)

    def _nearest_component_pin(
        self,
        x: float,
        y: float,
        max_distance: float,
    ) -> tuple[object, int, float, float] | None:
        if self._circuit is None:
            return None

        nearest = None
        nearest_sq = max_distance * max_distance
        for component in self._circuit.components.values():
            for pin_index in range(len(component.pins)):
                pin_x, pin_y = component.get_pin_position(pin_index)
                dx = pin_x - x
                dy = pin_y - y
                dist_sq = dx * dx + dy * dy
                if dist_sq <= nearest_sq:
                    nearest_sq = dist_sq
                    nearest = (component, pin_index, pin_x, pin_y)
        return nearest
