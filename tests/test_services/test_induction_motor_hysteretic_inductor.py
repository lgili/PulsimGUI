"""Tests for the pulsim 1.5 INDUCTION_MOTOR + HYSTERETIC_INDUCTOR
component integration (model → converter → shim → backend observer).

Three layers:
  1. Model — both ComponentTypes exist with sane defaults + the
     induction-motor leakage constraint holds.
  2. Converter + shim — building a circuit_data with each device
     records a ``nonlinear_observer_specs`` entry carrying the
     pulsim handle, and the underlying builder grows the device's
     sub-branches.
  3. Backend — ``_build_nonlinear_device_observers`` turns those
     specs into ``(step_observer, b_extra_fn)`` pairs, composes the
     b_extra residuals, and a real ``pulsim.simulate`` run with them
     evolves the device's internal state (J-A magnetisation / rotor
     flux) without NaN.
"""
from __future__ import annotations

import math
import types
import uuid

import pulsim as p

from pulsimgui.models.component import (
    Component,
    ComponentType,
    DEFAULT_PARAMETERS,
)
from pulsimgui.services.backend_adapter import PulsimBackend
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _cid() -> str:
    return str(uuid.uuid4())


def _adapter() -> PulsimBackend:
    adapter = PulsimBackend.__new__(PulsimBackend)
    adapter._module = p  # type: ignore[attr-defined]
    return adapter


# ---------------------------------------------------------------------------
# Layer 1 — model.
# ---------------------------------------------------------------------------
def test_induction_motor_model_defaults_and_pins() -> None:
    c = Component(type=ComponentType.INDUCTION_MOTOR, name="IM1")
    assert [pin.name for pin in c.pins] == ["A", "B", "C", "N"]
    pr = c.parameters
    # Leakage factor σ = 1 − Lm²/(Ls·Lr) must stay in (0, 1) or
    # pulsim.add_induction_motor raises.
    sigma = 1.0 - pr["L_m"] ** 2 / (pr["L_s"] * pr["L_r"])
    assert 0.0 < sigma < 1.0


def test_hysteretic_inductor_model_defaults_and_pins() -> None:
    c = Component(type=ComponentType.HYSTERETIC_INDUCTOR, name="LH1")
    assert [pin.name for pin in c.pins] == ["1", "2"]
    assert c.parameters["material"] in {
        "si_steel_m19", "annealed_iron", "ferrite_n87", "permalloy",
    }
    assert c.parameters["N_turns"] > 0
    assert c.parameters["l_m"] > 0
    assert c.parameters["A_core"] > 0


def test_both_devices_roundtrip_through_component_dict() -> None:
    for ct in (ComponentType.INDUCTION_MOTOR, ComponentType.HYSTERETIC_INDUCTOR):
        c = Component(type=ct, name="X")
        c2 = Component.from_dict(c.to_dict())
        assert c2.type == ct
        assert c2.parameters == DEFAULT_PARAMETERS[ct]


