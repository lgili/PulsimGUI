"""Tests for the pulsim 1.8 path-B multi-output C_BLOCK gate-drive
inference.

The inference (``CircuitConverter._infer_cblock_gate_drives``) detects
the topology

    C_BLOCK.out[k] ─(controlled voltage source)─▶ <gate node>
    <gate node> ──▶ MOSFET.G pin

and emits one descriptor per MOSFET whose gate net is driven by a
C_BLOCK output. The backend's post-pass closes over the
``CBlockHandle.outputs`` numpy buffer to synthesise a ``switch_fn`` that
thresholds each gate voltage against ``v_th`` per simulation step.

These tests pin the converter-side surface only — the backend's
``switch_fn`` synthesis is covered in the corresponding backend tests.
The inference is feature-detect safe: it requires no pulsim runtime
(no ``add_c_block``), so it runs identically against pulsim < 1.8 and
the backend's post-pass is a clean no-op there.
"""
from __future__ import annotations

import uuid

import pulsim as _real

from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _cid() -> str:
    return str(uuid.uuid4())


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(_real))


# --------------------------------------------------------------------------
# Synthetic circuit fixtures.
#
# Each fixture builds a minimal schematic exercising one corner of the
# inference. We keep the topology lean so the test scope is exactly the
# behaviour under test — no other inference (PI/PWM, FOC, PFC) fires.
# --------------------------------------------------------------------------


def _multi_output_cblock_to_mosfets(
    *,
    n_outputs: int,
    n_mosfets: int,
    implementation: str = "source",
    source_code: str = "out[0] = 0.0;",
    vth: float = 3.0,
) -> dict[str, object]:
    """Build a circuit with ONE C_BLOCK (1 input, ``n_outputs`` outputs)
    whose first ``n_mosfets`` outputs drive distinct MOSFET gates.

    Topology (load-side is intentionally trivial — we only test the
    inference, not the simulation):

        Vin ─ Rin ─▶ in_meas ──(VP)──▶ in_sig ──▶ C_BLOCK.in0
        C_BLOCK.out[k] ──▶ gate_k ──▶ M_k.G   for k in [0, n_mosfets)
        M_k.D = vbus, M_k.S = vout_k, vout_k tied to 0 via Rload_k

    Extra outputs (k ≥ n_mosfets) are wired to dummy load nodes
    instead of MOSFET gates — they should NOT produce descriptors.
    """
    assert n_outputs >= n_mosfets >= 1
    components: list[dict[str, object]] = []

    vsrc = _cid()
    rin = _cid()
    vp = _cid()
    cb_id = _cid()
    components.extend([
        {"id": vsrc, "type": "VOLTAGE_SOURCE", "name": "Vin",
         "pin_nodes": ["in_meas", "0"],
         "parameters": {"waveform": {"type": "dc", "value": 1.0}}},
        {"id": rin, "type": "RESISTOR", "name": "Rin",
         "pin_nodes": ["in_meas", "0"],
         "parameters": {"resistance": 1.0}},
        {"id": vp, "type": "VOLTAGE_PROBE_GND", "name": "VP_in",
         "pin_nodes": ["in_meas", "in_sig"],
         "pins": [{"index": 0, "name": "IN"}, {"index": 1, "name": "OUT"}],
         "parameters": {}},
    ])

    # The C_BLOCK has 1 input + n_outputs outputs. Pin order: inputs
    # first, then outputs. Outputs k=0..n_mosfets-1 wire to gate nodes;
    # extras wire to dummy "load_<k>" nodes that we'll tie to ground.
    cb_pins: list[dict[str, object]] = [
        {"index": 0, "name": "IN0"},
    ]
    cb_pin_nodes: list[str] = ["in_sig"]
    for k in range(n_outputs):
        cb_pins.append({"index": 1 + k, "name": f"OUT{k}"})
        if k < n_mosfets:
            cb_pin_nodes.append(f"gate_{k}")
        else:
            cb_pin_nodes.append(f"load_{k}")
    cb_params: dict[str, object] = {
        "implementation": implementation,
        "n_inputs": 1,
        "n_outputs": n_outputs,
        "n_states": 1,
        "sample_time": 1.0e-6,
    }
    if implementation == "source":
        cb_params["source_code"] = source_code
    elif implementation == "python_numba":
        cb_params["python_source"] = (
            "def step(measured, state):\n    return 0.0\n"
        )
    components.append({
        "id": cb_id, "type": "C_BLOCK", "name": "CB1",
        "pin_nodes": cb_pin_nodes,
        "pins": cb_pins,
        "parameters": cb_params,
    })

    # MOSFETs k = 0..n_mosfets - 1.  Pin order: D, G, S.
    vbus = "vbus"
    components.append({
        "id": _cid(), "type": "VOLTAGE_SOURCE", "name": "Vbus",
        "pin_nodes": [vbus, "0"],
        "parameters": {"waveform": {"type": "dc", "value": 24.0}},
    })
    for k in range(n_mosfets):
        mid = _cid()
        components.append({
            "id": mid, "type": "MOSFET_N", "name": f"M_{k}",
            "pin_nodes": [vbus, f"gate_{k}", f"vout_{k}"],
            "pins": [
                {"index": 0, "name": "D"},
                {"index": 1, "name": "G"},
                {"index": 2, "name": "S"},
            ],
            "parameters": {"vth": vth, "v_th": vth},
        })
        components.append({
            "id": _cid(), "type": "RESISTOR", "name": f"Rload_{k}",
            "pin_nodes": [f"vout_{k}", "0"],
            "parameters": {"resistance": 10.0},
        })

    # Extras: tie each non-gate output to ground through a resistor so
    # the converter doesn't see a floating node.
    for k in range(n_mosfets, n_outputs):
        components.append({
            "id": _cid(), "type": "RESISTOR", "name": f"Rdummy_{k}",
            "pin_nodes": [f"load_{k}", "0"],
            "parameters": {"resistance": 10.0},
        })

    # Build alias map identity for every node we mention so the
    # converter's ``_node_label`` returns the bare net name (not the
    # ``N<id>`` fallback used when the alias map is empty).
    aliases: dict[str, str] = {"in_meas": "in_meas", "in_sig": "in_sig",
                                "vbus": "vbus"}
    for k in range(n_outputs):
        if k < n_mosfets:
            aliases[f"gate_{k}"] = f"gate_{k}"
        else:
            aliases[f"load_{k}"] = f"load_{k}"
    for k in range(n_mosfets):
        aliases[f"vout_{k}"] = f"vout_{k}"

    return {
        "components": components,
        "node_map": {},
        "node_aliases": aliases,
    }


