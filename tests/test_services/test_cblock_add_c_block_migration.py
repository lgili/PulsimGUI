"""Tests for the pulsim 1.8 ``pulsim.add_c_block`` migration.

The migration moves C_BLOCK virtual-component dispatch from the legacy
``circuit.add_virtual_component("c_block", ...)`` path to the native
``pulsim.add_c_block(builder, inputs=, outputs=, dt=, fn|lib|code=,
name=, sim_dt=)`` API. These tests assert:

  * The converter snapshots each C_BLOCK's electrical wiring +
    authoring fields into ``circuit.c_block_records``.
  * The backend's post-pass (``_register_c_blocks_via_pulsim_18``)
    dispatches to ``pulsim.add_c_block`` with the right kwargs for
    each ``implementation`` mode (python_numba / lib / source).
  * The legacy ``add_virtual_component("c_block", ...)`` record is
    dropped from ``circuit.virtual_component_records`` once a block
    has been re-registered (avoids double-instantiation in the C++
    kernel).
  * Path-A blocks (python_numba blocks driving a closed PWM loop) are
    SKIPPED by Path B — they continue to flow through
    ``_build_cblock_closed_loops``.
"""
from __future__ import annotations

import types
import uuid

import pulsim as _real

from pulsimgui.services.backend_adapter import (
    BackendInfo,
    BackendVersion,
    PulsimBackend,
)
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _cid() -> str:
    return str(uuid.uuid4())


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(_real))


def _backend_adapter(module: object) -> PulsimBackend:
    info = BackendInfo(
        identifier="pulsim",
        name="Pulsim",
        version="1.8.0",
        status="available",
        parsed_version=BackendVersion(1, 8, 0),
    )
    return PulsimBackend(module, info)


def _standalone_cblock_circuit(
    *, implementation: str, **extra_params: object,
) -> dict[str, object]:
    """A tiny topology with a single C_BLOCK driven by a voltage probe.

        Vsrc → meas_e ──(VP1)──► meas_sig ──► C_BLOCK.in0
        Rload between 'out' and gnd; C_BLOCK.out drives 'out'.

    The block has nothing to do with a PWM loop, so it should be a
    PATH B candidate (and NOT show up in
    ``cblock_loop_descriptors``).
    """
    params = {
        "implementation": implementation,
        "n_inputs": 1,
        "n_outputs": 1,
        "n_states": 1,
        "sample_time": 1.0e-4,
    }
    params.update(extra_params)

    src_id, rmeas, vp_id, rload, cb = (_cid() for _ in range(5))
    components = [
        {"id": src_id, "type": "VOLTAGE_SOURCE", "name": "Vsrc",
         "pin_nodes": ["meas_e", "0"],
         "parameters": {"waveform": {"type": "dc", "value": 1.0}}},
        {"id": rmeas, "type": "RESISTOR", "name": "Rmeas",
         "pin_nodes": ["meas_e", "0"],
         "parameters": {"resistance": 1.0}},
        {"id": vp_id, "type": "VOLTAGE_PROBE_GND", "name": "VP1",
         "pin_nodes": ["meas_e", "meas_sig"],
         "pins": [{"index": 0, "name": "IN"}, {"index": 1, "name": "OUT"}],
         "parameters": {}},
        {"id": rload, "type": "RESISTOR", "name": "Rload",
         "pin_nodes": ["out", "0"],
         "parameters": {"resistance": 10.0}},
        {"id": cb, "type": "C_BLOCK", "name": "CB1",
         "pin_nodes": ["meas_sig", "out"],
         "pins": [{"index": 0, "name": "IN0"}, {"index": 1, "name": "OUT"}],
         "parameters": params},
    ]
    return {
        "components": components,
        "node_map": {},
        "node_aliases": {"meas_e": "meas_e", "meas_sig": "meas_sig", "out": "out"},
    }


# --------------------------------------------------------------------------
# Converter — Commit 1 surface.
# --------------------------------------------------------------------------


