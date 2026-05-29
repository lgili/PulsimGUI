"""Tests for the diode-bridge & MMC sub-module composite components.

The bridges and MMC cells are not native pulsim 1.5 builders — the
``CircuitConverter`` expands each composite into primitive
``add_diode`` / ``add_mosfet`` / ``add_capacitor`` calls. These tests
mock the backend with a recording fake and assert that each composite
emits the correct number and topology of primitive calls.
"""
from __future__ import annotations

from typing import Any

import pytest

from pulsimgui.models.component import (
    ComponentType, DEFAULT_PARAMETERS, DEFAULT_PINS,
)
from pulsimgui.services.circuit_converter import CircuitConverter


# ---------------------------------------------------------------------------
# Recording fake backend (mirrors the v0-compat shim that pulsim 1.5 uses)
# ---------------------------------------------------------------------------
class _FakeMOSFETParams:
    """Mirrors the v0-compat MOSFETParams bag-of-attributes."""

    def __init__(self) -> None:
        self.is_nmos = True
        self.R_on = 1e-3
        self.R_off = 1e9
        self.extras: dict[str, Any] = {}

    def __setattr__(self, name: str, value: Any) -> None:
        # Mirror v0-compat: dump unknown attrs into ``extras``.
        if name in {"is_nmos", "R_on", "R_off", "extras"}:
            object.__setattr__(self, name, value)
        else:
            try:
                bucket = object.__getattribute__(self, "extras")
            except AttributeError:
                object.__setattr__(self, "extras", {})
                bucket = self.extras
            bucket[name] = value


class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.diode_calls: list[dict[str, Any]] = []
        self.mosfet_calls: list[dict[str, Any]] = []
        self.cap_calls: list[dict[str, Any]] = []

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_diode(self, name: str, anode: int, cathode: int,
                  g_on: float, g_off: float) -> None:
        self.diode_calls.append({
            "name": name, "anode": anode, "cathode": cathode,
            "g_on": g_on, "g_off": g_off,
        })

    def add_mosfet(self, name: str, gate: int, drain: int, source: int,
                   params: _FakeMOSFETParams) -> None:
        self.mosfet_calls.append({
            "name": name, "gate": gate, "drain": drain, "source": source,
            "R_on": params.R_on, "R_off": params.R_off,
        })

    def add_capacitor(self, name: str, n1: int, n2: int,
                      C: float, c0: float = 0.0) -> None:
        self.cap_calls.append({
            "name": name, "n1": n1, "n2": n2, "C": C, "c0": c0,
        })


class _FakeBackend:
    Circuit = _FakeCircuit
    MOSFETParams = _FakeMOSFETParams


# ---------------------------------------------------------------------------
# Catalog & defaults
# ---------------------------------------------------------------------------
def test_catalog_lists_all_new_components() -> None:
    from pulsimgui.models.component_catalog import (
        COMPONENT_LIBRARY, QUICK_ADD_COMPONENTS,
    )
    pc = COMPONENT_LIBRARY.get("Power Conversion", [])
    types_in_section = {item["type"] for item in pc}
    assert ComponentType.SINGLE_PHASE_DIODE_BRIDGE in types_in_section
    assert ComponentType.THREE_PHASE_DIODE_BRIDGE in types_in_section
    assert ComponentType.MMC_CELL in types_in_section

    qa_types = {entry[0] for entry in QUICK_ADD_COMPONENTS}
    for ct in (
        ComponentType.SINGLE_PHASE_DIODE_BRIDGE,
        ComponentType.THREE_PHASE_DIODE_BRIDGE,
        ComponentType.MMC_CELL,
    ):
        assert ct in qa_types, f"{ct.name} missing from QUICK_ADD_COMPONENTS"


def test_default_pins_and_parameters() -> None:
    p1 = DEFAULT_PINS[ComponentType.SINGLE_PHASE_DIODE_BRIDGE]
    assert {p.name for p in p1} == {"AC+", "AC-", "DC+", "DC-"}

    p3 = DEFAULT_PINS[ComponentType.THREE_PHASE_DIODE_BRIDGE]
    assert {p.name for p in p3} == {"A", "B", "C", "DC+", "DC-"}

    # MMC cell's default pin layout is the half-bridge variant (4 pins).
    mmc = DEFAULT_PINS[ComponentType.MMC_CELL]
    assert {p.name for p in mmc} == {"TOP", "BOT", "S1_G", "S2_G"}

    # Defaults present
    assert "g_on" in DEFAULT_PARAMETERS[ComponentType.SINGLE_PHASE_DIODE_BRIDGE]
    mmc_params = DEFAULT_PARAMETERS[ComponentType.MMC_CELL]
    assert "c_cell" in mmc_params
    assert mmc_params["cell_topology"] == "Half-Bridge"


