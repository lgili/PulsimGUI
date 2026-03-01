"""Tests for template loading from full example projects."""

from __future__ import annotations

import pytest

from pulsimgui.models.component import ComponentType
from pulsimgui.services.template_service import TemplateService


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


def test_template_project_loads_with_saved_simulation_settings() -> None:
    """Project-based template loading should preserve persisted simulation settings."""
    project = TemplateService.create_project_from_template("buck_converter_closed_loop")

    assert project is not None
    assert project.active_circuit == "main"
    assert project.get_active_circuit().wires
    assert project.simulation_settings.tstop > 0.0
    assert project.simulation_settings.dt > 0.0
