"""Waveform editor widgets for source components."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QGroupBox,
)

from pulsimgui.views.properties.properties_panel import SIValueWidget


class WaveformPreview(QWidget):
    """Widget to preview waveform shape."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 100)
        self._points: list[tuple[float, float]] = []
        self._x_range = (0, 1)
        self._y_range = (-1, 1)

    def set_waveform(self, points: list[tuple[float, float]]) -> None:
        """Set waveform points to display."""
        self._points = points
        if points:
            x_vals = [p[0] for p in points]
            y_vals = [p[1] for p in points]
            self._x_range = (min(x_vals), max(x_vals))
            y_min, y_max = min(y_vals), max(y_vals)
            margin = (y_max - y_min) * 0.1 or 0.5
            self._y_range = (y_min - margin, y_max + margin)
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the waveform preview."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(240, 240, 240))

        if not self._points:
            return

        # Draw grid
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        w, h = self.width(), self.height()
        for i in range(1, 4):
            y = h * i // 4
            painter.drawLine(0, y, w, y)
            x = w * i // 4
            painter.drawLine(x, 0, x, h)

        # Draw zero line
        y_zero = self._map_y(0)
        painter.setPen(QPen(QColor(150, 150, 150), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, y_zero, w, y_zero)

        # Draw waveform
        painter.setPen(QPen(QColor(0, 100, 200), 2))
        for i in range(len(self._points) - 1):
            x1 = self._map_x(self._points[i][0])
            y1 = self._map_y(self._points[i][1])
            x2 = self._map_x(self._points[i + 1][0])
            y2 = self._map_y(self._points[i + 1][1])
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _map_x(self, x: float) -> float:
        """Map x value to widget coordinate."""
        if self._x_range[1] == self._x_range[0]:
            return self.width() / 2
        return (x - self._x_range[0]) / (self._x_range[1] - self._x_range[0]) * self.width()

    def _map_y(self, y: float) -> float:
        """Map y value to widget coordinate (inverted)."""
        if self._y_range[1] == self._y_range[0]:
            return self.height() / 2
        return self.height() - (y - self._y_range[0]) / (self._y_range[1] - self._y_range[0]) * self.height()


class DCEditor(QWidget):
    """Editor for DC source."""

    value_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QFormLayout(self)

        self._value_edit = SIValueWidget("V")
        self._value_edit.value_changed.connect(self._on_value_changed)
        layout.addRow("Value:", self._value_edit)

    def set_waveform(self, waveform: dict) -> None:
        """Set waveform parameters."""
        self._value_edit.value = waveform.get("value", 0)

    def get_waveform(self) -> dict:
        """Get waveform parameters."""
        return {"type": "dc", "value": self._value_edit.value}

    def _on_value_changed(self) -> None:
        self.value_changed.emit(self.get_waveform())


class PulseEditor(QWidget):
    """Editor for pulse waveform."""

    value_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Parameters
        params_layout = QFormLayout()

        self._v1_edit = SIValueWidget("V")
        self._v1_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Initial (V1):", self._v1_edit)

        self._v2_edit = SIValueWidget("V")
        self._v2_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Pulsed (V2):", self._v2_edit)

        self._td_edit = SIValueWidget("s")
        self._td_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Delay (TD):", self._td_edit)

        self._tr_edit = SIValueWidget("s")
        self._tr_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Rise time (TR):", self._tr_edit)

        self._tf_edit = SIValueWidget("s")
        self._tf_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Fall time (TF):", self._tf_edit)

        self._pw_edit = SIValueWidget("s")
        self._pw_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Pulse width (PW):", self._pw_edit)

        self._per_edit = SIValueWidget("s")
        self._per_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Period (PER):", self._per_edit)

        layout.addLayout(params_layout)

        # Preview
        self._preview = WaveformPreview()
        layout.addWidget(self._preview)

    def set_waveform(self, waveform: dict) -> None:
        """Set waveform parameters."""
        self._v1_edit.value = waveform.get("v1", 0)
        self._v2_edit.value = waveform.get("v2", 5)
        self._td_edit.value = waveform.get("td", 0)
        self._tr_edit.value = waveform.get("tr", 1e-9)
        self._tf_edit.value = waveform.get("tf", 1e-9)
        self._pw_edit.value = waveform.get("pw", 50e-6)
        self._per_edit.value = waveform.get("per", 100e-6)
        self._update_preview()

    def get_waveform(self) -> dict:
        """Get waveform parameters."""
        return {
            "type": "pulse",
            "v1": self._v1_edit.value,
            "v2": self._v2_edit.value,
            "td": self._td_edit.value,
            "tr": self._tr_edit.value,
            "tf": self._tf_edit.value,
            "pw": self._pw_edit.value,
            "per": self._per_edit.value,
        }

    def _on_value_changed(self) -> None:
        self._update_preview()
        self.value_changed.emit(self.get_waveform())

    def _update_preview(self) -> None:
        """Update the waveform preview."""
        v1 = self._v1_edit.value
        v2 = self._v2_edit.value
        td = self._td_edit.value
        tr = max(self._tr_edit.value, 1e-12)
        tf = max(self._tf_edit.value, 1e-12)
        pw = self._pw_edit.value
        per = max(self._per_edit.value, td + tr + pw + tf)

        points = [
            (0, v1),
            (td, v1),
            (td + tr, v2),
            (td + tr + pw, v2),
            (td + tr + pw + tf, v1),
            (per, v1),
        ]
        self._preview.set_waveform(points)


class SineEditor(QWidget):
    """Editor for sine waveform."""

    value_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Parameters
        params_layout = QFormLayout()

        self._vo_edit = SIValueWidget("V")
        self._vo_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Offset (VO):", self._vo_edit)

        self._va_edit = SIValueWidget("V")
        self._va_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Amplitude (VA):", self._va_edit)

        self._freq_edit = SIValueWidget("Hz")
        self._freq_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Frequency:", self._freq_edit)

        self._td_edit = SIValueWidget("s")
        self._td_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Delay (TD):", self._td_edit)

        self._theta_edit = SIValueWidget("")
        self._theta_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Damping (θ):", self._theta_edit)

        self._phase_edit = SIValueWidget("°")
        self._phase_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Phase:", self._phase_edit)

        layout.addLayout(params_layout)

        # Preview
        self._preview = WaveformPreview()
        layout.addWidget(self._preview)

    def set_waveform(self, waveform: dict) -> None:
        """Set waveform parameters."""
        self._vo_edit.value = waveform.get("vo", 0)
        self._va_edit.value = waveform.get("va", 1)
        self._freq_edit.value = waveform.get("freq", 1000)
        self._td_edit.value = waveform.get("td", 0)
        self._theta_edit.value = waveform.get("theta", 0)
        self._phase_edit.value = waveform.get("phase", 0)
        self._update_preview()

    def get_waveform(self) -> dict:
        """Get waveform parameters."""
        return {
            "type": "sine",
            "vo": self._vo_edit.value,
            "va": self._va_edit.value,
            "freq": self._freq_edit.value,
            "td": self._td_edit.value,
            "theta": self._theta_edit.value,
            "phase": self._phase_edit.value,
        }

    def _on_value_changed(self) -> None:
        self._update_preview()
        self.value_changed.emit(self.get_waveform())

    def _update_preview(self) -> None:
        """Update the waveform preview."""
        import math

        vo = self._vo_edit.value
        va = self._va_edit.value
        freq = max(self._freq_edit.value, 1)
        phase = self._phase_edit.value * math.pi / 180

        period = 1 / freq
        points = []
        n_points = 100
        for i in range(n_points + 1):
            t = i * period * 2 / n_points
            v = vo + va * math.sin(2 * math.pi * freq * t + phase)
            points.append((t, v))

        self._preview.set_waveform(points)


class PWLEditor(QWidget):
    """Editor for piecewise linear waveform."""

    value_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Table for time-value pairs
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Time (s)", "Value (V)"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.cellChanged.connect(self._on_table_changed)
        layout.addWidget(self._table)

        # Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Point")
        add_btn.clicked.connect(self._add_point)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove Point")
        remove_btn.clicked.connect(self._remove_point)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Preview
        self._preview = WaveformPreview()
        layout.addWidget(self._preview)

    def set_waveform(self, waveform: dict) -> None:
        """Set waveform parameters."""
        points = waveform.get("points", [(0, 0), (1e-3, 1)])
        self._table.setRowCount(len(points))
        for i, (t, v) in enumerate(points):
            self._table.setItem(i, 0, QTableWidgetItem(f"{t}"))
            self._table.setItem(i, 1, QTableWidgetItem(f"{v}"))
        self._update_preview()

    def get_waveform(self) -> dict:
        """Get waveform parameters."""
        points = []
        for row in range(self._table.rowCount()):
            t_item = self._table.item(row, 0)
            v_item = self._table.item(row, 1)
            if t_item and v_item:
                try:
                    t = float(t_item.text())
                    v = float(v_item.text())
                    points.append((t, v))
                except ValueError:
                    pass
        return {"type": "pwl", "points": points}

    def _add_point(self) -> None:
        """Add a new point to the table."""
        row = self._table.rowCount()
        self._table.insertRow(row)
        last_t = 0
        if row > 0:
            item = self._table.item(row - 1, 0)
            if item:
                try:
                    last_t = float(item.text())
                except ValueError:
                    pass
        self._table.setItem(row, 0, QTableWidgetItem(f"{last_t + 1e-3}"))
        self._table.setItem(row, 1, QTableWidgetItem("0"))

    def _remove_point(self) -> None:
        """Remove selected point."""
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._update_preview()

    def _on_table_changed(self) -> None:
        self._update_preview()
        self.value_changed.emit(self.get_waveform())

    def _update_preview(self) -> None:
        """Update the waveform preview."""
        waveform = self.get_waveform()
        points = waveform.get("points", [])
        self._preview.set_waveform(points)


class PWMEditor(QWidget):
    """Editor for PWM waveform."""

    value_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Parameters
        params_layout = QFormLayout()

        self._vlow_edit = SIValueWidget("V")
        self._vlow_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Low level:", self._vlow_edit)

        self._vhigh_edit = SIValueWidget("V")
        self._vhigh_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("High level:", self._vhigh_edit)

        self._freq_edit = SIValueWidget("Hz")
        self._freq_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Frequency:", self._freq_edit)

        self._duty_edit = SIValueWidget("%")
        self._duty_edit.value_changed.connect(self._on_value_changed)
        params_layout.addRow("Duty cycle:", self._duty_edit)

        layout.addLayout(params_layout)

        # Preview
        self._preview = WaveformPreview()
        layout.addWidget(self._preview)

    def set_waveform(self, waveform: dict) -> None:
        """Set waveform parameters."""
        self._vlow_edit.value = waveform.get("vlow", 0)
        self._vhigh_edit.value = waveform.get("vhigh", 5)
        self._freq_edit.value = waveform.get("freq", 10000)
        self._duty_edit.value = waveform.get("duty", 50)
        self._update_preview()

    def get_waveform(self) -> dict:
        """Get waveform parameters."""
        return {
            "type": "pwm",
            "vlow": self._vlow_edit.value,
            "vhigh": self._vhigh_edit.value,
            "freq": self._freq_edit.value,
            "duty": self._duty_edit.value,
        }

    def _on_value_changed(self) -> None:
        self._update_preview()
        self.value_changed.emit(self.get_waveform())

    def _update_preview(self) -> None:
        """Update the waveform preview."""
        vlow = self._vlow_edit.value
        vhigh = self._vhigh_edit.value
        freq = max(self._freq_edit.value, 1)
        duty = min(max(self._duty_edit.value, 0), 100) / 100

        period = 1 / freq
        t_on = period * duty

        points = [
            (0, vhigh),
            (t_on, vhigh),
            (t_on, vlow),
            (period, vlow),
            (period, vhigh),
            (period + t_on, vhigh),
            (period + t_on, vlow),
            (2 * period, vlow),
        ]
        self._preview.set_waveform(points)


class WaveformEditorDialog(QDialog):
    """Dialog for editing source waveforms."""

    def __init__(self, waveform: dict, parent=None):
        super().__init__(parent)
        self._waveform = waveform.copy()

        self.setWindowTitle("Edit Waveform")
        self.setMinimumSize(400, 500)

        self._setup_ui()
        self._load_waveform()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Waveform type selector
        type_group = QGroupBox("Waveform Type")
        type_layout = QHBoxLayout(type_group)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["DC", "Pulse", "Sine", "PWL", "PWM"])
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self._type_combo)

        layout.addWidget(type_group)

        # Tab widget for editors
        self._tabs = QTabWidget()
        self._tabs.setTabBarAutoHide(True)

        self._dc_editor = DCEditor()
        self._pulse_editor = PulseEditor()
        self._sine_editor = SineEditor()
        self._pwl_editor = PWLEditor()
        self._pwm_editor = PWMEditor()

        self._tabs.addTab(self._dc_editor, "DC")
        self._tabs.addTab(self._pulse_editor, "Pulse")
        self._tabs.addTab(self._sine_editor, "Sine")
        self._tabs.addTab(self._pwl_editor, "PWL")
        self._tabs.addTab(self._pwm_editor, "PWM")

        layout.addWidget(self._tabs)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_waveform(self) -> None:
        """Load waveform into editors."""
        waveform_type = self._waveform.get("type", "dc").lower()

        type_index = {"dc": 0, "pulse": 1, "sine": 2, "pwl": 3, "pwm": 4}.get(
            waveform_type, 0
        )
        self._type_combo.setCurrentIndex(type_index)
        self._tabs.setCurrentIndex(type_index)

        # Set waveform in appropriate editor
        if waveform_type == "dc":
            self._dc_editor.set_waveform(self._waveform)
        elif waveform_type == "pulse":
            self._pulse_editor.set_waveform(self._waveform)
        elif waveform_type == "sine":
            self._sine_editor.set_waveform(self._waveform)
        elif waveform_type == "pwl":
            self._pwl_editor.set_waveform(self._waveform)
        elif waveform_type == "pwm":
            self._pwm_editor.set_waveform(self._waveform)

    def _on_type_changed(self, index: int) -> None:
        """Handle waveform type change."""
        self._tabs.setCurrentIndex(index)

    def get_waveform(self) -> dict:
        """Get the edited waveform."""
        index = self._type_combo.currentIndex()
        editors = [
            self._dc_editor,
            self._pulse_editor,
            self._sine_editor,
            self._pwl_editor,
            self._pwm_editor,
        ]
        return editors[index].get_waveform()
