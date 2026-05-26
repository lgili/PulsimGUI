"""Regression tests for the motor templates shipped in v0.12.0a2.

The DC Motor and PMSM open-loop templates are .pulsim files that mirror the
analytical decoupled-axis models from the Pulsim benchmark suite. These tests
verify:
- Both templates appear under MOTOR_DRIVES category
- Loading produces a non-empty circuit with expected component count
- Component types match the expected R/L/V structure
- Simulation settings are reasonable (tstop > 0, dt > 0)
"""

from __future__ import annotations

import pytest

from pulsimgui.models.component import ComponentType
from pulsimgui.services.template_service import (
    TemplateCategory,
    TemplateService,
)


@pytest.fixture
def svc() -> TemplateService:
    return TemplateService()


def test_motor_templates_registered(svc: TemplateService) -> None:
    """Both motor templates SHALL appear under MOTOR_DRIVES."""
    motor_templates = svc.get_templates_by_category(TemplateCategory.MOTOR_DRIVES)
    ids = {info.id for info in motor_templates}
    assert "dc_motor_open_loop" in ids
    assert "pmsm_open_loop_dq" in ids


def test_dc_motor_template_loads(svc: TemplateService) -> None:
    """DC Motor template SHALL produce a valid Project with armature components."""
    project = svc.create_project_from_template("dc_motor_open_loop")
    assert project is not None
    circuit = project.get_active_circuit()
    assert circuit is not None

    types = [c.type for c in circuit.components.values()]
    # Armature: 2 DC voltage sources (Va, V_back_emf), 1 R, 1 L, 2 GND, 1 scope.
    assert types.count(ComponentType.VOLTAGE_SOURCE) == 2
    assert types.count(ComponentType.RESISTOR) == 1
    assert types.count(ComponentType.INDUCTOR) == 1
    assert types.count(ComponentType.GROUND) == 2
    assert types.count(ComponentType.ELECTRICAL_SCOPE) == 1

    # Sim settings should be transient with sane bounds.
    settings = project.simulation_settings
    assert settings.tstop > 0
    assert settings.dt > 0
    assert settings.tstop > settings.dt

    # Check value of Va and back-EMF (analytical: i_a_ss = (12 - 8) / 0.5 = 8 A)
    by_name = {c.name: c for c in circuit.components.values()}
    assert by_name["Va"].parameters["waveform"]["value"] == pytest.approx(12.0)
    assert by_name["V_back_emf"].parameters["waveform"]["value"] == pytest.approx(8.0)
    assert by_name["R_a"].parameters["resistance"] == pytest.approx(0.5)
    assert by_name["L_a"].parameters["inductance"] == pytest.approx(10e-3)


def test_pmsm_template_loads(svc: TemplateService) -> None:
    """PMSM open-loop template SHALL produce a valid 2-axis circuit."""
    project = svc.create_project_from_template("pmsm_open_loop_dq")
    assert project is not None
    circuit = project.get_active_circuit()

    types = [c.type for c in circuit.components.values()]
    # d-axis: V_d, R_s_d, L_d, GND_d_top, GND_d_bot
    # q-axis: V_q, R_s_q, L_q, V_emf_q, GND_q_bot, GND_emf
    # Plus scope.
    assert types.count(ComponentType.VOLTAGE_SOURCE) == 3  # V_d, V_q, V_emf_q
    assert types.count(ComponentType.RESISTOR) == 2  # R_s_d, R_s_q
    assert types.count(ComponentType.INDUCTOR) == 2  # L_d, L_q
    assert types.count(ComponentType.GROUND) == 4

    by_name = {c.name: c for c in circuit.components.values()}
    # Benchmark values: V_d=0, V_q=12, V_emf_q=8, R_s=0.5, L=2mH
    assert by_name["V_d"].parameters["waveform"]["value"] == pytest.approx(0.0)
    assert by_name["V_q"].parameters["waveform"]["value"] == pytest.approx(12.0)
    assert by_name["V_emf_q"].parameters["waveform"]["value"] == pytest.approx(8.0)
    assert by_name["R_s_d"].parameters["resistance"] == pytest.approx(0.5)
    assert by_name["R_s_q"].parameters["resistance"] == pytest.approx(0.5)
    assert by_name["L_d"].parameters["inductance"] == pytest.approx(2e-3)
    assert by_name["L_q"].parameters["inductance"] == pytest.approx(2e-3)


def test_motor_templates_have_wires(svc: TemplateService) -> None:
    """Wires SHALL exist so the topology is well-defined for the converter."""
    dc = svc.create_project_from_template("dc_motor_open_loop")
    pmsm = svc.create_project_from_template("pmsm_open_loop_dq")
    assert len(dc.get_active_circuit().wires) >= 4
    assert len(pmsm.get_active_circuit().wires) >= 8


def test_motor_templates_have_descriptive_metadata(svc: TemplateService) -> None:
    """The templates' description should mention their analytical reference."""
    dc_info = svc.get_template_info("dc_motor_open_loop")
    pmsm_info = svc.get_template_info("pmsm_open_loop_dq")
    assert dc_info is not None
    assert pmsm_info is not None
    assert "armature" in dc_info.description.lower()
    assert "dq" in pmsm_info.description.lower()
    assert "motor" in dc_info.tags
    assert "pmsm" in pmsm_info.tags
