"""Tests for the 3φ RL Load and PMSM steady-state converter wiring."""
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
# Fake backend
# ---------------------------------------------------------------------------
class _FakeThreePhaseLoadTopologyMember:
    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return f"FakeTopology.{self._name}"


class _FakeThreePhaseLoadTopology:
    Star = _FakeThreePhaseLoadTopologyMember("Star")
    Delta = _FakeThreePhaseLoadTopologyMember("Delta")


class _FakeThreePhaseRLLoadParams:
    resistance_per_phase = 10.0
    inductance_per_phase = 1e-3
    topology = _FakeThreePhaseLoadTopology.Star
    unbalance_factor = 0.0


class _FakePmsmSteadyStateParams:
    R_s = 0.5
    L_s = 2e-3
    lambda_pm = 0.1
    omega_electrical = 314.159
    phase_a_offset_deg = 0.0
    positive_sequence = True


class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.rl_load_calls: list[dict[str, Any]] = []
        self.pmsm_calls: list[dict[str, Any]] = []

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_three_phase_rl_load(self, name, n_a, n_b, n_c, n_n, params):
        self.rl_load_calls.append({
            "name": name, "n_a": n_a, "n_b": n_b, "n_c": n_c, "n_n": n_n,
            "R": params.resistance_per_phase,
            "L": params.inductance_per_phase,
            "topology": params.topology,
            "unbalance": params.unbalance_factor,
        })

    def add_pmsm_steady_state(self, name, n_a, n_b, n_c, n_n, params):
        self.pmsm_calls.append({
            "name": name, "n_a": n_a, "n_b": n_b, "n_c": n_c, "n_n": n_n,
            "R_s": params.R_s, "L_s": params.L_s,
            "lambda_pm": params.lambda_pm,
            "omega_electrical": params.omega_electrical,
            "phase_a_offset_deg": params.phase_a_offset_deg,
            "positive_sequence": params.positive_sequence,
        })


class _FakeBackendWithLoadAndPmsm:
    Circuit = _FakeCircuit
    ThreePhaseRLLoadParams = _FakeThreePhaseRLLoadParams
    ThreePhaseLoadTopology = _FakeThreePhaseLoadTopology
    PmsmSteadyStateParams = _FakePmsmSteadyStateParams


class _FakeBackendOld:
    Circuit = _FakeCircuit
    # No ThreePhaseRLLoadParams or PmsmSteadyStateParams.


# ---------------------------------------------------------------------------
# 3φ RL Load tests
# ---------------------------------------------------------------------------
def _rl_load_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_RL_LOAD])
    params.update(overrides)
    return {
        "id": "rl-1", "name": "RL1",
        "type": "THREE_PHASE_RL_LOAD",
        "parameters": params,
    }


def test_palette_lists_3p_rl_load() -> None:
    from pulsimgui.models.component_catalog import COMPONENT_LIBRARY, QUICK_ADD_COMPONENTS
    motors_section = COMPONENT_LIBRARY.get("Motors & Drives", [])
    assert any(item["type"] == ComponentType.THREE_PHASE_RL_LOAD
               for item in motors_section)
    quick_add = next(
        (entry for entry in QUICK_ADD_COMPONENTS
         if entry[0] == ComponentType.THREE_PHASE_RL_LOAD),
        None,
    )
    assert quick_add is not None
    assert "rl load" in quick_add[2]


def test_3p_rl_load_pins_and_defaults() -> None:
    pins = DEFAULT_PINS[ComponentType.THREE_PHASE_RL_LOAD]
    assert len(pins) == 4
    assert {p.name for p in pins} == {"A", "B", "C", "N"}
    params = DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_RL_LOAD]
    assert params["resistance_per_phase"] == pytest.approx(30.0)
    assert params["topology"] == "Star"


