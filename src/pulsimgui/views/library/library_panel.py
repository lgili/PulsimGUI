"""Component library panel with drag-and-drop support."""

from PySide6.QtCore import Qt, QMimeData, QByteArray, Signal, QPointF, QRectF
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QPushButton,
    QLabel,
    QHeaderView,
    QAbstractItemView,
)

from pulsimgui.models.component import ComponentType


def create_component_drag_pixmap(comp_type: ComponentType, size: int = 70) -> QPixmap:
    """Create a pixmap with the component symbol for drag preview."""
    # Create transparent pixmap
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Set up pen for drawing
    pen = QPen(QColor(0, 0, 0), 2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Center the drawing
    cx, cy = size / 2, size / 2
    painter.translate(cx, cy)

    # Draw symbol based on component type
    if comp_type == ComponentType.RESISTOR:
        _draw_resistor(painter)
    elif comp_type == ComponentType.CAPACITOR:
        _draw_capacitor(painter)
    elif comp_type == ComponentType.INDUCTOR:
        _draw_inductor(painter)
    elif comp_type == ComponentType.VOLTAGE_SOURCE:
        _draw_voltage_source(painter)
    elif comp_type == ComponentType.CURRENT_SOURCE:
        _draw_current_source(painter)
    elif comp_type == ComponentType.GROUND:
        _draw_ground(painter)
    elif comp_type == ComponentType.DIODE:
        _draw_diode(painter)
    elif comp_type in (ComponentType.MOSFET_N, ComponentType.MOSFET_P):
        _draw_mosfet(painter, comp_type == ComponentType.MOSFET_N)
    elif comp_type == ComponentType.IGBT:
        _draw_igbt(painter)
    elif comp_type == ComponentType.SWITCH:
        _draw_switch(painter)
    elif comp_type == ComponentType.TRANSFORMER:
        _draw_transformer(painter)
    else:
        # Fallback: draw a simple box
        painter.drawRect(-15, -15, 30, 30)

    painter.end()
    return pixmap


def _draw_resistor(painter: QPainter) -> None:
    """Draw resistor zigzag symbol."""
    points = [
        (-25, 0), (-18, 0), (-15, -8), (-9, 8), (-3, -8),
        (3, 8), (9, -8), (15, 8), (18, 0), (25, 0)
    ]
    for i in range(len(points) - 1):
        painter.drawLine(
            QPointF(points[i][0], points[i][1]),
            QPointF(points[i + 1][0], points[i + 1][1])
        )


def _draw_capacitor(painter: QPainter) -> None:
    """Draw capacitor symbol (two parallel plates)."""
    # Lead lines
    painter.drawLine(QPointF(-20, 0), QPointF(-5, 0))
    painter.drawLine(QPointF(5, 0), QPointF(20, 0))
    # Plates
    painter.drawLine(QPointF(-5, -12), QPointF(-5, 12))
    painter.drawLine(QPointF(5, -12), QPointF(5, 12))


def _draw_inductor(painter: QPainter) -> None:
    """Draw inductor coil symbol."""
    # Lead lines
    painter.drawLine(QPointF(-25, 0), QPointF(-18, 0))
    painter.drawLine(QPointF(18, 0), QPointF(25, 0))
    # Coil arcs
    for i in range(4):
        x = -13 + i * 9
        painter.drawArc(QRectF(x, -6, 9, 12), 0 * 16, 180 * 16)


def _draw_voltage_source(painter: QPainter) -> None:
    """Draw voltage source circle with +/-."""
    # Circle
    painter.drawEllipse(QPointF(0, 0), 15, 15)
    # Lead lines
    painter.drawLine(QPointF(-25, 0), QPointF(-15, 0))
    painter.drawLine(QPointF(15, 0), QPointF(25, 0))
    # Plus sign
    painter.drawLine(QPointF(-8, 0), QPointF(-3, 0))
    painter.drawLine(QPointF(-5.5, -3), QPointF(-5.5, 3))
    # Minus sign
    painter.drawLine(QPointF(3, 0), QPointF(8, 0))


def _draw_current_source(painter: QPainter) -> None:
    """Draw current source circle with arrow."""
    # Circle
    painter.drawEllipse(QPointF(0, 0), 15, 15)
    # Lead lines
    painter.drawLine(QPointF(-25, 0), QPointF(-15, 0))
    painter.drawLine(QPointF(15, 0), QPointF(25, 0))
    # Arrow inside
    painter.drawLine(QPointF(-8, 0), QPointF(8, 0))
    painter.drawLine(QPointF(4, -4), QPointF(8, 0))
    painter.drawLine(QPointF(4, 4), QPointF(8, 0))


def _draw_ground(painter: QPainter) -> None:
    """Draw ground symbol."""
    # Vertical line
    painter.drawLine(QPointF(0, -15), QPointF(0, 0))
    # Horizontal lines
    painter.drawLine(QPointF(-12, 0), QPointF(12, 0))
    painter.drawLine(QPointF(-8, 5), QPointF(8, 5))
    painter.drawLine(QPointF(-4, 10), QPointF(4, 10))


def _draw_diode(painter: QPainter) -> None:
    """Draw diode symbol."""
    # Lead lines
    painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
    painter.drawLine(QPointF(8, 0), QPointF(20, 0))
    # Triangle
    triangle = [QPointF(-8, 0), QPointF(8, -10), QPointF(8, 10)]
    painter.drawPolygon(triangle)
    # Bar
    painter.drawLine(QPointF(8, -10), QPointF(8, 10))


def _draw_mosfet(painter: QPainter, is_nmos: bool) -> None:
    """Draw MOSFET symbol."""
    # Gate line
    painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
    painter.drawLine(QPointF(-8, -10), QPointF(-8, 10))
    # Channel
    painter.drawLine(QPointF(-4, -10), QPointF(-4, -5))
    painter.drawLine(QPointF(-4, -2), QPointF(-4, 2))
    painter.drawLine(QPointF(-4, 5), QPointF(-4, 10))
    # Drain and Source
    painter.drawLine(QPointF(-4, -7), QPointF(8, -7))
    painter.drawLine(QPointF(8, -7), QPointF(8, -15))
    painter.drawLine(QPointF(-4, 7), QPointF(8, 7))
    painter.drawLine(QPointF(8, 7), QPointF(8, 15))
    # Body connection
    painter.drawLine(QPointF(-4, 0), QPointF(8, 0))
    painter.drawLine(QPointF(8, 0), QPointF(8, 7))
    # Arrow (direction depends on N or P)
    if is_nmos:
        painter.drawLine(QPointF(2, 0), QPointF(6, -3))
        painter.drawLine(QPointF(2, 0), QPointF(6, 3))
    else:
        painter.drawLine(QPointF(-2, -3), QPointF(2, 0))
        painter.drawLine(QPointF(-2, 3), QPointF(2, 0))


def _draw_igbt(painter: QPainter) -> None:
    """Draw IGBT symbol."""
    # Similar to MOSFET but with collector bar
    _draw_mosfet(painter, True)
    # Extra bar at collector
    painter.drawLine(QPointF(6, -12), QPointF(10, -12))


def _draw_switch(painter: QPainter) -> None:
    """Draw switch symbol."""
    # Two terminals
    painter.drawLine(QPointF(-20, 0), QPointF(-8, 0))
    painter.drawLine(QPointF(8, 0), QPointF(20, 0))
    # Contact points
    painter.drawEllipse(QPointF(-8, 0), 2, 2)
    painter.drawEllipse(QPointF(8, 0), 2, 2)
    # Switch arm (open position)
    painter.drawLine(QPointF(-6, 0), QPointF(6, -10))


def _draw_transformer(painter: QPainter) -> None:
    """Draw transformer symbol."""
    # Primary coil
    for i in range(3):
        y = -10 + i * 10
        painter.drawArc(QRectF(-15, y, 8, 10), 90 * 16, 180 * 16)
    # Secondary coil
    for i in range(3):
        y = -10 + i * 10
        painter.drawArc(QRectF(7, y, 8, 10), -90 * 16, 180 * 16)
    # Core lines
    painter.drawLine(QPointF(-2, -15), QPointF(-2, 15))
    painter.drawLine(QPointF(2, -15), QPointF(2, 15))


class DraggableTreeWidget(QTreeWidget):
    """Tree widget with proper drag support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions) -> None:
        """Start drag operation for the current item."""
        item = self.currentItem()
        if not item:
            return

        comp_type = item.data(0, Qt.ItemDataRole.UserRole)
        if not comp_type:
            return

        # Create mime data
        mime_data = QMimeData()
        mime_data.setData(
            "application/x-pulsim-component",
            QByteArray(comp_type.name.encode()),
        )

        # Create drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Create drag pixmap with component symbol
        pixmap = create_component_drag_pixmap(comp_type)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        drag.exec(Qt.DropAction.CopyAction)


# Component metadata for library display
COMPONENT_LIBRARY = {
    "Passive": [
        {
            "type": ComponentType.RESISTOR,
            "name": "Resistor",
            "shortcut": "R",
            "description": "Electrical resistance element",
        },
        {
            "type": ComponentType.CAPACITOR,
            "name": "Capacitor",
            "shortcut": "C",
            "description": "Energy storage in electric field",
        },
        {
            "type": ComponentType.INDUCTOR,
            "name": "Inductor",
            "shortcut": "L",
            "description": "Energy storage in magnetic field",
        },
        {
            "type": ComponentType.TRANSFORMER,
            "name": "Transformer",
            "shortcut": "T",
            "description": "Magnetic coupling between inductors",
        },
    ],
    "Sources": [
        {
            "type": ComponentType.VOLTAGE_SOURCE,
            "name": "Voltage Source",
            "shortcut": "V",
            "description": "Ideal voltage source (DC, AC, pulse, PWL)",
        },
        {
            "type": ComponentType.CURRENT_SOURCE,
            "name": "Current Source",
            "shortcut": "I",
            "description": "Ideal current source (DC, AC, pulse, PWL)",
        },
        {
            "type": ComponentType.GROUND,
            "name": "Ground",
            "shortcut": "G",
            "description": "Reference node (0V)",
        },
    ],
    "Semiconductors": [
        {
            "type": ComponentType.DIODE,
            "name": "Diode",
            "shortcut": "D",
            "description": "PN junction diode",
        },
        {
            "type": ComponentType.MOSFET_N,
            "name": "NMOS",
            "shortcut": "M",
            "description": "N-channel MOSFET",
        },
        {
            "type": ComponentType.MOSFET_P,
            "name": "PMOS",
            "shortcut": "Shift+M",
            "description": "P-channel MOSFET",
        },
        {
            "type": ComponentType.IGBT,
            "name": "IGBT",
            "shortcut": "B",
            "description": "Insulated Gate Bipolar Transistor",
        },
    ],
    "Switches": [
        {
            "type": ComponentType.SWITCH,
            "name": "Ideal Switch",
            "shortcut": "S",
            "description": "Controlled ideal switch",
        },
    ],
}


class LibraryPanel(QWidget):
    """Panel displaying component library with drag-and-drop."""

    component_selected = Signal(ComponentType)
    component_double_clicked = Signal(ComponentType)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._favorites: list[ComponentType] = []
        self._recent: list[ComponentType] = []
        self._max_recent = 5

        self._setup_ui()
        self._populate_tree()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search components...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_edit)

        layout.addLayout(search_layout)

        # Component tree
        self._tree = DraggableTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setMouseTracking(True)

        layout.addWidget(self._tree)

        # Info label
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._info_label)

    def _populate_tree(self) -> None:
        """Populate the tree with components."""
        self._tree.clear()

        # Recent category
        self._recent_item = QTreeWidgetItem(self._tree, ["Recently Used"])
        self._recent_item.setFlags(
            self._recent_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled
        )
        self._update_recent_items()

        # Favorites category
        self._favorites_item = QTreeWidgetItem(self._tree, ["Favorites"])
        self._favorites_item.setFlags(
            self._favorites_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled
        )
        self._update_favorites_items()

        # Component categories
        for category, components in COMPONENT_LIBRARY.items():
            category_item = QTreeWidgetItem(self._tree, [category])
            category_item.setFlags(
                category_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled
            )
            category_item.setExpanded(True)

            for comp in components:
                item = QTreeWidgetItem(category_item)
                item.setText(0, f"{comp['name']} ({comp['shortcut']})")
                item.setData(0, Qt.ItemDataRole.UserRole, comp["type"])
                item.setData(0, Qt.ItemDataRole.UserRole + 1, comp["description"])
                item.setToolTip(0, f"{comp['description']}\nShortcut: {comp['shortcut']}")

    def _update_recent_items(self) -> None:
        """Update the recently used items."""
        # Clear existing children
        while self._recent_item.childCount() > 0:
            self._recent_item.removeChild(self._recent_item.child(0))

        if not self._recent:
            empty_item = QTreeWidgetItem(self._recent_item, ["(empty)"])
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            return

        for comp_type in self._recent:
            comp_info = self._find_component_info(comp_type)
            if comp_info:
                item = QTreeWidgetItem(self._recent_item)
                item.setText(0, comp_info["name"])
                item.setData(0, Qt.ItemDataRole.UserRole, comp_type)
                item.setToolTip(0, comp_info["description"])

    def _update_favorites_items(self) -> None:
        """Update the favorites items."""
        # Clear existing children
        while self._favorites_item.childCount() > 0:
            self._favorites_item.removeChild(self._favorites_item.child(0))

        if not self._favorites:
            empty_item = QTreeWidgetItem(self._favorites_item, ["(empty)"])
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            return

        for comp_type in self._favorites:
            comp_info = self._find_component_info(comp_type)
            if comp_info:
                item = QTreeWidgetItem(self._favorites_item)
                item.setText(0, comp_info["name"])
                item.setData(0, Qt.ItemDataRole.UserRole, comp_type)
                item.setToolTip(0, comp_info["description"])

    def _find_component_info(self, comp_type: ComponentType) -> dict | None:
        """Find component info by type."""
        for components in COMPONENT_LIBRARY.values():
            for comp in components:
                if comp["type"] == comp_type:
                    return comp
        return None

    def _on_search_changed(self, text: str) -> None:
        """Filter tree based on search text."""
        text = text.lower()

        def set_item_visibility(item: QTreeWidgetItem, visible: bool):
            item.setHidden(not visible)

        def filter_category(category_item: QTreeWidgetItem) -> bool:
            """Returns True if any child is visible."""
            any_visible = False
            for i in range(category_item.childCount()):
                child = category_item.child(i)
                comp_type = child.data(0, Qt.ItemDataRole.UserRole)

                if comp_type is None:
                    # Skip non-component items like "(empty)"
                    child.setHidden(bool(text))
                    continue

                child_text = child.text(0).lower()
                description = (child.data(0, Qt.ItemDataRole.UserRole + 1) or "").lower()

                visible = not text or text in child_text or text in description
                set_item_visibility(child, visible)
                if visible:
                    any_visible = True

            return any_visible

        # Filter each category
        for i in range(self._tree.topLevelItemCount()):
            category = self._tree.topLevelItem(i)
            if category.childCount() > 0:
                has_visible = filter_category(category)
                set_item_visibility(category, has_visible or not text)
                if has_visible:
                    category.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item click."""
        comp_type = item.data(0, Qt.ItemDataRole.UserRole)
        if comp_type:
            description = item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
            self._info_label.setText(description)
            self.component_selected.emit(comp_type)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item double-click to add component."""
        comp_type = item.data(0, Qt.ItemDataRole.UserRole)
        if comp_type:
            self.add_to_recent(comp_type)
            self.component_double_clicked.emit(comp_type)

    def add_to_recent(self, comp_type: ComponentType) -> None:
        """Add a component to the recently used list."""
        if comp_type in self._recent:
            self._recent.remove(comp_type)
        self._recent.insert(0, comp_type)
        self._recent = self._recent[: self._max_recent]
        self._update_recent_items()

    def add_to_favorites(self, comp_type: ComponentType) -> None:
        """Add a component to favorites."""
        if comp_type not in self._favorites:
            self._favorites.append(comp_type)
            self._update_favorites_items()

    def remove_from_favorites(self, comp_type: ComponentType) -> None:
        """Remove a component from favorites."""
        if comp_type in self._favorites:
            self._favorites.remove(comp_type)
            self._update_favorites_items()
