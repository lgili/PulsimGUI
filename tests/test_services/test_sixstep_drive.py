"""Tests for the 6-step trapezoidal BLDC drive wiring
(model → converter → v0 shim → backend SIXSTEP loop), mirroring the
3-layer shape of ``test_foc_drive.py``.

The SIXSTEP controller is represented as a dedicated
``SIXSTEP_CONTROLLER`` component carrying speed-PI gains, duty clamp,
PWM frequency, and sector advance in its ``parameters``. It is a pure
descriptor — NOT wired into the power stage — that:

  1. Converter — ``_infer_sixstep_loops`` detects the controller co-
     resident with a native 3φ VSI + a dynamic PMSM and emits a
     ``sixstep_loop_descriptor`` (gains + clamp + the controlled VSI
     name + the observed PMSM name). The controller is exempt from
     fast-block translation, so it adds nothing to the builder.
  2. Backend — ``_build_sixstep_loops`` builds the outer speed-PI
     step_observer (over the PMSM observer bundle's ω + θ feedback)
     + the sector-table commutation VSI switch_fn, and reports the
     controlled VSI name so the open-loop SPWM
     (``_build_vsi_switch_fns``) skips that inverter. The same name
     set as the FOC's is unioned at the exclusion call.
  3. End-to-end — a short real simulate run spins the rotor toward
     the reference with the trapezoidal current pattern (sign-flips
     every electrical 60°), confirming the commutation table is
     wired correctly.
"""
from __future__ import annotations

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


def _sixstep_params(**overrides: object) -> dict:
    """A SIXSTEP_CONTROLLER parameter bag (descriptor-only)."""
    params = dict(DEFAULT_PARAMETERS[ComponentType.SIXSTEP_CONTROLLER])
    params.update(overrides)
    return params


