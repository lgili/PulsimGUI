"""The simulation engine (+ DSED knobs) must round-trip between the project
model and the runtime service.

Previously ``_apply_project_simulation_settings_to_service`` mirrored most
transient settings but NOT the engine, so a project's saved engine was
silently ignored — a user with a global DSED preference would run DSED even
on a circuit that needs PWL (e.g. an MMC, whose controlled-source arms have
no LTI state-space DSED can extract).
"""
from __future__ import annotations

from pulsimgui.views.main_window import MainWindow


def test_project_engine_overrides_service_on_apply(qapp) -> None:
    window = MainWindow()
    try:
        # User's global preference is DSED, but the open project asks for PWL.
        window._simulation_service.settings.engine = "dsed"
        window._project.simulation_settings.engine = "pwl"
        window._project.simulation_settings.dsed_integrator = "bdf2"

        window._apply_project_simulation_settings_to_service()

        assert window._simulation_service.settings.engine == "pwl"
        assert window._simulation_service.settings.dsed_integrator == "bdf2"
    finally:
        window.close()


def test_service_engine_persists_back_to_project(qapp) -> None:
    window = MainWindow()
    try:
        window._project.simulation_settings.engine = "pwl"
        window._simulation_service.settings.engine = "dsed"
        window._simulation_service.settings.dsed_rtol = 5e-7

        window._apply_simulation_service_settings_to_project()

        assert window._project.simulation_settings.engine == "dsed"
        assert window._project.simulation_settings.dsed_rtol == 5e-7
    finally:
        window.close()
