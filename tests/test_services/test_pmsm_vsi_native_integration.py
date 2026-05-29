"""Tests for the pulsim 1.6.4 dynamic-PMSM + native switched 3φ VSI
integration (model → converter → v0 shim → backend observer / switch_fn).

These exercise the REAL pulsim 1.6.4 surface (``add_pmsm``,
``make_pmsm_observer``, ``add_three_phase_vsi``,
``make_three_phase_spwm_fn``) through the GUI's compat shim + converter,
mirroring ``test_induction_motor_hysteretic_inductor.py``'s 3-layer shape:

  1. Shim — ``Circuit.add_pmsm`` records a ``nonlinear_observer_specs``
     entry of kind 'pmsm'; ``Circuit.add_three_phase_vsi`` records a
     ``vsi_specs`` entry with the topology's builder-global switch
     indices + SPWM drive params; ``set_pmsm_tau_load`` mutates the
     handle's mechanical load.
  2. Converter — building circuit_data with a PMSM / VSI drives those
     shim methods (native switched path, not the averaged 3-sine
     fallback) and the underlying builder grows the device branches.
  3. Backend — ``_build_nonlinear_device_observers`` turns the pmsm spec
     into a ``(step_observer, b_extra_fn)`` pair; ``_build_vsi_switch_fns``
     turns the vsi spec into an SPWM ``switch_fn``; a real simulate run
     spins the rotor + draws phase current without NaN, and the SPWM +
     a co-resident PFC MOSFET PWM compose without clobbering each other.
"""
from __future__ import annotations

import math
import types
import uuid

import numpy as np
import pulsim as p

from pulsimgui.models.component import DEFAULT_PARAMETERS, ComponentType
from pulsimgui.services.backend_adapter import PulsimBackend
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _cid() -> str:
    return str(uuid.uuid4())


def _adapter() -> PulsimBackend:
    adapter = PulsimBackend.__new__(PulsimBackend)
    adapter._module = p  # type: ignore[attr-defined]
    return adapter


def _pmsm_params(**overrides: object) -> dict:
    params = dict(DEFAULT_PARAMETERS[ComponentType.PMSM])
    params.update(overrides)
    return params


