"""Tests for scope window UI/workspace persistence integration in MainWindow."""

from __future__ import annotations

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.project import Project, ScopeWindowState
from pulsimgui.views.main_window import MainWindow


def test_main_window_persists_scope_ui_state_on_close(monkeypatch, qapp) -> None:
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        circuit = window._current_circuit()
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1", x=200.0, y=120.0)
        circuit.add_component(scope)

        scope_window = window._open_scope_window(scope)
        scope_window._on_toggle_left_panel_clicked(False)
        scope_window._on_measurement_key_toggled("rms", False)
        scope_window.close()

        component_id = str(scope.id)
        state = window._project.scope_windows[component_id]
        assert isinstance(state.ui_state, dict)
        assert state.ui_state["left_panel_visible"] is False
        assert "rms" not in state.ui_state["measurement_keys"]

        reopened = window._open_scope_window(scope, update_state=False)
        assert reopened._left_panel_visible is False
        assert "rms" not in reopened._stacked_measurements.visible_measurement_keys()
        assert isinstance(window._project.scope_workspace_state, dict)
    finally:
        window.close()


def test_main_window_restores_saved_open_scope_windows_on_project_load(monkeypatch, qapp) -> None:
    project = Project(name="RestoreScope")
    circuit = project.get_active_circuit()
    scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1", x=240.0, y=150.0)
    circuit.add_component(scope)
    component_id = str(scope.id)
    project.scope_windows[component_id] = ScopeWindowState(
        component_id=component_id,
        is_open=True,
        geometry=[40, 50, 760, 500],
        ui_state={
            "left_panel_visible": False,
            "measurement_keys": ["max", "mean"],
            "cursors_enabled": False,
        },
    )

    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        window._project = project
        window._load_project_to_scene()

        assert component_id in window._scope_windows
        restored = window._scope_windows[component_id]
        assert restored._left_panel_visible is False
        assert restored._stacked_measurements.visible_measurement_keys() == ["max", "mean"]
    finally:
        window.close()
