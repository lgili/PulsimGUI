"""Tests for MainWindow template project creation flow."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.project import Project
import pulsimgui.views.main_window as main_window_module
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