def test_converter_emits_c_block_records_for_python_numba() -> None:
    """python_numba blocks land in ``c_block_records`` with their wiring."""
    py_src = (
        "def control(measured, state):\n"
        "    state[0] += 0.1\n"
        "    return 2.0 * measured + state[0]\n"
    )
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="python_numba", python_source=py_src,
        )
    )
    records = getattr(circ, "c_block_records", None)
    assert records is not None
    assert len(records) == 1
    rec = records[0]
    assert rec["name"] == "CB1"
    assert rec["implementation"] == "python_numba"
    # Probe chase: the C_BLOCK's IN0 is wired to a probe's signal node,
    # so the record carries the electrical input node instead.
    assert rec["input_nodes"] == ["meas_e"]
    assert rec["output_node_pairs"] == [("out", "0")]
    assert rec["python_source"] == py_src
    assert rec["n_inputs"] == 1 and rec["n_outputs"] == 1
    assert rec["sample_time"] == 1.0e-4


def test_converter_emits_c_block_records_for_lib_mode() -> None:
    """lib= mode preserves ``lib_path`` in the record."""
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="lib", lib_path="/tmp/fake.so",
        )
    )
    records = getattr(circ, "c_block_records", [])
    assert len(records) == 1
    assert records[0]["implementation"] == "lib"
    assert records[0]["lib_path"] == "/tmp/fake.so"


def test_converter_emits_c_block_records_for_source_mode() -> None:
    """Inline source_code mode preserves the C body."""
    body = "out[0] = 3.5 * in[0] + 0.5;"
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="source", source_code=body,
        )
    )
    records = getattr(circ, "c_block_records", [])
    assert len(records) == 1
    assert records[0]["implementation"] == "source"
    assert records[0]["source_code"] == body


def test_converter_skips_foc_marker_in_c_block_records() -> None:
    """FOC markers are descriptor-only — must not leak into Path B."""
    cb = _cid()
    components = [
        {"id": cb, "type": "C_BLOCK", "name": "FOC_MARK",
         "pin_nodes": [],
         "parameters": {"control_kind": "foc"}},
    ]
    circ = _converter().build({
        "components": components,
        "node_map": {},
        "node_aliases": {},
    })
    assert getattr(circ, "c_block_records", []) == []


# --------------------------------------------------------------------------
# Backend post-pass — Commit 2 surface (with a mock ``add_c_block``).
# --------------------------------------------------------------------------


