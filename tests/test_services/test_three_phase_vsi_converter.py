"""Tests for the 3-Phase VSI palette → converter wiring.

Validates that PulsimGui's circuit converter correctly forwards
``ComponentType.THREE_PHASE_VSI`` entries to ``Circuit::add_three_phase_vsi``
from Pulsim 0.10.0a5+. Capability-gated against older runtimes.
"""
from __future__ import annotations

from typing import Any

import pytest

from pulsimgui.models.component import (
    ComponentType, DEFAULT_PARAMETERS, DEFAULT_PINS,
)
from pulsimgui.services.circuit_converter import CircuitConverter


# ---------------------------------------------------------------------------
# Fake backend mirroring pulsim 0.10.0a5 API surface
# ---------------------------------------------------------------------------
class _FakeThreePhaseVsiParams:
    v_gate_on = 12.0
    v_gate_off = 0.0
    switching_frequency_hz = 10e3
    modulation_index = 0.8
    modulation_frequency_hz = 50.0
    phase_a_deg = 0.0
    positive_sequence = True
    mosfet_r_on_ohm = 0.01
    mosfet_vth = 1.0


class _FakeBuilder:
    """Mirrors the pulsim 1.5+ raw ``CircuitBuilder`` surface that the
    converter's VSI fallback calls into via ``circuit._builder``."""

    def __init__(self) -> None:
        self.sine_calls: list[dict[str, Any]] = []

    def add_sine_voltage_source(self, name, n_pos, n_neg,
                                  v_dc, v_amplitude, frequency, phase):
        self.sine_calls.append({
            "name": name, "n_pos": n_pos, "n_neg": n_neg,
            "v_dc": v_dc, "v_amplitude": v_amplitude,
            "frequency": frequency, "phase": phase,
        })


class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.vsi_calls: list[dict[str, Any]] = []
        # ``_builder`` is the v1.5+ raw kernel handle the VSI fallback
        # uses for ``add_sine_voltage_source``. Exposed only on the
        # "no-native-VSI" path; the legacy native-builder path doesn't
        # touch it.
        self._builder = _FakeBuilder()

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def _name_of(self, node_id: int) -> str:
        """Reverse lookup used by the VSI fallback to resolve node names
        for the raw kernel calls."""
        if int(node_id) == -1:
            return "gnd"
        for name, idx in self.nodes.items():
            if idx == int(node_id):
                return name
        raise KeyError(node_id)

    def add_three_phase_vsi(
        self, name, n_vdc_pos, n_vdc_neg, n_a, n_b, n_c, params,
    ):
        self.vsi_calls.append({
            "name": name,
            "n_vdc_pos": n_vdc_pos, "n_vdc_neg": n_vdc_neg,
            "n_a": n_a, "n_b": n_b, "n_c": n_c,
            "switching_frequency_hz": params.switching_frequency_hz,
            "modulation_index": params.modulation_index,
            "modulation_frequency_hz": params.modulation_frequency_hz,
            "phase_a_deg": params.phase_a_deg,
            "positive_sequence": params.positive_sequence,
            "v_gate_on": params.v_gate_on,
            "v_gate_off": params.v_gate_off,
            "mosfet_r_on_ohm": params.mosfet_r_on_ohm,
            "mosfet_vth": params.mosfet_vth,
        })


class _FakeBackendWithVsi:
    Circuit = _FakeCircuit
    ThreePhaseVsiParams = _FakeThreePhaseVsiParams


class _FakeBackendOld:
    Circuit = _FakeCircuit
    # No ThreePhaseVsiParams → triggers capability error.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _vsi_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_VSI])
    params.update(overrides)
    return {
        "id": "vsi-1", "name": "INV1",
        "type": "THREE_PHASE_VSI",
        "parameters": params,
    }


# ---------------------------------------------------------------------------
# Palette / pins / defaults
# ---------------------------------------------------------------------------
def test_palette_lists_3_phase_vsi() -> None:
    from pulsimgui.models.component_catalog import (
        COMPONENT_LIBRARY, QUICK_ADD_COMPONENTS,
    )
    motors_section = COMPONENT_LIBRARY.get("Motors & Drives", [])
    assert any(item["type"] == ComponentType.THREE_PHASE_VSI
               for item in motors_section)
    quick_add = next(
        (entry for entry in QUICK_ADD_COMPONENTS
         if entry[0] == ComponentType.THREE_PHASE_VSI),
        None,
    )
    assert quick_add is not None
    assert "vsi" in quick_add[2]
    # pt-BR keyword present too
    assert any("inversor" in kw for kw in quick_add[2])


