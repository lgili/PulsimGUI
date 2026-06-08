"""Regression tests for ``examples/24_cmc_svm_cblock.pulsim``.

Example 24 is the showcase example for the pulsim 1.8 ``add_c_block``
"Path B" migration. A 3-phase Conventional Matrix Converter (CMC) is
modeled as 3 controlled voltage sources driven by a SINGLE ``C_BLOCK``
component running **inline-C** code that implements the Casadei–Serra
Space Vector Modulation algorithm.

What these tests pin
--------------------
The structural invariants below catch silent regressions in the
end-to-end pipeline that the showcase example exercises:

  1. The example file exists.
  2. Its schematic has the expected component shape (THREE_PHASE_SOURCE
     × 1, INDUCTOR × 6 = 3 input filter + 3 load, CAPACITOR × 3,
     RESISTOR × 3, C_BLOCK × 1, GROUND ≥ 3).
  3. The ``C_BLOCK`` component carries ``implementation == "source"`` and
     a non-empty ``source_code`` containing the ``Casadei`` sentinel
     (from the algorithm comment) — i.e. the inline-C body survived the
     ``Project.to_dict`` ↔ ``Project.from_dict`` round-trip.
  4. The ``C_BLOCK`` has 3 inputs and 3 outputs.
  5. The converter emits exactly ONE record into
     ``circuit.c_block_records`` with the right topology (3 input nodes
     + 3 output node pairs, each pair ``(<output_node>, "0")``).
  6. The simulation settings target the documented design point
     (``tstop = 0.1 s``, ``dt = 5e-6 s``, ``engine = "pwl"`` because the
     C_BLOCK refuses DSED's analytical fast-path).

These tests deliberately do **NOT** run the simulation — it would slow
down the gate. They just load + convert and assert structure. The
builder script and the README-style preamble at the top of
``scripts/build_example_24.py`` carry the rationale for the design
point itself; the tests here only catch shape-level regressions.
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
    Path(__file__).resolve().parents[2] / "examples" / "24_cmc_svm_cblock.pulsim"
)


@pytest.fixture(scope="module")
def example_circuit_data() -> dict:
    """Load + connectivity-resolve the ex 24 schematic, ready for
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
        "``python scripts/build_example_24.py``."
    )


def test_schematic_has_expected_component_shape(example_circuit_data) -> None:
    """Pin the component-type counts. A missing input filter inductor
    or an extra C_BLOCK would silently change what the example
    demonstrates."""
    components = example_circuit_data["components"]
    by_type: dict[str, int] = {}
    for c in components:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1

    assert by_type.get("THREE_PHASE_SOURCE") == 1, (
        f"Expected exactly 1 THREE_PHASE_SOURCE, got {by_type.get('THREE_PHASE_SOURCE')}"
    )
    # 6 inductors total: 3 input-filter (L_in_a/b/c) + 3 load (L_A/B/C).
    assert by_type.get("INDUCTOR") == 6, (
        f"Expected 6 INDUCTORs (3 input filter + 3 load), got {by_type.get('INDUCTOR')}"
    )
    # 3 input-filter capacitors. No DC link — the matrix converter is
    # AC-AC without intermediate DC storage.
    assert by_type.get("CAPACITOR") == 3, (
        f"Expected 3 CAPACITORs (input filter shunts), got {by_type.get('CAPACITOR')}"
    )
    # 3 load resistors.
    assert by_type.get("RESISTOR") == 3, (
        f"Expected 3 RESISTORs (load), got {by_type.get('RESISTOR')}"
    )
    # THE STAR: exactly one C_BLOCK (the CMC SVM controller).
    assert by_type.get("C_BLOCK") == 1, (
        f"Expected exactly 1 C_BLOCK, got {by_type.get('C_BLOCK')}"
    )
    # At least 3 grounds (grid neutral + filter cap return + load
    # neutral). The builder uses 3 distinct GROUND components — but
    # accept >= 3 in case future refactors split further.
    assert by_type.get("GROUND", 0) >= 3, (
        f"Expected ≥ 3 GROUNDs, got {by_type.get('GROUND', 0)}"
    )


