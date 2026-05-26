"""Tests for the dynamic PMSM (PMSM device-variant) converter wiring.

Validates that PulsimGui's circuit converter correctly forwards
``ComponentType.PMSM`` entries to ``Circuit::add_pmsm`` from
Pulsim 0.10.0a4+. Capability-gated against older runtimes.
"""
from __future__ import annotations

from typing import Any

import pytest

from pulsimgui.models.component import (
    ComponentType, DEFAULT_PARAMETERS, DEFAULT_PINS,
)
from pulsimgui.services.circuit_converter import (
    CircuitConversionError, CircuitConverter,
)


# ---------------------------------------------------------------------------
# Fake backend mirroring pulsim 0.10.0a4 API
# ---------------------------------------------------------------------------
class _FakePmsmParams:
    name = ""
    Rs = 0.5
    Ld = 2e-3
    Lq = 2e-3
    psi_pm = 0.1
    pole_pairs = 2
    J = 1e-3
    b_friction = 1e-4
    friction_coulomb = 0.0
    i_d_init = 0.0
    i_q_init = 0.0
    omega_init = 0.0
    theta_init = 0.0


class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.pmsm_calls: list[dict[str, Any]] = []
        self.tau_load_calls: list[tuple[str, float]] = []

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_pmsm(self, name, n_a, n_b, n_c, n_n, params):
        self.pmsm_calls.append({
            "name": name,
            "n_a": n_a, "n_b": n_b, "n_c": n_c, "n_n": n_n,
            "Rs": params.Rs, "Ld": params.Ld, "Lq": params.Lq,
            "psi_pm": params.psi_pm,
            "pole_pairs": params.pole_pairs,
            "J": params.J, "b_friction": params.b_friction,
            "friction_coulomb": params.friction_coulomb,
            "i_d_init": params.i_d_init,
            "i_q_init": params.i_q_init,
            "omega_init": params.omega_init,
            "theta_init": params.theta_init,
            "params_name": params.name,
        })

    def set_pmsm_tau_load(self, name: str, tau: float) -> None:
        self.tau_load_calls.append((name, tau))


class _FakeBackendWithPmsm:
    Circuit = _FakeCircuit
    PmsmParams = _FakePmsmParams


class _FakeBackendOld:
    Circuit = _FakeCircuit
    # No PmsmParams → triggers capability error.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pmsm_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.PMSM])
    params.update(overrides)
    return {
        "id": "pmsm-dyn-1", "name": "M1",
        "type": "PMSM",
        "parameters": params,
    }


# ---------------------------------------------------------------------------
# Palette / default registration
# ---------------------------------------------------------------------------
def test_palette_lists_pmsm_dynamic() -> None:
    from pulsimgui.models.component_catalog import COMPONENT_LIBRARY, QUICK_ADD_COMPONENTS
    motors_section = COMPONENT_LIBRARY.get("Motors & Drives", [])
    assert any(item["type"] == ComponentType.PMSM for item in motors_section)
    quick_add = next(
        (entry for entry in QUICK_ADD_COMPONENTS
         if entry[0] == ComponentType.PMSM),
        None,
    )
    assert quick_add is not None
    assert "pmsm dynamic" in quick_add[2]


def test_pmsm_dynamic_pins_and_defaults() -> None:
    pins = DEFAULT_PINS[ComponentType.PMSM]
    assert len(pins) == 4
    assert {p.name for p in pins} == {"A", "B", "C", "N"}
    params = DEFAULT_PARAMETERS[ComponentType.PMSM]
    assert params["Rs"] == pytest.approx(0.5)
    assert params["psi_pm"] == pytest.approx(0.1)
    assert params["pole_pairs"] == 2
    assert params["J"] == pytest.approx(1e-3)
    # Default load torque is zero — converter does not call set_pmsm_tau_load.
    assert params["tau_load"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Converter tests
# ---------------------------------------------------------------------------
def test_pmsm_dynamic_converter_calls_native_helper() -> None:
    converter = CircuitConverter(_FakeBackendWithPmsm)
    circuit_data = {
        "components": [_pmsm_component()],
        "node_map": {"pmsm-dyn-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.pmsm_calls) == 1
    call = circuit.pmsm_calls[0]
    assert call["name"] == "M1"
    assert call["Rs"] == pytest.approx(0.5)
    assert call["Ld"] == pytest.approx(2e-3)
    assert call["Lq"] == pytest.approx(2e-3)
    assert call["psi_pm"] == pytest.approx(0.1)
    assert call["pole_pairs"] == 2
    assert call["J"] == pytest.approx(1e-3)
    assert call["b_friction"] == pytest.approx(1e-4)
    # No tau_load → no extra call to set_pmsm_tau_load.
    assert circuit.tau_load_calls == []


def test_pmsm_dynamic_converter_forwards_overrides() -> None:
    converter = CircuitConverter(_FakeBackendWithPmsm)
    circuit_data = {
        "components": [_pmsm_component(
            Rs=0.3, Ld=5e-3, Lq=8e-3, psi_pm=0.15,
            pole_pairs=4, J=2e-3, b_friction=2e-4,
            omega_init=100.0, theta_init=0.5,
        )],
        "node_map": {"pmsm-dyn-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    call = circuit.pmsm_calls[0]
    assert call["Rs"] == pytest.approx(0.3)
    assert call["Lq"] == pytest.approx(8e-3)
    assert call["psi_pm"] == pytest.approx(0.15)
    assert call["pole_pairs"] == 4
    assert call["J"] == pytest.approx(2e-3)
    assert call["omega_init"] == pytest.approx(100.0)
    assert call["theta_init"] == pytest.approx(0.5)


def test_pmsm_dynamic_converter_forwards_tau_load() -> None:
    converter = CircuitConverter(_FakeBackendWithPmsm)
    circuit_data = {
        "components": [_pmsm_component(tau_load=1.25)],
        "node_map": {"pmsm-dyn-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    # Non-zero tau_load → converter calls set_pmsm_tau_load with the value.
    assert circuit.tau_load_calls == [("M1", 1.25)]


def test_pmsm_dynamic_raises_when_backend_too_old() -> None:
    converter = CircuitConverter(_FakeBackendOld)
    circuit_data = {
        "components": [_pmsm_component()],
        "node_map": {"pmsm-dyn-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    with pytest.raises(CircuitConversionError, match="pulsim>=0.10.0a4"):
        converter.build(circuit_data)