def _siso_cblock_pwm_mosfet() -> dict[str, object]:
    """Build a path-A SISO chain: probe → C_BLOCK[python_numba] →
    PWM_GENERATOR → MOSFET. The MOSFET MUST NOT be re-claimed by the
    new gate-drive inference (it's already on path A's switch_device
    list)."""
    py_src = (
        "def control(measured, setpoint, dt, state):\n"
        "    return 0.5\n"
    )
    vin, sw, probe, cb, pwm, gid, rload = (_cid() for _ in range(7))
    comps = [
        {"id": vin, "type": "VOLTAGE_SOURCE", "name": "Vin",
         "parameters": {"voltage": 24.0},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": sw, "type": "MOSFET_N", "name": "M1", "parameters": {},
         "pins": [{"index": 0, "name": "D"}, {"index": 1, "name": "G"},
                  {"index": 2, "name": "S"}]},
        {"id": rload, "type": "RESISTOR", "name": "Rload",
         "parameters": {"resistance": 10.0},
         "pins": [{"index": 0, "name": "a"}, {"index": 1, "name": "b"}]},
        {"id": probe, "type": "VOLTAGE_PROBE_GND", "name": "VP1",
         "parameters": {},
         "pins": [{"index": 0, "name": "in"}, {"index": 1, "name": "out"}]},
        {"id": cb, "type": "C_BLOCK", "name": "CTRL",
         "parameters": {
             "implementation": "python_numba", "python_source": py_src,
             "n_inputs": 1, "n_outputs": 1, "n_states": 1,
             "sample_time": 2e-5,
         },
         "pins": [{"index": 0, "name": "in"}, {"index": 1, "name": "out"}]},
        {"id": pwm, "type": "PWM_GENERATOR", "name": "PWM1",
         "parameters": {"frequency": 50_000.0},
         "pins": [{"index": 0, "name": "out"}, {"index": 1, "name": "duty"}]},
        {"id": gid, "type": "GROUND", "name": "G", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        vin: ["vin", "gnd"],
        sw: ["vin", "gate", "vout"],
        rload: ["vout", "gnd"],
        probe: ["vout", "vp_out"],
        cb: ["vp_out", "cb_out"],
        pwm: ["gate", "cb_out"],
        gid: ["gnd"],
    }
    return {"components": comps, "node_map": node_map, "node_aliases": {}}


# --------------------------------------------------------------------------
# Inference behaviour.
# --------------------------------------------------------------------------


def test_inference_emits_one_descriptor_per_gate_driven_mosfet() -> None:
    """A 1-input / 3-output C_BLOCK driving 3 MOSFET gates emits 3
    descriptors, one per (MOSFET, output-index) pair."""
    circ = _converter().build(
        _multi_output_cblock_to_mosfets(n_outputs=3, n_mosfets=3)
    )
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    assert len(descs) == 3, (
        f"Expected 3 descriptors (one per MOSFET), got {len(descs)}: {descs}"
    )
    names = sorted(d["mosfet_name"] for d in descs)
    assert names == ["M_0", "M_1", "M_2"]


def test_inference_descriptor_shape_and_indices_match_record_ordering() -> None:
    """Each descriptor carries the right ``(mosfet_id, c_block_id,
    output_index, v_threshold)`` tuple — and the output index matches
    the ordering on ``c_block_records[*]['output_node_pairs']``."""
    circ = _converter().build(
        _multi_output_cblock_to_mosfets(
            n_outputs=3, n_mosfets=3, vth=4.5,
        )
    )
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    records = list(getattr(circ, "c_block_records", []) or [])
    assert len(records) == 1
    rec = records[0]
    pairs = rec["output_node_pairs"]

    by_name = {d["mosfet_name"]: d for d in descs}
    for name, expected_idx in (("M_0", 0), ("M_1", 1), ("M_2", 2)):
        d = by_name[name]
        # output_index must point into the rec's output_node_pairs list,
        # and that pair's first slot must be the MOSFET's gate label.
        out_idx = int(d["c_block_output_index"])
        assert 0 <= out_idx < len(pairs)
        assert pairs[out_idx][0] == f"gate_{expected_idx}", (
            f"descriptor {name} output index {out_idx} maps to "
            f"{pairs[out_idx][0]!r}, expected gate_{expected_idx}"
        )
        # v_threshold reflects the MOSFET's params.
        assert d["v_threshold"] == 4.5, (
            f"v_threshold mismatch on {name}: {d['v_threshold']!r}"
        )
        # Identifier wiring: mosfet/cblock component IDs are set.
        assert d["c_block_name"] == "CB1"
        assert d["mosfet_component_id"]
        assert d["c_block_component_id"]


def test_inference_skips_mosfets_claimed_by_path_a() -> None:
    """A MOSFET whose gate is driven by a C_BLOCK through a
    PWM_GENERATOR (the SISO path-A chain) MUST NOT produce a gate-
    drive descriptor — path A already binds the switch via the duty
    mask, and double-binding would fight the same switch bit."""
    circ = _converter().build(_siso_cblock_pwm_mosfet())
    # Sanity: path A must have picked up the chain (otherwise this
    # test is vacuous).
    loops = list(getattr(circ, "cblock_loop_descriptors", []) or [])
    assert len(loops) == 1
    assert loops[0]["switch_device"] == "M1"
    # The new inference must skip M1.
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    assert descs == [], (
        f"Path A's M1 was double-bound by the gate-drive inference: {descs}"
    )


def test_inference_skips_mosfets_with_floating_gate() -> None:
    """A MOSFET whose gate node is not driven by any C_BLOCK output
    yields no descriptor (the existing all-OFF fallback still produces
    a runnable sim — we just don't fabricate a binding)."""
    # Build a tiny circuit: V → M (unwired gate) → Rload. No C_BLOCK
    # at all → no descriptor.
    vin, mosfet, rload, gid = (_cid() for _ in range(4))
    comps = [
        {"id": vin, "type": "VOLTAGE_SOURCE", "name": "Vin",
         "pin_nodes": ["vbus", "0"],
         "parameters": {"waveform": {"type": "dc", "value": 24.0}}},
        {"id": mosfet, "type": "MOSFET_N", "name": "M1",
         "pin_nodes": ["vbus", "floating_gate", "vout"],
         "pins": [{"index": 0, "name": "D"}, {"index": 1, "name": "G"},
                  {"index": 2, "name": "S"}],
         "parameters": {"vth": 3.0}},
        {"id": rload, "type": "RESISTOR", "name": "Rload",
         "pin_nodes": ["vout", "0"],
         "parameters": {"resistance": 10.0}},
        {"id": gid, "type": "GROUND", "name": "G",
         "pin_nodes": ["0"],
         "pins": [{"index": 0, "name": "gnd"}],
         "parameters": {}},
    ]
    circ = _converter().build({
        "components": comps, "node_map": {}, "node_aliases": {},
    })
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    assert descs == []


def test_inference_handles_mixed_gate_and_load_outputs() -> None:
    """A C_BLOCK with more outputs than gates (some outputs go to
    load nodes, some to MOSFET gates) only emits descriptors for the
    gate-driving outputs."""
    # 5 outputs total, 2 driving MOSFET gates, 3 driving dummy loads.
    circ = _converter().build(
        _multi_output_cblock_to_mosfets(n_outputs=5, n_mosfets=2)
    )
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    assert len(descs) == 2, (
        f"Expected 2 descriptors (one per MOSFET), got {len(descs)}: {descs}"
    )
    # Both descriptors must point into [0, 1] — the load-driving outputs
    # at index 2, 3, 4 must NOT be claimed.
    indices = sorted(d["c_block_output_index"] for d in descs)
    assert indices == [0, 1]


def test_inference_defaults_v_threshold_to_three_volts() -> None:
    """Missing ``v_th`` / ``vth`` falls back to 3.0 V (the schematic
    default; see the MMC_CELL switch model). Matches the threshold
    actually compared against the gate voltage at simulate time."""
    # Wire a 1-output C_BLOCK to a single MOSFET whose params dict
    # carries no threshold. The default 3.0 V applies. The C_BLOCK's
    # input must be driven through a probe (converter requirement).
    cb_id, mid, vsrc_id, rload_id, vp_id = (_cid() for _ in range(5))
    components = [
        {"id": vsrc_id, "type": "VOLTAGE_SOURCE", "name": "Vbus",
         "pin_nodes": ["vbus", "0"],
         "parameters": {"waveform": {"type": "dc", "value": 24.0}}},
        {"id": vp_id, "type": "VOLTAGE_PROBE_GND", "name": "VP",
         "pin_nodes": ["vbus", "in_sig"],
         "pins": [{"index": 0, "name": "IN"}, {"index": 1, "name": "OUT"}],
         "parameters": {}},
        {"id": cb_id, "type": "C_BLOCK", "name": "CB1",
         "pin_nodes": ["in_sig", "gate_0"],
         "pins": [{"index": 0, "name": "IN0"},
                  {"index": 1, "name": "OUT0"}],
         "parameters": {
             "implementation": "source",
             "n_inputs": 1, "n_outputs": 1, "n_states": 1,
             "sample_time": 1.0e-6,
             "source_code": "out[0] = 0.0;",
         }},
        {"id": mid, "type": "MOSFET_N", "name": "M_0",
         "pin_nodes": ["vbus", "gate_0", "vout_0"],
         "pins": [{"index": 0, "name": "D"}, {"index": 1, "name": "G"},
                  {"index": 2, "name": "S"}],
         "parameters": {}},
        {"id": rload_id, "type": "RESISTOR", "name": "Rload",
         "pin_nodes": ["vout_0", "0"],
         "parameters": {"resistance": 10.0}},
    ]
    circ = _converter().build({
        "components": components, "node_map": {},
        "node_aliases": {"vbus": "vbus", "gate_0": "gate_0",
                          "vout_0": "vout_0", "in_sig": "in_sig"},
    })
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    assert len(descs) == 1
    assert descs[0]["v_threshold"] == 3.0


def test_inference_runs_independent_of_pulsim_18_runtime() -> None:
    """The inference is a pure converter-time analysis — it makes no
    call to ``pulsim.add_c_block`` and produces descriptors regardless
    of which pulsim version is installed.

    This is what unlocks the backend's feature-detect path: even when
    ``add_c_block`` is missing the converter still emits the
    descriptors (the post-pass simply degrades to a no-op)."""
    # We use the real pulsim module here (it has add_c_block), then
    # ALSO build the same circuit with a stripped-down shim that lacks
    # add_c_block — both must produce identical descriptor lists.
    import types as _types

    circuit_data = _multi_output_cblock_to_mosfets(
        n_outputs=2, n_mosfets=2,
    )
    real_descs = list(
        getattr(_converter().build(circuit_data),
                "cblock_gate_drive_descriptors", []) or []
    )

    bare = _types.ModuleType("pulsim_no_add_c_block")
    for attr in dir(_real):
        if not attr.startswith("__") and attr != "add_c_block":
            setattr(bare, attr, getattr(_real, attr))
    if hasattr(bare, "add_c_block"):
        delattr(bare, "add_c_block")
    conv_bare = CircuitConverter(make_compat_module(bare))
    bare_descs = list(
        getattr(conv_bare.build(circuit_data),
                "cblock_gate_drive_descriptors", []) or []
    )

    # Same MOSFETs, same output indices, same thresholds — the
    # converter never touched add_c_block.
    def _norm(descs: list) -> list:
        return sorted(
            (
                d["mosfet_name"],
                d["c_block_name"],
                d["c_block_output_index"],
                d["v_threshold"],
            )
            for d in descs
        )

    assert _norm(real_descs) == _norm(bare_descs)
    # Both must produce 2 descriptors (one per MOSFET).
    assert len(real_descs) == 2


def test_inference_first_cblock_claims_overlapping_gate() -> None:
    """When two C_BLOCK outputs claim the SAME gate node (an authoring
    error the backend would already barf on at ``add_c_block`` time),
    the first record-order C_BLOCK wins so we emit a single descriptor
    and don't silently double-drive."""
    cb1_id, cb2_id, mid, vsrc_id, rload_id, vp_id = (_cid() for _ in range(6))
    components = [
        {"id": vsrc_id, "type": "VOLTAGE_SOURCE", "name": "Vbus",
         "pin_nodes": ["vbus", "0"],
         "parameters": {"waveform": {"type": "dc", "value": 24.0}}},
        {"id": vp_id, "type": "VOLTAGE_PROBE_GND", "name": "VP",
         "pin_nodes": ["vbus", "in_sig"],
         "pins": [{"index": 0, "name": "IN"}, {"index": 1, "name": "OUT"}],
         "parameters": {}},
        # Two C_BLOCKs whose output node is the same gate.
        {"id": cb1_id, "type": "C_BLOCK", "name": "CB1",
         "pin_nodes": ["in_sig", "gate_0"],
         "pins": [{"index": 0, "name": "IN0"},
                  {"index": 1, "name": "OUT0"}],
         "parameters": {
             "implementation": "source",
             "n_inputs": 1, "n_outputs": 1, "n_states": 1,
             "sample_time": 1.0e-6,
             "source_code": "out[0] = 0.0;",
         }},
        {"id": cb2_id, "type": "C_BLOCK", "name": "CB2",
         "pin_nodes": ["in_sig", "gate_0"],
         "pins": [{"index": 0, "name": "IN0"},
                  {"index": 1, "name": "OUT0"}],
         "parameters": {
             "implementation": "source",
             "n_inputs": 1, "n_outputs": 1, "n_states": 1,
             "sample_time": 1.0e-6,
             "source_code": "out[0] = 0.0;",
         }},
        {"id": mid, "type": "MOSFET_N", "name": "M_0",
         "pin_nodes": ["vbus", "gate_0", "vout_0"],
         "pins": [{"index": 0, "name": "D"}, {"index": 1, "name": "G"},
                  {"index": 2, "name": "S"}],
         "parameters": {"v_th": 3.0}},
        {"id": rload_id, "type": "RESISTOR", "name": "Rload",
         "pin_nodes": ["vout_0", "0"],
         "parameters": {"resistance": 10.0}},
    ]
    circ = _converter().build({
        "components": components, "node_map": {},
        "node_aliases": {"vbus": "vbus", "gate_0": "gate_0",
                          "vout_0": "vout_0", "in_sig": "in_sig"},
    })
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    # First record (CB1) wins; we don't fabricate two bindings for the
    # same switch bit.
    assert len(descs) == 1
    assert descs[0]["c_block_name"] == "CB1"
    assert descs[0]["mosfet_name"] == "M_0"
