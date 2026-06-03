"""Tests for the pulsim 1.6 DSED engine integration.

Covers the full chain:
  1. ``SimulationSettings`` carries the new ``engine`` + DSED knobs
     with sane defaults.
  2. ``normalize_engine`` / ``normalize_dsed_integrator`` handle
     aliases (variable_step → dsed, dopri5 → rk45) and reject typos
     by falling back to safe defaults.
  3. ``Project.SimulationSettings`` round-trips the new fields
     through .pulsim files; legacy projects (no ``engine`` key)
     default to PWL.
  4. ``apply_project_simulation_settings`` mirrors the on-disk
     fields onto the runtime ``SimulationSettings``.
  5. The dialog's engine combo flips the DSED visibility group.
"""
from __future__ import annotations

import pytest

from pulsimgui.models.project import (
    SimulationSettings as ProjectSettings,
)
from pulsimgui.services.simulation_service import (
    SimulationSettings,
    normalize_dsed_integrator,
    normalize_engine,
)


# ---------------------------------------------------------------------------
# Field defaults — pulsim 1.6 picked these; mirror them so the GUI's
# defaults always match what ``simulate(engine='dsed')`` would use
# with no kwargs at all.
# ---------------------------------------------------------------------------
def test_simulation_settings_engine_defaults_to_pwl() -> None:
    """``engine="pwl"`` keeps PulsimGUI byte-identical to v1.4.x for
    any user who hasn't opted into DSED yet."""
    s = SimulationSettings()
    assert s.engine == "pwl"


def test_simulation_settings_dsed_knob_defaults_match_pulsim() -> None:
    """DSED defaults match the pulsim 1.6.1 scheduler defaults so a
    user toggling engine='dsed' without touching anything else gets
    the kernel's sensible behavior."""
    s = SimulationSettings()
    assert s.dsed_rtol == 1e-6
    assert s.dsed_atol == 1e-9
    assert s.dsed_dt_init == 1e-9
    assert s.dsed_integrator == "auto"
    assert s.dsed_stiffness_threshold == 10.0
    assert s.dsed_h_bdf2 == 1e-6


# ---------------------------------------------------------------------------
# Normalizers — must accept legacy / typo'd values and produce a
# kernel-safe canonical value.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("pwl", "pwl"),
    ("PWL", "pwl"),
    ("dsed", "dsed"),
    ("variable", "dsed"),
    ("variable_step", "dsed"),
    ("ped", "dsed"),       # early-draft name
    ("path_based", "dsed"),
    ("fixed", "pwl"),
    ("trapezoidal", "pwl"),
    ("", "pwl"),
    (None, "pwl"),
    ("xyz", "pwl"),
])
def test_normalize_engine(raw, expected) -> None:
    assert normalize_engine(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("auto", "auto"),
    ("AUTO", "auto"),
    ("rk45", "rk45"),
    ("bdf2", "bdf2"),
    ("dopri5", "rk45"),         # DSED's DOPRI5 IS rk45
    ("dormand_prince", "rk45"),
    ("bdf", "bdf2"),
    ("auto_dispatch", "auto"),
    ("", "auto"),
    (None, "auto"),
    ("rk4", "auto"),            # not supported by DSED scheduler
    ("euler", "auto"),
])
def test_normalize_dsed_integrator(raw, expected) -> None:
    assert normalize_dsed_integrator(raw) == expected


# ---------------------------------------------------------------------------
# On-disk round-trip — opening / saving .pulsim files with the new
# fields must not lose information.
# ---------------------------------------------------------------------------
def test_project_settings_engine_round_trips() -> None:
    """to_dict → from_dict preserves every DSED field exactly."""
    src = ProjectSettings(
        engine="dsed",
        dsed_rtol=5e-7,
        dsed_atol=2e-10,
        dsed_dt_init=1e-10,
        dsed_integrator="rk45",
        dsed_stiffness_threshold=25.0,
        dsed_h_bdf2=5e-7,
    )
    rehydrated = ProjectSettings.from_dict(src.to_dict())
    assert rehydrated.engine == "dsed"
    assert rehydrated.dsed_rtol == 5e-7
    assert rehydrated.dsed_atol == 2e-10
    assert rehydrated.dsed_dt_init == 1e-10
    assert rehydrated.dsed_integrator == "rk45"
    assert rehydrated.dsed_stiffness_threshold == 25.0
    assert rehydrated.dsed_h_bdf2 == 5e-7


def test_project_settings_legacy_file_defaults_to_pwl() -> None:
    """A pre-v1.6 .pulsim file has no ``engine`` field. Loading must
    succeed and default to the PWL path so the user's run behaves
    bit-identically to what they had before the upgrade."""
    legacy = {"tstop": 5e-3, "dt": 1e-6, "solver": "auto"}
    settings = ProjectSettings.from_dict(legacy)
    assert settings.engine == "pwl"
    assert settings.dsed_rtol == 1e-6  # default
    assert settings.dsed_integrator == "auto"


# ---------------------------------------------------------------------------
# Project → runtime sync (the bridge that .pulsim load uses).
# ---------------------------------------------------------------------------
def test_apply_project_settings_mirrors_engine_fields(qapp) -> None:
    """``SimulationService.apply_project_simulation_settings`` must
    mirror the new on-disk fields onto the runtime ``SimulationSettings``
    so backend_adapter sees them on the next simulate() call."""
    from pulsimgui.services.simulation_service import SimulationService

    svc = SimulationService()
    # Build a tiny "project" stub carrying the on-disk type.
    class _ProjectStub:
        def __init__(self):
            self.simulation_settings = ProjectSettings(
                engine="dsed",
                dsed_rtol=1e-7,
                dsed_integrator="rk45",
                dsed_stiffness_threshold=15.0,
            )

    svc.apply_project_simulation_settings(_ProjectStub())

    assert svc.settings.engine == "dsed"
    assert svc.settings.dsed_rtol == 1e-7
    assert svc.settings.dsed_integrator == "rk45"
    assert svc.settings.dsed_stiffness_threshold == 15.0


