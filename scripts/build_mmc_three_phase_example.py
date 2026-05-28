#!/usr/bin/env python3
"""Builder for example 17 — 3-phase MMC DC-AC converter (6 arms).

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_mmc_three_phase_example.py

Regenerates ``examples/17_mmc_three_phase.pulsim``. Demonstrates the
new ``MMC_ARM`` component at the default L3 Detailed fidelity (full
switching + cap-voltage balancing). Edit ``model_fidelity`` on each
arm in the GUI to swap to L0 / L1 / L2 and compare results.

Topology (single-line):

       VDC+ ──┬──────────┬──────────┬──
              │          │          │
           [L_uA]      [L_uB]     [L_uC]      upper-arm inductors
              │          │          │
          [ARM_uA]   [ARM_uB]   [ARM_uC]      upper MMC arms (TOP at VDC+)
              │          │          │
              ●─Phase A  ●─Phase B  ●─Phase C ── 3φ R+L load
              │          │          │
          [ARM_lA]   [ARM_lB]   [ARM_lC]      lower MMC arms (BOT at VDC-)
              │          │          │
           [L_lA]      [L_lB]     [L_lC]      lower-arm inductors
              │          │          │
       VDC- ──┴──────────┴──────────┴──

Each arm gets a constant modulation reference (m_ref_constant=0.5
default — no AC output, just validates topology+convergence at DC).
For a real DC→AC inverter, modulation refs need to be time-varying
(sinusoidal, phase-shifted 120°/240°) — that requires backend
observer wiring on the M_REF pin (separate task).
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401 — defuse circular import
from pulsimgui.utils.wire_router import WireRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def uid() -> str:
    return str(uuid.uuid4())


def comp(*, type, name, x, y, parameters, pins, rotation=0):
    return {
        "id": uid(), "type": type, "name": name,
        "x": float(x), "y": float(y),
        "rotation": rotation, "mirrored_h": False, "mirrored_v": False,
        "parameters": parameters, "pins": pins,
    }


def pin(index, name, x, y):
    return {"index": index, "name": name, "x": float(x), "y": float(y)}


def wire(a_id, a_pin, b_id, b_pin, components_by_id, router, *,
         node_name="", alias=""):
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
        "id": uid(), "segments": segments,
        "start_connection": {"component_id": a_id, "pin_index": a_pin},
        "end_connection": {"component_id": b_id, "pin_index": b_pin},
        "junctions": [], "node_name": node_name, "alias": alias,
    }


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
# Each phase column carries: VDC+ → L_upper → ARM_upper → phase tap →
# ARM_lower → L_lower → VDC-. Spacing chosen so the new MMC_ARM
# bounding box (96 px tall, ±48 from centre) doesn't collide with
# the inductors above/below.
X_PHASE_A = -600
X_PHASE_B = -300
X_PHASE_C = 0
PHASE_X = (X_PHASE_A, X_PHASE_B, X_PHASE_C)

Y_VDC_POS = -460          # VDC+ rail Y
Y_L_UPPER = -360
Y_ARM_UPPER = -220        # ARM body centre — extends from -268 to -172
Y_PHASE_TAP = -60         # AC midpoint between upper/lower arms
Y_ARM_LOWER = 100         # ARM body centre — extends from 52 to 148
Y_L_LOWER = 240
Y_VDC_NEG = 340           # VDC- rail Y


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
components: list[dict] = []

# ---- DC source ----
v_dc = comp(
    type="VOLTAGE_SOURCE", name="V_DC", x=-960, y=-60,
    parameters={
        "waveform": {"type": "dc", "value": 800.0,
                       "amplitude": 0.0, "frequency": 0.0,
                       "offset": 800.0, "phase": 0.0},
    },
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
)
components.append(v_dc)

gnd_dc = comp(
    type="GROUND", name="GND_dc", x=-900, y=80,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_dc)

# ---- MMC arms — 6 of them, one upper + one lower per phase ----
arm_upper: list[dict] = []
arm_lower: list[dict] = []
L_upper: list[dict] = []
L_lower: list[dict] = []

ARM_DEFAULTS = {
    "model_fidelity": "L3 Detailed",
    "submodule_type": "Half-Bridge",
    "n_submodules": 4,
    "c_sm": 4.7e-3,
    "v_c0": 200.0,             # pre-charge cap to mid-bus level
    "r_arm": 0.01,
    "m_ref_constant": 0.5,     # 50 % duty → phase node sits at VDC/2
    "f_carrier": 1000.0,
    "modulation_scheme": "PSC",
    "t_dead": 1.0e-6,
    "t_min": 1.0e-7,
    "balancing": "sort_and_select",
}

L_ARM_INDUCTANCE = 5.0e-3        # 5 mH arm inductor

for phase_label, col_x in zip(("A", "B", "C"), PHASE_X):
    # Upper inductor (between VDC+ and the upper arm's TOP)
    lu = comp(
        type="INDUCTOR", name=f"L_u{phase_label}", x=col_x, y=Y_L_UPPER,
        parameters={"inductance": L_ARM_INDUCTANCE, "initial_current": 0.0},
        pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)],
    )
    components.append(lu)
    L_upper.append(lu)

    # Upper MMC arm — TOP towards VDC+ (via L_uX), BOT towards phase tap
    au = comp(
        type="MMC_ARM", name=f"ARM_u{phase_label}", x=col_x, y=Y_ARM_UPPER,
        parameters={**ARM_DEFAULTS},
        pins=[pin(0, "TOP", -35, -40),
              pin(1, "BOT", -35, 40),
              pin(2, "M_REF", 35, 0)],
    )
    components.append(au)
    arm_upper.append(au)

    # Lower MMC arm — TOP towards phase tap, BOT towards VDC- (via L_lX)
    al = comp(
        type="MMC_ARM", name=f"ARM_l{phase_label}", x=col_x, y=Y_ARM_LOWER,
        parameters={**ARM_DEFAULTS},
        pins=[pin(0, "TOP", -35, -40),
              pin(1, "BOT", -35, 40),
              pin(2, "M_REF", 35, 0)],
    )
    components.append(al)
    arm_lower.append(al)

    # Lower inductor (between lower arm BOT and VDC-)
    ll = comp(
        type="INDUCTOR", name=f"L_l{phase_label}", x=col_x, y=Y_L_LOWER,
        parameters={"inductance": L_ARM_INDUCTANCE, "initial_current": 0.0},
        pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)],
    )
    components.append(ll)
    L_lower.append(ll)

# ---- 3-phase R+L star load on the AC outputs ----
# Phase tap → R_X → L_X → neutral → ground
LOAD_X_R = 240
LOAD_X_L = 380
NEUTRAL_X = 520
R_LOAD = 10.0
L_LOAD = 10.0e-3

load_r: list[dict] = []
load_l: list[dict] = []
for i, (phase_label, col_x) in enumerate(zip(("A", "B", "C"), PHASE_X)):
    py = Y_PHASE_TAP + (i - 1) * 80  # spread phases vertically at the load
    r_load = comp(
        type="RESISTOR", name=f"R_{phase_label}", x=LOAD_X_R, y=py,
        parameters={"resistance": R_LOAD},
        pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    )
    components.append(r_load)
    load_r.append(r_load)

    l_load = comp(
        type="INDUCTOR", name=f"L_{phase_label}", x=LOAD_X_L, y=py,
        parameters={"inductance": L_LOAD, "initial_current": 0.0},
        pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    )
    components.append(l_load)
    load_l.append(l_load)

gnd_neutral = comp(
    type="GROUND", name="GND_neutral", x=NEUTRAL_X, y=80,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_neutral)

# ---- Probes ----
vp_phaseA = comp(
    type="VOLTAGE_PROBE_GND", name="V_phaseA",
    x=PHASE_X[0] + 80, y=Y_PHASE_TAP - 80,
    parameters={"display_name": "V_phA", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_phaseA)

vp_bus = comp(
    type="VOLTAGE_PROBE_GND", name="V_BUS",
    x=-800, y=-200,
    parameters={"display_name": "V_BUS", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_bus)

# ---- Scope ----
scope = comp(
    type="ELECTRICAL_SCOPE", name="Scope_MMC", x=800, y=-200,
    parameters={
        "channel_count": 3,
        "channels": [
            {"label": "V_phA", "overlay": False},
            {"label": "V_BUS", "overlay": False},
            {"label": "I_LA",  "overlay": False},
        ],
    },
    pins=[pin(0, "CH1", -40, -25),
          pin(1, "CH2", -40, 0),
          pin(2, "CH3", -40, 25)],
)
components.append(scope)


# ---------------------------------------------------------------------------
# Wires
# ---------------------------------------------------------------------------
comp_by_id = {c["id"]: c for c in components}
wires: list[dict] = []
router = WireRouter(grid=20.0)
router.add_obstacles_from_components(
    components, body_half_w=30.0, body_half_h=25.0, padding=6.0,
)


def w(a, ap, b, bp, *, node_name="", alias=""):
    wires.append(wire(a["id"], ap, b["id"], bp, comp_by_id, router,
                      node_name=node_name, alias=alias))


# ========================
# Power-stage wires
# ========================
# DC source → V_BUS probe → upper-inductor inputs (top rail)
#   V_DC.+ → vp_bus.in → L_uA/B/C top pin
w(v_dc, 0, vp_bus, 0, node_name="VDC_POS")
for lu in L_upper:
    w(vp_bus, 0, lu, 0, node_name="VDC_POS")

# V_DC.- → ground → lower-inductor outputs (bottom rail)
w(v_dc, 1, gnd_dc, 0, node_name="VDC_NEG")
for ll in L_lower:
    w(gnd_dc, 0, ll, 1, node_name="VDC_NEG")

# Per-phase column: L_upper.2 → ARM_upper.TOP, ARM_upper.BOT → phase tap,
# phase tap → ARM_lower.TOP, ARM_lower.BOT → L_lower.1
for lu, au, al, ll, phase_label in zip(
    L_upper, arm_upper, arm_lower, L_lower, ("A", "B", "C"),
):
    w(lu, 1, au, 0, node_name=f"ARM_u{phase_label}_TOP")
    # Upper-arm BOT → lower-arm TOP forms the phase tap
    w(au, 1, al, 0, node_name=f"PHASE_{phase_label}")
    w(al, 1, ll, 0, node_name=f"ARM_l{phase_label}_BOT")

# Phase A voltage probe taps off ARM_uA.BOT (phase A tap)
w(arm_upper[0], 1, vp_phaseA, 0, node_name="PHASE_A")

# ========================
# AC load wires
# ========================
# Phase X tap → R_X.1 → L_X.1, L_X.2 → ground (star neutral)
for au, r_load, l_load, phase_label in zip(
    arm_upper, load_r, load_l, ("A", "B", "C"),
):
    w(au, 1, r_load, 0, node_name=f"PHASE_{phase_label}")
    w(r_load, 1, l_load, 0, node_name=f"LOAD_{phase_label}_MID")
    w(l_load, 1, gnd_neutral, 0, node_name="NEUTRAL")

# ========================
# Scope wires
# ========================
w(vp_phaseA, 1, scope, 0)        # CH1: V_phA
w(vp_bus, 1, scope, 1)           # CH2: V_BUS


# ---------------------------------------------------------------------------
# Simulation settings (pulsim 1.5)
# ---------------------------------------------------------------------------
sim_settings = {
    "tstop": 0.020,                      # 20 ms — long enough to see DC settling
    "dt": 1.0e-6,
    "tstart": 0.0,
    "output_points": 20000,
    "control_sample_time": 1.0e-5,
    "control_mode": "discrete",
    "tol_newton_dx": 1.0e-6,
    "tol_newton_res": 1.0e-6,
    "enable_newton_line_search": True,
    "enable_newton_lm": False,
    "enable_substep_state_correction": True,
    "enable_nonlinear_refresh": False,
    "start_from_dc_op": False,
    "max_event_iterations": 50,
}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
now = datetime.now().isoformat(timespec="seconds")
project = {
    "version": "1.0",
    "name": "17 MMC 3-Phase DC-AC — 6 arms, L3 Detailed (edit fidelity per arm)",
    "created": now,
    "modified": now,
    "active_circuit": "main",
    "simulation_settings": sim_settings,
    "circuits": {
        "main": {
            "name": "main",
            "components": components,
            "wires": wires,
        },
    },
    "subcircuits": {},
    "scope_windows": {},
    "scope_workspace_state": {},
}

out_path = Path(
    "/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGUI/"
    "examples/17_mmc_three_phase.pulsim"
)
out_path.write_text(json.dumps(project, indent=2))
print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  {len(components)} components, {len(wires)} wires")