def test_3_phase_vsi_pins_and_defaults() -> None:
    pins = DEFAULT_PINS[ComponentType.THREE_PHASE_VSI]
    assert len(pins) == 5
    assert {p.name for p in pins} == {"VDC+", "VDC-", "A", "B", "C"}
    params = DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_VSI]
    assert params["switching_frequency_hz"] == pytest.approx(10e3)
    assert params["modulation_index"] == pytest.approx(0.8)
    assert params["modulation_frequency_hz"] == pytest.approx(50.0)
    assert params["positive_sequence"] is True


# ---------------------------------------------------------------------------
# Converter tests
# ---------------------------------------------------------------------------
def test_vsi_converter_calls_native_helper() -> None:
    converter = CircuitConverter(_FakeBackendWithVsi)
    circuit_data = {
        "components": [_vsi_component()],
        "node_map": {"vsi-1": ["VDC+", "VDC-", "A", "B", "C"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.vsi_calls) == 1
    call = circuit.vsi_calls[0]
    assert call["name"] == "INV1"
    assert call["switching_frequency_hz"] == pytest.approx(10e3)
    assert call["modulation_index"] == pytest.approx(0.8)
    assert call["modulation_frequency_hz"] == pytest.approx(50.0)
    assert call["positive_sequence"] is True
    assert call["v_gate_on"] == pytest.approx(12.0)
    assert call["mosfet_r_on_ohm"] == pytest.approx(0.01)


def test_vsi_converter_forwards_overrides() -> None:
    converter = CircuitConverter(_FakeBackendWithVsi)
    circuit_data = {
        "components": [_vsi_component(
            switching_frequency_hz=20e3,
            modulation_index=0.95,
            modulation_frequency_hz=60.0,
            phase_a_deg=30.0,
            positive_sequence=False,
            v_gate_on=15.0,
            mosfet_r_on_ohm=0.025,
            mosfet_vth=2.5,
        )],
        "node_map": {"vsi-1": ["VDC+", "VDC-", "A", "B", "C"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    call = circuit.vsi_calls[0]
    assert call["switching_frequency_hz"] == pytest.approx(20e3)
    assert call["modulation_index"] == pytest.approx(0.95)
    assert call["modulation_frequency_hz"] == pytest.approx(60.0)
    assert call["phase_a_deg"] == pytest.approx(30.0)
    assert call["positive_sequence"] is False
    assert call["v_gate_on"] == pytest.approx(15.0)
    assert call["mosfet_r_on_ohm"] == pytest.approx(0.025)
    assert call["mosfet_vth"] == pytest.approx(2.5)


def test_vsi_falls_back_to_three_sines_when_native_builder_missing() -> None:
    """Backends without ``add_three_phase_vsi`` (pulsim 1.5+ retired
    the native helper) fall back to a behavioral 3-sine averaged
    model. This keeps existing GUI projects loadable without forcing
    every user to manually rebuild their VSI from primitives.
    """
    converter = CircuitConverter(_FakeBackendOld)
    circuit_data = {
        "components": [_vsi_component(
            modulation_index=0.8,
            modulation_frequency_hz=50.0,
            phase_a_deg=0.0,
            positive_sequence=True,
        )],
        "node_map": {"vsi-1": ["VDC+", "VDC-", "A", "B", "C"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    # Should have emitted 3 sine sources (one per phase).
    sine_calls = circuit._builder.sine_calls
    assert len(sine_calls) == 3
    names = {c["name"] for c in sine_calls}
    assert names == {"INV1_VA", "INV1_VB", "INV1_VC"}

    # All three reference VDC- and share the same DC offset (= V_DC/2).
    import math
    for call in sine_calls:
        assert call["n_neg"] == "NVDC-"  # converter's normalized name
        assert call["frequency"] == pytest.approx(50.0)
        # Default V_DC_nominal is 400 → half-bus = 200, amplitude = 0.8 * 200
        assert call["v_dc"] == pytest.approx(200.0)
        assert call["v_amplitude"] == pytest.approx(160.0)

    # Phases shifted 120° apart (in radians, positive sequence).
    by_name = {c["name"]: c["phase"] for c in sine_calls}
    assert by_name["INV1_VA"] == pytest.approx(0.0)
    assert by_name["INV1_VB"] == pytest.approx(-2.0 * math.pi / 3.0)
    assert by_name["INV1_VC"] == pytest.approx(-4.0 * math.pi / 3.0)
