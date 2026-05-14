"""Tests for ParameterSweepDialog Monte-Carlo tab (wave-4 sub-A 1.3)."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.monte_carlo_sweep import (
    MonteCarloSweepSettings,
)
from pulsimgui.views.dialogs.parameter_sweep_dialog import ParameterSweepDialog


def _make_circuit() -> Circuit:
    """Build a minimal circuit with two numeric-parameter components."""
    circuit = Circuit(name="MC test")
    r = Component(type=ComponentType.RESISTOR, name="R1")
    r.parameters = {"resistance": 1000.0}
    c = Component(type=ComponentType.CAPACITOR, name="C1")
    c.parameters = {"capacitance": 1e-6}
    circuit.add_component(r)
    circuit.add_component(c)
    return circuit


def test_dialog_starts_in_range_mode(qapp):
    dlg = ParameterSweepDialog(_make_circuit())
    try:
        assert dlg.get_mode() == ParameterSweepDialog.MODE_RANGE
        assert dlg.get_monte_carlo_settings() is None
    finally:
        dlg.deleteLater()


def test_switching_to_mc_tab_flips_mode_and_returns_settings(qapp):
    circuit = _make_circuit()
    dlg = ParameterSweepDialog(circuit)
    try:
        dlg._tabs.setCurrentIndex(1)
        assert dlg.get_mode() == ParameterSweepDialog.MODE_MONTE_CARLO

        # Seeded row exists from _mc_seed_initial_row.
        assert dlg._mc_table.rowCount() == 1

        settings = dlg.get_monte_carlo_settings()
        assert isinstance(settings, MonteCarloSweepSettings)
        assert len(settings.parameters) == 1
        row = settings.parameters[0]
        assert row.distribution == "uniform"
        assert row.params == {"low": 0.0, "high": 1.0}
    finally:
        dlg.deleteLater()


def test_mc_tab_can_add_and_remove_rows(qapp):
    dlg = ParameterSweepDialog(_make_circuit())
    try:
        dlg._tabs.setCurrentIndex(1)
        before = dlg._mc_table.rowCount()
        dlg._mc_add_row()
        dlg._mc_add_row()
        assert dlg._mc_table.rowCount() == before + 2

        dlg._mc_table.selectRow(0)
        dlg._mc_remove_selected()
        assert dlg._mc_table.rowCount() == before + 1
    finally:
        dlg.deleteLater()


def test_mc_normal_distribution_maps_low_high_to_mu_sigma(qapp):
    dlg = ParameterSweepDialog(_make_circuit())
    try:
        dlg._tabs.setCurrentIndex(1)
        # Configure first row as normal(μ=5, σ=2)
        dist_combo = dlg._mc_table.cellWidget(0, 2)
        dist_combo.setCurrentText("normal")
        dlg._mc_table.cellWidget(0, 3).setValue(5.0)
        dlg._mc_table.cellWidget(0, 4).setValue(2.0)

        settings = dlg.get_monte_carlo_settings()
        assert settings is not None
        row = settings.parameters[0]
        assert row.distribution == "normal"
        assert row.params == {"mu": 5.0, "sigma": 2.0}
    finally:
        dlg.deleteLater()


def test_mc_seed_value_negative_one_means_auto(qapp):
    dlg = ParameterSweepDialog(_make_circuit())
    try:
        dlg._tabs.setCurrentIndex(1)
        dlg._mc_seed_spin.setValue(-1)
        settings = dlg.get_monte_carlo_settings()
        assert settings is not None
        assert settings.seed is None

        dlg._mc_seed_spin.setValue(123)
        settings = dlg.get_monte_carlo_settings()
        assert settings is not None
        assert settings.seed == 123
    finally:
        dlg.deleteLater()


def test_get_settings_returns_none_in_monte_carlo_mode(qapp):
    dlg = ParameterSweepDialog(_make_circuit())
    try:
        dlg._tabs.setCurrentIndex(1)
        assert dlg.get_settings() is None
    finally:
        dlg.deleteLater()