def test_mmc_synchronize_swaps_pin_layout() -> None:
    """Switching ``cell_topology`` should rewrite the pin set."""
    from pulsimgui.models.component import (
        Component, set_mmc_cell_topology,
    )
    comp = Component(type=ComponentType.MMC_CELL)
    # After __post_init__ the default pins (half-bridge layout) are present
    assert len(comp.pins) == 4
    assert {p.name for p in comp.pins} == {"TOP", "BOT", "S1_G", "S2_G"}

    set_mmc_cell_topology(comp, "Full-Bridge")
    assert comp.parameters["cell_topology"] == "Full-Bridge"
    assert len(comp.pins) == 6
    assert {p.name for p in comp.pins} == {
        "TOP", "BOT", "S1_G", "S2_G", "S3_G", "S4_G"
    }

    set_mmc_cell_topology(comp, "Half-Bridge")
    assert len(comp.pins) == 4
    assert {p.name for p in comp.pins} == {"TOP", "BOT", "S1_G", "S2_G"}


# ---------------------------------------------------------------------------
# Single-phase diode bridge: emits exactly 4 diodes (Graetz topology)
# ---------------------------------------------------------------------------
def _bridge_1p_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.SINGLE_PHASE_DIODE_BRIDGE])
    params.update(overrides)
    return {
        "id": "br-1", "name": "BR1",
        "type": "SINGLE_PHASE_DIODE_BRIDGE",
        "parameters": params,
    }


