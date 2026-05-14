"""Tests for C99ExportDialog (Wave-4 sub-wave A item 1.2)."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QMessageBox

from pulsimgui.services.backend_types import C99CodegenResult, C99CodegenSettings
from pulsimgui.views.dialogs.c99_export_dialog import C99ExportDialog


class _StubSimulationService:
    def __init__(
        self,
        *,
        capability: bool = True,
        result: C99CodegenResult | None = None,
        raise_: Exception | None = None,
    ) -> None:
        self._capability = capability
        self._result = result
        self._raise = raise_
        self.export_calls: list[tuple[Any, C99CodegenSettings]] = []

    def has_capability(self, name: str) -> bool:
        return self._capability if name == "c99_codegen" else False

    def export_c99(self, project: Any, settings: C99CodegenSettings) -> C99CodegenResult:
        self.export_calls.append((project, settings))
        if self._raise is not None:
            raise self._raise
        assert self._result is not None
        return self._result


class _StubProject:
    name = "demo_project"


@pytest.fixture
def stub_project() -> _StubProject:
    return _StubProject()


@pytest.fixture
def successful_result() -> C99CodegenResult:
    return C99CodegenResult(
        out_dir="/tmp/c99_out",
        target="c99",
        state_size=6,
        input_size=2,
        output_size=3,
        stability_radius=0.92,
        rom_estimate_bytes=12 * 1024,
        ram_estimate_bytes=2 * 1024,
        files_written=("controller.c", "controller.h", "driver.c"),
    )


def test_export_disabled_until_output_dir_set(qapp, stub_project):
    svc = _StubSimulationService()
    dlg = C99ExportDialog(svc, stub_project)
    try:
        assert dlg._export_btn.isEnabled() is False
        dlg._out_dir_edit.setText("/tmp/c99")
        assert dlg._export_btn.isEnabled() is True
        dlg._out_dir_edit.clear()
        assert dlg._export_btn.isEnabled() is False
    finally:
        dlg.deleteLater()


def test_browse_populates_output_dir(qapp, stub_project, monkeypatch):
    svc = _StubSimulationService()
    dlg = C99ExportDialog(svc, stub_project)
    try:
        monkeypatch.setattr(
            "pulsimgui.views.dialogs.c99_export_dialog.QFileDialog.getExistingDirectory",
            lambda *args, **kwargs: "/tmp/chosen",
        )
        dlg._on_browse()
        assert dlg._out_dir_edit.text() == "/tmp/chosen"
    finally:
        dlg.deleteLater()


def test_export_calls_service_with_collected_settings(
    qapp, stub_project, successful_result, monkeypatch
):
    svc = _StubSimulationService(result=successful_result)
    dlg = C99ExportDialog(svc, stub_project)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    try:
        dlg._out_dir_edit.setText("/tmp/c99_out")
        dlg._dt_spin.setValue(5e-5)
        dlg._t_op_spin.setValue(0.01)
        dlg._on_export_clicked()
        assert len(svc.export_calls) == 1
        _, settings = svc.export_calls[0]
        assert isinstance(settings, C99CodegenSettings)
        assert settings.out_dir.endswith("c99_out")
        assert settings.dt == pytest.approx(5e-5)
        assert settings.t_op == pytest.approx(0.01)
        assert settings.target == "c99"
        assert dlg.last_result is successful_result
    finally:
        dlg.deleteLater()


def test_export_blocks_when_capability_missing(qapp, stub_project, monkeypatch):
    svc = _StubSimulationService(capability=False)
    dlg = C99ExportDialog(svc, stub_project)
    crit = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *a, **kw: crit.append(a) or QMessageBox.StandardButton.Ok,
    )
    try:
        dlg._out_dir_edit.setText("/tmp/c99")
        dlg._on_export_clicked()
        assert crit
        assert svc.export_calls == []
    finally:
        dlg.deleteLater()


def test_export_failure_surfaces_in_dialog(qapp, stub_project, monkeypatch):
    svc = _StubSimulationService(raise_=RuntimeError("PWL admissibility check failed"))
    dlg = C99ExportDialog(svc, stub_project)
    crit = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *a, **kw: crit.append(a) or QMessageBox.StandardButton.Ok,
    )
    try:
        dlg._out_dir_edit.setText("/tmp/c99")
        dlg._on_export_clicked()
        assert crit
        # User can retry — button comes back enabled.
        assert dlg._export_btn.isEnabled() is True
    finally:
        dlg.deleteLater()
