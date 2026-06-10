"""Parameter Tuner — bench-style sliders with auto-rerun (PSIM free-run-ish).

True free-run (mutating parameters while the kernel integrates) needs kernel
support pulsim does not expose; what delivers the same bench experience for
the typical millisecond-scale run is: drag a slider → the parameter lands on
the model (undoable) → the transient re-runs automatically (debounced) → the
scopes refresh. Iteration feels live for short runs.

Each row: component.parameter, a slider sweeping ×0.2 … ×5 of the value the
row was added with (log scale — component values are ratio-ish quantities),
and a spinbox for exact entry.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

_SLIDER_STEPS = 1000
_RATIO = 5.0          # slider sweeps value/RATIO … value*RATIO


@dataclass
class _Row:
    component_id: str
    component_name: str
    param_name: str
    base_value: float
    widgets: list


class TuningPanel(QWidget):
    """Dockable tuner: rows of (component.param, slider, spinbox)."""

    parameter_changed = Signal(str, str, float)   # component_id, param, value
    run_requested = Signal()

    def __init__(self, parent=None, *, circuit_provider=None,
                 debounce_ms: int = 400) -> None:
        super().__init__(parent)
        self._circuit_provider = circuit_provider
        self._rows: list[_Row] = []

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self._add_btn = QPushButton("+ Add parameter")
        self._add_btn.clicked.connect(self._on_add)
        top.addWidget(self._add_btn)
        self.auto_run = QCheckBox("Auto-run")
        self.auto_run.setChecked(True)
        self.auto_run.setToolTip(
            "Re-run the transient automatically after each change "
            "(debounced) so the scopes follow the slider.")
        top.addWidget(self.auto_run)
        top.addStretch(1)
        root.addLayout(top)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 4, 0, 4)
        self._grid.setHorizontalSpacing(8)
        root.addWidget(self._grid_host)
        root.addStretch(1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._fire_run)

    # ── rows ────────────────────────────────────────────────────────────

    def add_parameter(self, component_id: str, component_name: str,
                      param_name: str, value: float) -> None:
        """Add one tuning row (no-op when the pair is already tuned)."""
        for row in self._rows:
            if (row.component_id == component_id
                    and row.param_name == param_name):
                return
        base = float(value) if value else 1.0

        label = QLabel(f"{component_name}.{param_name}")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, _SLIDER_STEPS)
        slider.setValue(_SLIDER_STEPS // 2)
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(-1e12, 1e12)
        spin.setValue(float(value))
        remove = QPushButton("✕")
        remove.setFixedWidth(28)

        r = self._grid.rowCount()
        self._grid.addWidget(label, r, 0)
        self._grid.addWidget(slider, r, 1)
        self._grid.addWidget(spin, r, 2)
        self._grid.addWidget(remove, r, 3)
        self._grid.setColumnStretch(1, 1)

        row = _Row(component_id, component_name, param_name, base,
                   [label, slider, spin, remove])
        self._rows.append(row)

        slider.valueChanged.connect(
            lambda step, rw=row, sp=spin: self._on_slider(rw, sp, step))
        spin.valueChanged.connect(
            lambda v, rw=row: self._apply(rw, float(v)))
        remove.clicked.connect(lambda _=False, rw=row: self._remove(rw))

    @staticmethod
    def slider_to_value(base: float, step: int) -> float:
        """Log map: step 0 → base/RATIO, mid → base, max → base*RATIO."""
        frac = step / _SLIDER_STEPS                      # 0..1
        return base * math.pow(_RATIO, 2.0 * frac - 1.0)

    def _on_slider(self, row: _Row, spin: QDoubleSpinBox, step: int) -> None:
        value = self.slider_to_value(row.base_value, step)
        spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(False)
        self._apply(row, value)

    def _apply(self, row: _Row, value: float) -> None:
        self.parameter_changed.emit(row.component_id, row.param_name, value)
        if self.auto_run.isChecked():
            self._debounce.start()

    def _fire_run(self) -> None:
        self.run_requested.emit()

    def _remove(self, row: _Row) -> None:
        if row not in self._rows:
            return
        self._rows.remove(row)
        for w in row.widgets:
            w.setParent(None)
            w.deleteLater()

    # ── add-parameter dialog ────────────────────────────────────────────

    def _on_add(self) -> None:
        circuit = self._circuit_provider() if callable(self._circuit_provider) else None
        if circuit is None:
            return
        dialog = _AddParameterDialog(circuit, self)
        if dialog.exec() and dialog.selection:
            self.add_parameter(*dialog.selection)


class _AddParameterDialog(QDialog):
    """Pick (component, numeric parameter) to tune."""

    def __init__(self, circuit, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add parameter to tuner")
        self.selection: tuple[str, str, str, float] | None = None
        self._components = {
            str(c.id): c for c in circuit.components.values()
            if any(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in (getattr(c, "parameters", {}) or {}).values())
        }

        form = QFormLayout(self)
        self._comp = QComboBox()
        for cid, comp in sorted(self._components.items(),
                                key=lambda kv: kv[1].name):
            self._comp.addItem(comp.name, cid)
        form.addRow("Component", self._comp)

        self._param = QComboBox()
        form.addRow("Parameter", self._param)
        self._comp.currentIndexChanged.connect(self._refill_params)
        self._refill_params()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _refill_params(self, *_args) -> None:
        self._param.clear()
        cid = self._comp.currentData()
        comp = self._components.get(cid)
        if comp is None:
            return
        for key, value in sorted((comp.parameters or {}).items()):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self._param.addItem(f"{key} = {value:g}", (key, float(value)))

    def _on_ok(self) -> None:
        cid = self._comp.currentData()
        comp = self._components.get(cid)
        data = self._param.currentData()
        if comp is None or data is None:
            self.reject()
            return
        key, value = data
        self.selection = (cid, comp.name, key, value)
        self.accept()
