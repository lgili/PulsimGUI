"""Quick-add palette dialog for fast component insertion."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QHBoxLayout,
)

from pulsimgui.models.component import ComponentType
from pulsimgui.resources.icons import IconService


# Component search data: (type, display_name, keywords)
COMPONENT_DATA = [
    (ComponentType.RESISTOR, "Resistor", ["r", "res", "resistance", "ohm"]),
    (ComponentType.CAPACITOR, "Capacitor", ["c", "cap", "capacitance", "farad"]),
    (ComponentType.INDUCTOR, "Inductor", ["l", "ind", "inductance", "henry"]),
    (ComponentType.VOLTAGE_SOURCE, "Voltage Source", ["v", "vs", "volt", "voltage", "vdc"]),
    (ComponentType.CURRENT_SOURCE, "Current Source", ["i", "is", "curr", "current", "idc"]),
    (ComponentType.GROUND, "Ground", ["gnd", "ground", "0"]),
    (ComponentType.DIODE, "Diode", ["d", "diode", "rectifier"]),
    (ComponentType.MOSFET_N, "N-Channel MOSFET", ["nmos", "nfet", "mosfet", "transistor"]),
    (ComponentType.MOSFET_P, "P-Channel MOSFET", ["pmos", "pfet"]),
    (ComponentType.IGBT, "IGBT", ["igbt", "transistor"]),
    (ComponentType.SWITCH, "Switch", ["sw", "switch"]),
    (ComponentType.TRANSFORMER, "Transformer", ["xfmr", "transformer", "trafo"]),
    (ComponentType.PI_CONTROLLER, "PI Controller", ["pi", "controller"]),
    (ComponentType.PID_CONTROLLER, "PID Controller", ["pid", "controller"]),
    (ComponentType.MATH_BLOCK, "Math Block", ["math", "gain", "sum"]),
    (ComponentType.PWM_GENERATOR, "PWM Generator", ["pwm", "pulse", "modulator"]),
    (ComponentType.ELECTRICAL_SCOPE, "Electrical Scope", ["scope", "probe", "measure"]),
    (ComponentType.THERMAL_SCOPE, "Thermal Scope", ["thermal", "temp", "temperature"]),
    (ComponentType.SIGNAL_MUX, "Signal Mux", ["mux", "multiplexer"]),
    (ComponentType.SIGNAL_DEMUX, "Signal Demux", ["demux", "demultiplexer"]),
]


class QuickAddDialog(QDialog):
    """Quick-add palette for fast component insertion (Cmd/Ctrl+K)."""

    component_selected = Signal(ComponentType)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Add Component")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Popup
        )
        self.setFixedWidth(400)
        self.setMaximumHeight(350)

        self._selected_type: ComponentType | None = None
        self._setup_ui()
        self._apply_styles()
        self._populate_list()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 12, 12, 8)

        # Search icon
        icon_label = QLabel()
        icon = IconService.get_icon("search", "#9ca3af")
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(16, 16))
        header_layout.addWidget(icon_label)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search components...")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.returnPressed.connect(self._on_select)
        header_layout.addWidget(self._search_input)

        layout.addWidget(header)

        # Results list
        self._results_list = QListWidget()
        self._results_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._results_list.itemClicked.connect(self._on_item_clicked)
        self._results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._results_list)

        # Hint footer
        hint = QLabel("↑↓ Navigate • Enter Select • Esc Cancel")
        hint.setStyleSheet("color: #9ca3af; font-size: 10px; padding: 8px 12px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        # Connect keyboard navigation
        self._search_input.installEventFilter(self)

    def _apply_styles(self) -> None:
        """Apply modern styling."""
        self.setStyleSheet("""
            QuickAddDialog {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
            QLineEdit {
                border: none;
                font-size: 14px;
                padding: 4px;
                background: transparent;
            }
            QListWidget {
                border: none;
                border-top: 1px solid #f3f4f6;
                background-color: #ffffff;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid #f9fafb;
            }
            QListWidget::item:selected {
                background-color: #eff6ff;
                color: #1d4ed8;
            }
            QListWidget::item:hover {
                background-color: #f9fafb;
            }
        """)

    def _populate_list(self, filter_text: str = "") -> None:
        """Populate the results list with matching components."""
        self._results_list.clear()
        filter_lower = filter_text.lower().strip()

        for comp_type, display_name, keywords in COMPONENT_DATA:
            # Check if matches filter
            if filter_lower:
                match = False
                if filter_lower in display_name.lower():
                    match = True
                else:
                    for kw in keywords:
                        if filter_lower in kw:
                            match = True
                            break
                if not match:
                    continue

            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, comp_type)
            self._results_list.addItem(item)

        # Select first item if any
        if self._results_list.count() > 0:
            self._results_list.setCurrentRow(0)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._populate_list(text)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle item click."""
        self._results_list.setCurrentItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle item double-click."""
        self._select_item(item)

    def _on_select(self) -> None:
        """Handle selection (Enter key)."""
        item = self._results_list.currentItem()
        if item:
            self._select_item(item)

    def _select_item(self, item: QListWidgetItem) -> None:
        """Select a component and emit signal."""
        comp_type = item.data(Qt.ItemDataRole.UserRole)
        if comp_type:
            self._selected_type = comp_type
            self.component_selected.emit(comp_type)
            self.accept()

    def eventFilter(self, obj, event) -> bool:
        """Handle keyboard navigation."""
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        if obj is self._search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                current = self._results_list.currentRow()
                if current < self._results_list.count() - 1:
                    self._results_list.setCurrentRow(current + 1)
                return True
            elif key == Qt.Key.Key_Up:
                current = self._results_list.currentRow()
                if current > 0:
                    self._results_list.setCurrentRow(current - 1)
                return True
            elif key == Qt.Key.Key_Escape:
                self.reject()
                return True

        return super().eventFilter(obj, event)

    def selected_component(self) -> ComponentType | None:
        """Get the selected component type."""
        return self._selected_type

    def showEvent(self, event) -> None:
        """Focus search input when shown."""
        super().showEvent(event)
        self._search_input.setFocus()
        self._search_input.selectAll()


class QWidget:
    """Placeholder to avoid import issues."""
    pass


# Re-import correctly
from PySide6.QtWidgets import QWidget