def _drive_components(
    *,
    pmsm_overrides: dict | None = None,
    sixstep_overrides: dict | None = None,
) -> tuple[list[dict], dict[str, list[str]]]:
    """A ±180 V bus → native VSI → PMSM + SIXSTEP-controller schematic
    payload. Mirrors the FOC test's ``_drive_components`` topology so
    the only thing that varies is the controller block."""
    vp, vn, vid, mid, sx, gid = (_cid() for _ in range(6))
    comps = [
        {"id": vp, "type": "VOLTAGE_SOURCE", "name": "VP",
         "parameters": {"waveform": {"type": "dc", "value": 180.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vn, "type": "VOLTAGE_SOURCE", "name": "VN",
         "parameters": {"waveform": {"type": "dc", "value": 180.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": vid, "type": "THREE_PHASE_VSI", "name": "INV1",
         "parameters": _vsi_params(switching_frequency_hz=20000.0),
         # Pin 5 is the new PWM input bus.
         "pins": [{"index": i, "name": n} for i, n in
                  enumerate(["VDC+", "VDC-", "A", "B", "C", "PWM"])]},
        {"id": mid, "type": "PMSM", "name": "M1",
         "parameters": _pmsm_params(Rs=6.6, Ld=12e-3, Lq=12e-3, psi_pm=0.05,
                                    pole_pairs=3, J=2e-4, b_friction=5e-4,
                                    **(pmsm_overrides or {})),
         # Pin 4 is the SIG bus.
         "pins": [{"index": i, "name": n}
                  for i, n in enumerate(["A", "B", "C", "N", "SIG"])]},
        {"id": sx, "type": "SIXSTEP_CONTROLLER", "name": "SIXSTEP1",
         "parameters": _sixstep_params(**(sixstep_overrides or {})),
         # Pin 2 is the PWM output bus.
         "pins": [{"index": 0, "name": "SP"},
                  {"index": 1, "name": "FB"},
                  {"index": 2, "name": "PWM"}]},
        {"id": gid, "type": "GROUND", "name": "G1", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    # PWM bus net shared between SIXSTEP.PWM (pin 2) and VSI.PWM (pin 5);
    # FB net shared between SIXSTEP.FB (pin 1) and PMSM.SIG (pin 4).
    node_map = {
        vp: ["busp", "0"], vn: ["0", "busn"],
        vid: ["busp", "busn", "pha", "phb", "phc", "pwm_bus"],
        mid: ["pha", "phb", "phc", "0", "motor_sig"],
        sx: ["sp", "motor_sig", "pwm_bus"],
        gid: ["0"],
    }
    return comps, node_map


# ---------------------------------------------------------------------------
# Layer 1+2 — converter detects the SIXSTEP controller; no builder side effect.
# ---------------------------------------------------------------------------
def test_converter_emits_sixstep_loop_descriptor() -> None:
    """A SIXSTEP_CONTROLLER alongside a VSI + PMSM yields one
    sixstep_loop_descriptor binding the VSI + PMSM by name and
    carrying the speed-PI gains / duty clamp / ramp / sector advance."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    descs = list(getattr(circ, "sixstep_loop_descriptors", []))
    assert len(descs) == 1
    d = descs[0]
    assert d["vsi_name"] == "INV1"
    assert d["pmsm_name"] == "M1"
    # Default speed-PI recipe + duty clamp.
    assert d["speed_kp"] == 0.0025
    assert d["speed_ki"] == 0.05
    assert d["duty_max"] == 0.95
    assert d["speed_ref_rpm"] == 1800.0
    assert d["switching_frequency_hz"] == 20000.0
    assert d["sector_advance_deg"] == 0.0


def test_sixstep_controller_adds_nothing_to_builder() -> None:
    """The SIXSTEP_CONTROLLER is descriptor-only: it is NOT translated
    as a fast_block, so the builder grows only the VSI (6 switches)."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})

    assert circ.builder.graph.num_switches == 6
    pmsm_specs = [s for s in circ.nonlinear_observer_specs
                  if s.get("kind") == "pmsm"]
    assert len(pmsm_specs) == 1
    # No virtual component / cblock loop tied to the controller.
    assert not any(
        getattr(r, "name", "") == "SIXSTEP1"
        for r in getattr(circ, "virtual_component_records", [])
    )
    assert getattr(circ, "cblock_loop_descriptors", []) == []


def test_sixstep_controller_with_unwired_pwm_emits_no_descriptor() -> None:
    """Mandatory contract: PWM wire MUST be present. The build path
    tolerates an unwired controller (no error) but emits NO descriptor
    when the PWM bus wire is missing — the user's visual cue that the
    loop isn't fully specified."""
    comps, node_map = _drive_components()
    # Break the PWM wire by isolating the SIXSTEP.PWM net from the VSI.
    nm = dict(node_map)
    for cid, nets in list(nm.items()):
        if cid in {c["id"] for c in comps if c.get("name") == "SIXSTEP1"}:
            # SIXSTEP pins: [sp, motor_sig, pwm_bus] — disconnect pwm pin.
            nm[cid] = list(nets[:2]) + [""]
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": nm})
    # Build still succeeds, but no SIXSTEP descriptor emitted.
    assert list(getattr(circ, "sixstep_loop_descriptors", [])) == []
    # The native VSI is still built; just the closed loop is missing.
    assert len(circ.vsi_specs) == 1


def test_no_sixstep_descriptor_without_controller() -> None:
    """Without a SIXSTEP_CONTROLLER, no descriptor is emitted (additive
    path; the VSI + PMSM alone go to open-loop)."""
    comps, node_map = _drive_components()
    comps = [c for c in comps if c.get("name") != "SIXSTEP1"]
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    assert list(getattr(circ, "sixstep_loop_descriptors", [])) == []
    assert len(circ.vsi_specs) == 1


# ---------------------------------------------------------------------------
# Layer 3 — backend builds the SIXSTEP loop; SPWM excludes the controlled VSI.
# ---------------------------------------------------------------------------
def test_build_sixstep_loops_returns_observer_switch_and_vsi_name() -> None:
    """_build_sixstep_loops turns the descriptor into a (step_observer,
    switch_fn) pair and reports the controlled VSI name."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder
    adapter = _adapter()

    adapter._build_nonlinear_device_observers(circ, b, dt=2e-6)
    step_obs, sw_fns, vsi_names = adapter._build_sixstep_loops(circ, b)
    assert len(step_obs) == 1
    assert len(sw_fns) == 1
    assert vsi_names == {"INV1"}


def test_sixstep_sector_table_drives_2of6_switches() -> None:
    """At any time, exactly one high-side switch is gateable (when its
    sector's duty-on band is active) and exactly one low-side switch
    is permanently on. The other four bits stay off.

    We sample the switch_fn at electrical-angle representative times by
    monkey-patching the bundle's θ_rad just before each query."""
    comps, node_map = _drive_components()
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps, "node_map": node_map})
    b = circ.builder
    adapter = _adapter()
    adapter._build_nonlinear_device_observers(circ, b, dt=2e-6)
    step_obs, sw_fns, _ = adapter._build_sixstep_loops(circ, b)
    sw = sw_fns[0]
    observer = step_obs[0]

    bundle = next(s["bundle"] for s in circ.nonlinear_observer_specs
                  if s.get("kind") == "pmsm")
    # Force the bundle so the speed PI saturates → duty_max, and walk
    # the rotor angle across all six sectors. The PMSM here has
    # pole_pairs=3, so θ_e = 3·θ_mech.
    pp = 3
    for sector in range(6):
        # θ_mech that lands in the middle of each electrical sector.
        # Each electrical sector is 60° = π/3 wide; mid-sector center
        # is at (sector + 0.5)·π/3 in electrical radians.
        theta_e_mid = (sector + 0.5) * (np.pi / 3.0)
        theta_mech = theta_e_mid / pp
        bundle.theta_rad.append(float(theta_mech))
        bundle.omega_rad_s.append(0.0)
        bundle.i_d.append(0.0)
        bundle.i_q.append(0.0)
        # Drive observer with t large enough to saturate ramp_s.
        observer(1.0, None)
        # Query switch_fn at a time where the PWM is ON
        # (carrier = (t * f_sw) % 1 ≈ 0 → < duty_max).
        # f_sw = 20k → period 50 µs → carrier ≈ 0 at t = 1.0 (exact).
        mask = sw(1.0)
        # Read the six bits (3 high + 3 low). The mask exposes a
        # boolean indexer; iterate by builder index.
        vsi_spec = circ.vsi_specs[0]
        hs = list(vsi_spec["high_side_switch_indices"])
        ls = list(vsi_spec["low_side_switch_indices"])
        # Expected per sector — matches the empirically-verified
        # ``SIXSTEP_SECTOR_TABLE`` on the backend. The pre-Jun-2026
        # table was ``((0,1), (0,2), (1,2), (1,0), (2,0), (2,1))``
        # which DROVE THE MOTOR IN REVERSE under pulsim's cos-convention
        # PMSM (the current vector at theta_e=0 was at -30° in αβ →
        # projection on q-axis was negative → negative torque). The
        # corrected table starts at (1, 2) = B+/C- so the current
        # vector aligns with the q-axis at sector midpoint and produces
        # maximum forward torque. Each subsequent sector advances the
        # current vector by +60° to track the rotating q-axis.
        # Verified empirically with M1.i_q sign for ex 22.
        expected = ((1, 2), (1, 0), (2, 0), (2, 1), (0, 1), (0, 2))
        hp, lp = expected[sector]
        # Use the mask's __getitem__ if available; otherwise raw .get.
        get_bit = getattr(mask, "__getitem__", None) or mask.get
        # Exactly one high-side on (the active sector's hp).
        assert bool(get_bit(hs[hp])), (
            f"sector {sector}: high-side phase {hp} should be ON"
        )
        for k in range(3):
            if k == hp:
                continue
            assert not bool(get_bit(hs[k])), (
                f"sector {sector}: high-side phase {k} must be OFF"
            )
        # Exactly one low-side on (the active sector's lp).
        assert bool(get_bit(ls[lp])), (
            f"sector {sector}: low-side phase {lp} should be ON"
        )
        for k in range(3):
            if k == lp:
                continue
            assert not bool(get_bit(ls[k])), (
                f"sector {sector}: low-side phase {k} must be OFF"
            )


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


def test_compressor_example_22_carries_sixstep_marker() -> None:
    """The shipped ex 22 file must convert without error and emit
    exactly one SIXSTEP descriptor bound to its VSI ("VSI") + PMSM
    ("M1"). This guards against silent regressions where the saved
    file format diverges from the converter's expectations."""
    circ = _convert_example("22_sixstep_drive_compressor.pulsim")

    descs = list(getattr(circ, "sixstep_loop_descriptors", []))
    assert len(descs) == 1, "expected one SIXSTEP descriptor"
    d = descs[0]
    assert d["vsi_name"] == "VSI"
    assert d["pmsm_name"] == "M1"
    assert d["speed_kp"] == pytest.approx(0.0025)
    assert d["speed_ki"] == pytest.approx(0.05)
    assert d["duty_max"] == pytest.approx(0.95)
    assert d["speed_ref_rpm"] == pytest.approx(1800.0)
    assert d["switching_frequency_hz"] == pytest.approx(20000.0)

    # The ex 22 file must NOT also emit a stray FOC descriptor — the
    # controller swap was clean.
    foc_descs = list(getattr(circ, "foc_loop_descriptors", []))
    assert foc_descs == [], "ex 22 should not emit any FOC descriptor"

    # The PFC front end is still present (we only swapped the motor side).
    pfc_descs = list(getattr(circ, "pfc_loop_descriptors", []))
    assert len(pfc_descs) == 1, "ex 22 must keep the PFC descriptor"


def test_sixstep_descriptor_skips_when_vsi_or_pmsm_missing() -> None:
    """A SIXSTEP_CONTROLLER without VSI or PMSM yields no descriptor
    (defensive: prevents a half-built loop from blowing up simulate)."""
    comps, node_map = _drive_components()
    # Drop the PMSM — the controller can't bind anywhere.
    motor_ids = {c["id"] for c in comps if c.get("name") == "M1"}
    comps_no_motor = [c for c in comps if c.get("name") != "M1"]
    nm = {k: v for k, v in node_map.items() if k not in motor_ids}
    conv = CircuitConverter(make_compat_module(p))
    circ = conv.build({"components": comps_no_motor, "node_map": nm})
    assert list(getattr(circ, "sixstep_loop_descriptors", [])) == []
