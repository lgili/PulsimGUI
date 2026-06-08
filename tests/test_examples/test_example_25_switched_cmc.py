"""Regression tests for ``examples/25_cmc_switched_svm_cblock.pulsim``.

Example 25 is the **high-fidelity counterpart to example 24** — a real
switched 3×3 Conventional Matrix Converter with 9 ``MOSFET_N``
bidirectional switches driven directly by a single ``C_BLOCK`` running
inline-C Venturini-PWM modulation (3 inputs, 9 outputs — the most
demanding multi-IO use of pulsim 1.8's ``add_c_block`` path B we have
ever shipped).

What these tests pin
--------------------
The structural invariants below catch silent regressions in the
end-to-end pipeline that the showcase example exercises:

  1. The example file exists.
  2. Its schematic has the expected component shape (THREE_PHASE_SOURCE
     × 1, INDUCTOR × 6 = 3 input filter + 3 load, CAPACITOR × 3,
     RESISTOR × 3, MOSFET_N × 9, C_BLOCK × 1, GROUND × 3).
  3. The ``C_BLOCK`` component carries ``implementation == "source"``,
     ``n_inputs == 3``, ``n_outputs == 9``, ``sample_time == 5e-6``,
     and a non-empty ``source_code`` containing the ``Venturini``
     sentinel — i.e. the inline-C body survived the
     ``Project.to_dict`` ↔ ``Project.from_dict`` round-trip.
  4. The converter emits exactly ONE entry in
     ``circuit.c_block_records`` with 3 input nodes and 9 output node
     pairs, each pair ``(<output_node>, "0")``.
  5. The simulation settings target the documented design point
     (``tstop = 0.05 s``, ``dt = 2e-6 s``, ``engine = "pwl"``).
  6. The ``sample_time`` on the C_BLOCK is 5e-6 (matches the spec —
     finer than the 50 µs PWM period for clean sub-period resolution).

These tests deliberately do **NOT** run the simulation — it would slow
the gate down. They just load + convert and assert structure. The
builder script's ``__main__`` carries the end-to-end verification (both
through the GUI pipeline and via a handbuilt CircuitBuilder + Python
switch_fn that demonstrates pulsim 1.8 CAN simulate the intended
switched CMC). See the docstring on ``scripts/build_example_25.py`` for
the architectural finding about gate-binding under the GUI converter's
current ``assemble_switch_fn`` path.
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


def test_schematic_has_expected_component_shape(example_circuit_data) -> None:
    """Pin the component-type counts. A missing input filter inductor
    or an extra MOSFET would silently change what the example
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
    # 3 input-filter capacitors. No DC link — AC-AC without storage.
    assert by_type.get("CAPACITOR") == 3, (
        f"Expected 3 CAPACITORs (input filter shunts), got {by_type.get('CAPACITOR')}"
    )
    # 3 load resistors.
    assert by_type.get("RESISTOR") == 3, (
        f"Expected 3 RESISTORs (load), got {by_type.get('RESISTOR')}"
    )
    # THE STAR: exactly 9 MOSFETs forming the 3×3 matrix.
    assert by_type.get("MOSFET_N") == 9, (
        f"Expected exactly 9 MOSFET_Ns (3×3 matrix), got {by_type.get('MOSFET_N')}"
    )
    # Exactly one C_BLOCK.
    assert by_type.get("C_BLOCK") == 1, (
        f"Expected exactly 1 C_BLOCK, got {by_type.get('C_BLOCK')}"
    )
    # At least 3 grounds (grid neutral + filter cap return + load neutral).
    assert by_type.get("GROUND", 0) >= 3, (
        f"Expected ≥ 3 GROUNDs, got {by_type.get('GROUND', 0)}"
    )


