"""Regression tests for ``examples/25_cmc_switched_svm_cblock.pulsim``.

Example 25 is the **high-fidelity counterpart to example 24** — a real
switched 3×3 Conventional Matrix Converter with 9 TRUE 4-quadrant
``BIDIRECTIONAL_SWITCH`` cells (each lowering to pulsim's ``add_switch``
— a pure symmetric conductance with NO body diode, unlike a MOSFET).
The cells are driven directly by a single ``C_BLOCK`` running inline-C
Venturini-PWM modulation that reads 3 filtered input voltages PLUS 3
output phase currents (6 inputs total) and drives 9 gate outputs — the
most demanding multi-IO use of pulsim 1.8's ``add_c_block`` path B we
have ever shipped.

Why bidirectional switches (not MOSFETs)
----------------------------------------
A matrix cell must conduct both directions ON and block both polarities
OFF. A MOSFET cannot: the GUI shim forces a body diode onto every
MOSFET, and 9 of those form an uncontrolled rectifier that clamps the
output regardless of the gate commands. ``BIDIRECTIONAL_SWITCH`` →
``add_switch`` has no body diode, so the matrix synthesises the real
output. The C_BLOCK also reads the output currents for
current-direction-aware safe commutation.

Input filter damping
--------------------
The input LC filter (L_in + C_in) is paired with an R-C damping branch
on each phase so it settles to the grid voltage (≈ ±339 V) instead of
ringing — without damping the undamped filter resonates and corrupts
the voltage the modulator reads.

What these tests pin
--------------------
  1. The example file exists.
  2. Component shape: THREE_PHASE_SOURCE ×1, INDUCTOR ×6 (3 input filter
     + 3 load), CAPACITOR ×6 (3 main + 3 damping), RESISTOR ×6 (3 load
     + 3 damping), **BIDIRECTIONAL_SWITCH ×9, MOSFET_N ×0**, C_BLOCK ×1,
     GROUND ≥3.
  3. The ``C_BLOCK`` carries ``implementation == "source"``,
     ``n_inputs == 6``, ``n_outputs == 9``, ``sample_time == 5e-6``, and
     a ``source_code`` containing BOTH ``Venturini`` and
     ``BIDIRECTIONAL`` sentinels.
  4. The converter emits ONE ``c_block_records`` entry with 6 input
     nodes + 9 output node pairs ``(<gate_node>, "0")``.
  5. The converter emits 9 ``cblock_gate_drive_descriptors`` — one per
     cell — so every bidirectional switch's gate is bound to a C_BLOCK
     output.
  6. Simulation settings target the design point (tstop=0.05, dt=2e-6,
     engine="pwl").

These tests do NOT run the simulation (too slow for the gate). The
builder's ``__main__`` carries the end-to-end verification.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import pulsim as p

from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "examples" / "25_cmc_switched_svm_cblock.pulsim"
)


@pytest.fixture(scope="module")
def example_circuit_data() -> dict:
    """Load + connectivity-resolve the ex 25 schematic, ready for
    ``CircuitConverter.build``. Module-scoped so the schematic is only
    parsed once across all tests in this file."""
    data = json.loads(EXAMPLE_PATH.read_text())
    project = Project.from_dict(data, path=EXAMPLE_PATH)
    circuit = project.circuits[project.active_circuit]

    node_map_raw = build_node_map(circuit)
    alias_map = build_node_alias_map(circuit, node_map_raw)

    components_list: list[dict] = []
    component_node_map: dict[str, list[str]] = {}
    for c in circuit.components.values():
        comp_id = str(c.id)
        components_list.append({
            "id": comp_id,
            "type": c.type.name,
            "name": c.name,
            "x": c.x, "y": c.y,
            "rotation": c.rotation,
            "parameters": dict(c.parameters),
            "pins": [
                {"index": pin.index, "name": pin.name, "x": pin.x, "y": pin.y}
                for pin in c.pins
            ],
        })
        pin_nodes: list[str] = []
        for pin_idx in range(len(c.pins)):
            raw = node_map_raw.get((comp_id, pin_idx), f"pin_{comp_id}_{pin_idx}")
            pin_nodes.append(alias_map.get(raw, raw))
        component_node_map[comp_id] = pin_nodes

    return {
        "components": components_list,
        "node_map": component_node_map,
        "node_aliases": alias_map,
        "_raw_project": project,
    }


@pytest.fixture(scope="module")
def converted_circuit(example_circuit_data):
    """Run the converter and return the lowered ``Circuit`` object."""
    conv = CircuitConverter(make_compat_module(p))
    return conv.build({
        "components": example_circuit_data["components"],
        "node_map": example_circuit_data["node_map"],
        "node_aliases": example_circuit_data["node_aliases"],
    })


def test_file_exists() -> None:
    assert EXAMPLE_PATH.is_file(), (
        f"Example file missing: {EXAMPLE_PATH}. Rebuild with "
        "``python scripts/build_example_25.py``."
    )


def test_schematic_uses_true_bidirectional_switches(example_circuit_data) -> None:
    """The matrix MUST be 9 ``BIDIRECTIONAL_SWITCH`` cells and ZERO
    ``MOSFET_N`` — a MOSFET here would get a body diode and rectify."""
    components = example_circuit_data["components"]
    by_type: dict[str, int] = {}
    for c in components:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1

    assert by_type.get("BIDIRECTIONAL_SWITCH") == 9, (
        f"Expected 9 BIDIRECTIONAL_SWITCH (3×3 matrix), got "
        f"{by_type.get('BIDIRECTIONAL_SWITCH')}"
    )
    assert by_type.get("MOSFET_N", 0) == 0, (
        f"Expected 0 MOSFET_N — the matrix cells must be true "
        f"bidirectional switches, got {by_type.get('MOSFET_N')}"
    )


def test_schematic_has_expected_component_shape(example_circuit_data) -> None:
    """Pin the rest of the topology: grid, damped input filter, load."""
    components = example_circuit_data["components"]
    by_type: dict[str, int] = {}
    for c in components:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1

    assert by_type.get("THREE_PHASE_SOURCE") == 1
    # 6 inductors: 3 input-filter (L_in_a/b/c) + 3 load (L_A/B/C).
    assert by_type.get("INDUCTOR") == 6, (
        f"Expected 6 INDUCTORs (3 input filter + 3 load), got {by_type.get('INDUCTOR')}"
    )
    # 6 capacitors: 3 main input-filter shunts + 3 R-C damping caps.
    assert by_type.get("CAPACITOR") == 6, (
        f"Expected 6 CAPACITORs (3 main filter + 3 damping), got {by_type.get('CAPACITOR')}"
    )
    # 6 resistors: 3 load + 3 damping.
    assert by_type.get("RESISTOR") == 6, (
        f"Expected 6 RESISTORs (3 load + 3 damping), got {by_type.get('RESISTOR')}"
    )
    assert by_type.get("C_BLOCK") == 1
    assert by_type.get("GROUND", 0) >= 3


def test_cblock_source_carries_both_sentinels(example_circuit_data) -> None:
    """The C_BLOCK must carry ``implementation="source"`` with a
    ``source_code`` containing BOTH ``Venturini`` (the modulation
    algorithm) and ``BIDIRECTIONAL`` (the switch-type marker)."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    cb = by_name.get("CMC_PWM")
    assert cb is not None, "CMC_PWM component missing from schematic"
    assert cb["type"] == "C_BLOCK"

    params = cb["parameters"]
    assert str(params.get("implementation") or "").strip().lower() == "source"
    src = str(params.get("source_code") or "")
    assert src.strip(), "CMC_PWM source_code is empty after the round-trip."
    assert "Venturini" in src, "Sentinel 'Venturini' missing from source_code."
    assert "BIDIRECTIONAL" in src, "Sentinel 'BIDIRECTIONAL' missing from source_code."


