"""Dialog for creating a subcircuit from selected components."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QDialogButtonBox,
    QGroupBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QWidget,
)


class CreateSubcircuitDialog(QDialog):
    """Dialog for creating a subcircuit from selected components.

    Allows the user to:
    - Name the subcircuit
    - Add a description
    - Configure ports (pins that connect to the parent circuit)
    """

    def __init__(
        self,
        selected_count: int,
        boundary_nets: list[str] | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize the dialog.

        Args:
            selected_count: Number of selected components
            boundary_nets: List of net names at the selection boundary
            parent: Parent widget
        """
        super().__init__(parent)
        self._selected_count = selected_count
        self._boundary_nets = boundary_nets or []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Create Subcircuit")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel(
            f"Create a reusable subcircuit from {self._selected_count} "
            f"selected component{'s' if self._selected_count != 1 else ''}."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Basic info group
        basic_group = QGroupBox("Subcircuit Information")
        basic_layout = QFormLayout(basic_group)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Half Bridge, Buck Stage")
        self._name_edit.setText("Subcircuit")
        basic_layout.addRow("Name:", self._name_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Optional description of the subcircuit...")
        self._desc_edit.setMaximumHeight(60)
        basic_layout.addRow("Description:", self._desc_edit)

        layout.addWidget(basic_group)

        # Ports group
        ports_group = QGroupBox("Ports (External Connections)")
        ports_layout = QVBoxLayout(ports_group)

        ports_info = QLabel(
            "Ports define how the subcircuit connects to the parent circuit. "
            "Each port becomes a pin on the subcircuit symbol."
        )
        ports_info.setWordWrap(True)
        ports_info.setStyleSheet("color: gray; font-size: 11px;")
        ports_layout.addWidget(ports_info)

        # Port list
        self._ports_list = QListWidget()
        self._ports_list.setMaximumHeight(120)

        if self._boundary_nets:
            for net in self._boundary_nets:
                item = QListWidgetItem(net)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self._ports_list.addItem(item)
        else:
            # If no boundary nets detected, show placeholder
            item = QListWidgetItem("(Ports will be auto-detected)")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._ports_list.addItem(item)

        ports_layout.addWidget(self._ports_list)

        # Add port button row
        port_btn_layout = QHBoxLayout()
        port_btn_layout.addStretch()
        ports_layout.addLayout(port_btn_layout)

        layout.addWidget(ports_group)

        # Symbol size group
        symbol_group = QGroupBox("Symbol Size")
        symbol_layout = QFormLayout(symbol_group)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(40, 200)
        self._width_spin.setValue(80)
        self._width_spin.setSuffix(" px")
        symbol_layout.addRow("Width:", self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(40, 200)
        self._height_spin.setValue(60)
        self._height_spin.setSuffix(" px")
        symbol_layout.addRow("Height:", self._height_spin)

        layout.addWidget(symbol_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Validation
        self._name_edit.textChanged.connect(self._validate)
        self._validate()

    def _validate(self) -> None:
        """Validate the dialog inputs."""
        # Name must not be empty
        valid = bool(self._name_edit.text().strip())

        # Find OK button and enable/disable
        for button in self.findChildren(QDialogButtonBox):
            ok_btn = button.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn:
                ok_btn.setEnabled(valid)

    def get_name(self) -> str:
        """Get the subcircuit name."""
        return self._name_edit.text().strip()

    def get_description(self) -> str:
        """Get the subcircuit description."""
        return self._desc_edit.toPlainText().strip()

    def get_selected_ports(self) -> list[str]:
        """Get the list of selected port names."""
        ports = []
        for i in range(self._ports_list.count()):
            item = self._ports_list.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                if item.checkState() == Qt.CheckState.Checked:
                    ports.append(item.text())
        return ports

    def get_symbol_size(self) -> tuple[int, int]:
        """Get the symbol size (width, height)."""
        return self._width_spin.value(), self._height_spin.value()
