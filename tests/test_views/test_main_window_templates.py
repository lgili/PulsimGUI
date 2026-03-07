"""Tests for MainWindow template project creation flow."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest

import pulsimgui.views.main_window as main_window_module
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType, set_thermal_port_enabled
from pulsimgui.models.project import Project
from pulsimgui.models.wire import Wire, WireSegment
from pulsimgui.services.backend_types import ConvergenceInfo
from pulsimgui.services.template_service import TemplateService
from pulsimgui.services.simulation_service import DCResult, SimulationResult, SimulationState
from pulsimgui.utils.net_utils import build_node_map
from pulsimgui.utils.signal_utils import format_signal_key
from pulsimgui.views.main_window import MainWindow
from pulsimgui.views.schematic.items import ComponentItem


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


def test_flyback_template_keeps_primary_and_output_nodes_after_scene_load(qapp) -> None:
    """Flyback template wiring should stay topologically valid after scene normalization."""

    project = TemplateService.create_project_from_template("flyback_converter")
    assert project is not None

    window = MainWindow()
    try:
        window._project = project
        window._load_project_to_scene()

        circuit = window._current_circuit()
        assert circuit is not None
        node_map = build_node_map(circuit)
        by_name = {component.name: component for component in circuit.components.values()}

        t1 = by_name["T1"]
        m1 = by_name["M1"]
        cout = by_name["Cout"]
        rload = by_name["Rload"]

        t1_primary_switch_node = node_map[(str(t1.id), 1)]  # P2
        t1_secondary_return = node_map[(str(t1.id), 3)]  # S2
        m1_drain_node = node_map[(str(m1.id), 0)]  # D
        cout_positive_node = node_map[(str(cout.id), 0)]  # +
        rload_positive_node = node_map[(str(rload.id), 0)]  # 1

        assert t1_primary_switch_node == m1_drain_node
        assert t1_primary_switch_node != "0"
        assert t1_secondary_return == "0"
        assert cout_positive_node == rload_positive_node
        assert cout_positive_node != "0"
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


def test_dc_finished_opens_results_dialog_with_parent_and_convergence_info(monkeypatch, qapp) -> None:
    """DC results dialog should receive convergence info and the window as parent."""
    captured: dict[str, object] = {}

    class _DialogStub:
        def __init__(self, result, convergence_info=None, parent=None) -> None:
            captured["result"] = result
            captured["convergence_info"] = convergence_info
            captured["parent"] = parent

        def exec(self) -> int:
            captured["exec_called"] = True
            return 0

    monkeypatch.setattr(main_window_module, "DCResultsDialog", _DialogStub)

    window = MainWindow()
    try:
        result = DCResult(node_voltages={"V(out)": 6.0})
        convergence_info = ConvergenceInfo(converged=True, iterations=4, final_residual=1e-12)
        window._simulation_service._last_convergence_info = convergence_info

        window._on_dc_finished(result)

        assert captured["result"] is result
        assert captured["convergence_info"] is convergence_info
        assert captured["parent"] is window
        assert captured["exec_called"] is True
    finally:
        window.close()


def test_delete_action_removes_selected_component_without_view_focus(monkeypatch, qapp) -> None:
    """Delete action should remove selected components even if focus moved away from scene."""
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        component = Component(type=ComponentType.RESISTOR, name="Rdel", x=0.0, y=0.0)
        circuit = window._current_circuit()
        circuit.add_component(component)
        window._schematic_scene.add_component(component)

        component_item = next(
            item
            for item in window._schematic_scene.items()
            if isinstance(item, ComponentItem) and item.component.id == component.id
        )
        component_item.setSelected(True)

        # Simulate typical focus loss from scene (common on Windows menus/docks).
        window._library_panel.setFocus()
        window.action_delete.trigger()

        assert circuit.get_component(component.id) is None
    finally:
        window.close()


def test_delete_action_ignored_while_typing_in_text_input(monkeypatch, qapp) -> None:
    """Delete shortcut must not remove components while user edits text fields."""
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        monkeypatch.setattr(window, "_has_text_input_focus", lambda: True)
        component = Component(type=ComponentType.RESISTOR, name="Rguard", x=0.0, y=0.0)
        circuit = window._current_circuit()
        circuit.add_component(component)
        window._schematic_scene.add_component(component)

        component_item = next(
            item
            for item in window._schematic_scene.items()
            if isinstance(item, ComponentItem) and item.component.id == component.id
        )
        component_item.setSelected(True)

        window.action_delete.trigger()

        assert circuit.get_component(component.id) is not None
    finally:
        window.close()


def test_schematic_view_delete_handles_keypad_modifier(monkeypatch, qapp) -> None:
    """Delete via numpad key should remove selected items."""
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        component = Component(type=ComponentType.RESISTOR, name="Rkeypad", x=0.0, y=0.0)
        circuit = window._current_circuit()
        circuit.add_component(component)
        window._schematic_scene.add_component(component)

        component_item = next(
            item
            for item in window._schematic_scene.items()
            if isinstance(item, ComponentItem) and item.component.id == component.id
        )
        component_item.setSelected(True)

        window._schematic_view.setFocus()
        window._schematic_view.viewport().setFocus()
        QTest.keyClick(
            window._schematic_view.viewport(),
            Qt.Key.Key_Delete,
            Qt.KeyboardModifier.KeypadModifier,
        )

        assert circuit.get_component(component.id) is None
    finally:
        window.close()


def test_edit_actions_forward_to_schematic_view_when_not_typing(monkeypatch, qapp) -> None:
    """Cut/copy/paste/delete/select-all actions should dispatch to schematic view."""
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        monkeypatch.setattr(window, "_has_text_input_focus", lambda: False)

        calls: list[str] = []
        monkeypatch.setattr(window._schematic_view, "cut_selected", lambda: calls.append("cut"))
        monkeypatch.setattr(window._schematic_view, "copy_selected", lambda: calls.append("copy"))
        monkeypatch.setattr(window._schematic_view, "paste_at_cursor", lambda: calls.append("paste"))
        monkeypatch.setattr(window._schematic_view, "delete_selected_items", lambda: calls.append("delete"))
        monkeypatch.setattr(window._schematic_view, "select_all_items", lambda: calls.append("select_all"))

        window.action_cut.trigger()
        window.action_copy.trigger()
        window.action_paste.trigger()
        window.action_delete.trigger()
        window.action_select_all.trigger()

        assert calls == ["cut", "copy", "paste", "delete", "select_all"]
    finally:
        window.close()


def test_edit_actions_ignored_when_typing(monkeypatch, qapp) -> None:
    """Cut/copy/paste/delete/select-all should be ignored while text input has focus."""
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        monkeypatch.setattr(window, "_has_text_input_focus", lambda: True)

        for method_name in (
            "cut_selected",
            "copy_selected",
            "paste_at_cursor",
            "delete_selected_items",
            "select_all_items",
        ):
            monkeypatch.setattr(
                window._schematic_view,
                method_name,
                lambda method_name=method_name: (_ for _ in ()).throw(
                    AssertionError(f"{method_name} should not be called")
                ),
            )

        window.action_cut.trigger()
        window.action_copy.trigger()
        window.action_paste.trigger()
        window.action_delete.trigger()
        window.action_select_all.trigger()
    finally:
        window.close()


@pytest.mark.parametrize(
    ("action_name", "key", "modifiers"),
    [
        ("action_rename_signal", Qt.Key.Key_F2, Qt.KeyboardModifier.NoModifier),
        ("action_run", Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier),
        ("action_stop", Qt.Key.Key_F5, Qt.KeyboardModifier.ShiftModifier),
        ("action_dc_op", Qt.Key.Key_F6, Qt.KeyboardModifier.NoModifier),
        ("action_ac", Qt.Key.Key_F7, Qt.KeyboardModifier.NoModifier),
        ("action_pause", Qt.Key.Key_F8, Qt.KeyboardModifier.NoModifier),
    ],
)
def test_function_shortcuts_trigger_expected_actions(
    monkeypatch,
    qapp,
    action_name: str,
    key: Qt.Key,
    modifiers: Qt.KeyboardModifier,
) -> None:
    """Function-key shortcuts should trigger their corresponding actions."""
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        action = getattr(window, action_name)

        # Isolate the shortcut trigger check from business-logic side effects.
        action.triggered.disconnect()
        fired: list[bool] = []
        action.triggered.connect(lambda *_: fired.append(True))
        action.setEnabled(True)

        window.show()
        window.activateWindow()
        window.setFocus()
        qapp.processEvents()
        QTest.keyClick(window, key, modifiers)
        qapp.processEvents()

        assert fired == [True]
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
