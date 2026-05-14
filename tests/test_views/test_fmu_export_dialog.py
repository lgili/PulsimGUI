"""Tests for FmuExportDialog (Wave-4 sub-wave A item 1.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from pulsimgui.services.backend_types import FmuExportResult, FmuExportSettings
from pulsimgui.views.dialogs.fmu_export_dialog import FmuExportDialog


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class _StubSimulationService:
    """Minimal SimulationService surface used by the dialog."""

    def __init__(
        self,
        *,
        capability: bool = True,
        result: FmuExportResult | None = None,
        raise_: Exception | None = None,
    ) -> None:
        self._capability = capability
        self._result = result
        self._raise = raise_
        self.export_calls: list[tuple[Any, FmuExportSettings]] = []

    def has_capability(self, name: str) -> bool:
        return self._capability if name == "fmu_export" else False

    def export_fmu(self, project: Any, settings: FmuExportSettings) -> FmuExportResult:
        self.export_calls.append((project, settings))
        if self._raise is not None:
            raise self._raise
        assert self._result is not None
        return self._result


class _StubProject:
    def __init__(self, name: str = "buck_demo") -> None:
        self.name = name


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def stub_project() -> _StubProject:
    return _StubProject()


@pytest.fixture
def successful_result() -> FmuExportResult:
    return FmuExportResult(
        path="/tmp/buck_demo.fmu",
        model_name="buck_demo",
        model_identifier="buck_demo_v1",
        guid="abc-123",
        fmi_version="2.0",
        state_size=4,
        input_size=1,
        output_size=2,
        inputs=("u_duty",),
        outputs=("v_out", "i_l"),
        files_in_archive=("modelDescription.xml",),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_dialog_renders_default_model_name_from_project(qapp, stub_project):
    """Project name SHALL prepopulate the model name field with spaces -> underscores."""
    project = _StubProject(name="My Buck Demo")
    svc = _StubSimulationService()
    dlg = FmuExportDialog(svc, project)
    try:
        assert dlg._name_edit.text() == "My_Buck_Demo"
    finally:
        dlg.deleteLater()


def test_export_button_disabled_until_path_and_name_set(qapp, stub_project):
    svc = _StubSimulationService()
    dlg = FmuExportDialog(svc, stub_project)
    try:
        # Default ctor leaves path blank -> button disabled.
        assert dlg._export_btn.isEnabled() is False
        dlg._path_edit.setText("/tmp/out.fmu")
        assert dlg._export_btn.isEnabled() is True
        dlg._name_edit.clear()
        assert dlg._export_btn.isEnabled() is False
    finally:
        dlg.deleteLater()


def test_browse_appends_fmu_extension(qapp, stub_project, monkeypatch):
    svc = _StubSimulationService()
    dlg = FmuExportDialog(svc, stub_project)
    try:
        monkeypatch.setattr(
            "pulsimgui.views.dialogs.fmu_export_dialog.QFileDialog.getSaveFileName",
            lambda *args, **kwargs: ("/tmp/no_ext", "FMU archives (*.fmu)"),
        )
        dlg._on_browse()
        assert dlg._path_edit.text() == "/tmp/no_ext.fmu"
    finally:
        dlg.deleteLater()


def test_outputs_list_collects_only_checked_items(qapp, stub_project):
    svc = _StubSimulationService()
    nodes = ["v_out", "i_l", "v_in"]
    dlg = FmuExportDialog(svc, stub_project, available_node_names=nodes)
    try:
        dlg._expose_nodes_check.setChecked(True)
        # Check first and third items.
        dlg._outputs_list.item(0).setCheckState(Qt.CheckState.Checked)
        dlg._outputs_list.item(2).setCheckState(Qt.CheckState.Checked)
        assert dlg._selected_outputs() == ("i_l", "v_out") or set(
            dlg._selected_outputs()
        ) == {"i_l", "v_out"}
    finally:
        dlg.deleteLater()


def test_export_calls_service_with_collected_settings(
    qapp, stub_project, successful_result, monkeypatch
):
    svc = _StubSimulationService(result=successful_result)
    dlg = FmuExportDialog(svc, stub_project)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    try:
        dlg._name_edit.setText("buck_demo")
        dlg._path_edit.setText("/tmp/buck_demo.fmu")
        dlg._dt_spin.setValue(2.5e-5)
        dlg._on_export_clicked()
        assert len(svc.export_calls) == 1
        project_arg, settings_arg = svc.export_calls[0]
        assert project_arg is stub_project
        assert isinstance(settings_arg, FmuExportSettings)
        assert settings_arg.model_name == "buck_demo"
        assert settings_arg.dt == pytest.approx(2.5e-5)
        assert Path(settings_arg.out_path).name == "buck_demo.fmu"
        assert dlg.last_result is successful_result
    finally:
        dlg.deleteLater()


def test_export_blocks_when_backend_lacks_capability(
    qapp, stub_project, monkeypatch
):
    svc = _StubSimulationService(capability=False)
    dlg = FmuExportDialog(svc, stub_project)
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: critical_calls.append(args) or QMessageBox.StandardButton.Ok,
    )
    try:
        dlg._name_edit.setText("buck_demo")
        dlg._path_edit.setText("/tmp/buck_demo.fmu")
        dlg._on_export_clicked()
        assert critical_calls, "QMessageBox.critical should fire when capability missing"
        assert svc.export_calls == []
    finally:
        dlg.deleteLater()


def test_export_failure_surfaces_in_dialog(qapp, stub_project, monkeypatch):
    svc = _StubSimulationService(
        raise_=RuntimeError("Compiler not found: cc")
    )
    dlg = FmuExportDialog(svc, stub_project)
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: critical_calls.append(args) or QMessageBox.StandardButton.Ok,
    )
    try:
        dlg._name_edit.setText("buck_demo")
        dlg._path_edit.setText("/tmp/buck_demo.fmu")
        dlg._on_export_clicked()
        assert critical_calls, "QMessageBox.critical should fire on backend error"
        # Button re-enabled so the user can retry after fixing things.
        assert dlg._export_btn.isEnabled() is True
    finally:
        dlg.deleteLater()


def test_build_settings_appends_extension_when_missing(qapp, stub_project):
    svc = _StubSimulationService()
    dlg = FmuExportDialog(svc, stub_project)
    try:
        dlg._name_edit.setText("buck_demo")
        dlg._path_edit.setText("/tmp/buck_demo")
        settings = dlg._build_settings()
        assert settings.out_path.endswith(".fmu")
    finally:
        dlg.deleteLater()
