"""Component library panel with drag-and-drop support."""

from PySide6.QtCore import Qt, QMimeData, QByteArray, Signal
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor
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

        # Create drag pixmap
        pixmap = QPixmap(100, 30)
        pixmap.fill(QColor(240, 240, 240))
        painter = QPainter(pixmap)
        painter.setPen(QColor(0, 0, 0))
        painter.drawRect(0, 0, 99, 29)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, item.text(0).split(" (")[0])
        painter.end()
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
