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

# ---- Voltage probes ----
# V_BUS: measure the DC bus rail (VDC+) wrt ground
vp_bus = comp(
    type="VOLTAGE_PROBE_GND", name="V_BUS",
    x=-820, y=-460,
    parameters={"display_name": "V_BUS", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_bus)

# Per-phase voltage probes — each phase tap to ground
vp_phaseA = comp(
    type="VOLTAGE_PROBE_GND", name="V_phaseA",
    x=PHASE_X[0] + 100, y=Y_PHASE_TAP - 60,
    parameters={"display_name": "V_phA", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_phaseA)

vp_phaseB = comp(
    type="VOLTAGE_PROBE_GND", name="V_phaseB",
    x=PHASE_X[1] + 100, y=Y_PHASE_TAP - 60,
    parameters={"display_name": "V_phB", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_phaseB)

vp_phaseC = comp(
    type="VOLTAGE_PROBE_GND", name="V_phaseC",
    x=PHASE_X[2] + 100, y=Y_PHASE_TAP - 60,
    parameters={"display_name": "V_phC", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_phaseC)

# ---- Current probes ----
# I_arm_uA: upper arm A inductor current (in series with L_uA)
ip_arm_uA = comp(
    type="CURRENT_PROBE", name="I_arm_uA",
    x=PHASE_X[0], y=Y_L_UPPER + 80,
    parameters={"display_name": "I_arm_uA", "scale": 1.0},
    pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25),
          pin(2, "OUT", 30, 0)],
)
components.append(ip_arm_uA)

# I_arm_lA: lower arm A inductor current (in series with L_lA)
ip_arm_lA = comp(
    type="CURRENT_PROBE", name="I_arm_lA",
    x=PHASE_X[0], y=Y_L_LOWER - 80,
    parameters={"display_name": "I_arm_lA", "scale": 1.0},
    pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25),
          pin(2, "OUT", 30, 0)],
)
components.append(ip_arm_lA)

# I_phaseA/B/C: phase-line current (in series with each load R)
ip_phaseA = comp(
    type="CURRENT_PROBE", name="I_phA",
    x=LOAD_X_R - 100, y=Y_PHASE_TAP - 80,
    parameters={"display_name": "I_phA", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0),
          pin(2, "OUT", 0, 25)],
)
components.append(ip_phaseA)

ip_phaseB = comp(
    type="CURRENT_PROBE", name="I_phB",
    x=LOAD_X_R - 100, y=Y_PHASE_TAP,
    parameters={"display_name": "I_phB", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0),
          pin(2, "OUT", 0, 25)],
)
components.append(ip_phaseB)

ip_phaseC = comp(
    type="CURRENT_PROBE", name="I_phC",
    x=LOAD_X_R - 100, y=Y_PHASE_TAP + 80,
    parameters={"display_name": "I_phC", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0),
          pin(2, "OUT", 0, 25)],
)
components.append(ip_phaseC)

# ---- Scopes ----
# Scope #1: DC bus + 3-phase voltages (4 channels)
scope_voltages = comp(
    type="ELECTRICAL_SCOPE", name="Scope_Voltages",
    x=900, y=-380,
    parameters={
        "channel_count": 4,
        "channels": [
            {"label": "V_BUS", "overlay": False},
            {"label": "V_phA", "overlay": False},
            {"label": "V_phB", "overlay": False},
            {"label": "V_phC", "overlay": False},
        ],
    },
    pins=[pin(0, "CH1", -40, -30),
          pin(1, "CH2", -40, -10),
          pin(2, "CH3", -40, 10),
          pin(3, "CH4", -40, 30)],
)
components.append(scope_voltages)

# Scope #2: 3-phase load currents (3 channels)
scope_load_currents = comp(
    type="ELECTRICAL_SCOPE", name="Scope_LoadCurrents",
    x=900, y=-120,
    parameters={
        "channel_count": 3,
        "channels": [
            {"label": "I_phA", "overlay": False},
            {"label": "I_phB", "overlay": False},
            {"label": "I_phC", "overlay": False},
        ],
    },
    pins=[pin(0, "CH1", -40, -25),
          pin(1, "CH2", -40, 0),
          pin(2, "CH3", -40, 25)],
)
components.append(scope_load_currents)

