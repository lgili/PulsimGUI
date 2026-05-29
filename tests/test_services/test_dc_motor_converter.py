"""Tests for the GUI → pulsim wiring of the DC Motor component (Pulsim 0.10.0a2)."""

from __future__ import annotations

from typing import Any

import pytest

from pulsimgui.models.component import (
    ComponentType,
    DEFAULT_PARAMETERS,
    DEFAULT_PINS,
)
from pulsimgui.services.circuit_converter import (
    CircuitConversionError,
    CircuitConverter,
)


# ---------------------------------------------------------------------------
# Fake backend (mirrors the pattern used for 3-phase tests)
# ---------------------------------------------------------------------------
class _FakeDcMotorParams:
    name = ""
    R_a = 1.0
    L_a = 1e-3
    K_e = 0.05
    K_t = 0.05
    J = 1e-4
    b = 1e-5
    i_a_init = 0.0
    omega_init = 0.0
    theta_init = 0.0


class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.dc_motor_calls: list[dict[str, Any]] = []
        self.tau_load_calls: list[tuple[str, float]] = []

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_dc_motor(
        self, name: str, n_plus: int, n_minus: int, params: _FakeDcMotorParams
    ) -> None:
        self.dc_motor_calls.append(
            {
                "name": name,
                "n_plus": n_plus,
                "n_minus": n_minus,
                "R_a": params.R_a,
                "L_a": params.L_a,
                "K_e": params.K_e,
                "K_t": params.K_t,
                "J": params.J,
                "b": params.b,
                "i_a_init": params.i_a_init,
                "omega_init": params.omega_init,
                "theta_init": params.theta_init,
            }
        )

    def set_motor_tau_load(self, name: str, tau: float) -> None:
        self.tau_load_calls.append((name, tau))


class _FakeBackendWithMotor:
    Circuit = _FakeCircuit
    DcMotorParams = _FakeDcMotorParams


class _FakeBackendWithoutMotor:
    Circuit = _FakeCircuit
    # No DcMotorParams — simulates an older Pulsim runtime.


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def _dc_motor_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.DC_MOTOR])
    params.update(overrides)
    return {
        "id": "m1",
        "name": "M1",
        "type": "DC_MOTOR",
        "parameters": params,
    }


def test_palette_lists_dc_motor() -> None:
    from pulsimgui.models.component_catalog import (
        COMPONENT_LIBRARY,
        QUICK_ADD_COMPONENTS,
    )

    motors_section = COMPONENT_LIBRARY.get("Motors & Drives", [])
    assert any(item["type"] == ComponentType.DC_MOTOR for item in motors_section)

    quick_add = next(
        (entry for entry in QUICK_ADD_COMPONENTS if entry[0] == ComponentType.DC_MOTOR),
        None,
    )
    assert quick_add is not None
    assert "motor" in quick_add[2]


def test_default_pins_and_parameters_registered() -> None:
    pins = DEFAULT_PINS[ComponentType.DC_MOTOR]
    assert len(pins) == 2
    assert {pin.name for pin in pins} == {"A+", "A-"}

    params = DEFAULT_PARAMETERS[ComponentType.DC_MOTOR]
    assert params["R_a"] == pytest.approx(0.5)
    assert params["L_a"] == pytest.approx(10e-3)
    assert params["K_e"] == pytest.approx(0.05)
    assert params["J"] == pytest.approx(1e-4)
    assert params["tau_load"] == pytest.approx(0.0)


def test_converter_calls_add_dc_motor_when_backend_supports_it() -> None:
    converter = CircuitConverter(_FakeBackendWithMotor)
    circuit_data = {
        "components": [_dc_motor_component()],
        "node_map": {"m1": ["arm_pos", "arm_neg"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.dc_motor_calls) == 1
    call = circuit.dc_motor_calls[0]
    assert call["name"] == "M1"
    assert call["R_a"] == pytest.approx(0.5)
    assert call["K_t"] == pytest.approx(0.05)
    assert call["J"] == pytest.approx(1e-4)
    # Default tau_load=0 → set_motor_tau_load should NOT be called.
    assert circuit.tau_load_calls == []


def test_converter_passes_tau_load_when_non_zero() -> None:
    converter = CircuitConverter(_FakeBackendWithMotor)
    circuit_data = {
        "components": [_dc_motor_component(tau_load=0.05)],
        "node_map": {"m1": ["arm_pos", "arm_neg"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert circuit.dc_motor_calls
    assert circuit.tau_load_calls == [("M1", 0.05)]


def test_converter_forwards_user_overrides() -> None:
    converter = CircuitConverter(_FakeBackendWithMotor)
    circuit_data = {
        "components": [
            _dc_motor_component(
                R_a=0.25, L_a=5e-3, K_e=0.08, K_t=0.08,
                J=2e-4, b=2e-5, omega_init=10.0,
            )
        ],
        "node_map": {"m1": ["arm_pos", "arm_neg"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    call = circuit.dc_motor_calls[0]
    assert call["R_a"] == pytest.approx(0.25)
    assert call["L_a"] == pytest.approx(5e-3)
    assert call["K_e"] == pytest.approx(0.08)
    assert call["K_t"] == pytest.approx(0.08)
    assert call["J"] == pytest.approx(2e-4)
    assert call["omega_init"] == pytest.approx(10.0)


def test_converter_raises_when_backend_too_old() -> None:
    converter = CircuitConverter(_FakeBackendWithoutMotor)
    circuit_data = {
        "components": [_dc_motor_component()],
        "node_map": {"m1": ["arm_pos", "arm_neg"]},
        "node_aliases": {},
    }
    with pytest.raises(CircuitConversionError, match="pulsim>=0.10.0a2"):
        converter.build(circuit_data)
