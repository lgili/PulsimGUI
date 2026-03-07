"""Tests for MainWindow template project creation flow."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

import pulsimgui.views.main_window as main_window_module
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType, set_thermal_port_enabled
from pulsimgui.models.project import Project
from pulsimgui.models.wire import Wire, WireSegment
from pulsimgui.services.simulation_service import SimulationResult, SimulationState
from pulsimgui.utils.signal_utils import format_signal_key
from pulsimgui.views.main_window import MainWindow


def test_on_new_from_template_uses_project_circuits_mapping(monkeypatch, qapp) -> None:
    """Template flow should populate Project.circuits with the generated circuit."""

    template_circuit = Circuit(name="Template Circuit")

    class _TemplateDialogStub:
        def __init__(self, parent=None) -> None:
            self._selected_template_id = "buck_converter"

        def exec(self) -> bool:
            return True

        def get_selected_template_id(self) -> str:
            return self._selected_template_id

    monkeypatch.setattr(main_window_module, "TemplateDialog", _TemplateDialogStub)
    monkeypatch.setattr(
        main_window_module.TemplateService,
        "create_project_from_template",
        staticmethod(lambda _template_id: None),
    )
    monkeypatch.setattr(
        main_window_module.TemplateService,
        "create_circuit_from_template",
        staticmethod(lambda _template_id: template_circuit),
    )

    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        window._on_new_from_template()

        assert window._project.circuits["main"] is template_circuit
        assert window._project.active_circuit == "main"
        assert window._project.name == "Template Circuit"
        assert window._project.is_dirty
    finally:
        window.close()


def test_on_new_from_template_loads_project_simulation_settings(monkeypatch, qapp) -> None:
    """Template flow should load project settings when template provides a full project."""

    template_project = Project(name="Template Project")
    template_project.simulation_settings.tstop = 0.012
    template_project.simulation_settings.dt = 3e-6
    template_project.simulation_settings.max_iterations = 77

    class _TemplateDialogStub:
        def __init__(self, parent=None) -> None:
            self._selected_template_id = "buck_converter_closed_loop"

        def exec(self) -> bool:
            return True

        def get_selected_template_id(self) -> str:
            return self._selected_template_id

    monkeypatch.setattr(main_window_module, "TemplateDialog", _TemplateDialogStub)
    monkeypatch.setattr(
        main_window_module.TemplateService,
        "create_project_from_template",
        staticmethod(lambda _template_id: template_project),
    )
    monkeypatch.setattr(
        main_window_module.TemplateService,
        "create_circuit_from_template",
        staticmethod(lambda _template_id: None),
    )

    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        window._on_new_from_template()

        assert window._project is template_project
        assert window._project.path is None
        assert window._project.simulation_settings.tstop == 0.012
        assert window._project.simulation_settings.dt == 3e-6
        assert window._project.simulation_settings.max_iterations == 77
        assert window._simulation_service.settings.t_stop == 0.012
        assert window._simulation_service.settings.t_step == 3e-6
        assert window._simulation_service.settings.max_newton_iterations == 77
    finally:
        window.close()


def test_open_project_file_syncs_saved_simulation_settings(monkeypatch, qapp, tmp_path) -> None:
    """Opening a saved project should immediately sync persisted settings to runtime service."""

    saved = Project(name="Saved Project")
    saved.simulation_settings.tstop = 0.02
    saved.simulation_settings.dt = 5e-6
    saved.simulation_settings.max_step = 5e-6
    saved.simulation_settings.max_iterations = 88
    saved_path = tmp_path / "saved_project.pulsim"
    saved.save(saved_path)

    window = MainWindow()
    try:
        monkeypatch.setattr(window._settings, "add_recent_project", lambda _path: None)
        monkeypatch.setattr(window, "_update_recent_menu", lambda: None)
        window._open_project_file(str(saved_path))

        assert window._project.simulation_settings.tstop == 0.02
        assert window._project.simulation_settings.dt == 5e-6
        assert window._simulation_service.settings.t_stop == 0.02
        assert window._simulation_service.settings.t_step == 5e-6
        assert window._simulation_service.settings.max_newton_iterations == 88
    finally:
        window.close()


def test_waveform_dock_starts_hidden(qapp) -> None:
    """Waveform panel should not open by default on startup."""
    window = MainWindow()
    try:
        assert window.waveform_dock.isHidden()
        assert not window.waveform_dock.toggleViewAction().isChecked()
    finally:
        window.close()


def test_apply_theme_updates_qt_palette(qapp) -> None:
    """Applying a theme should update base Qt palette roles."""
    window = MainWindow()
    try:
        window._set_theme("light")
        colors = window._theme_service.current_theme.colors
        palette = qapp.palette()
        assert palette.color(QPalette.ColorRole.Window).name().lower() == QColor(colors.background).name().lower()
        assert palette.color(QPalette.ColorRole.Base).name().lower() == QColor(colors.input_background).name().lower()
    finally:
        window.close()


def test_thermal_scope_uses_transient_telemetry_without_secondary_backend_call(
    monkeypatch, qapp
) -> None:
    """Thermal scope should not synthesize sampled traces from summary-only telemetry."""

    window = MainWindow()
    try:
        circuit = window._current_circuit()
        circuit.add_component(Component(type=ComponentType.MOSFET_N, name="M1"))

        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={},
            statistics={
                "thermal_summary": {
                    "enabled": True,
                    "ambient": 25.0,
                    "device_temperatures": [
                        {"device_name": "M1", "final_temperature": 55.0},
                    ],
                },
            },
        )

        def _should_not_call(*_args, **_kwargs):
            raise AssertionError("thermal backend should not be called for telemetry-backed scope")

        monkeypatch.setattr(window._thermal_service, "build_result", _should_not_call)

        waveform = window._ensure_thermal_waveform()
        assert waveform is None
    finally:
        window.close()


def test_simulation_progress_resets_on_retry_message(qapp) -> None:
    """Retry progress updates should not stay clamped at previous high percentages."""
    window = MainWindow()
    try:
        window._on_simulation_state_changed(SimulationState.RUNNING)
        window._on_simulation_progress(95.0, "Transient failed at t=0.0001")
        assert window._sim_progress.value() == 95

        window._on_simulation_progress(2.0, "Retrying convergence with profile 'gmin-seed'...")
        assert window._sim_progress.value() == 2
    finally:
        window.close()


def test_simulation_progress_keeps_value_for_indeterminate_updates(qapp) -> None:
    """Indeterminate backend callbacks should preserve last determinate progress value."""
    window = MainWindow()
    try:
        window._on_simulation_state_changed(SimulationState.RUNNING)
        window._on_simulation_progress(40.0, "Running transient with SimulationOptions...")
        assert window._sim_progress.value() == 40

        window._on_simulation_progress(-1.0, "Simulating circuit...")
        assert window._sim_progress.value() == 40
    finally:
        window.close()


def test_thermal_scope_prefers_sampled_thermal_channels_from_transient(qapp) -> None:
    """Sampled T(...) channels from transient output should be reused as-is."""

    window = MainWindow()
    try:
        key = format_signal_key("T", "M1")
        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3, 2e-3],
            signals={key: [26.0, 31.0, 37.5]},
            statistics={},
        )

        waveform = window._ensure_thermal_waveform()
        assert waveform is not None
        assert waveform.signals[key] == [26.0, 31.0, 37.5]
    finally:
        window.close()


def _connect_pins(
    circuit: Circuit,
    left: Component,
    left_pin: int,
    right: Component,
    right_pin: int,
) -> None:
    x1, y1 = left.get_pin_position(left_pin)
    x2, y2 = right.get_pin_position(right_pin)
    circuit.add_wire(Wire(segments=[WireSegment(x1, y1, x2, y2)]))


def test_thermal_scope_maps_scope_virtual_channel_to_component_binding(monkeypatch, qapp) -> None:
    """Thermal scope channels keyed by scope name should map to connected T(component) keys."""

    window = MainWindow()
    try:
        circuit = window._current_circuit()
        resistor = Component(type=ComponentType.RESISTOR, name="R1", x=100.0, y=100.0)
        set_thermal_port_enabled(resistor, True)
        scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1", x=220.0, y=109.0)
        circuit.add_component(resistor)
        circuit.add_component(scope)
        _connect_pins(circuit, resistor, 2, scope, 0)

        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={"TS1": [35.0, 42.0]},
            statistics={},
        )

        def _should_not_call(*_args, **_kwargs):
            raise AssertionError("thermal backend should not be called for thermal-scope telemetry")

        monkeypatch.setattr(window._thermal_service, "build_result", _should_not_call)

        waveform = window._ensure_thermal_waveform()
        key = format_signal_key("T", "R1")
        assert waveform is not None
        assert key in waveform.signals
        assert waveform.signals[key] == [35.0, 42.0]
    finally:
        window.close()


def test_thermal_scope_maps_wrapped_scope_channel_to_component_binding(monkeypatch, qapp) -> None:
    """Wrapped channels like V(TS1) should resolve to connected thermal bindings."""

    window = MainWindow()
    try:
        circuit = window._current_circuit()
        resistor = Component(type=ComponentType.RESISTOR, name="R1", x=100.0, y=100.0)
        set_thermal_port_enabled(resistor, True)
        scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1", x=220.0, y=109.0)
        circuit.add_component(resistor)
        circuit.add_component(scope)
        _connect_pins(circuit, resistor, 2, scope, 0)

        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={"V(TS1)": [36.0, 43.0]},
            statistics={},
        )

        def _should_not_call(*_args, **_kwargs):
            raise AssertionError("thermal backend should not be called for thermal-scope telemetry")

        monkeypatch.setattr(window._thermal_service, "build_result", _should_not_call)

        waveform = window._ensure_thermal_waveform()
        key = format_signal_key("T", "R1")
        assert waveform is not None
        assert key in waveform.signals
        assert waveform.signals[key] == [36.0, 43.0]
    finally:
        window.close()


def test_thermal_scope_accepts_tj_prefixed_channels(qapp) -> None:
    """TJ(...) backend channels should be aliased to canonical T(...) keys."""

    window = MainWindow()
    try:
        circuit = window._current_circuit()
        circuit.add_component(Component(type=ComponentType.MOSFET_N, name="M1"))

        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={"TJ(M1)": [27.0, 49.5]},
            statistics={},
        )

        waveform = window._ensure_thermal_waveform()
        key = format_signal_key("T", "M1")
        assert waveform is not None
        assert key in waveform.signals
        assert waveform.signals[key] == [27.0, 49.5]
    finally:
        window.close()


def test_thermal_scope_accepts_underscore_tj_channels(qapp) -> None:
    """TJ_<name> backend channels should be aliased to canonical T(...) keys."""

    window = MainWindow()
    try:
        circuit = window._current_circuit()
        circuit.add_component(Component(type=ComponentType.MOSFET_N, name="M1"))

        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={"TJ_M1": [28.0, 50.0]},
            statistics={},
        )

        waveform = window._ensure_thermal_waveform()
        key = format_signal_key("T", "M1")
        assert waveform is not None
        assert key in waveform.signals
        assert waveform.signals[key] == [28.0, 50.0]
    finally:
        window.close()


def test_thermal_scope_uses_virtual_channel_metadata_for_thermal_domain(qapp) -> None:
    """Thermal domain metadata should map non-canonical keys to T(component)."""

    window = MainWindow()
    try:
        circuit = window._current_circuit()
        circuit.add_component(Component(type=ComponentType.MOSFET_N, name="M1"))

        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={"thermal:trace:1": [25.2, 26.1]},
            statistics={
                "virtual_channel_metadata": {
                    "thermal:trace:1": {
                        "domain": "thermal",
                        "component_type": "thermal_trace",
                        "source_component": "M1",
                        "unit": "degC",
                    }
                }
            },
        )

        waveform = window._ensure_thermal_waveform()
        key = format_signal_key("T", "M1")
        assert waveform is not None
        assert key in waveform.signals
        assert waveform.signals[key] == [25.2, 26.1]
    finally:
        window.close()


def test_thermal_scope_without_transient_telemetry_does_not_call_secondary_backend(
    monkeypatch, qapp
) -> None:
    """Thermal scope should not trigger separate thermal backend runs."""

    window = MainWindow()
    try:
        window._latest_electrical_result = SimulationResult(
            time=[0.0, 1e-3],
            signals={"V(OUT)": [0.0, 1.0]},
            statistics={},
        )

        def _should_not_call(*_args, **_kwargs):
            raise AssertionError("secondary thermal backend path must not be called")

        monkeypatch.setattr(window._thermal_service, "build_result", _should_not_call)

        waveform = window._ensure_thermal_waveform()
        assert waveform is None
    finally:
        window.close()