def test_single_phase_bridge_emits_four_diodes() -> None:
    converter = CircuitConverter(_FakeBackend)
    circuit_data = {
        "components": [_bridge_1p_component()],
        "node_map": {"br-1": ["ACp", "ACn", "DCp", "DCn"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.diode_calls) == 4
    assert {c["name"] for c in circuit.diode_calls} == {
        "BR1_D1", "BR1_D2", "BR1_D3", "BR1_D4",
    }
    # Verify Graetz topology by counting unique (anode, cathode) endpoints.
    # The converter normalizes node names with an "N" prefix.
    acp = circuit.nodes["NACp"]
    acn = circuit.nodes["NACn"]
    dcp = circuit.nodes["NDCp"]
    dcn = circuit.nodes["NDCn"]
    pairs = {(c["anode"], c["cathode"]) for c in circuit.diode_calls}
    assert (acp, dcp) in pairs  # D1: AC+ → DC+
    assert (acn, dcp) in pairs  # D2: AC- → DC+
    assert (dcn, acp) in pairs  # D3: DC- → AC+
    assert (dcn, acn) in pairs  # D4: DC- → AC-


# ---------------------------------------------------------------------------
# Three-phase diode bridge: 6 diodes (6-pulse)
# ---------------------------------------------------------------------------
def _bridge_3p_component(**overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_DIODE_BRIDGE])
    params.update(overrides)
    return {
        "id": "br-3", "name": "BR3",
        "type": "THREE_PHASE_DIODE_BRIDGE",
        "parameters": params,
    }


def test_three_phase_bridge_emits_six_diodes() -> None:
    converter = CircuitConverter(_FakeBackend)
    circuit_data = {
        "components": [_bridge_3p_component()],
        "node_map": {"br-3": ["A", "B", "C", "DCp", "DCn"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.diode_calls) == 6
    assert {c["name"] for c in circuit.diode_calls} == {
        "BR3_D1", "BR3_D2", "BR3_D3", "BR3_D4", "BR3_D5", "BR3_D6",
    }
    # Converter normalizes node names with an "N" prefix.
    a = circuit.nodes["NA"]
    b = circuit.nodes["NB"]
    c = circuit.nodes["NC"]
    dcp = circuit.nodes["NDCp"]
    dcn = circuit.nodes["NDCn"]
    pairs = {(call["anode"], call["cathode"]) for call in circuit.diode_calls}
    # Upper bank (phase → DC+)
    assert (a, dcp) in pairs
    assert (b, dcp) in pairs
    assert (c, dcp) in pairs
    # Lower bank (DC- → phase)
    assert (dcn, a) in pairs
    assert (dcn, b) in pairs
    assert (dcn, c) in pairs


# ---------------------------------------------------------------------------
# MMC half-bridge: cell_topology="Half-Bridge" → 2 MOSFETs + 1 cap
# ---------------------------------------------------------------------------
def _mmc_cell_component(topology: str, *, name: str = "HB1",
                          comp_id: str = "hb-1",
                          **overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.MMC_CELL])
    params["cell_topology"] = topology
    params.update(overrides)
    return {
        "id": comp_id, "name": name,
        "type": "MMC_CELL",
        "parameters": params,
    }


def test_mmc_cell_half_bridge_emits_two_switches_and_cap() -> None:
    converter = CircuitConverter(_FakeBackend)
    circuit_data = {
        "components": [_mmc_cell_component("Half-Bridge")],
        "node_map": {"hb-1": ["TOP", "BOT", "G1", "G2"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.mosfet_calls) == 2
    assert {c["name"] for c in circuit.mosfet_calls} == {"HB1_S1", "HB1_S2"}
    assert len(circuit.cap_calls) == 1
    assert circuit.cap_calls[0]["name"] == "HB1_C"
    # Default capacitance 4.7e-3 F
    assert circuit.cap_calls[0]["C"] == pytest.approx(4.7e-3)

    # S1 (upper): drain=internal cap_top, source=TOP
    s1 = next(c for c in circuit.mosfet_calls if c["name"] == "HB1_S1")
    top_idx = circuit.nodes["NTOP"]
    assert s1["source"] == top_idx
    cap_top_idx = circuit.nodes["__HB1_captop"]
    assert s1["drain"] == cap_top_idx
    assert s1["gate"] == circuit.nodes["NG1"]

    # S2 (lower): drain=TOP, source=BOT
    s2 = next(c for c in circuit.mosfet_calls if c["name"] == "HB1_S2")
    bot_idx = circuit.nodes["NBOT"]
    assert s2["drain"] == top_idx
    assert s2["source"] == bot_idx
    assert s2["gate"] == circuit.nodes["NG2"]

    # Cap floats between cap_top and BOT
    cap = circuit.cap_calls[0]
    assert {cap["n1"], cap["n2"]} == {cap_top_idx, bot_idx}


# ---------------------------------------------------------------------------
# MMC full-bridge: cell_topology="Full-Bridge" → 4 MOSFETs + 1 cap
# ---------------------------------------------------------------------------
def test_mmc_cell_full_bridge_emits_four_switches_and_cap() -> None:
    converter = CircuitConverter(_FakeBackend)
    circuit_data = {
        "components": [
            _mmc_cell_component("Full-Bridge", name="FB1", comp_id="fb-1"),
        ],
        "node_map": {"fb-1": ["TOP", "BOT", "G1", "G2", "G3", "G4"]},
        "node_aliases": {},
    }
    circuit = converter.build(circuit_data)
    assert len(circuit.mosfet_calls) == 4
    assert {c["name"] for c in circuit.mosfet_calls} == {
        "FB1_S1", "FB1_S2", "FB1_S3", "FB1_S4",
    }
    assert len(circuit.cap_calls) == 1
    assert circuit.cap_calls[0]["name"] == "FB1_C"

    by_name = {c["name"]: c for c in circuit.mosfet_calls}
    assert by_name["FB1_S1"]["gate"] == circuit.nodes["NG1"]
    assert by_name["FB1_S2"]["gate"] == circuit.nodes["NG2"]
    assert by_name["FB1_S3"]["gate"] == circuit.nodes["NG3"]
    assert by_name["FB1_S4"]["gate"] == circuit.nodes["NG4"]

    # Cap floats across internal cap_top/cap_bot nodes.
    cap_top = circuit.nodes["__FB1_captop"]
    cap_bot = circuit.nodes["__FB1_capbot"]
    cap = circuit.cap_calls[0]
    assert {cap["n1"], cap["n2"]} == {cap_top, cap_bot}