def test_apply_project_settings_mirrors_enable_newton_lm(qapp) -> None:
    """``enable_newton_lm`` persisted in the .pulsim file schema must be
    mirrored onto the runtime ``SimulationSettings`` by
    ``apply_project_simulation_settings`` so ``backend_adapter`` forwards
    it to ``pulsim.simulate`` on the next Run. This is the bridge example
    20 (boost PFC + switched VSI) relies on — that drive only converges
    with LM damping, and the flag must come from the project file rather
    than app preferences on a fresh GUI Run."""
    from pulsimgui.services.simulation_service import SimulationService

    svc = SimulationService()
    # Friendly default: LM damping is ON so first-time users don't hit the
    # Newton stall on switched / closed-loop circuits.
    assert svc.settings.enable_newton_lm is True

    class _ProjectStub:
        def __init__(self):
            self.simulation_settings = ProjectSettings(enable_newton_lm=False)

    svc.apply_project_simulation_settings(_ProjectStub())
    # A project that explicitly disables LM must propagate (expert
    # circuits where Newton dynamics is known to converge cleanly).
    assert svc.settings.enable_newton_lm is False


def test_apply_project_settings_normalises_aliases(qapp) -> None:
    """``engine="variable"`` and ``integrator="dopri5"`` should land
    on the runtime as their canonical equivalents."""
    from pulsimgui.services.simulation_service import SimulationService

    svc = SimulationService()
    class _ProjectStub:
        def __init__(self):
            self.simulation_settings = ProjectSettings(
                engine="variable_step",
                dsed_integrator="dopri5",
            )

    svc.apply_project_simulation_settings(_ProjectStub())
    assert svc.settings.engine == "dsed"
    assert svc.settings.dsed_integrator == "rk45"


# ---------------------------------------------------------------------------
# Dialog UI — engine combo flips DSED visibility group.
# ---------------------------------------------------------------------------
def test_dialog_starts_with_pwl_visible(qapp) -> None:
    """Default settings → PWL selected, DSED knobs all hidden."""
    from pulsimgui.views.dialogs.simulation_settings_dialog import (
        SimulationSettingsDialog,
    )

    settings = SimulationSettings()
    dialog = SimulationSettingsDialog(settings)
    try:
        assert dialog._engine_combo.currentData() == "pwl"
        # The dialog is not shown — ``isVisible`` returns False for
        # everything. ``isHidden`` is the inverse query: only True
        # when ``setVisible(False)`` was explicitly called. That's
        # what ``_apply_engine_visibility`` toggles for the DSED
        # group, so use it directly.
        for widget in dialog._dsed_widgets:
            assert widget.isHidden(), (
                f"DSED widget {widget!r} should be hidden on PWL"
            )
    finally:
        dialog.deleteLater()


def test_dialog_dsed_widgets_become_visible_on_engine_switch(qapp) -> None:
    """Flipping engine→DSED shows the DSED knobs (i.e., none of them
    remain explicitly-hidden) and hides the PWL-only Integration
    method combo."""
    from pulsimgui.views.dialogs.simulation_settings_dialog import (
        SimulationSettingsDialog,
    )

    settings = SimulationSettings()
    dialog = SimulationSettingsDialog(settings)
    try:
        dialog._engine_combo.setCurrentIndex(
            dialog._engine_combo.findData("dsed")
        )
        # On DSED, the group is no longer explicitly-hidden. (We
        # can't assert ``isVisible() == True`` because the dialog
        # itself isn't shown; ``isHidden()`` tracks only the explicit
        # ``setVisible(False)`` flag and is the right query here.)
        for widget in dialog._dsed_widgets:
            assert not widget.isHidden(), (
                f"DSED widget {widget!r} should be un-hidden on DSED"
            )
        # PWL integration combo + label hidden — DSED has its own
        # integrator selector inside the DSED group.
        assert dialog._solver_combo.isHidden()
        assert dialog._solver_label.isHidden()
    finally:
        dialog.deleteLater()


def test_dialog_round_trips_dsed_knobs(qapp) -> None:
    """Load → edit → ``_store_settings`` must land the new values
    onto the dialog's bound ``SimulationSettings`` object."""
    from pulsimgui.views.dialogs.simulation_settings_dialog import (
        SimulationSettingsDialog,
    )

    settings = SimulationSettings()
    dialog = SimulationSettingsDialog(settings)
    try:
        dialog._engine_combo.setCurrentIndex(
            dialog._engine_combo.findData("dsed")
        )
        dialog._dsed_rtol_spin.setValue(2e-7)
        dialog._dsed_atol_spin.setValue(5e-11)
        dialog._dsed_integrator_combo.setCurrentIndex(
            dialog._dsed_integrator_combo.findData("rk45")
        )
        dialog._dsed_stiffness_spin.setValue(20.0)
        dialog._dsed_dt_init_edit.value = 5e-10
        dialog._dsed_h_bdf2_edit.value = 2e-6

        dialog._store_settings()

        assert settings.engine == "dsed"
        assert settings.dsed_rtol == 2e-7
        assert settings.dsed_atol == 5e-11
        assert settings.dsed_integrator == "rk45"
        assert settings.dsed_stiffness_threshold == 20.0
        assert settings.dsed_dt_init == 5e-10
        assert settings.dsed_h_bdf2 == 2e-6
    finally:
        dialog.deleteLater()
