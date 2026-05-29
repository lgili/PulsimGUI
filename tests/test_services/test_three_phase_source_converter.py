"""Tests for the GUI → pulsim wiring of the Three-Phase Source component.

Sub-onda C Track 1 lands ``Circuit::add_three_phase_source`` in
pulsim>=0.10.0a1. The PulsimGui converter prefers that helper but
falls back to manual sine-source decomposition for older runtimes.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from pulsimgui.models.component import ComponentType, DEFAULT_PARAMETERS, DEFAULT_PINS
from pulsimgui.services.circuit_converter import CircuitConverter


# ---------------------------------------------------------------------------
# Fake backend
# ---------------------------------------------------------------------------
class _FakeSineParams:
    amplitude: float = 0.0
    frequency: float = 0.0
    offset: float = 0.0
    phase: float = 0.0


class _FakeThreePhaseSourceParams:
    line_to_line_voltage_rms: float = 400.0
    frequency_hz: float = 50.0
    phase_a_deg: float = 0.0
    positive_sequence: bool = True
    unbalance_factor: float = 0.0


class _FakeCircuit:
    """Records calls so tests can assert on the converter's choices."""

    GROUND = -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.three_phase_calls: list[dict[str, Any]] = []
        self.sine_calls: list[dict[str, Any]] = []

    @staticmethod
    def ground() -> int:
        return -1

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_three_phase_source(
        self,
        name: str,
        n_a: int,
        n_b: int,
        n_c: int,
        n_neutral: int,
        params: _FakeThreePhaseSourceParams,
    ) -> None:
        self.three_phase_calls.append(
            {
                "name": name,
                "n_a": n_a,
                "n_b": n_b,
                "n_c": n_c,
                "n_neutral": n_neutral,
                "v_ll_rms": params.line_to_line_voltage_rms,
                "frequency_hz": params.frequency_hz,
                "phase_a_deg": params.phase_a_deg,
                "positive_sequence": params.positive_sequence,
                "unbalance_factor": params.unbalance_factor,
            }
        )

    def add_sine_voltage_source(
        self, name: str, npos: int, nneg: int, params: _FakeSineParams
    ) -> None:
        self.sine_calls.append(
            {
                "name": name,
                "npos": npos,
                "nneg": nneg,
                "amplitude": params.amplitude,
                "frequency": params.frequency,
                "phase": params.phase,
                "offset": params.offset,
            }
        )


class _FakeBackendWithHelper:
    Circuit = _FakeCircuit
    SineParams = _FakeSineParams
    ThreePhaseSourceParams = _FakeThreePhaseSourceParams


class _FakeCircuitNoHelper(_FakeCircuit):
    """Simulates pulsim < 0.10.0a1 — no add_three_phase_source method."""

    add_three_phase_source = None  # type: ignore[assignment]


class _FakeBackendNoHelper:
    Circuit = _FakeCircuitNoHelper
    SineParams = _FakeSineParams
    # No ThreePhaseSourceParams — forces the fallback path.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _three_phase_component(**overrides: Any) -> dict[str, Any]:
    """Build a serialized GUI 3-phase source ready for the converter."""
    params = dict(DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_SOURCE])
    params.update(overrides)
    return {
        "id": "vgrid-1",
        "name": "Vgrid",
        "type": "THREE_PHASE_SOURCE",
        "parameters": params,
    }


