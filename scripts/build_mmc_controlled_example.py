#!/usr/bin/env python3
"""Builder for example 24 — controlled 3-phase MMC DC→AC inverter.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_mmc_controlled_example.py

Regenerates ``examples/24_mmc_three_phase_controlled.pulsim``.

Unlike example 17 (constant m_ref = 0.5, DC-equilibrium only), this one
adds a dedicated ``MMC_CONTROLLER`` whose six outputs drive the six arm
``M_REF`` pins with open-loop sinusoidal modulation (phase A/B/C, 120°
apart, upper/lower complementary). The arms run at L0 (average) fidelity
so the observer advances each arm's capacitor voltage and publishes it as
``<arm>.v_C`` telemetry.

Split DC bus (±Vdc/2, midpoint grounded = load neutral) so the AC phase
nodes swing about 0. Scopes expose the AC output voltages (V(PHASE_x) node
signals), the phase currents, the per-arm capacitor voltages, and the
phase-A arm currents.

NOTE — this is the OPEN-LOOP stepping stone. With fixed sinusoidal
modulation and no circulating-current / energy control, the arm capacitor
voltages are only *marginally* stable: they hold near 800 V but slowly
drift and the phases gradually imbalance (Scope_CapVoltages /
Scope_ACVoltages show one phase sag over a few cycles), because nothing
actively regulates the internal energy. The closed-loop version —
``examples/25_mmc_three_phase_closed_loop.pulsim`` (flip the
MMC_CONTROLLER to ``control_mode="closed_loop"``) — adds arm-energy
balancing + circulating-current suppression (and optional dq output-current
control) to hold v_C tight and keep the 3φ output balanced and sustained.
This example proves the end-to-end path (MMC_CONTROLLER → arm M_REF → L0
observer telemetry → scopes) that the controller then closes around.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401 — defuse circular import
from pulsimgui.utils.wire_router import WireRouter


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


def wire_direct(a_id, a_pin, b_id, b_pin, components_by_id, *, node_name=""):
    """A single-segment wire — no router. Connectivity is by endpoint
    (component_id, pin_index), so geometry never merges it with other nets."""
    ca = components_by_id[a_id]
    cb = components_by_id[b_id]
    ax = ca["x"] + next(p["x"] for p in ca["pins"] if p["index"] == a_pin)
    ay = ca["y"] + next(p["y"] for p in ca["pins"] if p["index"] == a_pin)
    bx = cb["x"] + next(p["x"] for p in cb["pins"] if p["index"] == b_pin)
    by = cb["y"] + next(p["y"] for p in cb["pins"] if p["index"] == b_pin)
    return {
        "id": uid(), "segments": [{"x1": ax, "y1": ay, "x2": bx, "y2": by}],
        "start_connection": {"component_id": a_id, "pin_index": a_pin},
        "end_connection": {"component_id": b_id, "pin_index": b_pin},
        "junctions": [], "node_name": node_name, "alias": "",
    }


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
# Ratings / layout
# ---------------------------------------------------------------------------
VDC_HALF = 400.0          # split DC bus: ±400 V (800 V total)
ARM_L = 5.0e-3
ARM_R = 0.1
C_SM = 4.7e-3
N_SM = 4
VC0 = 2.0 * VDC_HALF      # arm cap voltage equilibrium ≈ Vdc total
MOD_INDEX = 0.6
F_OUT = 60.0
R_LOAD = 15.0
L_LOAD = 10.0e-3

X_PHASE = (-600, -300, 0)
Y_VDC_POS = -460
Y_L_UPPER = -360
Y_ARM_UPPER = -220
Y_PHASE_TAP = -60
Y_ARM_LOWER = 100
Y_L_LOWER = 240
Y_VDC_NEG = 340

components: list[dict] = []

# ---- Split DC bus: VDC_POS ── V_DCp ── MID(gnd) ── V_DCn ── VDC_NEG ----
v_dcp = comp(
    type="VOLTAGE_SOURCE", name="V_DCp", x=-960, y=-200,
    parameters={"waveform": {"type": "dc", "value": VDC_HALF, "amplitude": 0.0,
                             "frequency": 0.0, "offset": VDC_HALF, "phase": 0.0}},
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
)
v_dcn = comp(
    type="VOLTAGE_SOURCE", name="V_DCn", x=-960, y=120,
    parameters={"waveform": {"type": "dc", "value": VDC_HALF, "amplitude": 0.0,
                             "frequency": 0.0, "offset": VDC_HALF, "phase": 0.0}},
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
)
gnd_mid = comp(type="GROUND", name="GND_mid", x=-900, y=-40, parameters={},
               pins=[pin(0, "gnd", 0, -20)])
components += [v_dcp, v_dcn, gnd_mid]

# ---- 6 MMC arms (L0 Average) + 6 arm inductors ----
ARM_DEFAULTS = {
    "model_fidelity": "L0 Average", "submodule_type": "Half-Bridge",
    "n_submodules": N_SM, "c_sm": C_SM, "v_c0": VC0, "r_arm": ARM_R,
    "m_ref_constant": 0.5, "f_carrier": 1000.0, "modulation_scheme": "PSC",
    "t_dead": 1.0e-6, "t_min": 1.0e-7, "balancing": "sort_and_select",
}
arm_upper, arm_lower, L_upper, L_lower = [], [], [], []
for ph, col_x in zip(("A", "B", "C"), X_PHASE):
    lu = comp(type="INDUCTOR", name=f"L_u{ph}", x=col_x, y=Y_L_UPPER,
              parameters={"inductance": ARM_L, "initial_current": 0.0},
              pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)])
    au = comp(type="MMC_ARM", name=f"ARM_u{ph}", x=col_x, y=Y_ARM_UPPER,
              parameters={**ARM_DEFAULTS},
              pins=[pin(0, "TOP", -35, -40), pin(1, "BOT", -35, 40), pin(2, "M_REF", 35, 0),
                    pin(3, "V_C", 35, -40), pin(4, "V_C_SPRD", 35, 40)])
    al = comp(type="MMC_ARM", name=f"ARM_l{ph}", x=col_x, y=Y_ARM_LOWER,
              parameters={**ARM_DEFAULTS},
              pins=[pin(0, "TOP", -35, -40), pin(1, "BOT", -35, 40), pin(2, "M_REF", 35, 0),
                    pin(3, "V_C", 35, -40), pin(4, "V_C_SPRD", 35, 40)])
    ll = comp(type="INDUCTOR", name=f"L_l{ph}", x=col_x, y=Y_L_LOWER,
              parameters={"inductance": ARM_L, "initial_current": 0.0},
              pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)])
    components += [lu, au, al, ll]
    L_upper.append(lu); arm_upper.append(au); arm_lower.append(al); L_lower.append(ll)

# ---- MMC controller (six modulation outputs) ----
mmc_ctrl = comp(
    type="MMC_CONTROLLER", name="MMC_Ctrl", x=-600, y=480,
    parameters={"m_ref_offset": 0.5, "modulation_index": MOD_INDEX,
                "frequency": F_OUT, "phase_deg": 0.0, "sample_time": 0.0},
    pins=[pin(0, "A_UP", 40, -60), pin(1, "A_LO", 40, -40),
          pin(2, "B_UP", 40, -20), pin(3, "B_LO", 40, 20),
          pin(4, "C_UP", 40, 40), pin(5, "C_LO", 40, 60)],
)
components.append(mmc_ctrl)

# Each controller output → arm M_REF, carried by a matching GOTO/FROM net
# label pair (merge is by label text, immune to wire-routing geometry —
# routed signal wires across the schematic otherwise short on the 5 px
# coincidence tolerance).
mref_targets = [arm_upper[0], arm_lower[0], arm_upper[1], arm_lower[1],
                arm_upper[2], arm_lower[2]]
goto_labels, from_labels = [], []
_ctrl_dy = (-60, -40, -20, 20, 40, 60)  # MMC_CONTROLLER output pin Y offsets
for i, arm in enumerate(mref_targets):
    text = f"MREF_{i}"
    # GOTO label aligned to its controller output (full grid Y) so the stub
    # is horizontal and the label never snap-collapses onto its neighbour.
    g = comp(type="GOTO_LABEL", name=f"GOTO_{text}", x=-480, y=480 + _ctrl_dy[i],
             parameters={"net_label": text}, pins=[pin(0, "NET", 0, 0)])
    fr = comp(type="FROM_LABEL", name=f"FROM_{text}", x=arm["x"] + 120, y=arm["y"],
              parameters={"net_label": text}, pins=[pin(0, "NET", 0, 0)])
    components += [g, fr]
    goto_labels.append(g)
    from_labels.append(fr)

# ---- 3φ wye R+L load (neutral = ground = DC midpoint) ----
load_r, load_l, ip_phase = [], [], []
for i, (ph, col_x) in enumerate(zip(("A", "B", "C"), X_PHASE)):
    py = Y_PHASE_TAP + (i - 1) * 80
    ipx = comp(type="CURRENT_PROBE", name=f"I_ph{ph}", x=160, y=py,
               parameters={"display_name": f"I_ph{ph}", "scale": 1.0},
               pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0), pin(2, "OUT", 0, 25)])
    rx = comp(type="RESISTOR", name=f"R_{ph}", x=300, y=py,
              parameters={"resistance": R_LOAD}, pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)])
    lx = comp(type="INDUCTOR", name=f"L_{ph}", x=440, y=py,
              parameters={"inductance": L_LOAD, "initial_current": 0.0},
              pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)])
    components += [ipx, rx, lx]
    ip_phase.append(ipx); load_r.append(rx); load_l.append(lx)
gnd_n = comp(type="GROUND", name="GND_n", x=580, y=80, parameters={}, pins=[pin(0, "gnd", 0, -20)])
components.append(gnd_n)

# Phase tap → load is carried by a GOTO/FROM net-label pair (PH_x), not a long
# routed wire. Three routed phase wires would otherwise share the y=arm-BOT
# corridor, overlap, and get merged into one node on the scene's junction pass
# (shorting all three AC phases together → singular matrix). GOTO sits at each
# arm (300 px apart), FROM sits at each load probe.
goto_ph, from_ph = [], []
for i, (ph, col_x) in enumerate(zip(("A", "B", "C"), X_PHASE)):
    gp = comp(type="GOTO_LABEL", name=f"GOTO_PH_{ph}", x=col_x + 60, y=Y_ARM_UPPER + 40,
              parameters={"net_label": f"PH_{ph}"}, pins=[pin(0, "NET", 0, 0)])
    fp = comp(type="FROM_LABEL", name=f"FROM_PH_{ph}", x=100, y=Y_PHASE_TAP + (i - 1) * 80,
              parameters={"net_label": f"PH_{ph}"}, pins=[pin(0, "NET", 0, 0)])
    components += [gp, fp]
    goto_ph.append(gp); from_ph.append(fp)

# ---- Phase voltage probes — a clean column right of the load, aligned with
# the AC-voltage scope. Each one taps its phase through a (left) PH_x FROM
# label and feeds the scope through a (right) SIG_VPHx GOTO label, so the
# probe→scope path is fully visible. Kept out of the dense load row, where the
# horizontal IN→OUT body would otherwise sit on top of its own sense wire. ----
VP_Y = (-420, -380, -340)   # full grid, 40 px apart, matched to scope_v CH pins
vp_phase, vp_sense_from = [], []
for i, ph in enumerate(("A", "B", "C")):
    vp = comp(type="VOLTAGE_PROBE_GND", name=f"V_ph{ph}", x=600, y=VP_Y[i],
              parameters={"display_name": f"V_ph{ph}", "scale": 1.0},
              pins=[pin(0, "IN", -20, 0), pin(1, "OUT", 20, 0)])
    sf = comp(type="FROM_LABEL", name=f"FROM_VPH_{ph}", x=540, y=VP_Y[i],
              parameters={"net_label": f"PH_{ph}"}, pins=[pin(0, "NET", 0, 0)])
    components += [vp, sf]
    vp_phase.append(vp); vp_sense_from.append(sf)

# ---- Phase-A arm current probes ----
# Rotated 90°: CURRENT_PROBE's canonical pins are horizontal (IN/OUT left-right),
# but these sit in a vertical arm leg. Rotating makes IN/OUT vertical so the
# series wires run straight down the leg; a horizontal probe here forces the
# OUT→arm wire back across the IN pin, shorting the ammeter (singular matrix).
# Full-grid Y (±80) so the body never snap-shifts on load.
ip_arm_uA = comp(type="CURRENT_PROBE", name="I_arm_uA", x=X_PHASE[0], y=Y_L_UPPER + 80, rotation=90,
                 parameters={"display_name": "I_arm_uA", "scale": 1.0},
                 pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25), pin(2, "OUT", 30, 0)])
ip_arm_lA = comp(type="CURRENT_PROBE", name="I_arm_lA", x=X_PHASE[0], y=Y_L_LOWER - 80, rotation=90,
                 parameters={"display_name": "I_arm_lA", "scale": 1.0},
                 pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25), pin(2, "OUT", 30, 0)])
components += [ip_arm_uA, ip_arm_lA]

# ---- Scopes ----
# CH pins spaced 40 px (full grid) so the per-channel FROM labels never
# snap-collapse onto a neighbour. Channels are *wired* (label only, no direct
# signal) — fed from the probes through SIG_* GOTO/FROM label pairs below.
scope_v = comp(type="ELECTRICAL_SCOPE", name="Scope_ACVoltages", x=820, y=-380,
               parameters={"channel_count": 3, "channels": [
                   {"label": "V_phA", "overlay": True},
                   {"label": "V_phB", "overlay": True},
                   {"label": "V_phC", "overlay": True}]},
               pins=[pin(0, "CH1", -40, -40), pin(1, "CH2", -40, 0), pin(2, "CH3", -40, 40)])
scope_i = comp(type="ELECTRICAL_SCOPE", name="Scope_PhaseCurrents", x=820, y=-160,
               parameters={"channel_count": 3, "channels": [
                   {"label": "I_phA", "overlay": True},
                   {"label": "I_phB", "overlay": True},
                   {"label": "I_phC", "overlay": True}]},
               pins=[pin(0, "CH1", -40, -40), pin(1, "CH2", -40, 0), pin(2, "CH3", -40, 40)])
# Cap-voltage scope — direct-signal channels (the <arm>.v_C telemetry the
# L0 observer publishes; no wires needed for a direct-signal channel).
scope_vc = comp(type="ELECTRICAL_SCOPE", name="Scope_CapVoltages", x=820, y=80,
                parameters={"channel_count": 6, "channels": [
                    {"label": f"Vc {a}", "overlay": True}
                    for a in ("uA", "lA", "uB", "lB", "uC", "lC")]},
                pins=[pin(i, f"CH{i+1}", -40, -100 + i * 40) for i in range(6)])
scope_arm = comp(type="ELECTRICAL_SCOPE", name="Scope_ArmCurrentsA", x=820, y=320,
                 parameters={"channel_count": 2, "channels": [
                     {"label": "I_arm_uA", "overlay": True},
                     {"label": "I_arm_lA", "overlay": True}]},
                 pins=[pin(0, "CH1", -40, -40), pin(1, "CH2", -40, 40)])
components += [scope_v, scope_i, scope_vc, scope_arm]

# ---- Scope signal wiring (visible GOTO/FROM pairs) -------------------------
# Each probe's measurement reaches its scope channel through a SIG_* net-label
# pair: GOTO at the source signal pin, FROM at the scope channel pin. Merge is
# by label text (geometry-independent), so the schematic shows what feeds every
# scope without long routed signal wires shorting nets on load. Every scope is
# wired this way — the cap-voltage scope reads each arm's V_C telemetry pin, so
# the whole example is reproducible in the GUI with no hidden direct signals.
sig_links: list[tuple] = []  # (probe, sig_pin, scope, ch_idx, goto, from)


def _sig(probe, sig_pin, scope, ch_idx, text, goto_xy, from_xy):
    g = comp(type="GOTO_LABEL", name=f"GOTO_{text}", x=goto_xy[0], y=goto_xy[1],
             parameters={"net_label": text}, pins=[pin(0, "NET", 0, 0)])
    fr = comp(type="FROM_LABEL", name=f"FROM_{text}", x=from_xy[0], y=from_xy[1],
              parameters={"net_label": text}, pins=[pin(0, "NET", 0, 0)])
    components.extend([g, fr])
    sig_links.append((probe, sig_pin, scope, ch_idx, g, fr))


SCOPE_V_CH_Y = (-420, -380, -340)
SCOPE_I_CH_Y = (-200, -160, -120)
SCOPE_ARM_CH_Y = (280, 360)
for i, ph in enumerate(("A", "B", "C")):
    _sig(vp_phase[i], 1, scope_v, i, f"SIG_VPH{ph}",
         (660, VP_Y[i]), (740, SCOPE_V_CH_Y[i]))               # V_ph OUT → scope_v
    _py = Y_PHASE_TAP + (i - 1) * 80
    _sig(ip_phase[i], 2, scope_i, i, f"SIG_IPH{ph}",
         (160, _py - 40), (740, SCOPE_I_CH_Y[i]))              # I_ph MEAS (up) → scope_i
_sig(ip_arm_uA, 2, scope_arm, 0, "SIG_IARMUA",
     (X_PHASE[0] - 80, Y_L_UPPER + 80), (740, SCOPE_ARM_CH_Y[0]))
_sig(ip_arm_lA, 2, scope_arm, 1, "SIG_IARMLA",
     (X_PHASE[0] - 80, Y_L_LOWER - 80), (740, SCOPE_ARM_CH_Y[1]))

# Cap-voltage scope: each arm's V_C telemetry pin (index 3) → its channel. The
# GOTO sits just right of the arm (arms are 300 px apart, so no merge); the
# FROM at the grouped scope channels (40 px apart, full grid).
_cap_arms = [arm_upper[0], arm_lower[0], arm_upper[1],
             arm_lower[1], arm_upper[2], arm_lower[2]]
for i, _arm in enumerate(_cap_arms):
    _nm = _arm["name"][4:]  # "uA", "lA", ...
    _sig(_arm, 3, scope_vc, i, f"SIG_VC_{_nm}",
         (_arm["x"] + 90, _arm["y"] - 40), (740, 80 - 100 + i * 40))

# ---------------------------------------------------------------------------
# Wires
# ---------------------------------------------------------------------------
comp_by_id = {c["id"]: c for c in components}
wires: list[dict] = []
router = WireRouter(grid=20.0)
router.add_obstacles_from_components(components, body_half_w=30.0, body_half_h=25.0, padding=6.0)


def w(a, ap, b, bp, *, node_name="", alias=""):
    wires.append(wire(a["id"], ap, b["id"], bp, comp_by_id, router,
                      node_name=node_name, alias=alias))


# DC bus: VDC_POS rail, MID(gnd), VDC_NEG rail
w(v_dcp, 1, gnd_mid, 0, node_name="MID")          # V_DCp.-  → MID
w(v_dcn, 0, gnd_mid, 0, node_name="MID")          # V_DCn.+  → MID
for lu in L_upper:
    w(v_dcp, 0, lu, 0, node_name="VDC_POS")       # V_DCp.+ → upper inductors
for ll in L_lower:
    w(v_dcn, 1, ll, 1, node_name="VDC_NEG")       # V_DCn.- → lower inductors

# Phase columns: L_u → ARM_u(TOP→BOT=PHASE) → ARM_l(TOP→BOT) → L_l ; A has arm probes
for i, ph in enumerate(("A", "B", "C")):
    au, al, lu, ll = arm_upper[i], arm_lower[i], L_upper[i], L_lower[i]
    if ph == "A":
        w(lu, 1, ip_arm_uA, 0, node_name="ARM_uA_TOP_PRE")
        w(ip_arm_uA, 1, au, 0, node_name="ARM_uA_TOP")
        w(au, 1, al, 0, node_name="PHASE_A")
        w(al, 1, ip_arm_lA, 0, node_name="ARM_lA_BOT_PRE")
        w(ip_arm_lA, 1, ll, 0, node_name="ARM_lA_BOT")
    else:
        w(lu, 1, au, 0, node_name=f"ARM_u{ph}_TOP")
        w(au, 1, al, 0, node_name=f"PHASE_{ph}")
        w(al, 1, ll, 0, node_name=f"ARM_l{ph}_BOT")

# Controller output i → GOTO_i ;  arm_i.M_REF → FROM_i  (same label → merged).
# Direct single-segment stubs keep the label attachments off the router.
for i, arm in enumerate(mref_targets):
    wires.append(wire_direct(mmc_ctrl["id"], i, goto_labels[i]["id"], 0, comp_by_id))
    wires.append(wire_direct(arm["id"], 2, from_labels[i]["id"], 0, comp_by_id))

# AC load + phase probes. The phase tap reaches each load through its PH_x
# label pair; only short, column-local wires are routed here.
for i, ph in enumerate(("A", "B", "C")):
    au = arm_upper[i]
    wires.append(wire_direct(au["id"], 1, goto_ph[i]["id"], 0, comp_by_id))          # tap → PH_x
    wires.append(wire_direct(ip_phase[i]["id"], 0, from_ph[i]["id"], 0, comp_by_id))  # PH_x → load
    wires.append(wire_direct(vp_phase[i]["id"], 0, vp_sense_from[i]["id"], 0, comp_by_id))  # V_ph sense → PH_x
    w(ip_phase[i], 1, load_r[i], 0, node_name=f"LOAD_{ph}_PRE")
    w(load_r[i], 1, load_l[i], 0, node_name=f"LOAD_{ph}_MID")
    w(load_l[i], 1, gnd_n, 0, node_name="NEUTRAL")

# Scope signal wiring: each probe's signal pin → GOTO, each scope channel → FROM
# (the matching SIG_* label text joins them). Short, isolated stubs only.
for probe, sig_pin, scope, ch_idx, g, fr in sig_links:
    wires.append(wire_direct(probe["id"], sig_pin, g["id"], 0, comp_by_id))
    wires.append(wire_direct(scope["id"], ch_idx, fr["id"], 0, comp_by_id))

# ---------------------------------------------------------------------------
sim_settings = {
    # Short window: open-loop modulation has no energy/circulating-current
    # control, so the arm caps drift — keep it brief to see clean 3φ AC
    # (Scope_ACVoltages) before the drift (Scope_CapVoltages) dominates.
    # PWL engine: the MMC average arms drive controlled sources via a
    # b_extra residual that DSED can't extract an LTI state-space for.
    "engine": "pwl",
    "tstop": 0.025, "dt": 2.0e-6, "tstart": 0.0, "output_points": 12500,
    "control_sample_time": 1.0e-5, "control_mode": "discrete",
    "tol_newton_dx": 1.0e-6, "tol_newton_res": 1.0e-6,
    "enable_newton_line_search": True, "enable_newton_lm": True,
    "enable_substep_state_correction": True, "enable_nonlinear_refresh": True,
    "start_from_dc_op": False, "max_event_iterations": 50,
}

now = datetime.now().isoformat(timespec="seconds")
project = {
    "version": "1.0",
    "name": "24 MMC 3-Phase Controlled — open-loop sinusoidal modulation (L0)",
    "created": now, "modified": now, "active_circuit": "main",
    "simulation_settings": sim_settings,
    "circuits": {"main": {"name": "main", "components": components, "wires": wires}},
    "subcircuits": {}, "scope_windows": {}, "scope_workspace_state": {},
}

out_path = Path(__file__).resolve().parent.parent / "examples" / "24_mmc_three_phase_controlled.pulsim"
out_path.write_text(json.dumps(project, indent=2))
print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  {len(components)} components, {len(wires)} wires")
