"""Tests for the converter's C_BLOCK control-loop detection.

``CircuitConverter._infer_cblock_control_loops`` scans a circuit for a
``python_numba`` C_BLOCK regulating a PWM-driven switch and emits a
``cblock_loop_descriptor`` (which the backend then compiles + runs).
The pass is standalone and must NOT perturb the existing PI detection.
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


_PI_SRC = "def control(measured, setpoint, dt, state):\n    return 0.5\n"


def _siso_cblock_circuit(
    *, implementation: str = "python_numba", source: str = _PI_SRC,
):
    """Buck-ish topology:
        Vin, MOSFET M1, VOLTAGE_PROBE_GND(vout)→CTRL.in,
        CTRL.out→PWM.duty, PWM.out→M1.gate.
    """
    vin, sw, probe, cb, pwm, gid = (_cid() for _ in range(6))
    comps = [
        {"id": vin, "type": "VOLTAGE_SOURCE", "name": "Vin",
         "parameters": {"voltage": 24.0},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": sw, "type": "MOSFET_N", "name": "M1", "parameters": {},
         "pins": [{"index": 0, "name": "D"}, {"index": 1, "name": "G"},
                  {"index": 2, "name": "S"}]},
        {"id": probe, "type": "VOLTAGE_PROBE_GND", "name": "VP1",
         "parameters": {},
         "pins": [{"index": 0, "name": "in"}, {"index": 1, "name": "out"}]},
        {"id": cb, "type": "C_BLOCK", "name": "CTRL",
         "parameters": {
             "implementation": implementation, "python_source": source,
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
        probe: ["vout", "vp_out"],
        cb: ["vp_out", "cb_out"],
        pwm: ["gate", "cb_out"],
        gid: ["gnd"],
    }
    return {"components": comps, "node_map": node_map}


def test_detects_python_numba_cblock_loop() -> None:
    circ = _converter().build(_siso_cblock_circuit())
    descs = circ.cblock_loop_descriptors
    assert len(descs) == 1
    d = descs[0]
    assert d["switch_device"] == "M1"
    assert d["feedback_node"] == "Nvout"   # _node_label("vout")
    assert d["pwm_frequency"] == 50_000.0
    assert d["sample_time"] == 2e-5
    assert "def control" in d["source"]
    assert d["n_states"] == 1


def test_source_mode_cblock_is_not_detected() -> None:
    """A C-source (legacy) C_BLOCK must NOT produce a fast_block loop
    — only python_numba mode does."""
    circ = _converter().build(
        _siso_cblock_circuit(implementation="source")
    )
    assert circ.cblock_loop_descriptors == []


def test_empty_python_source_not_detected() -> None:
    circ = _converter().build(
        _siso_cblock_circuit(source="")
    )
    assert circ.cblock_loop_descriptors == []


def test_cblock_without_pwm_target_not_detected() -> None:
    """A python_numba C_BLOCK whose output doesn't drive a PWM is not
    a control loop — skip it."""
    data = _siso_cblock_circuit()
    # Re-point the PWM's duty input away from the C_BLOCK output.
    for cid_, nodes in data["node_map"].items():
        comp = next(c for c in data["components"] if c["id"] == cid_)
        if comp["type"] == "PWM_GENERATOR":
            data["node_map"][cid_] = ["gate", "some_other_node"]
    circ = _converter().build(data)
    assert circ.cblock_loop_descriptors == []


def test_detection_does_not_disturb_pi_path() -> None:
    """A circuit with NO C_BLOCK must yield an empty cblock list and
    leave closed_loop_descriptors (PI path) untouched / present."""
    vin, gid = _cid(), _cid()
    data = {
        "components": [
            {"id": vin, "type": "VOLTAGE_SOURCE", "name": "Vin",
             "parameters": {"voltage": 5.0},
             "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
            {"id": gid, "type": "GROUND", "name": "G", "parameters": {},
             "pins": [{"index": 0, "name": "gnd"}]},
        ],
        "node_map": {vin: ["a", "gnd"], gid: ["gnd"]},
    }
    circ = _converter().build(data)
    assert circ.cblock_loop_descriptors == []
    # PI path still attaches its (empty here) list.
    assert hasattr(circ, "closed_loop_descriptors")


def test_detected_descriptor_runs_through_backend() -> None:
    """The emitted descriptor must be consumable by the backend's
    execution engine — close the loop converter→backend."""
    from pulsimgui.services.backend_adapter import PulsimBackend

    circ = _converter().build(_siso_cblock_circuit())
    assert len(circ.cblock_loop_descriptors) == 1

    # The descriptor's feedback_node + switch_device must resolve on
    # the builder the converter produced.
    builder = circ.builder
    adapter = PulsimBackend.__new__(PulsimBackend)
    adapter._module = _real  # type: ignore[attr-defined]
    loops = adapter._build_cblock_closed_loops(
        circ.cblock_loop_descriptors, builder, 0.0,
    )
    assert len(loops) == 1
    assert hasattr(loops[0], "switch_fn")
    assert hasattr(loops[0], "step_observer")
