"""Tests for SimulationService runtime backend provisioning integration."""

from __future__ import annotations

from dataclasses import dataclass

from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.backend_runtime_service import (
    DEFAULT_BACKEND_TARGET_VERSION,
    BackendInstallResult,
    BackendRuntimeConfig,
)
from pulsimgui.services.simulation_service import SimulationService, SimulationSettings


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
        return {}

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
    )

    assert fake_settings.sim_settings is not None
    assert fake_settings.sim_settings["t_stop"] == 5e-3
    assert fake_settings.sim_settings["solver"] == "rk45"
    assert fake_settings.sim_settings["output_points"] == 5000

    assert fake_settings.solver_settings is not None
    assert fake_settings.solver_settings["max_newton_iterations"] == 80
    assert fake_settings.solver_settings["dc_strategy"] == "gmin"


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
