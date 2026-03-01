"""Device library dialog for selecting pre-defined device models."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QDialogButtonBox,
    QLineEdit,
    QLabel,
    QGroupBox,
    QHeaderView,
)

from pulsimgui.models.component import ComponentType


# Pre-defined device library
# In a real implementation, this would be loaded from files or a database
DEVICE_LIBRARY = {
    ComponentType.MOSFET_N: {
        "Power MOSFETs": [
            {
                "name": "IRF540N",
                "manufacturer": "Infineon",
                "parameters": {
                    "vth": 4.0,
                    "kp": 10.0,
                    "rds_on": 0.044,
                },
                "specs": {
                    "Vds_max": "100V",
                    "Id_max": "33A",
                    "Rds_on": "44mΩ",
                    "Package": "TO-220",
                },
            },
            {
                "name": "IRFZ44N",
                "manufacturer": "Infineon",
                "parameters": {
                    "vth": 4.0,
                    "kp": 15.0,
                    "rds_on": 0.0175,
                },
                "specs": {
                    "Vds_max": "55V",
                    "Id_max": "49A",
                    "Rds_on": "17.5mΩ",
                    "Package": "TO-220",
                },
            },
            {
                "name": "IPB072N15N3",
                "manufacturer": "Infineon",
                "parameters": {
                    "vth": 3.5,
                    "kp": 20.0,
                    "rds_on": 0.0072,
                },
                "specs": {
                    "Vds_max": "150V",
                    "Id_max": "100A",
                    "Rds_on": "7.2mΩ",
                    "Package": "TO-263",
                },
            },
        ],
        "Logic Level": [
            {
                "name": "IRLZ44N",
                "manufacturer": "Infineon",
                "parameters": {
                    "vth": 2.0,
                    "kp": 12.0,
                    "rds_on": 0.022,
                },
                "specs": {
                    "Vds_max": "55V",
                    "Id_max": "47A",
                    "Rds_on": "22mΩ",
                    "Vgs_th": "2V (Logic Level)",
                    "Package": "TO-220",
                },
            },
        ],
    },
    ComponentType.MOSFET_P: {
        "Power MOSFETs": [
            {
                "name": "IRF9540N",
                "manufacturer": "Infineon",
                "parameters": {
                    "vth": -4.0,
                    "kp": 5.0,
                    "rds_on": 0.117,
                },
                "specs": {
                    "Vds_max": "-100V",
                    "Id_max": "-23A",
                    "Rds_on": "117mΩ",
                    "Package": "TO-220",
                },
            },
        ],
    },
    ComponentType.IGBT: {
        "Standard IGBTs": [
            {
                "name": "IRG4PC40U",
                "manufacturer": "Infineon",
                "parameters": {
                    "vth": 5.0,
                    "vce_sat": 1.5,
                },
                "specs": {
                    "Vce_max": "600V",
                    "Ic_max": "40A",
                    "Vce_sat": "1.5V",
                    "Package": "TO-247",
                },
            },
            {
                "name": "FGH40N60SFD",
                "manufacturer": "Fairchild",
                "parameters": {
                    "vth": 5.5,
                    "vce_sat": 2.0,
                },
                "specs": {
                    "Vce_max": "600V",
                    "Ic_max": "40A",
                    "Vce_sat": "2.0V",
                    "Package": "TO-247",
                },
            },
        ],
    },
    ComponentType.DIODE: {
        "Schottky Diodes": [
            {
                "name": "1N5819",
                "manufacturer": "Various",
                "parameters": {
                    "is_": 1e-5,
                    "n": 1.05,
                    "rs": 0.04,
                },
                "specs": {
                    "Vr_max": "40V",
                    "If_max": "1A",
                    "Vf": "0.6V",
                    "Package": "DO-41",
                },
            },
            {
                "name": "MBR20100CT",
                "manufacturer": "ON Semi",
                "parameters": {
                    "is_": 1e-4,
                    "n": 1.1,
                    "rs": 0.02,
                },
                "specs": {
                    "Vr_max": "100V",
                    "If_max": "20A",
                    "Vf": "0.8V",
                    "Package": "TO-220",
                },
            },
        ],
        "Fast Recovery": [
            {
                "name": "UF4007",
                "manufacturer": "Various",
                "parameters": {
                    "is_": 1e-14,
                    "n": 1.8,
                    "rs": 0.1,
                },
                "specs": {
                    "Vr_max": "1000V",
                    "If_max": "1A",
                    "trr": "75ns",
                    "Package": "DO-41",
                },
            },
        ],
    },
}


class DeviceLibraryDialog(QDialog):
    """Dialog for browsing and selecting pre-defined devices."""

    device_selected = Signal(dict)  # Emits device parameters

    def __init__(self, component_type: ComponentType, parent=None):
        super().__init__(parent)
        self._component_type = component_type
        self._selected_device: dict | None = None

        self.setWindowTitle(f"Device Library - {component_type.name}")
        self.setMinimumSize(700, 500)

        self._setup_ui()
        self._populate_tree()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter devices...")
        self._search_edit.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_edit)
        layout.addLayout(search_layout)

        # Splitter with tree and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Device tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(200)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        splitter.addWidget(self._tree)

        # Details panel
        details_widget = QVBoxLayout()
        details_container = QGroupBox("Device Details")
        details_layout = QVBoxLayout(details_container)

        self._name_label = QLabel("-")
        self._name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        details_layout.addWidget(self._name_label)

        self._manufacturer_label = QLabel("")
        self._manufacturer_label.setStyleSheet("color: gray;")
        details_layout.addWidget(self._manufacturer_label)

        # Specifications table
        self._specs_table = QTableWidget()
        self._specs_table.setColumnCount(2)
        self._specs_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self._specs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._specs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        details_layout.addWidget(self._specs_table)

        details_wrapper = QVBoxLayout()
        details_wrapper.addWidget(details_container)
        details_wrapper.addStretch()

        details_widget_container = QVBoxLayout()
        details_widget_container.addWidget(details_container)

        right_widget = QVBoxLayout()
        right_widget.addWidget(details_container)

        right_container = QVBoxLayout()
        right_container.addWidget(details_container)

        right_frame = QVBoxLayout()
        right_frame.addWidget(details_container)

        wrapper = QVBoxLayout()
        wrapper.addWidget(details_container)

        from PySide6.QtWidgets import QFrame

        right_panel = QFrame()
        right_panel.setLayout(wrapper)
        splitter.addWidget(right_panel)

        splitter.setSizes([250, 450])
        layout.addWidget(splitter)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setEnabled(False)
        self._ok_button.setText("Apply Device")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_tree(self) -> None:
        """Populate the tree with devices."""
        self._tree.clear()

        devices = DEVICE_LIBRARY.get(self._component_type, {})

        for category, device_list in devices.items():
            category_item = QTreeWidgetItem(self._tree, [category])
            category_item.setFlags(
                category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
            )
            category_item.setExpanded(True)

            for device in device_list:
                item = QTreeWidgetItem(category_item, [device["name"]])
                item.setData(0, Qt.ItemDataRole.UserRole, device)

    def _on_search_changed(self, text: str) -> None:
        """Filter devices based on search text."""
        text = text.lower()

        for i in range(self._tree.topLevelItemCount()):
            category = self._tree.topLevelItem(i)
            any_visible = False

            for j in range(category.childCount()):
                child = category.child(j)
                device = child.data(0, Qt.ItemDataRole.UserRole)
                if device:
                    name = device["name"].lower()
                    manufacturer = device.get("manufacturer", "").lower()
                    visible = not text or text in name or text in manufacturer
                    child.setHidden(not visible)
                    if visible:
                        any_visible = True

            category.setHidden(not any_visible and bool(text))

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle device selection."""
        device = item.data(0, Qt.ItemDataRole.UserRole)
        if device:
            self._selected_device = device
            self._ok_button.setEnabled(True)
            self._update_details(device)
        else:
            self._selected_device = None
            self._ok_button.setEnabled(False)
            self._clear_details()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click to select and apply."""
        device = item.data(0, Qt.ItemDataRole.UserRole)
        if device:
            self._selected_device = device
            self.accept()

    def _update_details(self, device: dict) -> None:
        """Update the details panel with device info."""
        self._name_label.setText(device["name"])
        self._manufacturer_label.setText(f"Manufacturer: {device.get('manufacturer', 'Unknown')}")

        specs = device.get("specs", {})
        self._specs_table.setRowCount(len(specs))

        for row, (param, value) in enumerate(specs.items()):
            self._specs_table.setItem(row, 0, QTableWidgetItem(param))
            self._specs_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _clear_details(self) -> None:
        """Clear the details panel."""
        self._name_label.setText("-")
        self._manufacturer_label.setText("")
        self._specs_table.setRowCount(0)

    def get_selected_parameters(self) -> dict | None:
        """Get the parameters of the selected device."""
        if self._selected_device:
            return self._selected_device.get("parameters", {}).copy()
        return None

    def get_selected_device(self) -> dict | None:
        """Get the full selected device info."""
        return self._selected_device
