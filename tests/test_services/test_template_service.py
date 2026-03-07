"""Tests for template loading from full example projects."""

from __future__ import annotations

from pathlib import Path

import pytest

import pulsimgui.services.template_service as template_service_module
from pulsimgui.models.component import ComponentType
from pulsimgui.services.template_service import TemplateService
from pulsimgui.utils.net_utils import build_node_map


@pytest.mark.parametrize(
    ("template_id", "expected_component_type"),
    [
        ("buck_converter", ComponentType.PWM_GENERATOR),
        ("boost_converter", ComponentType.PWM_GENERATOR),
        ("flyback_converter", ComponentType.TRANSFORMER),
        ("buck_converter_closed_loop", ComponentType.PI_CONTROLLER),
    ],
)
def test_template_circuits_are_loaded_from_examples_with_wiring(
    template_id: str,
    expected_component_type: ComponentType,
) -> None:
    """Each converter template should load a fully wired circuit from examples."""
    circuit = TemplateService.create_circuit_from_template(template_id)

    assert circuit is not None
    assert len(circuit.components) > 0
    assert len(circuit.wires) > 0

    component_types = {component.type for component in circuit.components.values()}
    assert expected_component_type in component_types

    # Example-based templates should include signal observation blocks out of the box.
    assert ComponentType.ELECTRICAL_SCOPE in component_types
    assert ComponentType.VOLTAGE_PROBE in component_types


def test_closed_loop_buck_template_contains_control_chain() -> None:
    """Closed-loop template should expose basic control blocks for feedback tuning."""
    circuit = TemplateService.create_circuit_from_template("buck_converter_closed_loop")

    assert circuit is not None
    component_types = {component.type for component in circuit.components.values()}

    assert ComponentType.CONSTANT in component_types
    assert ComponentType.SUBTRACTOR in component_types
    assert ComponentType.PI_CONTROLLER in component_types


def test_closed_loop_buck_template_has_no_self_loop_wires() -> None:
    """Closed-loop template should not contain algebraic self-loop wiring artifacts."""
    circuit = TemplateService.create_circuit_from_template("buck_converter_closed_loop")
    assert circuit is not None

    for wire in circuit.wires.values():
        sc = wire.start_connection
        ec = wire.end_connection
        if not sc or not ec:
            continue
        assert not (
            sc.component_id == ec.component_id and sc.pin_index == ec.pin_index
        ), f"Invalid self-loop wire on {sc.component_id}:{sc.pin_index}"


def test_closed_loop_buck_template_wires_pi_out_to_pwm_duty_and_error_polarity() -> None:
    """Control wiring must be setpoint-minus-feedback and PI output must drive PWM duty."""
    circuit = TemplateService.create_circuit_from_template("buck_converter_closed_loop")
    assert circuit is not None

    by_name = {component.name: component for component in circuit.components.values()}
    required = {"PI1", "PWM1", "SUB1", "X1", "Xout"}
    assert required.issubset(by_name.keys())

    node_map = build_node_map(circuit)

    pi_out_node = node_map[(str(by_name["PI1"].id), 1)]
    pwm_duty_node = node_map[(str(by_name["PWM1"].id), 1)]
    assert pi_out_node == pwm_duty_node

    setpoint_node = node_map[(str(by_name["X1"].id), 0)]
    feedback_node = node_map[(str(by_name["Xout"].id), 2)]
    subtractor_in1 = node_map[(str(by_name["SUB1"].id), 0)]
    subtractor_in2 = node_map[(str(by_name["SUB1"].id), 1)]

    assert subtractor_in1 == setpoint_node
    assert subtractor_in2 == feedback_node


def test_template_project_loads_with_saved_simulation_settings() -> None:
    """Project-based template loading should preserve persisted simulation settings."""
    project = TemplateService.create_project_from_template("buck_converter_closed_loop")

    assert project is not None
    assert project.active_circuit == "main"
    assert project.get_active_circuit().wires
    assert project.simulation_settings.tstop > 0.0
    assert project.simulation_settings.dt > 0.0


def test_buck_template_uses_robust_transient_defaults() -> None:
    """Buck template should ship with convergence-safe transient defaults."""
    project = TemplateService.create_project_from_template("buck_converter")

    assert project is not None
    settings = project.simulation_settings
    assert settings.transient_robust_mode is True
    assert settings.transient_auto_regularize is True
    assert settings.max_iterations >= 50


def test_template_loading_falls_back_to_packaged_resources(monkeypatch) -> None:
    """Release builds should load templates from bundled resources."""

    monkeypatch.setattr(
        template_service_module,
        "_candidate_example_paths",
        lambda _example_file: [Path("/nonexistent/template/path.pulsim")],
    )

    project = TemplateService.create_project_from_template("buck_converter")

    assert project is not None
    circuit = project.get_active_circuit()
    assert len(circuit.components) > 0
    assert len(circuit.wires) > 0
    assert project.simulation_settings.transient_robust_mode is True
    assert project.simulation_settings.transient_auto_regularize is True