def _vsi_params(**overrides: object) -> dict:
    params = dict(DEFAULT_PARAMETERS[ComponentType.THREE_PHASE_VSI])
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# Layer 1+2 — converter + shim record the native specs.
# ---------------------------------------------------------------------------
def test_converter_records_pmsm_observer_spec() -> None:
    """A PMSM through the real CompatModule shim records a kind='pmsm'
    nonlinear_observer_spec holding a live pulsim PMSM handle whose
    parameters round-trip onto the kernel."""
    mid, gid = _cid(), _cid()
    srcs = [_cid() for _ in range(3)]
    comps = [
        {"id": srcs[k], "type": "VOLTAGE_SOURCE", "name": f"V{k}",
         "parameters": {"waveform": {"type": "dc", "value": 100.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]}
        for k in range(3)
    ]
    comps.append(
        {"id": mid, "type": "PMSM", "name": "M1",
         "parameters": _pmsm_params(Rs=6.6, Ld=12e-3, psi_pm=0.05,
                                    pole_pairs=3, J=2e-4, b_friction=5e-4),
         "pins": [{"index": i, "name": n}
                  for i, n in enumerate(["A", "B", "C", "N"])]}
    )
    comps.append({"id": gid, "type": "GROUND", "name": "G1",
                  "parameters": {}, "pins": [{"index": 0, "name": "gnd"}]})
    node_map = {
        srcs[0]: ["a", "gnd"], srcs[1]: ["b", "gnd"], srcs[2]: ["c", "gnd"],
        mid: ["a", "b", "c", "gnd"], gid: ["gnd"],
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    specs = [s for s in circ.nonlinear_observer_specs if s["kind"] == "pmsm"]
    assert len(specs) == 1
    assert specs[0]["name"] == "M1"
    motor = specs[0]["handle"]
    assert motor is not None
    # Parameters mapped onto the kernel handle.
    assert motor.R_s_ohm == 6.6
    assert motor.L_s_H == 12e-3  # Ld → kernel's single L_s
    assert motor.psi_pm_Wb == 0.05
    assert motor.pole_pairs == 3


def test_converter_forwards_pmsm_tau_load_to_handle() -> None:
    """Non-zero tau_load drives the shim's set_pmsm_tau_load, which
    mutates the kernel handle's mechanical load in place."""
    mid, gid = _cid(), _cid()
    srcs = [_cid() for _ in range(3)]
    comps = [
        {"id": srcs[k], "type": "VOLTAGE_SOURCE", "name": f"V{k}",
         "parameters": {"waveform": {"type": "dc", "value": 100.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]}
        for k in range(3)
    ]
    comps.append(
        {"id": mid, "type": "PMSM", "name": "M1",
         "parameters": _pmsm_params(tau_load=0.30),
         "pins": [{"index": i, "name": n}
                  for i, n in enumerate(["A", "B", "C", "N"])]}
    )
    comps.append({"id": gid, "type": "GROUND", "name": "G1",
                  "parameters": {}, "pins": [{"index": 0, "name": "gnd"}]})
    node_map = {
        srcs[0]: ["a", "gnd"], srcs[1]: ["b", "gnd"], srcs[2]: ["c", "gnd"],
        mid: ["a", "b", "c", "gnd"], gid: ["gnd"],
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    motor = next(s["handle"] for s in circ.nonlinear_observer_specs
                 if s["kind"] == "pmsm")
    assert motor.mech.T_load_Nm == 0.30


def test_converter_records_native_vsi_spec_not_averaged() -> None:
    """A THREE_PHASE_VSI through the real shim takes the NATIVE switched
    path: it records a vsi_spec with the topology's builder-global
    HS/LS switch indices + SPWM params, and does NOT emit averaged
    sine sources."""
    vid, vp, vn, gid = _cid(), _cid(), _cid(), _cid()
    comps = [
        {"id": vp, "type": "VOLTAGE_SOURCE", "name": "VP",
         "parameters": {"waveform": {"type": "dc", "value": 155.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vn, "type": "VOLTAGE_SOURCE", "name": "VN",
         "parameters": {"waveform": {"type": "dc", "value": 155.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vid, "type": "THREE_PHASE_VSI", "name": "INV1",
         "parameters": _vsi_params(switching_frequency_hz=20000.0,
                                   modulation_index=0.8,
                                   modulation_frequency_hz=90.0),
         "pins": [{"index": i, "name": n} for i, n in
                  enumerate(["VDC+", "VDC-", "A", "B", "C"])]},
        {"id": gid, "type": "GROUND", "name": "G1", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        vp: ["busp", "gnd"], vn: ["gnd", "busn"],
        vid: ["busp", "busn", "pha", "phb", "phc"], gid: ["gnd"],
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    assert len(circ.vsi_specs) == 1
    spec = circ.vsi_specs[0]
    assert spec["name"] == "INV1"
    assert spec["carrier_frequency"] == 20000.0
    assert spec["modulation_frequency"] == 90.0
    assert spec["modulation_index"] == 0.8
    # Six power switches with builder-global indices.
    assert len(spec["high_side_switch_indices"]) == 3
    assert len(spec["low_side_switch_indices"]) == 3
    all_idx = (spec["high_side_switch_indices"]
               + spec["low_side_switch_indices"])
    assert len(set(all_idx)) == 6
    # Native topology registered 6 switches on the builder.
    assert circ.builder.graph.num_switches == 6


def test_vsi_switch_indices_are_builder_global_with_prior_switches() -> None:
    """When another switching device precedes the VSI (a body-diode-
    bearing MOSFET adds 2 builder switch slots), the VSI's recorded
    indices are the builder-global ones from the topology result — NOT
    the shim's pending_gate_signals counter (which omits body diodes).
    This is what lets the backend target exactly the inverter's bits.
    """
    q1, vp, vn, vid, gid = _cid(), _cid(), _cid(), _cid(), _cid()
    comps = [
        {"id": q1, "type": "MOSFET_N", "name": "Q1",
         "parameters": {"r_on": 1e-3, "r_off": 1e9},
         "pins": [{"index": 0, "name": "G"}, {"index": 1, "name": "D"},
                  {"index": 2, "name": "S"}]},
        {"id": vp, "type": "VOLTAGE_SOURCE", "name": "VP",
         "parameters": {"waveform": {"type": "dc", "value": 155.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vn, "type": "VOLTAGE_SOURCE", "name": "VN",
         "parameters": {"waveform": {"type": "dc", "value": 155.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vid, "type": "THREE_PHASE_VSI", "name": "INV1",
         "parameters": _vsi_params(),
         "pins": [{"index": i, "name": n} for i, n in
                  enumerate(["VDC+", "VDC-", "A", "B", "C"])]},
        {"id": gid, "type": "GROUND", "name": "G1", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        q1: ["g1", "sw", "gnd"],
        vp: ["busp", "gnd"], vn: ["gnd", "busn"],
        vid: ["busp", "busn", "pha", "phb", "phc"], gid: ["gnd"],
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    # MOSFET + body diode = 2 switch slots, then 6 VSI switches = 8.
    assert circ.builder.graph.num_switches == 8
    spec = circ.vsi_specs[0]
    vsi_idx = set(spec["high_side_switch_indices"]
                  + spec["low_side_switch_indices"])
    # The Q1 (idx 0) + body-diode (idx 1) slots are NOT in the VSI set;
    # the VSI owns the 6 indices after them.
    assert vsi_idx == {2, 3, 4, 5, 6, 7}
    # The shim's user-controlled switch map still only lists Q1 (the
    # body diode + VSI switches are driven by switch_fn, not the gate
    # heuristic).
    assert circ.switch_indices == {"Q1": 0}


# ---------------------------------------------------------------------------
# Layer 3 — backend observer + switch_fn helpers, real simulate runs.
# ---------------------------------------------------------------------------
def test_backend_pmsm_observer_spins_rotor() -> None:
    """A pmsm spec → make_pmsm_observer pair; a real 3-sine-driven run
    spins the rotor (mechanical state leaves zero) and keeps states
    finite."""
    b = p.CircuitBuilder()
    for k, node in enumerate(("a", "b", "c")):
        b.add_sine_voltage_source(
            f"Vs{k}", node, "gnd", 0.0, 120.0, 90.0,
            k * 2.0 * math.pi / 3.0,
        )
    motor = p.add_pmsm(
        b, name="M1", phase_nodes=("a", "b", "c"), neutral_node="gnd",
        R_s=6.6, L_s=12e-3, psi_pm=0.05, pole_pairs=3, J=2e-4, B=5e-4,
        T_load=0.0,
    )
    circuit = types.SimpleNamespace(
        nonlinear_observer_specs=[
            {"kind": "pmsm", "name": "M1", "handle": motor},
        ],
    )
    adapter = _adapter()
    obs, b_extra = adapter._build_nonlinear_device_observers(
        circuit, b, dt=20e-6,
    )
    assert len(obs) == 1
    assert b_extra is not None

    res = p.simulate(
        b, t_end=0.03, dt=20e-6,
        switch_fn=lambda t: p.SwitchStateMask(0),
        step_observer=lambda t, x: [o(t, x) for o in obs],
        b_extra_fn=b_extra,
        enable_nonlinear_refresh=True,
    )
    assert res.num_steps() > 0
    states = np.array([list(s) for s in res.states])
    assert np.all(np.isfinite(states))
    # Rotor must have moved off zero (energised, unloaded → it spins up).
    assert abs(motor.mech.omega_rad_s) > 1.0
    assert abs(motor.mech.theta_rad) > 0.0


def test_backend_builds_no_vsi_switch_fns_when_no_specs() -> None:
    adapter = _adapter()
    circuit = types.SimpleNamespace(vsi_specs=[])
    fns = adapter._build_vsi_switch_fns(circuit, p.CircuitBuilder())
    assert fns == []


def test_backend_vsi_switch_fn_drives_only_inverter_bits() -> None:
    """_build_vsi_switch_fns turns a vsi_spec into an SPWM switch_fn
    whose mask sets exactly the inverter's 6 bits, leaving any prior
    switch bit (a PFC MOSFET) untouched."""
    b = p.CircuitBuilder()
    for n in ("sw", "busp", "busn", "pha", "phb", "phc"):
        b.node(n)
    b.add_mosfet_with_body_diode("Q1", "sw", "gnd", 1e-3, 1e9)  # idx 0, 1
    b.add_voltage_source("VP", "busp", "gnd", 155.0)
    b.add_voltage_source("VN", "gnd", "busn", 155.0)
    vsi = p.add_three_phase_vsi(
        b, "INV", vdc_pos="busp", vdc_neg="busn",
        out_a="pha", out_b="phb", out_c="phc",
    )
    hs = [int(i) for i in vsi.high_side_switch_indices]
    ls = [int(i) for i in vsi.low_side_switch_indices]
    circuit = types.SimpleNamespace(vsi_specs=[{
        "name": "INV",
        "high_side_switch_indices": hs,
        "low_side_switch_indices": ls,
        "carrier_frequency": 20000.0,
        "modulation_frequency": 90.0,
        "modulation_index": 0.8,
        "dead_time": 0.0,
        "modulation_phase_deg": 0.0,
    }])
    adapter = _adapter()
    fns = adapter._build_vsi_switch_fns(circuit, b)
    assert len(fns) == 1

    vsi_idx = set(hs) | set(ls)
    # Sample over a fundamental period: the PFC bits (0, 1) must never
    # be set by the SPWM fn; the inverter always has 3 of 6 conducting.
    pfc_ever_on = False
    leg_counts = set()
    for t in np.linspace(0.0, 2e-3, 2000):
        m = fns[0](float(t))
        if m.get(0) or m.get(1):
            pfc_ever_on = True
        leg_counts.add(sum(m.get(i) for i in vsi_idx))
    assert not pfc_ever_on, "SPWM fn clobbered a non-inverter switch bit"
    assert leg_counts == {3}, "2-level VSI should always have 3 of 6 on"


def test_vsi_spwm_composes_with_pfc_pwm_without_clobber() -> None:
    """The VSI SPWM and a co-resident PFC MOSFET PWM, composed via
    make_combined_switch_fn (the backend's path), drive their disjoint
    switch bits simultaneously — the PFC keeps its duty and the SPWM
    keeps modulating."""
    b = p.CircuitBuilder()
    for n in ("sw", "busp", "busn", "pha", "phb", "phc"):
        b.node(n)
    b.add_mosfet_with_body_diode("Q1", "sw", "gnd", 1e-3, 1e9)  # idx 0, 1
    b.add_voltage_source("VP", "busp", "gnd", 155.0)
    b.add_voltage_source("VN", "gnd", "busn", 155.0)
    vsi = p.add_three_phase_vsi(
        b, "INV", vdc_pos="busp", vdc_neg="busn",
        out_a="pha", out_b="phb", out_c="phc",
    )
    hs = [int(i) for i in vsi.high_side_switch_indices]
    ls = [int(i) for i in vsi.low_side_switch_indices]
    num_sw = b.graph.num_switches

    legs = p.ThreePhaseLegIndices(hs[0], ls[0], hs[1], ls[1], hs[2], ls[2])
    spwm = p.make_three_phase_spwm_fn(20000.0, 90.0, 0.8, legs, num_sw, 0.0)
    # PFC MOSFET on switch idx 0 at 65 kHz / 45 %.
    pfc = p.make_pwm_switch_fn(65000.0, 0.45, 0, num_sw, 0.0)
    combined = p.make_combined_switch_fn(num_sw, [spwm, pfc])

    ts = np.linspace(0.0, 2e-3, 4000)
    q1_on = [combined(float(t)).get(0) for t in ts]
    hsa_on = [combined(float(t)).get(hs[0]) for t in ts]
    # PFC keeps ~45 % duty on its bit.
    assert 0.40 < (sum(q1_on) / len(q1_on)) < 0.50
    # SPWM keeps modulating its inverter bit (toggles, not stuck).
    assert 0 < sum(hsa_on) < len(hsa_on)
    # Many distinct full-mask patterns => both groups switch independently.
    patterns = {tuple(combined(float(t)).get(i) for i in range(num_sw))
                for t in ts}
    assert len(patterns) >= 4


def test_full_native_vsi_pmsm_drive_simulates() -> None:
    """End-to-end through the converter + backend helpers: ±155 V bus →
    native switched VSI → dynamic PMSM. The SPWM switch_fn + PMSM
    observer evolve the system — real switching ripple on the phase
    voltage, bounded rotor, finite states."""
    vp, vn, vid, mid, gid = _cid(), _cid(), _cid(), _cid(), _cid()
    comps = [
        {"id": vp, "type": "VOLTAGE_SOURCE", "name": "VP",
         "parameters": {"waveform": {"type": "dc", "value": 155.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vn, "type": "VOLTAGE_SOURCE", "name": "VN",
         "parameters": {"waveform": {"type": "dc", "value": 155.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vid, "type": "THREE_PHASE_VSI", "name": "INV1",
         "parameters": _vsi_params(switching_frequency_hz=20000.0,
                                   modulation_index=0.8,
                                   modulation_frequency_hz=90.0),
         "pins": [{"index": i, "name": n} for i, n in
                  enumerate(["VDC+", "VDC-", "A", "B", "C"])]},
        {"id": mid, "type": "PMSM", "name": "M1",
         "parameters": _pmsm_params(Rs=6.6, Ld=12e-3, Lq=12e-3,
                                    psi_pm=0.05, pole_pairs=3, J=2e-4,
                                    b_friction=5e-4, tau_load=0.30),
         "pins": [{"index": i, "name": n}
                  for i, n in enumerate(["A", "B", "C", "N"])]},
        {"id": gid, "type": "GROUND", "name": "G1", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    # Ground nets MUST be the literal "0" in a converter node_map — the
    # converter only maps "0" to the kernel ground node; any other net
    # name (incl. "gnd") becomes a regular floating node, which would
    # leave the 3-phase star point ungrounded.
    node_map = {
        vp: ["busp", "0"], vn: ["0", "busn"],
        vid: ["busp", "busn", "pha", "phb", "phc"],
        mid: ["pha", "phb", "phc", "0"], gid: ["0"],
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder

    adapter = _adapter()
    dt = 2e-6
    obs, b_extra = adapter._build_nonlinear_device_observers(circ, b, dt=dt)
    vsi_fns = adapter._build_vsi_switch_fns(circ, b)
    assert len(obs) == 1
    assert len(vsi_fns) == 1

    motor = next(s["handle"] for s in circ.nonlinear_observer_specs
                 if s["kind"] == "pmsm")
    res = p.simulate(
        b, t_end=0.02, dt=dt,
        switch_fn=vsi_fns[0],
        step_observer=lambda t, x: [o(t, x) for o in obs],
        b_extra_fn=b_extra,
        enable_nonlinear_refresh=True,
    )
    assert res.num_steps() > 0
    states = np.array([list(s) for s in res.states])
    assert np.all(np.isfinite(states))

    # Phase-A node voltage: switching → many large sample-to-sample
    # jumps (not a smooth fundamental). num_nodes columns lead the
    # state vector; pha is among them.
    node_block = states[:, : b.graph.num_nodes]
    # Find the column whose swing matches a rail (±155) — a phase node.
    swings = node_block.max(axis=0) - node_block.min(axis=0)
    assert swings.max() > 100.0  # rail-to-rail switching present
    # Rotor moved (energised, loaded) but stayed bounded/finite.
    assert math.isfinite(motor.mech.omega_rad_s)
    assert abs(motor.mech.omega_rad_s) > 0.5
    assert abs(motor.mech.omega_rad_s) < 1e4