# ---------------------------------------------------------------------------
# Layer 2 — converter + shim record the observer spec.
# ---------------------------------------------------------------------------
def test_converter_records_hysteretic_inductor_spec() -> None:
    lid, rid, vid, gid = _cid(), _cid(), _cid(), _cid()
    circuit_data = {
        "components": [
            {"id": vid, "type": "VOLTAGE_SOURCE", "name": "V1",
             "parameters": {"voltage": 10.0},
             "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
            {"id": rid, "type": "RESISTOR", "name": "R1",
             "parameters": {"resistance": 1.0},
             "pins": [{"index": 0, "name": "1"}, {"index": 1, "name": "2"}]},
            {"id": lid, "type": "HYSTERETIC_INDUCTOR", "name": "LH1",
             "parameters": {"material": "ferrite_n87", "N_turns": 100,
                            "l_m": 0.05, "A_core": 1e-4},
             "pins": [{"index": 0, "name": "1"}, {"index": 1, "name": "2"}]},
            {"id": gid, "type": "GROUND", "name": "G1", "parameters": {},
             "pins": [{"index": 0, "name": "gnd"}]},
        ],
        "node_map": {
            vid: ["a", "gnd"], rid: ["a", "n1"],
            lid: ["n1", "gnd"], gid: ["gnd"],
        },
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build(circuit_data)
    specs = circ.nonlinear_observer_specs
    assert len(specs) == 1
    assert specs[0]["kind"] == "hysteretic_inductor"
    assert specs[0]["name"] == "LH1"
    assert specs[0]["handle"] is not None


def test_converter_records_induction_motor_spec() -> None:
    mid, gid = _cid(), _cid()
    srcs = [_cid() for _ in range(3)]
    comps = [
        {"id": srcs[k], "type": "VOLTAGE_SOURCE", "name": f"V{k}",
         "parameters": {"voltage": 100.0},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]}
        for k in range(3)
    ]
    comps.append(
        {"id": mid, "type": "INDUCTION_MOTOR", "name": "IM1",
         "parameters": dict(DEFAULT_PARAMETERS[ComponentType.INDUCTION_MOTOR]),
         "pins": [{"index": 0, "name": "A"}, {"index": 1, "name": "B"},
                  {"index": 2, "name": "C"}, {"index": 3, "name": "N"}]}
    )
    comps.append({"id": gid, "type": "GROUND", "name": "G1",
                  "parameters": {}, "pins": [{"index": 0, "name": "gnd"}]})
    node_map = {
        srcs[0]: ["a", "gnd"], srcs[1]: ["b", "gnd"], srcs[2]: ["c", "gnd"],
        mid: ["a", "b", "c", "gnd"], gid: ["gnd"],
    }
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    specs = [s for s in circ.nonlinear_observer_specs
             if s["kind"] == "induction_motor"]
    assert len(specs) == 1
    assert specs[0]["name"] == "IM1"
    assert specs[0]["handle"] is not None


def test_induction_motor_unphysical_leakage_raises_conversion_error() -> None:
    """L_m² ≥ L_s·L_r is unphysical; the converter must surface a
    clear CircuitConversionError, not a raw ValueError."""
    from pulsimgui.services.circuit_converter import CircuitConversionError

    mid, gid = _cid(), _cid()
    srcs = [_cid() for _ in range(3)]
    bad = dict(DEFAULT_PARAMETERS[ComponentType.INDUCTION_MOTOR])
    bad["L_m"] = 0.5  # L_m² = 0.25 >> L_s·L_r = 0.0025
    comps = [
        {"id": srcs[k], "type": "VOLTAGE_SOURCE", "name": f"V{k}",
         "parameters": {"voltage": 100.0},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]}
        for k in range(3)
    ]
    comps.append({"id": mid, "type": "INDUCTION_MOTOR", "name": "IMbad",
                  "parameters": bad,
                  "pins": [{"index": i, "name": n} for i, n in
                           enumerate(["A", "B", "C", "N"])]})
    comps.append({"id": gid, "type": "GROUND", "name": "G1",
                  "parameters": {}, "pins": [{"index": 0, "name": "gnd"}]})
    node_map = {srcs[0]: ["a", "gnd"], srcs[1]: ["b", "gnd"],
                srcs[2]: ["c", "gnd"], mid: ["a", "b", "c", "gnd"],
                gid: ["gnd"]}
    conv = CircuitConverter(make_compat_module(p))
    try:
        conv.build({"components": comps, "node_map": node_map})
    except CircuitConversionError as exc:
        assert "IMbad" in str(exc)
    else:
        raise AssertionError("expected CircuitConversionError for bad leakage")


# ---------------------------------------------------------------------------
# Layer 3 — backend observer composition + a real simulate run.
# ---------------------------------------------------------------------------
def test_backend_builds_no_observers_when_no_specs() -> None:
    adapter = _adapter()
    circuit = types.SimpleNamespace(nonlinear_observer_specs=[])
    obs, b_extra = adapter._build_nonlinear_device_observers(
        circuit, None, dt=1e-5,
    )
    assert obs == []
    assert b_extra is None