def test_cblock_uses_inline_c_source_with_venturini_sentinel(
    example_circuit_data,
) -> None:
    """The C_BLOCK must carry ``implementation="source"`` AND a non-empty
    ``source_code`` containing the sentinel string ``Venturini`` (from
    the algorithm comment). This is the whole point of the example —
    the pulsim 1.8 inline-C ``add_c_block(code=...)`` path."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    cb = by_name.get("CMC_PWM")
    assert cb is not None, "CMC_PWM component missing from schematic"
    assert cb["type"] == "C_BLOCK"

    params = cb["parameters"]
    impl = str(params.get("implementation") or "").strip().lower()
    assert impl == "source", (
        f"CMC_PWM implementation={impl!r}, expected 'source' "
        "(pulsim 1.8 inline-C ``add_c_block(code=...)`` path)."
    )
    src = str(params.get("source_code") or "")
    assert src.strip(), (
        "CMC_PWM source_code is empty — the inline-C body did not "
        "survive the Project.from_dict round-trip."
    )
    assert "Venturini" in src, (
        "Sentinel string 'Venturini' missing from CMC_PWM source_code — "
        "the body is not the Venturini PWM algorithm anymore."
    )


def test_cblock_has_three_inputs_nine_outputs_and_5us_sample_time(
    example_circuit_data,
) -> None:
    """3 inputs (filtered grid voltages) + 9 outputs (gate drives for
    the 3×3 MOSFET matrix). ``sample_time`` must be 5 µs — 10× finer
    than the 50 µs PWM period so the within-period Venturini segment
    progression is correctly resolved.

    This is the most demanding multi-IO use of pulsim 1.8's
    ``add_c_block`` path B (3-in / 9-out) we have ever shipped.
    """
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    cb = by_name["CMC_PWM"]
    params = cb["parameters"]
    assert int(params.get("n_inputs", 0)) == 3, (
        f"n_inputs={params.get('n_inputs')}, expected 3"
    )
    assert int(params.get("n_outputs", 0)) == 9, (
        f"n_outputs={params.get('n_outputs')}, expected 9"
    )
    sample_time = float(params.get("sample_time", 0.0) or 0.0)
    assert sample_time == pytest.approx(5.0e-6), (
        f"sample_time={sample_time}, expected 5e-6 (5 µs = 10× finer "
        "than the 50 µs PWM period)."
    )


def test_converter_emits_one_cblock_record_with_correct_topology(
    converted_circuit,
) -> None:
    """The converter must produce exactly ONE entry in
    ``circuit.c_block_records`` with:
      * implementation = "source"
      * 3 input nodes (filtered Va/Vb/Vc grid voltages)
      * 9 output node pairs, each pair = (<output_node>, "0")
        (ground-referenced controlled voltage source on each gate node)
      * non-empty source_code containing the Venturini sentinel.
    """
    records = list(getattr(converted_circuit, "c_block_records", []) or [])
    assert len(records) == 1, (
        f"Expected 1 c_block_record, got {len(records)}. The converter "
        "Path B prep is not picking up the CMC_PWM block."
    )
    rec = records[0]
    assert rec["name"] == "CMC_PWM"
    assert rec["implementation"] == "source"
    assert rec["n_inputs"] == 3
    assert rec["n_outputs"] == 9
    assert rec["sample_time"] == pytest.approx(5.0e-6)
    assert len(rec["input_nodes"]) == 3, (
        f"input_nodes has {len(rec['input_nodes'])} entries, expected 3"
    )
    for idx, node in enumerate(rec["input_nodes"]):
        assert isinstance(node, str) and node, (
            f"input_nodes[{idx}] = {node!r} (empty/wrong type)"
        )
    # Output pairs: 9 entries, each (gate_node, "0"). Gate-node label
    # text varies (it's the internal alias) — what matters is shape +
    # the ground reference.
    assert len(rec["output_node_pairs"]) == 9, (
        f"output_node_pairs has {len(rec['output_node_pairs'])} entries, "
        "expected 9 (one per MOSFET in the 3×3 matrix)"
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
            "(ground-referenced controlled voltage source for each gate)"
        )
    assert "Venturini" in rec["source_code"], (
        "Venturini sentinel missing from the converter's record — the "
        "source body did not survive Project.from_dict + CircuitConverter."
    )


def test_simulation_settings_match_design_point(example_circuit_data) -> None:
    """The schematic's ``simulation_settings`` must request the
    documented design point: ``tstop = 0.05 s`` (≥ one output cycle at
    25 Hz), ``dt = 2e-6 s`` (much finer than the 5 µs C_BLOCK sample so
    the PWL engine has clean switching points), and the PWL engine
    (DSED can't extract LTI state-space for an inline-C C_BLOCK).
    """
    project = example_circuit_data["_raw_project"]
    settings = project.simulation_settings
    assert settings.tstop == pytest.approx(0.05), (
        f"tstop={settings.tstop}, expected 0.05 s (≥ 1 output cycle at 25 Hz)."
    )
    assert settings.dt == pytest.approx(2.0e-6), (
        f"dt={settings.dt}, expected 2e-6 s (much finer than 5 µs C_BLOCK)."
    )
    assert settings.engine == "pwl", (
        f"engine={settings.engine!r}, expected 'pwl' (DSED can't extract LTI "
        "state-space for an inline-C C_BLOCK)."
    )


def test_converter_emits_one_gate_drive_descriptor_per_mosfet(
    converted_circuit,
) -> None:
    """The path-B gate-drive inference must bind every one of the 9
    MOSFETs in the matrix to a distinct C_BLOCK output.

    This is the structural invariant that unlocks the GUI-side
    switched-CMC simulation: without these descriptors the backend's
    ``switch_fn`` leaves every MOSFET at the all-OFF default and the
    matrix collapses to body-diode-only operation (a 3-phase rectifier
    waveform instead of the Venturini-modulated AC-AC conversion).

    The 9 descriptors must:

      * Cover every MOSFET ``S_xY`` with ``x ∈ {a, b, c}`` and
        ``Y ∈ {A, B, C}`` — the full 3×3 input × output matrix.
      * Each point at the single ``CMC_PWM`` C_BLOCK (path B emits
        exactly one record for this schematic).
      * Have ``c_block_output_index`` in ``range(9)`` and every index
        in that range claimed exactly once (no duplicates, none of
        the C_BLOCK's 9 outputs left unbound — every one of them
        drives a gate).
    """
    descs = list(
        getattr(converted_circuit, "cblock_gate_drive_descriptors", []) or []
    )
    assert len(descs) == 9, (
        f"Expected 9 gate-drive descriptors (one per MOSFET in the 3×3 "
        f"matrix), got {len(descs)}. The converter's "
        "``_infer_cblock_gate_drives`` is not picking up the CMC_PWM "
        "outputs as MOSFET gate drives."
    )

    expected_names = {
        f"S_{in_phase}{out_phase}"
        for in_phase in ("a", "b", "c")
        for out_phase in ("A", "B", "C")
    }
    actual_names = {str(d["mosfet_name"]) for d in descs}
    assert actual_names == expected_names, (
        f"Gate-drive descriptors don't cover the full 3×3 matrix:\n"
        f"  expected: {sorted(expected_names)}\n"
        f"  got:      {sorted(actual_names)}"
    )

    # Each descriptor names the same C_BLOCK (path B emits one record
    # for CMC_PWM, so every descriptor must reference it).
    cb_names = {str(d["c_block_name"]) for d in descs}
    assert cb_names == {"CMC_PWM"}, (
        f"Expected every descriptor to reference CMC_PWM, got {cb_names}"
    )

    # Output indices: full coverage of [0, 9), no duplicates. Every
    # output of the C_BLOCK drives a gate; none are left dangling.
    output_indices = sorted(int(d["c_block_output_index"]) for d in descs)
    assert output_indices == list(range(9)), (
        f"Output-index claim is wrong: expected {list(range(9))}, "
        f"got {output_indices}. Either an output is unbound or two "
        "gates claim the same output."
    )


def test_gate_drive_descriptors_match_mosfet_v_threshold(
    converted_circuit, example_circuit_data,
) -> None:
    """Each descriptor's ``v_threshold`` must match the MOSFET's gate
    threshold parameter from the schematic.

    The ex 25 schematic carries ``v_th=3.0`` on every MOSFET (matches
    the MMC_CELL switch model default and the typical sub-12V-gate
    NMOS family). The backend's ``switch_fn`` compares the live gate
    voltage against this threshold per simulation step, so a mismatch
    here would silently shift the duty cycle of every leg.
    """
    descs = list(
        getattr(converted_circuit, "cblock_gate_drive_descriptors", []) or []
    )
    assert len(descs) == 9

    # Cross-reference the descriptor's threshold against the original
    # MOSFET's schematic params. Both v_th and vth spellings are
    # acceptable on the source side — the inference normalises.
    by_name = {c["name"]: c for c in example_circuit_data["components"]
               if c["type"] == "MOSFET_N"}

    for d in descs:
        name = str(d["mosfet_name"])
        params = by_name[name]["parameters"]
        # Look up whichever spelling the schematic used.
        expected = None
        for key in ("v_th", "vth"):
            if key in params:
                expected = float(params[key])
                break
        if expected is None:
            expected = 3.0  # default fallback the inference applies
        assert d["v_threshold"] == pytest.approx(expected), (
            f"MOSFET {name}: descriptor v_threshold={d['v_threshold']!r} "
            f"but schematic carries v_th={expected!r}. The backend's "
            "switch_fn would compare against the wrong threshold and "
            "shift the duty cycle off the C source's intent."
        )
