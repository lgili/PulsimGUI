"""Tests for SimulationService runtime backend provisioning integration."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.backend_runtime_service import (
    DEFAULT_BACKEND_TARGET_VERSION,
    BackendInstallResult,
    BackendRuntimeConfig,
)
from pulsimgui.services.simulation_service import (
    SimulationResult,
    SimulationService,
    SimulationSettings,
    SimulationState,
    SimulationWorker,
)


class _DummyBackend:
    def __init__(self) -> None:
        self.info = BackendInfo(
            identifier="placeholder",
            name="Demo",
            version="0.0",
            status="error",
            message="Demo mode",
        )

    def has_capability(self, name: str) -> bool:
        return False


class _DummyLoader:
    def __init__(self, preferred_backend_id: str | None = None) -> None:
        self.backend = _DummyBackend()
        self.available_backends = [self.backend.info]
        self.active_backend_id = self.backend.info.identifier

    def activate(self, identifier: str):
        if identifier != "placeholder":
            raise ValueError(identifier)
        return self.backend.info


@dataclass
class _FakeSettingsService:
    sim_settings: dict | None = None
    solver_settings: dict | None = None
    runtime_settings: dict | None = None
    backend_preference: str | None = None

    def get_backend_preference(self):
        return self.backend_preference

    def set_backend_preference(self, identifier):
        self.backend_preference = identifier

    def get_simulation_settings(self):
        return {}

    def get_solver_settings(self):
        return self.solver_settings or {}

    def get_backend_runtime_settings(self):
        return self.runtime_settings or {}

    def set_simulation_settings(self, settings: dict):
        self.sim_settings = settings

    def set_solver_settings(self, settings: dict):
        self.solver_settings = settings

    def set_backend_runtime_settings(self, settings: dict):
        self.runtime_settings = settings


def test_settings_assignment_persists_simulation_and_solver(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    fake_settings = _FakeSettingsService()
    service = SimulationService(settings_service=fake_settings)

    service.settings = SimulationSettings(
        t_stop=5e-3,
        t_step=2e-6,
        solver="rk45",
        max_step=5e-6,
        rel_tol=1e-5,
        abs_tol=1e-8,
        output_points=5000,
        max_newton_iterations=80,
        enable_voltage_limiting=False,
        max_voltage_step=7.5,
        dc_strategy="gmin",
        gmin_initial=1e-2,
        gmin_final=1e-13,
        dc_source_steps=21,
        transient_robust_mode=False,
        transient_auto_regularize=False,
        enable_losses=False,
        thermal_ambient=37.5,
        thermal_include_switching_losses=False,
        thermal_include_conduction_losses=True,
        thermal_network="cauer",
        thermal_policy="loss_only",
        thermal_default_rth=2.5,
        thermal_default_cth=0.4,
        formulation_mode="direct",
        direct_formulation_fallback=False,
        control_mode="discrete",
        control_sample_time=2e-6,
    )

    assert fake_settings.sim_settings is not None
    assert fake_settings.sim_settings["t_stop"] == 5e-3
    assert fake_settings.sim_settings["solver"] == "trapezoidal"
    assert fake_settings.sim_settings["output_points"] == 5000
    assert fake_settings.sim_settings["enable_losses"] is False

    assert fake_settings.solver_settings is not None
    assert fake_settings.solver_settings["max_newton_iterations"] == 80
    assert fake_settings.solver_settings["dc_strategy"] == "gmin"
    assert fake_settings.solver_settings["dc_source_steps"] == 21
    assert fake_settings.solver_settings["transient_robust_mode"] is False
    assert fake_settings.solver_settings["transient_auto_regularize"] is False
    assert fake_settings.solver_settings["thermal_ambient"] == 37.5
    assert fake_settings.solver_settings["thermal_include_switching_losses"] is False
    assert fake_settings.solver_settings["thermal_include_conduction_losses"] is True
    assert fake_settings.solver_settings["thermal_network"] == "cauer"
    assert fake_settings.solver_settings["thermal_policy"] == "loss_only"
    assert fake_settings.solver_settings["thermal_default_rth"] == 2.5
    assert fake_settings.solver_settings["thermal_default_cth"] == 0.4
    assert fake_settings.solver_settings["formulation_mode"] == "direct"
    assert fake_settings.solver_settings["direct_formulation_fallback"] is False
    assert fake_settings.solver_settings["control_mode"] == "discrete"
    assert fake_settings.solver_settings["control_sample_time"] == 2e-6


def test_solver_settings_loaded_without_forcing_voltage_limiting_off(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    fake_settings = _FakeSettingsService(
        solver_settings={
            "enable_voltage_limiting": True,
            "dc_source_steps": 33,
            "transient_robust_mode": False,
            "transient_auto_regularize": False,
            "thermal_ambient": 30.0,
            "thermal_include_switching_losses": False,
            "thermal_include_conduction_losses": False,
            "thermal_network": "cauer",
            "thermal_policy": "loss_only",
            "thermal_default_rth": 1.8,
            "thermal_default_cth": 0.22,
            "formulation_mode": "direct",
            "direct_formulation_fallback": False,
            "control_mode": "discrete",
            "control_sample_time": 1e-6,
        }
    )
    service = SimulationService(settings_service=fake_settings)

    assert service.settings.enable_voltage_limiting is True
    assert service.settings.dc_source_steps == 33
    assert service.settings.transient_robust_mode is False
    assert service.settings.transient_auto_regularize is False
    assert service.settings.thermal_ambient == 30.0
    assert service.settings.thermal_include_switching_losses is False
    assert service.settings.thermal_include_conduction_losses is False
    assert service.settings.thermal_network == "cauer"
    assert service.settings.thermal_policy == "loss_only"
    assert service.settings.thermal_default_rth == 1.8
    assert service.settings.thermal_default_cth == 0.22
    assert service.settings.formulation_mode == "direct"
    assert service.settings.direct_formulation_fallback is False
    assert service.settings.control_mode == "discrete"
    assert service.settings.control_sample_time == 1e-6


def test_default_runtime_target_version_loaded_when_settings_empty(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    fake_settings = _FakeSettingsService(runtime_settings={})
    service = SimulationService(settings_service=fake_settings)

    assert service.backend_runtime_config.target_version == DEFAULT_BACKEND_TARGET_VERSION


def test_update_backend_runtime_config_persists_settings(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    fake_settings = _FakeSettingsService()
    service = SimulationService(settings_service=fake_settings)

    config = BackendRuntimeConfig(
        target_version="v0.3.0",
        source="pypi",
        local_path="",
        auto_sync=True,
    )
    service.update_backend_runtime_config(config)

    assert fake_settings.runtime_settings == config.to_dict()


def test_install_backend_runtime_failure_sets_runtime_issue(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    fake_settings = _FakeSettingsService()
    service = SimulationService(settings_service=fake_settings)

    failure = BackendInstallResult(success=False, message="install failed")
    monkeypatch.setattr(service._runtime_service, "ensure_target_version", lambda *_args, **_kwargs: failure)

    result = service.install_backend_runtime(BackendRuntimeConfig(target_version="0.3.0"), force=True)

    assert not result.success
    assert service.backend_issue_message == "install failed"


def test_install_backend_runtime_success_reloads_backends(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    fake_settings = _FakeSettingsService()
    service = SimulationService(settings_service=fake_settings)

    success = BackendInstallResult(success=True, message="ok", changed=False)
    monkeypatch.setattr(service._runtime_service, "ensure_target_version", lambda *_args, **_kwargs: success)

    reloaded: dict[str, bool] = {"called": False}

    def _reload_backend_loader(*, emit_signal: bool):
        reloaded["called"] = emit_signal

    monkeypatch.setattr(service, "_reload_backend_loader", _reload_backend_loader)

    result = service.install_backend_runtime(BackendRuntimeConfig(target_version="0.3.0"), force=True)

    assert result.success
    assert reloaded["called"] is True


def test_prevalidate_blocks_discrete_control_without_sample_time(monkeypatch) -> None:
    class _ReadyBackend:
        def __init__(self) -> None:
            self.info = BackendInfo(
                identifier="pulsim",
                name="Pulsim",
                version="0.6.0",
                status="available",
            )
            self.run_transient_calls = 0

        def has_capability(self, _name: str) -> bool:
            return True

        def run_transient(self, *_args, **_kwargs):
            self.run_transient_calls += 1
            raise AssertionError("run_transient should not be called for invalid discrete control")

    backend = _ReadyBackend()

    class _ReadyLoader:
        def __init__(self, preferred_backend_id: str | None = None) -> None:
            _ = preferred_backend_id
            self.backend = backend
            self.available_backends = [backend.info]
            self.active_backend_id = backend.info.identifier

        def activate(self, identifier: str):
            if identifier != backend.info.identifier:
                raise ValueError(identifier)
            return self.backend.info

    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _ReadyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(control_mode="discrete", control_sample_time=0.0)

    errors: list[str] = []
    service.error.connect(errors.append)
    service.run_transient({"components": [{"type": "RESISTOR", "name": "R1", "parameters": {}}]})

    assert errors
    assert "PULSIM_YAML_E_CONTROL_SAMPLE_TIME_REQUIRED" in errors[-1]
    assert service.state == SimulationState.IDLE
    assert backend.run_transient_calls == 0


def test_prevalidate_blocks_invalid_pwm_target_component(monkeypatch) -> None:
    class _ReadyBackend:
        def __init__(self) -> None:
            self.info = BackendInfo(
                identifier="pulsim",
                name="Pulsim",
                version="0.6.0",
                status="available",
            )
            self.run_transient_calls = 0

        def has_capability(self, _name: str) -> bool:
            return True

        def run_transient(self, *_args, **_kwargs):
            self.run_transient_calls += 1
            raise AssertionError("run_transient should not be called for invalid PWM target")

    backend = _ReadyBackend()

    class _ReadyLoader:
        def __init__(self, preferred_backend_id: str | None = None) -> None:
            _ = preferred_backend_id
            self.backend = backend
            self.available_backends = [backend.info]
            self.active_backend_id = backend.info.identifier

        def activate(self, identifier: str):
            if identifier != backend.info.identifier:
                raise ValueError(identifier)
            return self.backend.info

    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _ReadyLoader)
    service = SimulationService()

    errors: list[str] = []
    service.error.connect(errors.append)
    service.run_transient(
        {
            "components": [
                {"type": "RESISTOR", "name": "R1", "parameters": {}},
                {
                    "type": "PWM_GENERATOR",
                    "name": "PWM1",
                    "parameters": {"target_component": "R1"},
                },
            ]
        }
    )

    assert errors
    assert "PULSIM_YAML_E_CONTROL_TARGET_INVALID" in errors[-1]
    assert service.state == SimulationState.IDLE
    assert backend.run_transient_calls == 0


def test_prevalidate_blocks_unsupported_thermal_component(monkeypatch) -> None:
    class _ReadyBackend:
        def __init__(self) -> None:
            self.info = BackendInfo(
                identifier="pulsim",
                name="Pulsim",
                version="0.6.0",
                status="available",
            )
            self.run_transient_calls = 0

        def has_capability(self, _name: str) -> bool:
            return True

        def run_transient(self, *_args, **_kwargs):
            self.run_transient_calls += 1
            raise AssertionError("run_transient should not be called for invalid thermal component")

    backend = _ReadyBackend()

    class _ReadyLoader:
        def __init__(self, preferred_backend_id: str | None = None) -> None:
            _ = preferred_backend_id
            self.backend = backend
            self.available_backends = [backend.info]
            self.active_backend_id = backend.info.identifier

        def activate(self, identifier: str):
            if identifier != backend.info.identifier:
                raise ValueError(identifier)
            return self.backend.info

    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _ReadyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(enable_losses=True)

    errors: list[str] = []
    service.error.connect(errors.append)
    service.run_transient(
        {
            "components": [
                {
                    "type": "CAPACITOR",
                    "name": "C1",
                    "parameters": {
                        "thermal_enabled": True,
                        "thermal_rth": 1.0,
                        "thermal_cth": 0.1,
                        "thermal_temp_init": 25.0,
                        "thermal_temp_ref": 25.0,
                        "thermal_alpha": 0.004,
                    },
                }
            ]
        }
    )

    assert errors
    assert "PULSIM_YAML_E_THERMAL_UNSUPPORTED_COMPONENT" in errors[-1]
    assert service.state == SimulationState.IDLE
    assert backend.run_transient_calls == 0


def test_worker_adds_runtime_consistency_kpis() -> None:
    worker = SimulationWorker(
        backend=_DummyBackend(),
        circuit_data={
            "components": [
                {"type": "MOSFET_N", "name": "M1", "parameters": {}},
                {"type": "RESISTOR", "name": "Rload", "parameters": {}},
                {"type": "PI_CONTROLLER", "name": "PI1", "parameters": {}},
                {"type": "PWM_GENERATOR", "name": "PWM1", "parameters": {"duty_min": 0.0, "duty_max": 0.95}},
            ]
        },
        settings=SimulationSettings(t_stop=1e-3, t_step=1e-6, enable_losses=True),
    )

    result = SimulationResult(
        time=[0.0, 1e-3],
        signals={
            "PI1": [0.1, 0.2],
            "PWM1.duty": [0.4, 0.5],
        },
        statistics={
            "loss_summary": {"total_loss": 10.0},
            "thermal_summary": {
                "enabled": True,
                "ambient": 25.0,
                "max_temperature": 50.0,
                "device_temperatures": [
                    {"device_name": "M1", "peak_temperature": 50.0},
                    {"device_name": "Rload", "peak_temperature": 30.0},
                ],
            },
            "component_electrothermal": [
                {"component_name": "M1", "total_energy": 0.006, "peak_temperature": 50.0},
                {"component_name": "Rload", "total_energy": 0.004, "peak_temperature": 30.0},
            ],
        },
    )

    worker._append_runtime_contract_checks(result)

    assert result.statistics["runtime_contract_ok"] is True
    assert result.statistics["component_coverage_rate"] == 1.0
    assert result.statistics["component_coverage_gap"] == 0
    assert result.statistics["component_loss_summary_consistency_error"] == 0.0
    assert result.statistics["component_thermal_summary_consistency_error"] == 0.0


def test_convert_gui_circuit_emits_pulsim_v1_simulation_contract(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(
        t_start=0.0,
        t_stop=2e-3,
        t_step=2e-6,
        step_mode="variable",
        formulation_mode="direct",
        direct_formulation_fallback=False,
        enable_events=True,
        enable_losses=True,
        control_mode="discrete",
        control_sample_time=5e-6,
        thermal_ambient=30.0,
        thermal_policy="loss_only",
        thermal_default_rth=2.5,
        thermal_default_cth=0.2,
    )

    project = Project(name="Contract")
    circuit = project.get_active_circuit()
    circuit.add_component(Component(type=ComponentType.VOLTAGE_SOURCE, name="Vin"))
    circuit.add_component(Component(type=ComponentType.RESISTOR, name="R1"))

    data = service.convert_gui_circuit(project)
    sim = data["simulation"]

    assert data["schema"] == "pulsim-v1"
    assert data["version"] == 1
    assert sim["tstart"] == 0.0
    assert sim["tstop"] == 2e-3
    assert sim["dt"] == 2e-6
    assert sim["step_mode"] == "variable"
    assert sim["formulation"] == "direct"
    assert sim["direct_formulation_fallback"] is False
    assert sim["control"]["mode"] == "discrete"
    assert sim["control"]["sample_time"] == 5e-6
    assert sim["thermal"]["enabled"] is True
    assert sim["thermal"]["policy"] == "loss_only"
    assert "backend" not in sim
    assert "sundials" not in sim


def test_convert_gui_circuit_returns_detached_cached_payload(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()

    project = Project(name="DetachedPayload")
    circuit = project.get_active_circuit()
    resistor = Component(type=ComponentType.RESISTOR, name="R1")
    resistor.parameters["resistance"] = 10.0
    circuit.add_component(resistor)

    first = service.convert_gui_circuit(project)
    comp_first = next(comp for comp in first["components"] if comp.get("name") == "R1")
    comp_first["parameters"]["resistance"] = 999.0

    second = service.convert_gui_circuit(project)
    comp_second = next(comp for comp in second["components"] if comp.get("name") == "R1")

    assert comp_second["parameters"]["resistance"] == 10.0


def test_convert_gui_circuit_emits_component_thermal_and_loss_blocks(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()

    project = Project(name="ElectrothermalBlocks")
    circuit = project.get_active_circuit()
    m1 = Component(type=ComponentType.MOSFET_N, name="M1")
    m1.parameters.update(
        {
            "thermal_enabled": True,
            "thermal_network": "cauer",
            "thermal_rth_stages": "0.2,0.3",
            "thermal_cth_stages": "0.01,0.02",
            "thermal_shared_sink_id": "HS1",
            "thermal_shared_sink_rth": 0.25,
            "thermal_shared_sink_cth": 0.04,
            "switching_loss_model": "datasheet",
            "switching_loss_axes_current": "0,10",
            "switching_loss_axes_voltage": "0,20",
            "switching_loss_axes_temperature": "25,125",
            "switching_loss_eon_table": "1e-6,1e-6,1e-6,1e-6,1e-6,1e-6,1e-6,1e-6",
            "switching_loss_eoff_table": "2e-6,2e-6,2e-6,2e-6,2e-6,2e-6,2e-6,2e-6",
        }
    )
    circuit.add_component(m1)

    payload = service.convert_gui_circuit(project)
    comp = next(item for item in payload["components"] if item.get("name") == "M1")

    assert comp["thermal"]["enabled"] is True
    assert comp["thermal"]["network"] == "cauer"
    assert comp["thermal"]["rth_stages"] == [0.2, 0.3]
    assert comp["thermal"]["cth_stages"] == [0.01, 0.02]
    assert comp["thermal"]["shared_sink_id"] == "HS1"
    assert comp["loss"]["model"] == "datasheet"
    assert comp["loss"]["axes"]["current"] == [0.0, 10.0]
    assert len(comp["loss"]["eon"]) == 8
    assert len(comp["loss"]["eoff"]) == 8


def test_worker_conversion_reuses_cache_until_project_changes(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()

    project = Project(name="WorkerCache")
    circuit = project.get_active_circuit()
    circuit.add_component(Component(type=ComponentType.VOLTAGE_SOURCE, name="Vin"))
    circuit.add_component(Component(type=ComponentType.RESISTOR, name="R1"))

    first = service.convert_gui_circuit_cached(project)
    second = service.convert_gui_circuit_cached(project)
    assert first is second

    circuit.add_component(Component(type=ComponentType.CAPACITOR, name="C1"))
    project.mark_dirty()

    third = service.convert_gui_circuit_cached(project)
    assert third is not second
    assert any(comp.get("name") == "C1" for comp in third["components"])


def test_worker_conversion_cache_invalidated_when_settings_change(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()
    project = Project(name="SettingsCache")
    circuit = project.get_active_circuit()
    circuit.add_component(Component(type=ComponentType.RESISTOR, name="R1"))

    first = service.convert_gui_circuit_cached(project)
    assert first["simulation"]["tstop"] == service.settings.t_stop

    service.settings = SimulationSettings(t_stop=2e-3, t_step=2e-6)
    second = service.convert_gui_circuit_cached(project)

    assert second is not first
    assert second["simulation"]["tstop"] == 2e-3


def test_prevalidate_blocks_component_thermal_when_global_thermal_disabled(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(enable_losses=True)

    issue = service._prevalidate_runtime_contract(
        {
            "simulation": {
                "thermal": {"enabled": False},
            },
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "thermal": {
                        "enabled": True,
                        "rth": 1.0,
                        "cth": 0.1,
                        "temp_init": 25.0,
                        "temp_ref": 25.0,
                        "alpha": 0.004,
                    },
                    "parameters": {},
                }
            ],
        }
    )

    assert issue is not None
    assert "simulation.thermal.enabled=true" in issue


def test_prevalidate_accepts_staged_component_thermal_network(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(enable_losses=True)

    issue = service._prevalidate_runtime_contract(
        {
            "simulation": {
                "thermal": {"enabled": True},
            },
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "thermal": {
                        "enabled": True,
                        "network": "foster",
                        "rth_stages": [0.4, 0.6],
                        "cth_stages": [0.01, 0.02],
                        "temp_init": 25.0,
                        "temp_ref": 25.0,
                        "alpha": 0.004,
                    },
                    "parameters": {},
                }
            ],
        }
    )

    assert issue is None


def test_prevalidate_blocks_invalid_loss_model(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()

    issue = service._prevalidate_runtime_contract(
        {
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "parameters": {
                        "switching_loss_model": "lookup2d",
                    },
                }
            ]
        }
    )

    assert issue is not None
    assert "PULSIM_YAML_E_LOSS_MODEL_INVALID" in issue


def test_prevalidate_accepts_valid_datasheet_loss_tables(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()

    issue = service._prevalidate_runtime_contract(
        {
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "parameters": {
                        "switching_loss_model": "datasheet",
                        "switching_loss_axes_current": "0,10",
                        "switching_loss_axes_voltage": "0,20",
                        "switching_loss_axes_temperature": "25,125",
                        "switching_loss_eon_table": "1e-6,1e-6,1e-6,1e-6,1e-6,1e-6,1e-6,1e-6",
                        "switching_loss_eoff_table": "2e-6,2e-6,2e-6,2e-6,2e-6,2e-6,2e-6,2e-6",
                    },
                }
            ]
        }
    )

    assert issue is None


def test_prevalidate_blocks_invalid_datasheet_loss_dimensions(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()

    issue = service._prevalidate_runtime_contract(
        {
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "parameters": {
                        "switching_loss_model": "datasheet",
                        "switching_loss_axes_current": "0,10",
                        "switching_loss_axes_voltage": "0,20",
                        "switching_loss_axes_temperature": "25,125",
                        "switching_loss_eon_table": "1e-6,1e-6,1e-6",
                        "switching_loss_eoff_table": "2e-6,2e-6,2e-6,2e-6",
                    },
                }
            ]
        }
    )

    assert issue is not None
    assert "PULSIM_YAML_E_LOSS_DIMENSION_INVALID" in issue


def test_prevalidate_blocks_shared_sink_fields_without_sink_id(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(enable_losses=True)

    issue = service._prevalidate_runtime_contract(
        {
            "simulation": {
                "thermal": {"enabled": True},
            },
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "thermal": {
                        "enabled": True,
                        "rth": 1.0,
                        "cth": 0.1,
                        "temp_init": 25.0,
                        "temp_ref": 25.0,
                        "alpha": 0.004,
                        "shared_sink_rth": 0.25,
                        "shared_sink_cth": 0.04,
                    },
                    "parameters": {},
                }
            ],
        }
    )

    assert issue is not None
    assert "PULSIM_YAML_E_THERMAL_RANGE_INVALID" in issue
    assert "shared_sink_id" in issue


def test_prevalidate_blocks_inconsistent_shared_sink_parameters(monkeypatch) -> None:
    monkeypatch.setattr("pulsimgui.services.simulation_service.BackendLoader", _DummyLoader)
    service = SimulationService()
    service.settings = SimulationSettings(enable_losses=True)

    issue = service._prevalidate_runtime_contract(
        {
            "simulation": {
                "thermal": {"enabled": True},
            },
            "components": [
                {
                    "type": "mosfet",
                    "name": "M1",
                    "thermal": {
                        "enabled": True,
                        "rth": 1.0,
                        "cth": 0.1,
                        "temp_init": 25.0,
                        "temp_ref": 25.0,
                        "alpha": 0.004,
                        "shared_sink_id": "HS1",
                        "shared_sink_rth": 0.25,
                        "shared_sink_cth": 0.04,
                    },
                    "parameters": {},
                },
                {
                    "type": "diode",
                    "name": "D1",
                    "thermal": {
                        "enabled": True,
                        "rth": 1.2,
                        "cth": 0.1,
                        "temp_init": 25.0,
                        "temp_ref": 25.0,
                        "alpha": 0.004,
                        "shared_sink_id": "HS1",
                        "shared_sink_rth": 0.30,
                        "shared_sink_cth": 0.04,
                    },
                    "parameters": {},
                },
            ],
        }
    )

    assert issue is not None
    assert "PULSIM_YAML_E_THERMAL_RANGE_INVALID" in issue
    assert "HS1" in issue


def test_worker_maps_invalid_thermal_configuration_diagnostic_to_error() -> None:
    worker = SimulationWorker(
        backend=_DummyBackend(),
        circuit_data={"components": []},
        settings=SimulationSettings(),
    )

    result = SimulationResult(
        time=[0.0, 1e-6],
        signals={},
        statistics={"diagnostic": "invalid_thermal_configuration"},
    )
    worker._append_runtime_contract_checks(result)

    assert "invalid_thermal_configuration" in result.error_message
    assert result.statistics["runtime_contract_ok"] is False


def test_worker_builds_circuit_data_before_running_backend() -> None:
    seen: dict[str, object] = {}

    class _Backend:
        def run_transient(self, circuit_data, _settings, _callbacks):  # noqa: ANN001
            seen["backend_circuit_data"] = circuit_data
            return SimpleNamespace(
                time=[0.0, 1e-6],
                signals={"V(out)": [0.0, 1.0]},
                statistics={},
                error_message="",
            )

    source = {"source": "project"}

    def _builder(payload):  # noqa: ANN001
        seen["builder_payload"] = payload
        return {"components": [{"type": "RESISTOR", "name": "R1", "parameters": {}}]}

    def _validator(circuit_data):  # noqa: ANN001
        seen["validator_data"] = circuit_data
        return None

    worker = SimulationWorker(
        backend=_Backend(),  # type: ignore[arg-type]
        circuit_data=None,
        settings=SimulationSettings(),
        circuit_source=source,
        circuit_builder=_builder,
        contract_validator=_validator,
    )

    results: list[SimulationResult] = []
    errors: list[str] = []
    worker.finished_signal.connect(results.append)
    worker.error.connect(errors.append)
    worker.run()

    assert not errors
    assert seen["builder_payload"] == source
    assert seen["validator_data"] == seen["backend_circuit_data"]
    assert isinstance(seen["backend_circuit_data"], dict)
    assert results
    assert results[0].error_message == ""
    assert results[0].time == [0.0, 1e-6]


def test_worker_reuses_backend_buffers_for_transient_vectors() -> None:
    backend_time = [0.0, 1e-6, 2e-6]
    backend_signal = [0.1, 0.2, 0.3]
    backend_stats: dict[str, object] = {"meta": "ok"}

    class _Backend:
        def run_transient(self, _circuit_data, _settings, _callbacks):  # noqa: ANN001
            return SimpleNamespace(
                time=backend_time,
                signals={"V(out)": backend_signal},
                statistics=backend_stats,
                error_message="",
            )

    worker = SimulationWorker(
        backend=_Backend(),  # type: ignore[arg-type]
        circuit_data={"components": [{"type": "RESISTOR", "name": "R1", "parameters": {}}]},
        settings=SimulationSettings(),
    )

    results: list[SimulationResult] = []
    worker.finished_signal.connect(results.append)
    worker.run()

    assert results
    assert results[0].time is backend_time
    assert results[0].signals["V(out)"] is backend_signal
    assert results[0].statistics is backend_stats


def test_worker_stops_before_backend_when_contract_validator_fails() -> None:
    class _Backend:
        def __init__(self) -> None:
            self.calls = 0

        def run_transient(self, _circuit_data, _settings, _callbacks):  # noqa: ANN001
            self.calls += 1
            return SimpleNamespace(time=[], signals={}, statistics={}, error_message="")

    backend = _Backend()
    worker = SimulationWorker(
        backend=backend,  # type: ignore[arg-type]
        circuit_data={"components": [{"type": "RESISTOR", "name": "R1", "parameters": {}}]},
        settings=SimulationSettings(control_mode="discrete", control_sample_time=0.0),
        contract_validator=lambda _data: "PULSIM_YAML_E_CONTROL_SAMPLE_TIME_REQUIRED",
    )

    results: list[SimulationResult] = []
    errors: list[str] = []
    worker.finished_signal.connect(results.append)
    worker.error.connect(errors.append)
    worker.run()

    assert backend.calls == 0
    assert errors == ["PULSIM_YAML_E_CONTROL_SAMPLE_TIME_REQUIRED"]
    assert results
    assert results[0].error_message == "PULSIM_YAML_E_CONTROL_SAMPLE_TIME_REQUIRED"
