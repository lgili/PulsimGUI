#!/usr/bin/env python3
"""Builder for example 21 — FOC Compressor Drive (DC bus → VSI → PMSM).

Run from the repo root::

    PYTHONPATH=src .venv/bin/python scripts/build_foc_drive_example.py

Regenerates ``examples/21_foc_drive_compressor.pulsim`` deterministically
(component IDs are stable across runs so diffs stay clean).

A faithful Field-Oriented-Control (FOC) drive for an Embraco VLT403U
PMSM. Open-loop V/f pole-slips a PMSM (the rotor angle and the imposed
stator-field angle drift apart, the motor stalls, and the phase current
runs to 17-29 A of useless garbage). Closing the d-q current loops +
an outer speed loop is what lets the motor actually track a speed
reference with rated current (~1-3 A phase, matching the datasheet FLA):

    DC bus: two ±180 V sources referenced to ground "0" (360 V bus)
        → 3φ 2-level VSI (six ideal switches)
        → PMSM (dynamic, VLT403U), neutral tied to ground
        + FOC controller (a C_BLOCK marker, control_kind="foc")

The FOC controller is represented (lowest-friction option) as a C_BLOCK
carrying ``control_kind="foc"`` plus the loop gains / speed-reference
ramp / limits in its ``parameters``. It is a pure *marker* — NOT wired
into the power stage — that the converter detects (``_infer_foc_loops``)
and the backend executes (``_build_foc_loops``):

  * an outer speed PI produces ``iq_ref`` (clamped),
  * inner i_d (=0) / i_q PIs with back-EMF + cross-coupling decoupling
    produce ``v_d`` / ``v_q`` (clamped to a fraction of the half-bus),
  * inverse Park (using the ELECTRICAL angle pp·θ_mech) → inverse
    Clarke → a per-phase carrier comparison at f_sw drives the VSI's
    six switches, REPLACING its open-loop SPWM.

The PMSM observer (``make_pmsm_observer``) integrates the d-q current +
mechanical ODE each step and exposes the live i_d / i_q / ω / θ the FOC
loop reads back. The speed reference ramps 0 → 1800 rpm over 0.10 s then
holds; the rotor follows (with mild speed-loop overshoot) and settles on
~1800 rpm.

This is intentionally focused on the drive — no rectifier front-end —
so the example converts + simulates correctly through the GUI's real
``CircuitDataBuilder`` → ``BackendLoader().backend.run_transient`` stack.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401  — defuse circular import
from pulsimgui.utils.wire_router import WireRouter

REPO = Path("/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGUI")
OUT_PATH = REPO / "examples" / "21_foc_drive_compressor.pulsim"

# Deterministic IDs: a fixed namespace + per-component name keeps the
# generated JSON byte-stable across runs.
_NS = uuid.UUID("21000000-0f0c-1e72-d21e-000000000000")

VBUS = 360.0      # total DC-bus voltage (two ±180 V sources)
FSW = 20000.0     # inverter switching frequency [Hz]


def uid(tag: str) -> str:
    return str(uuid.uuid5(_NS, tag))


def comp(*, type: str, name: str, x: float, y: float, parameters: dict,
         pins: list[dict], rotation: int = 0) -> dict:
    return {
        "id": uid(name),
        "type": type,
        "name": name,
        "x": float(x),
        "y": float(y),
        "rotation": rotation,
        "mirrored_h": False,
        "mirrored_v": False,
        "parameters": parameters,
        "pins": pins,
    }


def pin(index: int, name: str, x: float, y: float) -> dict:
    return {"index": index, "name": name, "x": float(x), "y": float(y)}


def wire(a_id: str, a_pin: int, b_id: str, b_pin: int,
         components_by_id: dict, router: WireRouter, *,
         node_name: str = "", alias: str = "") -> dict:
    ca = components_by_id[a_id]
    cb = components_by_id[b_id]
    ax = ca["x"] + next(p["x"] for p in ca["pins"] if p["index"] == a_pin)
    ay = ca["y"] + next(p["y"] for p in ca["pins"] if p["index"] == a_pin)
    bx = cb["x"] + next(p["x"] for p in cb["pins"] if p["index"] == b_pin)
    by = cb["y"] + next(p["y"] for p in cb["pins"] if p["index"] == b_pin)
    raw = router.route(ax, ay, bx, by)
    segments = [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                for (x1, y1, x2, y2) in raw]
    return {
        "id": uid(f"wire:{a_id}:{a_pin}:{b_id}:{b_pin}"),
        "segments": segments,
        "start_connection": {"component_id": a_id, "pin_index": a_pin},
        "end_connection": {"component_id": b_id, "pin_index": b_pin},
        "junctions": [],
        "node_name": node_name,
        "alias": alias,
    }


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
components: list[dict] = []

# ------------------ DC bus: two ±180 V sources to ground ------------------
# busp ──(+180)── 0 ──(+180)── busn  →  busp - busn = 360 V, midpoint = 0.
v_pos = comp(
    type="VOLTAGE_SOURCE", name="V_pos", x=-360, y=-80,
    parameters={"waveform": {"type": "dc", "value": VBUS / 2.0}},
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
    rotation=90,
)
components.append(v_pos)

v_neg = comp(
    type="VOLTAGE_SOURCE", name="V_neg", x=-360, y=120,
    parameters={"waveform": {"type": "dc", "value": VBUS / 2.0}},
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
    rotation=90,
)
components.append(v_neg)

gnd_mid = comp(
    type="GROUND", name="GND_mid", x=-280, y=40,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_mid)

# ------------------ Bus voltage probe ------------------
vp_bus = comp(
    type="VOLTAGE_PROBE", name="V_bus", x=-160, y=0,
    parameters={"display_name": "V_bus", "scale": 1.0},
    pins=[pin(0, "+", 0, -20), pin(1, "-", 0, 20), pin(2, "OUT", 25, 0)],
)
components.append(vp_bus)

# ------------------ 3φ VSI ------------------
# The SPWM drive params below are inert for this example — the FOC
# controller commands the six switches via inverse Park/Clarke and the
# converter excludes a FOC-controlled VSI from the open-loop SPWM path.
vsi = comp(
    type="THREE_PHASE_VSI", name="VSI", x=40, y=0,
    parameters={
        "switching_frequency_hz": FSW,
        "modulation_index": 0.8,
        "modulation_frequency_hz": 90.0,
        "phase_a_deg": 0.0,
        "positive_sequence": True,
        "v_gate_on": 12.0,
        "v_gate_off": 0.0,
        "mosfet_r_on_ohm": 5.0e-3,
        "mosfet_r_off_ohm": 1.0e9,
        "mosfet_vth": 1.0,
        "dead_time_s": 0.0,
    },
    pins=[
        pin(0, "VDC+", -35, -25),
        pin(1, "VDC-", -35, 25),
        pin(2, "A",     35, -25),
        pin(3, "B",     35, 0),
        pin(4, "C",     35, 25),
    ],
)
components.append(vsi)

# ------------------ Motor phase-A voltage probe ------------------
vp_motor_a = comp(
    type="VOLTAGE_PROBE_GND", name="V_motor_A", x=220, y=-140,
    parameters={"display_name": "V(A)", "scale": 1.0},
    pins=[pin(0, "IN", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_motor_a)

# ------------------ PMSM (Embraco VLT403U) ------------------
pmsm = comp(
    type="PMSM", name="M1", x=300, y=0,
    parameters={
        "Rs": 6.6,
        "Ld": 12e-3,
        "Lq": 12e-3,
        "psi_pm": 0.05,
        "pole_pairs": 3,
        "J": 2e-4,
        "b_friction": 5e-4,
        "tau_load": 0.30,
        "i_d_init": 0.0,
        "i_q_init": 0.0,
        "omega_init": 0.0,
        "theta_init": 0.0,
    },
    pins=[
        pin(0, "A", -30, -25),
        pin(1, "B", -30, 0),
        pin(2, "C", -30, 25),
        pin(3, "N",  30, 0),
    ],
)
components.append(pmsm)

gnd_motor = comp(
    type="GROUND", name="GND_motor", x=300, y=140,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_motor)

# ------------------ FOC controller (C_BLOCK marker) ------------------
# control_kind="foc" → the converter emits a foc_loop_descriptor binding
# this marker to the VSI (commanded) + the PMSM (observed). It carries no
# pins and is NOT wired into the power stage; the backend reads the loop
# gains / speed-reference ramp / limits below and closes the loops at
# simulate time. Gains match the validated VLT403U FOC recipe.
foc = comp(
    type="C_BLOCK", name="FOC", x=300, y=-200,
    parameters={
        "control_kind": "foc",
        "vsi_name": "VSI",
        "pmsm_name": "M1",
        "v_bus": VBUS,
        # Speed (outer) PI -> iq_ref.
        "speed_kp": 0.17,
        "speed_ki": 6.0,
        # Current (inner) PIs (shared id/iq gains).
        "current_kp": 45.0,
        "current_ki": 24000.0,
        # References / limits.
        "id_ref": 0.0,
        "iq_limit": 3.0,
        "v_limit_frac": 0.92,
        # Speed reference: 0 -> 1800 rpm over 0.10 s, then hold.
        "speed_ref_rpm": 1800.0,
        "speed_ramp_s": 0.10,
        "switching_frequency_hz": FSW,
        # No fast_block law / IO — pure descriptor marker.
        "n_inputs": 0,
        "n_outputs": 0,
        "implementation": "source",
    },
    pins=[],
)
components.append(foc)

# ------------------ Scope ------------------
scope = comp(
    type="ELECTRICAL_SCOPE", name="Scope", x=560, y=-100,
    parameters={
        "channel_count": 2,
        "channels": [
            {"label": "V_bus", "overlay": False},
            {"label": "V(A)",  "overlay": False},
        ],
    },
    pins=[
        pin(0, "CH1", -40, -25),
        pin(1, "CH2", -40, 25),
    ],
)
components.append(scope)

# ---------------------------------------------------------------------------
# Wires
# ---------------------------------------------------------------------------
comp_by_id = {c["id"]: c for c in components}
wires: list[dict] = []

router = WireRouter(grid=20.0)
router.add_obstacles_from_components(
    components,
    body_half_w=30.0,
    body_half_h=25.0,
    padding=6.0,
)


def w(a, ap, b, bp, *, node_name="", alias=""):
    wires.append(wire(a["id"], ap, b["id"], bp, comp_by_id, router,
                      node_name=node_name, alias=alias))


# ===== DC bus: busp ──(V_pos +)..(- )── 0 ──(V_neg +)..(-)── busn =====
# V_pos: + → busp, - → ground "0"
w(v_pos, 0, vp_bus, 0, node_name="BUSP")
w(v_pos, 1, gnd_mid, 0, node_name="0")
# V_neg: + → ground "0", - → busn
w(v_neg, 0, gnd_mid, 0, node_name="0")
w(v_neg, 1, vp_bus, 1, node_name="BUSN")

# ===== V_bus probe → VSI DC rails =====
w(vp_bus, 0, vsi, 0, node_name="BUSP")
w(vp_bus, 1, vsi, 1, node_name="BUSN")

# ===== VSI → PMSM (3 phases) =====
# Phase A taps a ground-referenced voltage probe on the way to the motor.
w(vsi, 2, vp_motor_a, 0, node_name="MOT_A")
w(vp_motor_a, 0, pmsm, 0, node_name="MOT_A")
w(vsi, 3, pmsm, 1, node_name="MOT_B")
w(vsi, 4, pmsm, 2, node_name="MOT_C")
# PMSM neutral → ground "0"
w(pmsm, 3, gnd_motor, 0, node_name="0")

# ===== Scope wires =====
w(vp_bus, 2, scope, 0)
w(vp_motor_a, 1, scope, 1)

# ---------------------------------------------------------------------------
# Simulation settings (pulsim 1.6 compatible)
# ---------------------------------------------------------------------------
# t_stop = 0.24 s lets the speed loop ramp (0.10 s) + overshoot + settle to
# ~1800 rpm. dt = 2 µs resolves the 20 kHz carrier (25 samples/period). The
# FOC switch_fn is plain Python so the run is ~3 s of wall time.
sim_settings = {
    "tstop": 0.24,
    "dt": 2.0e-6,
    "tstart": 0.0,
    "output_points": 20000,
    "control_sample_time": 2.0e-6,
    "control_mode": "auto",
    "formulation_mode": "projected_wrapper",
    "direct_formulation_fallback": True,
    "enable_events": True,
    "enable_losses": True,
    "tol_newton_dx": 1.0e-6,
    "tol_newton_res": 1.0e-6,
    "enable_newton_line_search": True,
    "enable_newton_lm": False,
    "enable_substep_state_correction": True,
    "enable_nonlinear_refresh": True,
    "start_from_dc_op": False,
    "max_event_iterations": 50,
    "thermal_ambient": 25.0,
    "thermal_policy": "loss_with_temperature_scaling",
    "thermal_default_rth": 1.0,
    "thermal_default_cth": 0.1,
}

# ---------------------------------------------------------------------------
# Project shell
# ---------------------------------------------------------------------------
now = datetime.now().isoformat(timespec="seconds")
project = {
    "version": "1.0",
    "name": "21 FOC Drive — 360 V DC Bus + VSI + Field-Oriented Control "
            "(Embraco VLT403U PMSM)",
    "created": now,
    "modified": now,
    "active_circuit": "main",
    "simulation_settings": sim_settings,
    "circuits": {
        "main": {
            "name": "main",
            "components": components,
            "wires": wires,
        }
    },
    "subcircuits": {},
    "scope_windows": {},
    "scope_workspace_state": {},
}

OUT_PATH.write_text(json.dumps(project, indent=2))
print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")
print(f"  {len(components)} components, {len(wires)} wires")