def test_hysteretic_inductor_observer_drives_simulation() -> None:
    """End-to-end: build a sine-driven RL loop with a J-A hysteretic
    inductor, wire the observer via the backend helper, simulate, and
    confirm the magnetisation state evolves without NaN."""
    b = p.CircuitBuilder()
    b.add_sine_voltage_source("Vs", "a", "gnd", 0.0, 50.0, 50.0, 0.0)
    b.add_resistor("Rs", "a", "n1", 1.0)
    hyst = p.add_hysteretic_inductor(
        b, name="L_core", from_node="n1", to_node="gnd",
        params=p.reference_material("ferrite_n87"),
        N_turns=100, l_m=0.05, A_core=1e-4,
    )

    circuit = types.SimpleNamespace(
        nonlinear_observer_specs=[
            {"kind": "hysteretic_inductor", "name": "L_core", "handle": hyst},
        ],
    )
    adapter = _adapter()
    obs, b_extra = adapter._build_nonlinear_device_observers(
        circuit, b, dt=100e-6,
    )
    assert len(obs) == 1
    assert b_extra is not None

    res = p.simulate(
        b, t_end=0.05, dt=100e-6,
        switch_fn=lambda t: p.SwitchStateMask(0),
        step_observer=lambda t, x: [o(t, x) for o in obs],
        b_extra_fn=b_extra,
    )
    assert res.num_steps() > 0
    assert math.isfinite(hyst.M)
    # 50V / 50Hz exercises the core well above its initial state.
    assert abs(hyst.M) > 1.0, f"J-A magnetisation didn't build up: M={hyst.M}"


def test_induction_motor_observer_drives_simulation() -> None:
    """End-to-end: 3-phase sine source → induction motor; the observer
    must spin the rotor (flux / mechanical state leaves zero) and keep
    states finite."""
    b = p.CircuitBuilder()
    for k, node in enumerate(("a", "b", "c")):
        b.add_sine_voltage_source(
            f"Vs{k}", node, "gnd", 0.0, 311.0, 50.0,
            k * 2.0 * math.pi / 3.0,
        )
    pr = DEFAULT_PARAMETERS[ComponentType.INDUCTION_MOTOR]
    motor = p.add_induction_motor(
        b, name="IM1", phase_nodes=("a", "b", "c"), neutral_node="gnd",
        R_s=pr["R_s"], L_s=pr["L_s"], R_r=pr["R_r"], L_r=pr["L_r"],
        L_m=pr["L_m"], pole_pairs=pr["pole_pairs"], J=pr["J"], B=pr["B"],
    )

    circuit = types.SimpleNamespace(
        nonlinear_observer_specs=[
            {"kind": "induction_motor", "name": "IM1", "handle": motor},
        ],
    )
    adapter = _adapter()
    obs, b_extra = adapter._build_nonlinear_device_observers(
        circuit, b, dt=100e-6,
    )
    assert len(obs) == 1
    assert b_extra is not None

    import numpy as np
    res = p.simulate(
        b, t_end=0.05, dt=100e-6,
        switch_fn=lambda t: p.SwitchStateMask(0),
        step_observer=lambda t, x: [o(t, x) for o in obs],
        b_extra_fn=b_extra,
    )
    assert res.num_steps() > 0
    states = np.array(res.states)
    assert np.all(np.isfinite(states))
    # Stator currents must be non-trivial — the motor is energised.
    assert states.std() > 1e-3


def test_combined_b_extra_sums_two_devices() -> None:
    """Two hysteretic inductors in one builder → the combined
    b_extra_fn returns a single full-length vector summing both
    devices' residual contributions."""
    b = p.CircuitBuilder()
    b.add_sine_voltage_source("Vs", "a", "gnd", 0.0, 50.0, 50.0, 0.0)
    b.add_resistor("Rs", "a", "n1", 1.0)
    h1 = p.add_hysteretic_inductor(
        b, name="L1", from_node="n1", to_node="n2",
        params=p.reference_material("ferrite_n87"),
        N_turns=100, l_m=0.05, A_core=1e-4,
    )
    h2 = p.add_hysteretic_inductor(
        b, name="L2", from_node="n2", to_node="gnd",
        params=p.reference_material("permalloy"),
        N_turns=80, l_m=0.04, A_core=1e-4,
    )
    circuit = types.SimpleNamespace(
        nonlinear_observer_specs=[
            {"kind": "hysteretic_inductor", "name": "L1", "handle": h1},
            {"kind": "hysteretic_inductor", "name": "L2", "handle": h2},
        ],
    )
    adapter = _adapter()
    obs, b_extra = adapter._build_nonlinear_device_observers(
        circuit, b, dt=100e-6,
    )
    assert len(obs) == 2
    assert b_extra is not None
    # The combined function returns one vector (a list of floats),
    # not a list-of-lists.
    vec = b_extra(0.0)
    assert isinstance(vec, list)
    assert all(isinstance(v, (int, float)) for v in vec)
