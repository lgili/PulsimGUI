"""Tests for the PSIM/PLECS-style floating-node convergence helper.

The converter injects an invisible high-value resistor from every
subnet that can't reach ground through a DC-conductive path. Users
draw their topology and the simulator just works — they don't have
to remember the "high-R-to-ground" trick that pre-SPICE-3 days
required.

The helpers are added directly to the backend ``Circuit`` and never
to the GUI dictionary, so the schematic stays clean. Each ghost
resistor is named ``__gmin_<net>`` and recorded in
``circuit.ghost_resistor_records`` for debugging / banner display.
"""
from __future__ import annotations

import pytest

from pulsimgui.services.backend_adapter import BackendLoader


@pytest.fixture(scope="module")
def converter():
    return BackendLoader().backend._converter


def _build(converter, circuit_data: dict):
    """Run the converter and return (count, list of ghost-net names)."""
    circuit = converter.build(circuit_data)
    count = getattr(circuit, "ghost_resistors_injected", 0)
    records = getattr(circuit, "ghost_resistor_records", [])
    return circuit, count, [rec["net"] for rec in records]


def test_no_ghost_when_every_net_reaches_ground(converter) -> None:
    """A plain RC circuit with V→R→C all touching ground needs no help."""
    circuit, count, nets = _build(converter, {
        "components": [
            {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
             "parameters": {"waveform": {"type": "dc", "value": 10.0}}},
            {"id": "r1", "type": "RESISTOR", "name": "R1",
             "parameters": {"resistance": 100.0}},
            {"id": "c1", "type": "CAPACITOR", "name": "C1",
             "parameters": {"capacitance": 1.0e-6}},
        ],
        "node_map": {
            "v1": ["N1", "0"],
            "r1": ["N1", "N2"],
            "c1": ["N2", "0"],
        },
        "node_aliases": {},
    })
    assert count == 0
    assert nets == []


def test_ghost_added_for_capacitor_only_branch_to_floating_net(converter) -> None:
    """An extra capacitor reaching out to N3 (no DC return) → one ghost R
    from N3 to ground.

    This is the canonical failure mode pre-injection: the matrix row for
    N3 contains only the C2 stamp, so it goes singular at DC.
    """
    circuit, count, nets = _build(converter, {
        "components": [
            {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
             "parameters": {"waveform": {"type": "dc", "value": 10.0}}},
            {"id": "r1", "type": "RESISTOR", "name": "R1",
             "parameters": {"resistance": 100.0}},
            {"id": "c1", "type": "CAPACITOR", "name": "C1",
             "parameters": {"capacitance": 1.0e-6}},
            {"id": "c2", "type": "CAPACITOR", "name": "C2",
             "parameters": {"capacitance": 1.0e-6}},
        ],
        "node_map": {
            "v1": ["N1", "0"],
            "r1": ["N1", "N2"],
            "c1": ["N2", "0"],
            "c2": ["N2", "N3"],
        },
        "node_aliases": {},
    })
    assert count == 1
    # The floating subnet is {N3} → ghost lands on it. Net names get
    # prefixed with "N" by the converter's labeller (raw ids → ``N<id>``).
    assert nets == ["NN3"]


def test_ghost_added_for_transformer_isolated_secondary(converter) -> None:
    """A transformer's secondary (S1/S2) is galvanically separated from
    its primary. Without a DC return on the secondary side, both S1 and
    S2 are floating — but they share a subnet (through the load R), so
    a single ghost R is enough.
    """
    circuit, count, nets = _build(converter, {
        "components": [
            {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
             "parameters": {"waveform": {"type": "dc", "value": 100.0}}},
            {"id": "t1", "type": "TRANSFORMER", "name": "T1",
             "parameters": {}},
            {"id": "r2", "type": "RESISTOR", "name": "R2",
             "parameters": {"resistance": 10.0}},
        ],
        "node_map": {
            "v1": ["N1", "0"],
            "t1": ["N1", "0", "N2", "N3"],  # P1, P2, S1, S2
            "r2": ["N2", "N3"],
        },
        "node_aliases": {},
    })
    assert count == 1
    # One of N2/N3 (the smaller name wins for determinism).
    assert nets == ["NN2"]


def test_ghosts_added_per_independent_floating_subnet(converter) -> None:
    """Two separately-floating subnets → two ghosts, one per subnet."""
    circuit, count, nets = _build(converter, {
        "components": [
            {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
             "parameters": {"waveform": {"type": "dc", "value": 10.0}}},
            {"id": "r1", "type": "RESISTOR", "name": "R1",
             "parameters": {"resistance": 100.0}},
            # Floating cap from N1 to A — A is otherwise isolated.
            {"id": "ca", "type": "CAPACITOR", "name": "CA",
             "parameters": {"capacitance": 1.0e-6}},
            # Independent floating cap from N1 to B — B is also isolated.
            {"id": "cb", "type": "CAPACITOR", "name": "CB",
             "parameters": {"capacitance": 1.0e-6}},
        ],
        "node_map": {
            "v1": ["N1", "0"],
            "r1": ["N1", "0"],
            "ca": ["N1", "A"],
            "cb": ["N1", "B"],
        },
        "node_aliases": {},
    })
    assert count == 2
    assert sorted(nets) == ["NA", "NB"]


def test_ghost_resistor_records_carry_metadata(converter) -> None:
    """Each ghost-resistor record carries (name, net, resistance, reason)."""
    circuit, count, nets = _build(converter, {
        "components": [
            {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
             "parameters": {"waveform": {"type": "dc", "value": 10.0}}},
            {"id": "r1", "type": "RESISTOR", "name": "R1",
             "parameters": {"resistance": 100.0}},
            {"id": "c1", "type": "CAPACITOR", "name": "C1",
             "parameters": {"capacitance": 1.0e-6}},
            {"id": "c2", "type": "CAPACITOR", "name": "C2",
             "parameters": {"capacitance": 1.0e-6}},
        ],
        "node_map": {
            "v1": ["N1", "0"],
            "r1": ["N1", "N2"],
            "c1": ["N2", "0"],
            "c2": ["N2", "N3"],
        },
        "node_aliases": {},
    })
    assert count == 1
    records = getattr(circuit, "ghost_resistor_records", [])
    assert len(records) == 1
    rec = records[0]
    assert rec["name"] == "__gmin_NN3"
    assert rec["net"] == "NN3"
    assert rec["resistance"] == 1.0e9
    assert rec["reason"] == "floating-subnet-to-ground"