def _node_map() -> dict[str, list[str]]:
    """A → B → C → N. The converter's node_map is keyed by component id and
    holds the list of net names in pin-index order."""
    return {"vgrid-1": ["A", "B", "C", "N"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_palette_lists_three_phase_source() -> None:
    """Palette catalog should include the new entry in the 3φ category."""
    from pulsimgui.models.component_catalog import COMPONENT_LIBRARY, QUICK_ADD_COMPONENTS

    three_phase_entry = next(
        (
            item
            for item in COMPONENT_LIBRARY["Three-Phase / Vector Control"]
            if item["type"] == ComponentType.THREE_PHASE_SOURCE
        ),
        None,
    )
    assert three_phase_entry is not None
    # Palette uses the short "3φ Src" label to match its siblings
    # ("3φ VSI", "3φ RL", "1φ/3φ Bridge"). The catalog is the source
    # of truth — don't rename without re-flowing those neighbors too.
    assert three_phase_entry["name"] == "3φ Src"

    quick_add_entry = next(
        (
            entry
            for entry in QUICK_ADD_COMPONENTS
            if entry[0] == ComponentType.THREE_PHASE_SOURCE
        ),
        None,
    )
    assert quick_add_entry is not None
    assert "three phase" in quick_add_entry[2]


def test_pins_and_defaults_registered() -> None:
    """DEFAULT_PINS and DEFAULT_PARAMETERS must cover the new ComponentType."""
    pins = DEFAULT_PINS[ComponentType.THREE_PHASE_SOURCE]
    assert len(pins) == 4
    assert {pin.name for pin in pins} == {"A", "B", "C", "N"}

    params = DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_SOURCE]
    assert params["line_to_line_voltage_rms"] == pytest.approx(400.0)
    assert params["frequency_hz"] == pytest.approx(50.0)
    assert params["positive_sequence"] is True
    assert params["unbalance_factor"] == pytest.approx(0.0)


def test_converter_uses_native_helper_when_available() -> None:
    """When the backend exposes ``add_three_phase_source``, the converter calls it."""
    converter = CircuitConverter(_FakeBackendWithHelper)
    circuit_data = {
        "components": [_three_phase_component()],
        "node_map": _node_map(),
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)

    assert len(circuit.three_phase_calls) == 1
    assert circuit.sine_calls == []
    call = circuit.three_phase_calls[0]
    assert call["name"] == "Vgrid"
    assert call["v_ll_rms"] == pytest.approx(400.0)
    assert call["frequency_hz"] == pytest.approx(50.0)
    assert call["positive_sequence"] is True
    assert call["unbalance_factor"] == pytest.approx(0.0)
    # Node indices were resolved via add_node().
    assert call["n_a"] == 0
    assert call["n_b"] == 1
    assert call["n_c"] == 2
    assert call["n_neutral"] == 3


def test_converter_passes_user_overrides() -> None:
    converter = CircuitConverter(_FakeBackendWithHelper)
    circuit_data = {
        "components": [
            _three_phase_component(
                line_to_line_voltage_rms=230.0,
                frequency_hz=60.0,
                phase_a_deg=15.0,
                positive_sequence=False,
                unbalance_factor=0.05,
            )
        ],
        "node_map": _node_map(),
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    call = circuit.three_phase_calls[0]
    assert call["v_ll_rms"] == pytest.approx(230.0)
    assert call["frequency_hz"] == pytest.approx(60.0)
    assert call["phase_a_deg"] == pytest.approx(15.0)
    assert call["positive_sequence"] is False
    assert call["unbalance_factor"] == pytest.approx(0.05)


def test_converter_falls_back_when_helper_missing() -> None:
    """Older pulsim runtimes get the manual 3-sine decomposition."""
    converter = CircuitConverter(_FakeBackendNoHelper)
    circuit_data = {
        "components": [_three_phase_component()],
        "node_map": _node_map(),
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)

    # The fallback path emits 3 sine sources, no 3-phase calls.
    assert circuit.three_phase_calls == []
    assert len(circuit.sine_calls) == 3

    # Per-phase peak = V_LL_RMS * sqrt(2) / sqrt(3)
    expected_peak = 400.0 * math.sqrt(2.0) / math.sqrt(3.0)
    for call in circuit.sine_calls:
        assert call["amplitude"] == pytest.approx(expected_peak, rel=1e-9)
        assert call["frequency"] == pytest.approx(50.0)

    names = sorted(call["name"] for call in circuit.sine_calls)
    assert names == ["Vgrid__A", "Vgrid__B", "Vgrid__C"]

    # Phase shifts (positive sequence): 0, -2π/3, -4π/3
    by_name = {call["name"]: call for call in circuit.sine_calls}
    assert by_name["Vgrid__A"]["phase"] == pytest.approx(0.0, abs=1e-12)
    assert by_name["Vgrid__B"]["phase"] == pytest.approx(-2.0 * math.pi / 3.0, abs=1e-12)
    assert by_name["Vgrid__C"]["phase"] == pytest.approx(-4.0 * math.pi / 3.0, abs=1e-12)


def test_fallback_respects_unbalance_factor() -> None:
    converter = CircuitConverter(_FakeBackendNoHelper)
    circuit_data = {
        "components": [_three_phase_component(unbalance_factor=0.1)],
        "node_map": _node_map(),
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    by_name = {call["name"]: call for call in circuit.sine_calls}
    nominal_peak = 400.0 * math.sqrt(2.0) / math.sqrt(3.0)
    assert by_name["Vgrid__A"]["amplitude"] == pytest.approx(nominal_peak)
    assert by_name["Vgrid__B"]["amplitude"] == pytest.approx(nominal_peak * 0.9)
    assert by_name["Vgrid__C"]["amplitude"] == pytest.approx(nominal_peak * 1.1)