def test_cblock_uses_inline_c_source(example_circuit_data) -> None:
    """The C_BLOCK must carry ``implementation="source"`` AND a non-empty
    ``source_code``. This is the whole point of the example — the
    pulsim 1.8 inline-C ``add_c_block(code=...)`` path.

    The sentinel string ``Casadei`` (from the algorithm comment) pins
    the actual SVM body, not just any random C snippet."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    cb = by_name.get("CMC_SVM")
    assert cb is not None, "CMC_SVM component missing from schematic"
    assert cb["type"] == "C_BLOCK"

    params = cb["parameters"]
    impl = str(params.get("implementation") or "").strip().lower()
    assert impl == "source", (
        f"CMC_SVM implementation={impl!r}, expected 'source' "
        "(pulsim 1.8 inline-C ``add_c_block(code=...)`` path)."
    )
    src = str(params.get("source_code") or "")
    assert src.strip(), (
        "CMC_SVM source_code is empty — the inline-C body did not "
        "survive the Project.from_dict round-trip."
    )
    assert "Casadei" in src, (
        "Sentinel string 'Casadei' missing from CMC_SVM source_code — "
        "the body is not the Casadei-Serra SVM algorithm anymore."
    )


def test_cblock_has_three_inputs_and_three_outputs(example_circuit_data) -> None:
    """3 inputs (filtered grid voltages) + 3 outputs (synthesised load
    phase voltages). A future schema bump that silently re-derives
    ``n_inputs`` / ``n_outputs`` from a pin count change would land
    here."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    cb = by_name["CMC_SVM"]
    params = cb["parameters"]
    assert int(params.get("n_inputs", 0)) == 3, (
        f"n_inputs={params.get('n_inputs')}, expected 3"
    )
    assert int(params.get("n_outputs", 0)) == 3, (
        f"n_outputs={params.get('n_outputs')}, expected 3"
    )


def test_converter_emits_one_cblock_record_with_correct_topology(
    converted_circuit,
) -> None:
    """The converter must produce exactly ONE entry in
    ``circuit.c_block_records`` with:
      * implementation = "source"
      * 3 input nodes
      * 3 output node pairs, each pair = (<output_node>, "0")
        (ground-referenced controlled voltage source)
      * a non-empty source_code containing the Casadei sentinel.
    """
    records = list(getattr(converted_circuit, "c_block_records", []) or [])
    assert len(records) == 1, (
        f"Expected 1 c_block_record, got {len(records)}. The converter "
        "Path B prep is not picking up the CMC_SVM block."
    )
    rec = records[0]
    assert rec["name"] == "CMC_SVM"
    assert rec["implementation"] == "source"
    assert rec["n_inputs"] == 3
    assert rec["n_outputs"] == 3
    assert len(rec["input_nodes"]) == 3, (
        f"input_nodes has {len(rec['input_nodes'])} entries, expected 3"
    )
    # Every input node must be a non-empty string.
    for idx, node in enumerate(rec["input_nodes"]):
        assert isinstance(node, str) and node, (
            f"input_nodes[{idx}] = {node!r} (empty/wrong type)"
        )
    # Output pairs are (node, neg). Each must be (str, "0").
    assert len(rec["output_node_pairs"]) == 3, (
        f"output_node_pairs has {len(rec['output_node_pairs'])} entries, expected 3"
    )
    for idx, pair in enumerate(rec["output_node_pairs"]):
        assert len(pair) == 2, (
            f"output_node_pairs[{idx}] = {pair!r} (expected 2-tuple)"
        )
        out_node, neg_node = pair
        assert isinstance(out_node, str) and out_node, (
            f"output_node_pairs[{idx}][0] = {out_node!r} (empty/wrong type)"
        )
        assert neg_node == "0", (
            f"output_node_pairs[{idx}][1] = {neg_node!r}, expected '0' "
            "(ground-referenced controlled voltage source)"
        )
    assert "Casadei" in rec["source_code"], (
        "Casadei sentinel missing from the converter's record — the "
        "source body did not survive Project.from_dict + CircuitConverter."
    )


def test_simulation_settings_match_design_point(example_circuit_data) -> None:
    """The schematic's ``simulation_settings`` must request the
    documented design point: ``tstop = 0.1 s`` (2.5 output cycles at
    25 Hz), ``dt = 5e-6 s`` (10× oversample of the 50 µs PWM period),
    and the PWL engine (the C_BLOCK refuses DSED's analytical fast-
    path).
    """
    project = example_circuit_data["_raw_project"]
    settings = project.simulation_settings
    assert settings.tstop == pytest.approx(0.1), (
        f"tstop={settings.tstop}, expected 0.1 s (2.5 output cycles at 25 Hz)."
    )
    assert settings.dt == pytest.approx(5e-6), (
        f"dt={settings.dt}, expected 5e-6 (10× oversample of the 50 µs PWM)."
    )
    assert settings.engine == "pwl", (
        f"engine={settings.engine!r}, expected 'pwl' (DSED can't extract LTI "
        "state-space for an inline-C C_BLOCK)."
    )