def test_3p_rl_load_converter_calls_native_helper_star() -> None:
    converter = CircuitConverter(_FakeBackendWithLoadAndPmsm)
    circuit_data = {
        "components": [_rl_load_component()],
        "node_map": {"rl-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.rl_load_calls) == 1
    call = circuit.rl_load_calls[0]
    assert call["R"] == pytest.approx(30.0)
    assert call["L"] == pytest.approx(50e-3)
    assert call["topology"] is _FakeThreePhaseLoadTopology.Star


def test_3p_rl_load_converter_handles_delta() -> None:
    converter = CircuitConverter(_FakeBackendWithLoadAndPmsm)
    circuit_data = {
        "components": [_rl_load_component(topology="Delta")],
        "node_map": {"rl-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert circuit.rl_load_calls[0]["topology"] is _FakeThreePhaseLoadTopology.Delta


def test_3p_rl_load_raises_when_backend_too_old() -> None:
    converter = CircuitConverter(_FakeBackendOld)
    circuit_data = {
        "components": [_rl_load_component()],
        "node_map": {"rl-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    with pytest.raises(CircuitConversionError, match="pulsim>=0.10.0a3"):
        converter.build(circuit_data)


# ---------------------------------------------------------------------------
# PMSM tests
# ---------------------------------------------------------------------------
def _pmsm_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.PMSM_STEADY_STATE])
    params.update(overrides)
    return {
        "id": "pmsm-1", "name": "M1",
        "type": "PMSM_STEADY_STATE",
        "parameters": params,
    }


def test_palette_lists_pmsm() -> None:
    from pulsimgui.models.component_catalog import COMPONENT_LIBRARY, QUICK_ADD_COMPONENTS
    motors_section = COMPONENT_LIBRARY.get("Motors & Drives", [])
    assert any(item["type"] == ComponentType.PMSM_STEADY_STATE
               for item in motors_section)
    quick_add = next(
        (entry for entry in QUICK_ADD_COMPONENTS
         if entry[0] == ComponentType.PMSM_STEADY_STATE),
        None,
    )
    assert quick_add is not None
    assert "pmsm" in quick_add[2]


def test_pmsm_pins_and_defaults() -> None:
    pins = DEFAULT_PINS[ComponentType.PMSM_STEADY_STATE]
    assert len(pins) == 4
    assert {p.name for p in pins} == {"A", "B", "C", "N"}
    params = DEFAULT_PARAMETERS[ComponentType.PMSM_STEADY_STATE]
    assert params["R_s"] == pytest.approx(0.5)
    assert params["lambda_pm"] == pytest.approx(0.1)


def test_pmsm_converter_calls_native_helper() -> None:
    converter = CircuitConverter(_FakeBackendWithLoadAndPmsm)
    circuit_data = {
        "components": [_pmsm_component()],
        "node_map": {"pmsm-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.pmsm_calls) == 1
    call = circuit.pmsm_calls[0]
    assert call["R_s"] == pytest.approx(0.5)
    assert call["lambda_pm"] == pytest.approx(0.1)
    assert call["positive_sequence"] is True


def test_pmsm_converter_forwards_overrides() -> None:
    converter = CircuitConverter(_FakeBackendWithLoadAndPmsm)
    circuit_data = {
        "components": [_pmsm_component(
            R_s=0.3, L_s=5e-3, lambda_pm=0.15,
            omega_electrical=628.32, positive_sequence=False,
        )],
        "node_map": {"pmsm-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    call = circuit.pmsm_calls[0]
    assert call["R_s"] == pytest.approx(0.3)
    assert call["lambda_pm"] == pytest.approx(0.15)
    assert call["omega_electrical"] == pytest.approx(628.32)
    assert call["positive_sequence"] is False


def test_pmsm_raises_when_backend_too_old() -> None:
    converter = CircuitConverter(_FakeBackendOld)
    circuit_data = {
        "components": [_pmsm_component()],
        "node_map": {"pmsm-1": ["A", "B", "C", "N"]},
        "node_aliases": {},
    }
    with pytest.raises(CircuitConversionError, match="pulsim>=0.10.0a3"):
        converter.build(circuit_data)
