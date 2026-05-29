"""Tests for sub-wave B analysis-mode dialogs (FRA / PSS / HB)."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QMessageBox

from pulsimgui.services.backend_types import (
    FraResult,
    FraResultEntry,
    FraSettings,
    HarmonicBalanceResult,
    HarmonicBalanceSettings,
    PeriodicSteadyStateResult,
    PeriodicSteadyStateSettings,
)
from pulsimgui.views.dialogs.analysis_modes_dialogs import (
    FraDialog,
    HarmonicBalanceDialog,
    PeriodicSteadyStateDialog,
)


class _StubService:
    def __init__(
        self,
        *,
        capability: dict[str, bool] | None = None,
        fra_result: FraResult | None = None,
        pss_result: PeriodicSteadyStateResult | None = None,
        hb_result: HarmonicBalanceResult | None = None,
        raise_: Exception | None = None,
    ) -> None:
        self._capability = capability or {
            "fra": True,
            "periodic_steady_state": True,
            "harmonic_balance": True,
        }
        self._fra_result = fra_result
        self._pss_result = pss_result
        self._hb_result = hb_result
        self._raise = raise_
        self.calls: list[tuple[str, Any]] = []

    def has_capability(self, name: str) -> bool:
        return self._capability.get(name, False)

    def run_fra(self, project: Any, settings: FraSettings) -> FraResult:
        self.calls.append(("fra", settings))
        if self._raise:
            raise self._raise
        return self._fra_result

    def run_periodic_steady_state(
        self, project: Any, settings: PeriodicSteadyStateSettings
    ) -> PeriodicSteadyStateResult:
        self.calls.append(("pss", settings))
        if self._raise:
            raise self._raise
        return self._pss_result

    def run_harmonic_balance(
        self, project: Any, settings: HarmonicBalanceSettings
    ) -> HarmonicBalanceResult:
        self.calls.append(("hb", settings))
        if self._raise:
            raise self._raise
        return self._hb_result


class _StubProject:
    name = "demo"


@pytest.fixture
def project():
    return _StubProject()


# ---------------------------------------------------------------------------
# FRA
# ---------------------------------------------------------------------------
def test_fra_collects_settings_and_calls_service(qapp, project, monkeypatch):
    success = FraResult(
        success=True,
        wall_seconds=0.5,
        total_transient_steps=1000,
        frequencies=(1.0, 10.0, 100.0),
        entries=(
            FraResultEntry(1.0, -1.0, -5.0),
            FraResultEntry(10.0, -3.0, -45.0),
            FraResultEntry(100.0, -20.0, -90.0),
        ),
    )
    svc = _StubService(fra_result=success)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)

    dlg = FraDialog(svc, project)
    try:
        dlg._f_start.setValue(2.0)
        dlg._f_stop.setValue(2e5)
        dlg._points_per_decade.setValue(20)
        dlg._perturbation_amp.setValue(0.05)
        dlg._perturbation_source.setText("Vin")
        dlg._measurement_nodes.setText("Vout, Vfb")
        dlg._on_run_clicked()

        assert len(svc.calls) == 1
        kind, settings = svc.calls[0]
        assert kind == "fra"
        assert settings.f_start == pytest.approx(2.0)
        assert settings.f_stop == pytest.approx(2e5)
        assert settings.points_per_decade == 20
        assert settings.perturbation_amplitude == pytest.approx(0.05)
        assert settings.perturbation_source == "Vin"
        assert settings.measurement_nodes == ("Vout", "Vfb")
        assert dlg.last_result is success
    finally:
        dlg.deleteLater()


def test_fra_capability_gate(qapp, project, monkeypatch):
    svc = _StubService(capability={"fra": False})
    calls = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **kw: calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg = FraDialog(svc, project)
    try:
        dlg._on_run_clicked()
        assert calls
        assert svc.calls == []
    finally:
        dlg.deleteLater()


def test_fra_failure_surfaces_warning(qapp, project, monkeypatch):
    failed = FraResult(success=False, failure_reason="Perturbation source not found")
    svc = _StubService(fra_result=failed)
    calls = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **kw: calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg = FraDialog(svc, project)
    try:
        dlg._perturbation_source.setText("Vmissing")
        dlg._on_run_clicked()
        assert calls
        # Backend was called even though it failed — dialog shows the error.
        assert svc.calls
    finally:
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# Periodic Steady-State
# ---------------------------------------------------------------------------
def test_pss_collects_settings_and_calls_service(qapp, project, monkeypatch):
    success = PeriodicSteadyStateResult(
        success=True, iterations=8, residual_norm=1e-9, diagnostic="converged"
    )
    svc = _StubService(pss_result=success)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)

    dlg = PeriodicSteadyStateDialog(svc, project)
    try:
        dlg._period.setValue(2e-5)
        dlg._max_iter.setValue(80)
        dlg._tolerance.setValue(1e-9)
        dlg._relaxation.setValue(0.8)
        dlg._store_transient.setChecked(False)
        dlg._on_run_clicked()

        assert len(svc.calls) == 1
        kind, settings = svc.calls[0]
        assert kind == "pss"
        assert settings.period == pytest.approx(2e-5)
        assert settings.max_iterations == 80
        assert settings.tolerance == pytest.approx(1e-9)
        assert settings.relaxation == pytest.approx(0.8)
        assert settings.store_last_transient is False
        assert dlg.last_result is success
    finally:
        dlg.deleteLater()


def test_pss_failure_warning_not_critical(qapp, project, monkeypatch):
    failed = PeriodicSteadyStateResult(
        success=False, message="Maximum iterations exceeded"
    )
    svc = _StubService(pss_result=failed)
    calls = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **kw: calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg = PeriodicSteadyStateDialog(svc, project)
    try:
        dlg._on_run_clicked()
        assert calls
    finally:
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# Harmonic Balance
# ---------------------------------------------------------------------------
def test_hb_collects_settings_and_calls_service(qapp, project, monkeypatch):
    success = HarmonicBalanceResult(
        success=True,
        iterations=4,
        residual_norm=5e-10,
        sample_count=128,
        diagnostic="balanced",
    )
    svc = _StubService(hb_result=success)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)

    dlg = HarmonicBalanceDialog(svc, project)
    try:
        dlg._period.setValue(2.5e-5)
        dlg._num_samples.setValue(128)
        dlg._max_iter.setValue(40)
        dlg._tolerance.setValue(1e-8)
        dlg._relaxation.setValue(0.9)
        dlg._init_from_transient.setChecked(False)
        dlg._on_run_clicked()

        assert len(svc.calls) == 1
        kind, settings = svc.calls[0]
        assert kind == "hb"
        assert settings.period == pytest.approx(2.5e-5)
        assert settings.num_samples == 128
        assert settings.max_iterations == 40
        assert settings.tolerance == pytest.approx(1e-8)
        assert settings.relaxation == pytest.approx(0.9)
        assert settings.initialize_from_transient is False
        assert dlg.last_result is success
    finally:
        dlg.deleteLater()


def test_hb_backend_exception_critical(qapp, project, monkeypatch):
    svc = _StubService(raise_=RuntimeError("Singular matrix"))
    calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *a, **kw: calls.append(a) or QMessageBox.StandardButton.Ok,
    )
    dlg = HarmonicBalanceDialog(svc, project)
    try:
        dlg._on_run_clicked()
        assert calls
    finally:
        dlg.deleteLater()