# Scope #3: Phase-A arm currents (upper vs lower) — circulating-
# current insight: I_arm_uA + I_arm_lA = I_dc/3 + I_circ, while
# I_arm_uA - I_arm_lA = I_phA (the AC line current). A user can
# eyeball these to verify the arm-balance behavior of each
# fidelity model.
scope_arm_currents = comp(
    type="ELECTRICAL_SCOPE", name="Scope_ArmCurrents",
    x=900, y=140,
    parameters={
        "channel_count": 2,
        "channels": [
            {"label": "I_arm_uA", "overlay": False},
            {"label": "I_arm_lA", "overlay": False},
        ],
    },
    pins=[pin(0, "CH1", -40, -15),
          pin(1, "CH2", -40, 15)],
)
components.append(scope_arm_currents)


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

# Phase A column: L_upper → I_arm_uA → ARM_upper → phase tap →
# ARM_lower → I_arm_lA → L_lower (probes break the chain on phase A)
w(L_upper[0], 1, ip_arm_uA, 0, node_name="ARM_uA_TOP_PRE")
w(ip_arm_uA, 1, arm_upper[0], 0, node_name="ARM_uA_TOP")
w(arm_upper[0], 1, arm_lower[0], 0, node_name="PHASE_A")
w(arm_lower[0], 1, ip_arm_lA, 0, node_name="ARM_lA_BOT_PRE")
w(ip_arm_lA, 1, L_lower[0], 0, node_name="ARM_lA_BOT")

# Phases B and C — same chain, no arm probes (cheaper sim)
for lu, au, al, ll, phase_label in zip(
    L_upper[1:], arm_upper[1:], arm_lower[1:],
    L_lower[1:], ("B", "C"),
):
    w(lu, 1, au, 0, node_name=f"ARM_u{phase_label}_TOP")
    w(au, 1, al, 0, node_name=f"PHASE_{phase_label}")
    w(al, 1, ll, 0, node_name=f"ARM_l{phase_label}_BOT")

# Phase voltage probes tap off each phase node
w(arm_upper[0], 1, vp_phaseA, 0, node_name="PHASE_A")
w(arm_upper[1], 1, vp_phaseB, 0, node_name="PHASE_B")
w(arm_upper[2], 1, vp_phaseC, 0, node_name="PHASE_C")

# ========================
# AC load wires — each phase tap → I_phX → R_X → L_X → neutral
# ========================
phase_taps = arm_upper  # phase tap is the BOT pin of the upper arm
ip_phases = (ip_phaseA, ip_phaseB, ip_phaseC)
for au, ip_ph, r_load, l_load, phase_label in zip(
    phase_taps, ip_phases, load_r, load_l, ("A", "B", "C"),
):
    w(au, 1, ip_ph, 0, node_name=f"PHASE_{phase_label}")
    w(ip_ph, 1, r_load, 0, node_name=f"LOAD_{phase_label}_PRE")
    w(r_load, 1, l_load, 0, node_name=f"LOAD_{phase_label}_MID")
    w(l_load, 1, gnd_neutral, 0, node_name="NEUTRAL")

# ========================
# Scope wires
# ========================
# Scope_Voltages: V_BUS, V_phA, V_phB, V_phC
w(vp_bus, 1, scope_voltages, 0, node_name="SIG_VBUS")
w(vp_phaseA, 1, scope_voltages, 1, node_name="SIG_VPHA")
w(vp_phaseB, 1, scope_voltages, 2, node_name="SIG_VPHB")
w(vp_phaseC, 1, scope_voltages, 3, node_name="SIG_VPHC")

# Scope_LoadCurrents: I_phA, I_phB, I_phC
w(ip_phaseA, 2, scope_load_currents, 0, node_name="SIG_IPHA")
w(ip_phaseB, 2, scope_load_currents, 1, node_name="SIG_IPHB")
w(ip_phaseC, 2, scope_load_currents, 2, node_name="SIG_IPHC")

# Scope_ArmCurrents: I_arm_uA, I_arm_lA
w(ip_arm_uA, 2, scope_arm_currents, 0, node_name="SIG_IARMUA")
w(ip_arm_lA, 2, scope_arm_currents, 1, node_name="SIG_IARMLA")


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