def test_cblock_has_six_inputs_nine_outputs_and_5us_sample_time(
    example_circuit_data,
) -> None:
    """6 inputs (3 filtered grid voltages + 3 output phase currents)
    + 9 outputs (gate drives). The 3 current inputs are the user-
    requested output sensing for current-direction-aware commutation.
    ``sample_time`` = 5 µs (10× finer than the 50 µs PWM period)."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    cb = by_name["CMC_PWM"]
    params = cb["parameters"]
    assert int(params.get("n_inputs", 0)) == 6, (
        f"n_inputs={params.get('n_inputs')}, expected 6 "
        "(3 voltages + 3 output currents)"
    )
    assert int(params.get("n_outputs", 0)) == 9, (
        f"n_outputs={params.get('n_outputs')}, expected 9"
    )
    sample_time = float(params.get("sample_time", 0.0) or 0.0)
    assert sample_time == pytest.approx(5.0e-6)


def test_converter_emits_one_cblock_record_with_six_inputs(
    converted_circuit,
) -> None:
    """ONE ``c_block_records`` entry: 6 input nodes (3 voltage + 3
    current sense) + 9 ground-referenced output pairs."""
    records = list(getattr(converted_circuit, "c_block_records", []) or [])
    assert len(records) == 1, f"Expected 1 c_block_record, got {len(records)}."
    rec = records[0]
    assert rec["name"] == "CMC_PWM"
    assert rec["implementation"] == "source"
    assert rec["n_inputs"] == 6
    assert rec["n_outputs"] == 9
    assert rec["sample_time"] == pytest.approx(5.0e-6)
    assert len(rec["input_nodes"]) == 6, (
        f"input_nodes has {len(rec['input_nodes'])} entries, expected 6"
    )
    for idx, node in enumerate(rec["input_nodes"]):
        assert isinstance(node, str) and node, (
            f"input_nodes[{idx}] = {node!r} (empty/wrong type)"
        )
    assert len(rec["output_node_pairs"]) == 9
    for idx, pair in enumerate(rec["output_node_pairs"]):
        assert len(pair) == 2
        out_node, neg_node = pair
        assert isinstance(out_node, str) and out_node
        assert neg_node == "0", (
            f"output_node_pairs[{idx}][1] = {neg_node!r}, expected '0'"
        )
    assert "Venturini" in rec["source_code"]
    assert "BIDIRECTIONAL" in rec["source_code"]


def test_converter_binds_all_nine_switch_gates(converted_circuit) -> None:
    """The gate-drive inference must emit exactly 9 descriptors — one
    per bidirectional-switch cell — so every gate is threshold-driven
    by its C_BLOCK output. Zero descriptors would mean the matrix never
    switches (all cells stuck OFF)."""
    descs = list(
        getattr(converted_circuit, "cblock_gate_drive_descriptors", []) or []
    )
    assert len(descs) == 9, (
        f"Expected 9 gate-drive descriptors (one per cell), got {len(descs)}."
    )
    # Every output index 0..8 is claimed exactly once.
    out_indices = sorted(d["c_block_output_index"] for d in descs)
    assert out_indices == list(range(9)), (
        f"Gate-drive output indices = {out_indices}, expected 0..8."
    )


def test_simulation_settings_match_design_point(example_circuit_data) -> None:
    """tstop=0.05 (≥1 output cycle at 25 Hz), dt=2e-6 (finer than the
    5 µs C_BLOCK sample), engine='pwl' (DSED can't extract an LTI
    state-space for an inline-C C_BLOCK)."""
    project = example_circuit_data["_raw_project"]
    settings = project.simulation_settings
    assert settings.tstop == pytest.approx(0.05)
    assert settings.dt == pytest.approx(2.0e-6)
    assert settings.engine == "pwl"
