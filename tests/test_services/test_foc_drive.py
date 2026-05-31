"""Tests for the Field-Oriented-Control (FOC) PMSM drive wiring
(model → converter → v0 shim → backend FOC loop), mirroring the 3-layer
shape of ``test_pmsm_vsi_native_integration.py``.

The FOC controller is represented as a ``C_BLOCK`` marker carrying
``control_kind="foc"`` plus the loop gains / speed-reference ramp /
limits in its ``parameters``. It is a pure descriptor — NOT wired into
the power stage — that:

  1. Converter — ``_infer_foc_loops`` detects the marker co-resident with
     a native 3φ VSI + a dynamic PMSM and emits a ``foc_loop_descriptor``
     (gains + ramp + the controlled VSI name + the observed PMSM name).
     The marker is exempt from C_BLOCK translation + input-channel
     validation, so it adds nothing to the builder.
  2. Backend — ``_build_foc_loops`` builds the cascaded-PI step_observer
     (over the PMSM observer bundle's d-q feedback) + the inverse-
     Park/Clarke VSI switch_fn, and reports the controlled VSI name so the
     open-loop SPWM (``_build_vsi_switch_fns``) skips that inverter.
  3. End-to-end — a short real simulate run spins the rotor toward the +
     reference with a bounded i_d and bounded phase current (NOT the
     17-29 A garbage open-loop V/f produces on a PMSM).
"""
from __future__ import annotations

import math
import types
import uuid
from pathlib import Path

import numpy as np
import pulsim as p
import pytest

from pulsimgui.models.component import DEFAULT_PARAMETERS, ComponentType
from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import PulsimBackend
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_map

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


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


def _foc_params(**overrides: object) -> dict:
    """A FOC-marker C_BLOCK parameter bag (descriptor-only)."""
    params = {
        "control_kind": "foc",
        "vsi_name": "INV1",
        "pmsm_name": "M1",
        "v_bus": 360.0,
        "speed_ref_rpm": 1800.0,
        "speed_ramp_s": 0.02,
        "switching_frequency_hz": 20000.0,
        "n_inputs": 0,
        "n_outputs": 0,
        "implementation": "source",
    }
    params.update(overrides)
    return params