class _CapturedCall:
    """Records every ``add_c_block`` invocation for assertion."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, builder: object, **kwargs: object) -> object:
        self.calls.append({"builder": builder, **kwargs})
        # Mimic what real add_c_block does: stash a handle on builder._c_blocks
        if not hasattr(builder, "_c_blocks"):
            try:
                builder._c_blocks = []
            except Exception:
                pass
        handle = types.SimpleNamespace(name=kwargs.get("name", "CBLK"))
        try:
            builder._c_blocks.append(handle)
        except Exception:
            pass
        return handle


def _wrap_pulsim_with_mock_add_c_block(captured: _CapturedCall) -> types.ModuleType:
    """Return a minimal stand-in module that proxies real pulsim but
    overrides ``add_c_block`` with the capture mock."""
    shim = types.ModuleType("pulsim_shim_for_test")
    for attr in dir(_real):
        if not attr.startswith("__"):
            setattr(shim, attr, getattr(_real, attr))
    shim.add_c_block = captured
    return shim


def test_backend_post_pass_dispatches_python_numba_via_fn() -> None:
    """python_numba records call add_c_block with fn=, dt, name, sim_dt."""
    py_src = (
        "def control(measured, state):\n"
        "    return 2.0 * measured\n"
    )
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="python_numba", python_source=py_src,
        )
    )
    captured = _CapturedCall()
    shim = _wrap_pulsim_with_mock_add_c_block(captured)
    adapter = _backend_adapter(shim)

    n = adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=1.0e-5,
    )
    assert n == 1
    assert len(captured.calls) == 1
    call = captured.calls[0]
    assert call["name"] == "CB1"
    assert call["dt"] == 1.0e-4
    assert call["sim_dt"] == 1.0e-5
    assert call["inputs"] == [("v", "meas_e")]
    assert call["outputs"] == [("v", "out", "0")]
    # python path → fn= present, lib= / code= absent.
    assert callable(call.get("fn"))
    assert "lib" not in call and "code" not in call


def test_backend_post_pass_dispatches_lib_mode() -> None:
    """``implementation="lib"`` calls add_c_block with lib=<path>."""
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="lib", lib_path="/tmp/myblock.so",
        )
    )
    captured = _CapturedCall()
    shim = _wrap_pulsim_with_mock_add_c_block(captured)
    adapter = _backend_adapter(shim)
    n = adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=1.0e-5,
    )
    assert n == 1
    call = captured.calls[0]
    assert call["lib"] == "/tmp/myblock.so"
    assert "fn" not in call and "code" not in call


def test_backend_post_pass_dispatches_source_mode_with_inline_body() -> None:
    """Inline source_code goes through code=, lang="c"."""
    body = "out[0] = 3.5 * in[0] + 0.5;"
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="source", source_code=body,
            extra_cflags=["-O3"],
        )
    )
    captured = _CapturedCall()
    shim = _wrap_pulsim_with_mock_add_c_block(captured)
    adapter = _backend_adapter(shim)
    n = adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=1.0e-5,
    )
    assert n == 1
    call = captured.calls[0]
    assert call["code"] == body
    assert call["lang"] == "c"
    assert call["extra_compile_args"] == ["-O3"]


def test_backend_post_pass_no_op_when_add_c_block_unavailable() -> None:
    """Pulsim < 1.8 (no ``add_c_block``) → post-pass is a clean no-op."""
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="lib", lib_path="/tmp/myblock.so",
        )
    )
    # Shim without add_c_block.
    shim = types.ModuleType("pulsim_shim_no_addcblock")
    for attr in dir(_real):
        if not attr.startswith("__") and attr != "add_c_block":
            setattr(shim, attr, getattr(_real, attr))
    if hasattr(shim, "add_c_block"):
        delattr(shim, "add_c_block")
    adapter = _backend_adapter(shim)
    n = adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=1.0e-5,
    )
    assert n == 0
    # Legacy record must still be present so the kernel still tries to
    # do something with the block.
    cblock_records = [
        r for r in circ.virtual_component_records
        if r.get("kind") == "c_block"
    ]
    assert len(cblock_records) == 1


def test_backend_post_pass_pops_legacy_record() -> None:
    """Once a block is re-registered, its legacy entry is removed."""
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="lib", lib_path="/tmp/myblock.so",
        )
    )
    legacy_before = [
        r for r in circ.virtual_component_records
        if r.get("kind") == "c_block"
    ]
    assert len(legacy_before) == 1
    captured = _CapturedCall()
    shim = _wrap_pulsim_with_mock_add_c_block(captured)
    adapter = _backend_adapter(shim)
    adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=1.0e-5,
    )
    legacy_after = [
        r for r in circ.virtual_component_records
        if r.get("kind") == "c_block"
    ]
    assert legacy_after == []


def test_backend_post_pass_skips_path_a_blocks() -> None:
    """A python_numba block in a closed PWM loop stays on Path A.

    Path A handles it via ``_build_cblock_closed_loops`` (duty mask);
    ``add_c_block`` produces a controlled V/I source instead, so the
    two MUST NOT both fire for the same block.
    """
    py_src = (
        "def control(measured, setpoint, dt, state):\n"
        "    return 0.5\n"
    )
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
        probe: ["vout", "vp_out"],
        cb: ["vp_out", "cb_out"],
        pwm: ["gate", "cb_out"],
        gid: ["gnd"],
    }
    circ = _converter().build({"components": comps, "node_map": node_map})

    # Path A should have detected the loop.
    descs = list(getattr(circ, "cblock_loop_descriptors", []) or [])
    assert len(descs) == 1
    assert descs[0]["cblock_name"] == "CTRL"

    # Path B should NOT re-register that block.
    captured = _CapturedCall()
    shim = _wrap_pulsim_with_mock_add_c_block(captured)
    adapter = _backend_adapter(shim)
    n = adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=1.0e-5,
    )
    assert n == 0
    assert captured.calls == []


def test_backend_post_pass_clamps_zero_sample_time() -> None:
    """``sample_time=0`` falls back to the simulation dt to satisfy
    ``add_c_block``'s ``dt > 0`` precondition."""
    py_src = "def control(measured, state):\n    return measured\n"
    circ = _converter().build(
        _standalone_cblock_circuit(
            implementation="python_numba",
            python_source=py_src,
            sample_time=0.0,
        )
    )
    captured = _CapturedCall()
    shim = _wrap_pulsim_with_mock_add_c_block(captured)
    adapter = _backend_adapter(shim)
    n = adapter._register_c_blocks_via_pulsim_18(
        circ, circ.builder, sim_dt=2.5e-6,
    )
    assert n == 1
    # add_c_block requires dt > 0; sample_time was 0 → fall back to sim_dt.
    assert captured.calls[0]["dt"] == 2.5e-6
