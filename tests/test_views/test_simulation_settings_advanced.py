"""Tests for SimulationSettingsDialog Solver Stack tab (wave-4 sub-A 1.6)."""

from __future__ import annotations

import pytest

from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.views.dialogs.simulation_settings_dialog import (
    SimulationSettingsDialog,
)


@pytest.fixture
def dialog(qapp):
    settings = SimulationSettings()
    dlg = SimulationSettingsDialog(settings=settings)
    yield dlg
    dlg.deleteLater()


def test_solver_stack_page_present(dialog):
    """Solver Stack is a first-class nav entry (the advanced sections
    were flattened out of the nested QTabWidget into the dialog's
    left navigation)."""
    labels = [
        str(btn.property("navLabel") or btn.text())
        for btn in dialog._nav_buttons
    ]
    assert "Solver Stack" in labels
    # The full advanced set rides in the nav, one entry each.
    for expected in (
        "Transient",
        "DC Setup",
        "Thermal & Losses",
        "Frequency Analysis",
    ):
        assert expected in labels


def test_solver_stack_tab_has_four_advanced_knobs(dialog):
    """LinearSolverStackConfig / IterativeSolver / BDF order widgets exist."""
    assert dialog._linear_solver_combo.count() == 5
    # Auto entry should be first.
    assert dialog._linear_solver_combo.itemData(0) == "auto"
    # All known stacks reachable.
    stacks = {
        dialog._linear_solver_combo.itemData(i)
        for i in range(dialog._linear_solver_combo.count())
    }
    assert stacks == {"auto", "klu", "enhanced_sparse_lu", "gmres", "bicgstab"}

    assert dialog._iterative_max_iter_spin.value() == 200
    assert dialog._iterative_restart_spin.value() == 30
    assert dialog._bdf_max_order_spin.value() == 5


def test_solver_stack_roundtrips_through_settings(qapp):
    """Apply → reload preserves all four advanced knobs."""
    src = SimulationSettings(
        linear_solver_stack="gmres",
        iterative_solver_max_iterations=512,
        iterative_solver_restart=64,
        bdf_max_order=3,
    )
    dlg = SimulationSettingsDialog(settings=src)
    try:
        assert dlg._linear_solver_combo.currentData() == "gmres"
        assert dlg._iterative_max_iter_spin.value() == 512
        assert dlg._iterative_restart_spin.value() == 64
        assert dlg._bdf_max_order_spin.value() == 3

        # Switch + apply.
        dlg._linear_solver_combo.setCurrentIndex(
            dlg._linear_solver_combo.findData("klu")
        )
        dlg._iterative_max_iter_spin.setValue(150)
        dlg._iterative_restart_spin.setValue(25)
        dlg._bdf_max_order_spin.setValue(2)
        dlg._store_settings()

        assert dlg._settings.linear_solver_stack == "klu"
        assert dlg._settings.iterative_solver_max_iterations == 150
        assert dlg._settings.iterative_solver_restart == 25
        assert dlg._settings.bdf_max_order == 2
    finally:
        dlg.deleteLater()


def test_dialog_handles_missing_advanced_fields_gracefully(qapp):
    """Older-style settings without the new fields default to safe values."""

    class _LegacySettings(SimulationSettings):
        pass

    legacy = _LegacySettings()
    # Strip the new attributes off so getattr fallback fires.
    for attr in (
        "linear_solver_stack",
        "iterative_solver_max_iterations",
        "iterative_solver_restart",
        "bdf_max_order",
    ):
        if hasattr(legacy, attr):
            delattr(legacy, attr)

    dlg = SimulationSettingsDialog(settings=legacy)
    try:
        assert dlg._linear_solver_combo.currentData() == "auto"
        assert dlg._iterative_max_iter_spin.value() == 200
        assert dlg._iterative_restart_spin.value() == 30
        assert dlg._bdf_max_order_spin.value() == 5
    finally:
        dlg.deleteLater()