def _drive_components(
    *, pmsm_overrides: dict | None = None, foc_overrides: dict | None = None,
) -> tuple[list[dict], dict[str, list[str]]]:
    """A ±180 V bus → native VSI → PMSM + FOC-marker schematic payload.

    Ground nets are the literal "0" — the converter only maps "0" to the
    kernel ground, so the star point + bus midpoint stay grounded.
    """
    vp, vn, vid, mid, cb, gid = (_cid() for _ in range(6))
    comps = [
        {"id": vp, "type": "VOLTAGE_SOURCE", "name": "VP",
         "parameters": {"waveform": {"type": "dc", "value": 180.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vn, "type": "VOLTAGE_SOURCE", "name": "VN",
         "parameters": {"waveform": {"type": "dc", "value": 180.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vid, "type": "THREE_PHASE_VSI", "name": "INV1",
         "parameters": _vsi_params(switching_frequency_hz=20000.0),
         "pins": [{"index": i, "name": n} for i, n in
                  enumerate(["VDC+", "VDC-", "A", "B", "C"])]},
        {"id": mid, "type": "PMSM", "name": "M1",
         "parameters": _pmsm_params(Rs=6.6, Ld=12e-3, Lq=12e-3, psi_pm=0.05,
                                    pole_pairs=3, J=2e-4, b_friction=5e-4,
                                    **(pmsm_overrides or {})),
         "pins": [{"index": i, "name": n}
                  for i, n in enumerate(["A", "B", "C", "N"])]},
        {"id": cb, "type": "C_BLOCK", "name": "FOC1",
         "parameters": _foc_params(**(foc_overrides or {})),
         "pins": []},
        {"id": gid, "type": "GROUND", "name": "G1", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        vp: ["busp", "0"], vn: ["0", "busn"],
        vid: ["busp", "busn", "pha", "phb", "phc"],
        mid: ["pha", "phb", "phc", "0"], gid: ["0"],
    }
    return comps, node_map


# ---------------------------------------------------------------------------
# Layer 1+2 — converter detects the FOC marker; it doesn't touch the builder.
# ---------------------------------------------------------------------------
def test_converter_emits_foc_loop_descriptor() -> None:
    """A FOC marker (C_BLOCK control_kind='foc') alongside a VSI + PMSM
    yields one foc_loop_descriptor binding the VSI + PMSM by name and
    carrying the loop gains / speed-reference ramp / limits."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    descs = list(getattr(circ, "foc_loop_descriptors", []))
    assert len(descs) == 1
    d = descs[0]
    assert d["vsi_name"] == "INV1"
    assert d["pmsm_name"] == "M1"
    # Gains default to the validated VLT403U recipe.
    assert d["speed_kp"] == 0.17
    assert d["speed_ki"] == 6.0
    assert d["current_kp"] == 45.0
    assert d["current_ki"] == 24000.0
    assert d["id_ref"] == 0.0
    assert d["iq_limit"] == 3.0
    assert d["speed_ref_rpm"] == 1800.0


def test_foc_marker_adds_nothing_to_builder() -> None:
    """The FOC marker is descriptor-only: it is NOT translated as a
    fast_block, so the builder grows only the VSI (6 switches) — the
    marker registers no switches, nodes, or control components."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    # Only the native VSI's six switches exist (the marker added none).
    assert circ.builder.graph.num_switches == 6
    # The PMSM observer spec is present; no extra control/virtual record
    # was created for the FOC marker.
    pmsm_specs = [s for s in circ.nonlinear_observer_specs
                  if s.get("kind") == "pmsm"]
    assert len(pmsm_specs) == 1
    # The marker is not recorded as a virtual component / cblock loop.
    assert not any(
        getattr(r, "name", "") == "FOC1"
        for r in getattr(circ, "virtual_component_records", [])
    )
    assert getattr(circ, "cblock_loop_descriptors", []) == []


def test_foc_marker_with_unwired_pins_does_not_raise() -> None:
    """A FOC marker with no input wiring must NOT trip the C_BLOCK
    input-channel validation (which rejects a normal C_BLOCK whose input
    is undriven). The marker is exempt."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    # Must not raise CircuitConversionError.
    circ = conv.build({"components": comps, "node_map": node_map})
    assert len(circ.foc_loop_descriptors) == 1


def test_no_foc_descriptor_without_marker() -> None:
    """Without a control_kind='foc' marker, no FOC descriptor is emitted —
    the open-loop VSI path is untouched (additive). The VSI + PMSM alone
    must NOT spuriously trigger FOC detection."""
    comps, node_map = _drive_components()
    # Drop the FOC-marker C_BLOCK entirely (keep VP/VN/VSI/PMSM/GND).
    comps = [c for c in comps if c.get("name") != "FOC1"]
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    assert list(getattr(circ, "foc_loop_descriptors", [])) == []
    # The native VSI is still built (open-loop path intact).
    assert len(circ.vsi_specs) == 1


# ---------------------------------------------------------------------------
# Layer 3 — backend builds the FOC loop; SPWM excludes the controlled VSI.
# ---------------------------------------------------------------------------
def test_build_foc_loops_returns_observer_switch_and_vsi_name() -> None:
    """_build_foc_loops turns the descriptor into a (step_observer,
    switch_fn) pair and reports the controlled VSI name."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder
    adapter = _adapter()

    # The PMSM observer build stashes the bundle the FOC loop reads.
    adapter._build_nonlinear_device_observers(circ, b, dt=2e-6)
    step_obs, sw_fns, vsi_names = adapter._build_foc_loops(circ, b)
    assert len(step_obs) == 1
    assert len(sw_fns) == 1
    assert vsi_names == {"INV1"}
    # The pmsm spec carries the live observer bundle for the FOC loop.
    bundle = next(s.get("bundle") for s in circ.nonlinear_observer_specs
                  if s.get("kind") == "pmsm")
    assert bundle is not None
    assert hasattr(bundle, "i_d") and hasattr(bundle, "theta_rad")


def test_spwm_excludes_foc_controlled_vsi() -> None:
    """A FOC-controlled VSI is excluded from the open-loop SPWM path so
    the SPWM and the FOC don't both drive the same six switch bits."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder
    adapter = _adapter()

    # Without exclusion the native VSI yields an SPWM switch_fn.
    assert len(adapter._build_vsi_switch_fns(circ, b)) == 1
    # Excluding the FOC-controlled inverter drops it.
    assert adapter._build_vsi_switch_fns(circ, b, exclude_names={"INV1"}) == []


def test_foc_switch_fn_is_replayable_function_of_time() -> None:
    """The FOC switch_fn must be a deterministic function of t (so the
    electrothermal post-processor can REPLAY it at historical timesteps).
    Re-querying a past t after stepping forward returns the SAME mask —
    a stateful switch_fn frozen at its final command would not."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder
    adapter = _adapter()
    dso, dbe = adapter._build_nonlinear_device_observers(circ, b, dt=4e-6)
    fso, fsw, _ = adapter._build_foc_loops(circ, b)
    foc_switch = fsw[0]

    def step(t: float, x: object) -> None:
        for o in dso:
            o(t, x)
        for o in fso:
            o(t, x)

    # Run a short sim to populate the FOC command log over real timesteps.
    p.simulate(
        b, t_end=6e-3, dt=4e-6,
        switch_fn=foc_switch,
        step_observer=step,
        b_extra_fn=dbe,
        enable_nonlinear_refresh=True,
    )

    # Replay an early, mid, and late time twice each (forward then again
    # after a later query). Each (t) must map to a STABLE mask.
    probes = [1.0e-3, 3.0e-3, 5.0e-3]
    masks_first = {t: [foc_switch(t).get(i) for i in range(6)] for t in probes}
    # Query a late time, then re-query the earlier ones.
    _ = foc_switch(5.5e-3)
    for t in probes:
        again = [foc_switch(t).get(i) for i in range(6)]
        assert again == masks_first[t], (
            f"FOC switch_fn not replay-stable at t={t}"
        )
    # Sanity: each leg is complementary (HS/LS never both on).
    hs = [0, 2, 4]
    ls = [1, 3, 5]
    for t in probes:
        m = foc_switch(t)
        for h, low in zip(hs, ls):
            assert bool(m.get(h)) != bool(m.get(low))


def test_foc_drive_spins_rotor_toward_reference() -> None:
    """End-to-end: ±180 V bus → native VSI → PMSM + FOC marker, built via
    the converter + backend helpers. A short unloaded run spins the rotor
    toward the +reference with a bounded i_d and a bounded phase current
    (NOT the 17-29 A garbage open-loop V/f produces on a PMSM)."""
    comps, node_map = _drive_components(
        pmsm_overrides={"tau_load": 0.0},
        foc_overrides={"speed_ramp_s": 0.02},
    )
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder
    adapter = _adapter()
    dt = 4e-6

    dso, dbe = adapter._build_nonlinear_device_observers(circ, b, dt=dt)
    fso, fsw, fnames = adapter._build_foc_loops(circ, b)
    vsw = adapter._build_vsi_switch_fns(circ, b, exclude_names=fnames)
    assert len(fso) == 1 and len(fsw) == 1 and fnames == {"INV1"}
    # SPWM excluded for the FOC VSI → only the FOC switch_fn drives it.
    assert vsw == []

    num_sw = b.graph.num_switches
    sub_fns = list(vsw) + list(fsw)
    switch_fn = (
        p.make_combined_switch_fn(num_sw, sub_fns)
        if len(sub_fns) > 1 else sub_fns[0]
    )
    bundle = next(s["bundle"] for s in circ.nonlinear_observer_specs
                  if s["kind"] == "pmsm")
    motor = next(s["handle"] for s in circ.nonlinear_observer_specs
                 if s["kind"] == "pmsm")

    def step(t: float, x: object) -> None:
        for o in dso:
            o(t, x)
        for o in fso:
            o(t, x)

    res = p.simulate(
        b, t_end=0.02, dt=dt,
        switch_fn=switch_fn,
        step_observer=step,
        b_extra_fn=dbe,
        enable_nonlinear_refresh=True,
    )
    assert res.num_steps() > 0
    states = np.array([list(s) for s in res.states])
    assert np.all(np.isfinite(states))

    rpm = np.asarray(bundle.omega_rad_s) * 60.0 / (2.0 * math.pi)
    i_d = np.asarray(bundle.i_d)
    i_a = np.asarray(bundle.i_a)
    # Rotor accelerated toward the POSITIVE reference (FOC tracking the
    # ramp), and the handle's mechanical state agrees.
    assert rpm[-1] > 200.0
    assert motor.mech.omega_rad_s > 0.0
    # i_d held near its zero reference (FOC decoupling working) — NOT the
    # ~31 A explosion you get from feeding the MECHANICAL angle.
    assert np.abs(i_d).max() < 1.0
    # Phase current bounded well under the open-loop garbage band.
    assert np.abs(i_a).max() < 5.0


def test_build_foc_loops_empty_without_descriptor() -> None:
    """No foc_loop_descriptors ⇒ the backend builds nothing (the FOC path
    is fully additive)."""
    adapter = _adapter()
    circuit = types.SimpleNamespace(
        foc_loop_descriptors=[],
        vsi_specs=[],
        nonlinear_observer_specs=[],
    )
    step_obs, sw_fns, names = adapter._build_foc_loops(
        circuit, p.CircuitBuilder()
    )
    assert step_obs == [] and sw_fns == [] and names == set()


# ---------------------------------------------------------------------------
# Shipped examples — the doubler (19) + PFC (20) compressor drives must each
# carry a FOC marker bound to their VSI + PMSM, and convert without error.
# (No long sim here — just the converter/backend wiring.)
# ---------------------------------------------------------------------------
def _convert_example(name: str):
    """Load a shipped ``.pulsim``, build its per-component node map the same
    way the GUI does, and convert it through ``CircuitConverter``."""
    path = _EXAMPLES / name
    project = Project.load(path)
    circ = project.get_active_circuit()
    node_map_raw = build_node_map(circ)
    comps: list[dict] = []
    node_map: dict[str, list[str]] = {}
    for component in circ.components.values():
        cid = str(component.id)
        comps.append(component.to_dict())
        node_map[cid] = [
            str(node_map_raw.get((cid, pin.index), f"_nc_{cid}_{pin.index}"))
            for pin in sorted(component.pins, key=lambda pp: pp.index)
        ]
    conv = CircuitConverter(make_compat_module(p))
    return conv.build({"components": comps, "node_map": node_map})


@pytest.mark.parametrize(
    "example, v_bus",
    [
        ("19_doubler_drive_compressor.pulsim", 340.0),
        ("20_pfc_drive_compressor.pulsim", 400.0),
    ],
)
def test_compressor_example_carries_foc_marker(example: str, v_bus: float) -> None:
    """Both compressor-drive examples must convert without error and emit
    exactly one FOC descriptor bound to their VSI ("VSI") + PMSM ("M1"),
    carrying the front-end's nominal ``v_bus`` and the validated VLT403U
    gain recipe. This is what makes the persisted file drive the PMSM with
    field-oriented control (closed i_d/i_q/speed loops) instead of the
    pole-slipping open-loop V/f."""
    circ = _convert_example(example)

    descs = list(getattr(circ, "foc_loop_descriptors", []))
    assert len(descs) == 1, f"{example}: expected one FOC descriptor"
    d = descs[0]
    assert d["vsi_name"] == "VSI"
    assert d["pmsm_name"] == "M1"
    # The descriptor carries the front-end's nominal DC bus (used by the
    # backend to normalise modulation + clamp v_d/v_q).
    assert d["v_bus"] == pytest.approx(v_bus)
    # Validated VLT403U FOC recipe (same gains as example 21).
    assert d["speed_kp"] == pytest.approx(0.17)
    assert d["speed_ki"] == pytest.approx(6.0)
    assert d["current_kp"] == pytest.approx(45.0)
    assert d["current_ki"] == pytest.approx(24000.0)
    assert d["id_ref"] == pytest.approx(0.0)
    assert d["iq_limit"] == pytest.approx(3.0)
    assert d["speed_ref_rpm"] == pytest.approx(1800.0)


@pytest.mark.parametrize(
    "example",
    [
        "19_doubler_drive_compressor.pulsim",
        "20_pfc_drive_compressor.pulsim",
    ],
)
def test_compressor_example_foc_binds_to_native_vsi_and_pmsm(example: str) -> None:
    """The FOC descriptor in each example resolves to the example's native
    3φ VSI (six switches) + dynamic PMSM observer — the binding the backend
    ``_build_foc_loops`` needs to close the loops + drive the inverter."""
    circ = _convert_example(example)
    b = circ.builder
    adapter = _adapter()

    # The PMSM observer build stashes the bundle the FOC loop reads.
    adapter._build_nonlinear_device_observers(circ, b, dt=2e-6)
    step_obs, sw_fns, vsi_names = adapter._build_foc_loops(circ, b)
    assert len(step_obs) == 1
    assert len(sw_fns) == 1
    assert vsi_names == {"VSI"}
    # The FOC-controlled VSI is excluded from the open-loop SPWM path so the
    # SPWM + FOC don't both drive the same six switch bits.
    assert adapter._build_vsi_switch_fns(circ, b, exclude_names=vsi_names) == []
    # The example's native VSI contributes the six switches the FOC drives
    # (plus any front-end switches: the doubler has none extra; the PFC adds
    # its boost MOSFET + bridge diodes).
    assert int(b.graph.num_switches) >= 6
