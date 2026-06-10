"""Parameter Tuner — slider mapping, change signals, debounced auto-run."""
from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.tuning_panel import TuningPanel, _SLIDER_STEPS


def _circuit() -> Circuit:
    circuit = Circuit(name="t")
    r = Component(type=ComponentType.RESISTOR, name="R1")
    r.parameters["resistance"] = 100.0
    circuit.add_component(r)
    return circuit


def test_slider_log_mapping() -> None:
    assert abs(TuningPanel.slider_to_value(100.0, _SLIDER_STEPS // 2) - 100.0) < 1e-9
    assert abs(TuningPanel.slider_to_value(100.0, 0) - 20.0) < 1e-9       # /5
    assert abs(TuningPanel.slider_to_value(100.0, _SLIDER_STEPS) - 500.0) < 1e-9  # ×5


def test_add_parameter_and_change_emits(qapp) -> None:
    circuit = _circuit()
    comp = next(iter(circuit.components.values()))
    panel = TuningPanel(circuit_provider=lambda: circuit, debounce_ms=1)
    changes: list[tuple[str, str, float]] = []
    panel.parameter_changed.connect(
        lambda cid, p, v: changes.append((cid, p, v)))
    try:
        panel.add_parameter(str(comp.id), comp.name, "resistance", 100.0)
        assert len(panel._rows) == 1
        # duplicate add is a no-op
        panel.add_parameter(str(comp.id), comp.name, "resistance", 100.0)
        assert len(panel._rows) == 1
        # dragging the slider emits the mapped value
        slider = panel._rows[0].widgets[1]
        slider.setValue(_SLIDER_STEPS)
        assert changes
        cid, pname, value = changes[-1]
        assert cid == str(comp.id) and pname == "resistance"
        assert abs(value - 500.0) < 1e-6
    finally:
        panel.deleteLater()


def test_auto_run_debounce_fires_once(qapp) -> None:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    circuit = _circuit()
    comp = next(iter(circuit.components.values()))
    panel = TuningPanel(circuit_provider=lambda: circuit, debounce_ms=10)
    runs: list[bool] = []
    panel.run_requested.connect(lambda: runs.append(True))
    try:
        panel.add_parameter(str(comp.id), comp.name, "resistance", 100.0)
        slider = panel._rows[0].widgets[1]
        # several rapid movements within the debounce window…
        for step in (600, 700, 800, 900):
            slider.setValue(step)
        # …let the debounce timer fire
        loop = QEventLoop()
        QTimer.singleShot(60, loop.quit)
        loop.exec()
        QCoreApplication.processEvents()
        assert len(runs) == 1                  # one rerun for the whole drag
        # auto-run off ⇒ silent
        panel.auto_run.setChecked(False)
        slider.setValue(100)
        QTimer.singleShot(40, loop.quit)
        loop.exec()
        assert len(runs) == 1
    finally:
        panel.deleteLater()


def test_remove_row(qapp) -> None:
    circuit = _circuit()
    comp = next(iter(circuit.components.values()))
    panel = TuningPanel(circuit_provider=lambda: circuit)
    try:
        panel.add_parameter(str(comp.id), comp.name, "resistance", 100.0)
        row = panel._rows[0]
        panel._remove(row)
        assert panel._rows == []
    finally:
        panel.deleteLater()
