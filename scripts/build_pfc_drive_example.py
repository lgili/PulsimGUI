#!/usr/bin/env python3
"""Builder for example 16 — full AC→DC→AC drive with cascaded PFC.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_pfc_drive_example.py

Regenerates ``examples/16_pfc_drive_full_chain.pulsim``. Doubles as a
worked example of the smart wire router
(:mod:`pulsimgui.utils.wire_router`) producing clean orthogonal
routes with corner-collision avoidance.

Topology:
    Vac (1φ, 311 V peak, 50 Hz)
        → 1φ Diode Bridge (Graetz)
        → Boost PFC stage (L + MOSFET + diode + Cbus)
            ↳ outer voltage loop:  V_REF − V_DC → PI_V → I_REF
            ↳ inner current loop:  I_REF − I_L  → PI_I → PWM duty
        → DC bus (≈ 400 V regulated)
        → 3φ VSI (behavioral fallback @ 50 Hz, m=0.8)
        → 3φ R+L star network (motor stand-in — pulsim 1.5 dropped
          the native PMSM dynamic builder; the R+L preserves the
          three-phase loading behavior for V/f demos)
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def uid() -> str:
    return str(uuid.uuid4())


def comp(*, type: str, name: str, x: float, y: float, parameters: dict,
         pins: list[dict], rotation: int = 0) -> dict:
    return {
        "id": uid(),
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


import pulsimgui.models  # noqa: F401  — defuse circular import
from pulsimgui.utils.wire_router import WireRouter


def wire(a_id: str, a_pin: int, b_id: str, b_pin: int,
         components_by_id: dict, router: WireRouter, *,
         node_name: str = "", alias: str = "") -> dict:
    """Build a wire between two pins using the smart orthogonal router.

    Returns a wire dict with grid-snapped orthogonal segments (L- or
    Z-routed), obstacles avoided, and corner collisions guaranteed
    not to share coordinates with previously-routed wires (which
    would otherwise trigger the union-find merge bug at netlist
    build time).
    """
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
        "id": uid(),
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

# ------------------ AC mains + rectifier ------------------
v_ac = comp(
    type="VOLTAGE_SOURCE", name="Vac", x=-900, y=0,
    parameters={
        "waveform": {
            "type": "sine",
            "amplitude": 311.0,    # 220 Vrms ≈ 311 V peak
            "frequency": 50.0,
            "offset": 0.0,
            "phase": 0.0,
        },
    },
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
)
components.append(v_ac)

gnd_ac = comp(
    type="GROUND", name="GND_ac", x=-840, y=60,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_ac)

br1 = comp(
    type="SINGLE_PHASE_DIODE_BRIDGE", name="BR1", x=-700, y=0,
    parameters={
        "g_on": 1.0e3,
        "g_off": 1.0e-9,
        "v_forward": 0.7,
        "r_th_jc": 1.5,
        "tau_th": 0.075,
    },
    pins=[
        pin(0, "AC+", -35, -20),
        pin(1, "AC-", -35, 20),
        pin(2, "DC+",  35, -20),
        pin(3, "DC-",  35, 20),
    ],
)
components.append(br1)

# ------------------ Boost PFC stage ------------------
l_boost = comp(
    type="INDUCTOR", name="L_boost", x=-560, y=-20,
    parameters={"inductance": 2.0e-3, "initial_current": 0.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(l_boost)

m_boost = comp(
    type="MOSFET_N", name="M_boost", x=-420, y=20,
    parameters={
        "is_nmos": True,
        "R_on": 25e-3,
        "R_off": 1.0e9,
        "v_th": 3.0,
    },
    pins=[pin(0, "D", 0, -25), pin(1, "G", -25, 0), pin(2, "S", 0, 25)],
)
components.append(m_boost)

d_boost = comp(
    type="DIODE", name="D_boost", x=-320, y=-20,
    parameters={"g_on": 1.0e3, "g_off": 1.0e-9, "v_forward": 0.7},
    pins=[pin(0, "A", -25, 0), pin(1, "K", 25, 0)],
)
components.append(d_boost)

c_bus = comp(
    type="CAPACITOR", name="C_bus", x=-200, y=20,
    # Start at the rectified DC peak (~310 V) so the diode bridge has
    # already pre-charged the cap before the boost engages. Avoids a
    # huge current inrush at t=0.
    parameters={"capacitance": 470e-6, "initial_voltage": 310.0},
    pins=[pin(0, "+", 0, -25), pin(1, "-", 0, 25)],
)
components.append(c_bus)

# DC bus load resistor — gives the boost stage something to regulate
# against. Sized for ~50 W (R = V²/P = 400²/50 = 3.2 kΩ). Without
# this, the cap voltage is static at its initial value because the
# behavioral VSI fallback doesn't actually pull power from the bus.
r_bus_load = comp(
    type="RESISTOR", name="R_bus_load", x=-40, y=80,
    parameters={"resistance": 3.2e3},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_bus_load)

gnd_dc = comp(
    type="GROUND", name="GND_dc", x=-200, y=100,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_dc)

# ------------------ Sensors ------------------
ip_l = comp(
    type="CURRENT_PROBE", name="I_L", x=-490, y=-20,
    parameters={"display_name": "I_L", "scale": 1.0},
    pins=[
        pin(0, "1", -25, 0),
        pin(1, "2",  25, 0),
        pin(2, "OUT", 0, 25),
    ],
)
components.append(ip_l)

vp_dc = comp(
    type="VOLTAGE_PROBE_GND", name="V_DC", x=-120, y=0,
    parameters={"display_name": "V_DC", "scale": 1.0},
    pins=[
        pin(0, "1", -25, 0),
        pin(1, "OUT", 25, 0),
    ],
)
components.append(vp_dc)

# ------------------ Cascaded V/I control (outer V, inner I) ------------------
# The chain is:  V_REF → SUB_V → PI_V → SUB_I → PI_I → PWM → MOSFET
# with feedback:  VOLTAGE_PROBE(V_DC) → SUB_V,  CURRENT_PROBE(I_L) → SUB_I
#
# The circuit_converter detects this cascaded structure and emits a
# single closed-loop descriptor with an ``outer_pi`` sub-block. The
# backend then binds the INNER PI to the MOSFET via bind_pi_to_switch
# using a time-varying setpoint that's the OUTER PI's output (updated
# once per PWM cycle from the V_DC measurement).
v_ref = comp(
    type="CONSTANT", name="V_REF", x=-820, y=-260,
    parameters={"value": 400.0, "sample_time": 2.0e-5},
    pins=[pin(0, "OUT", 30, 0)],
)
components.append(v_ref)

sub_v = comp(
    type="SUBTRACTOR", name="SUB_V", x=-680, y=-260,
    parameters={"input_count": 2, "signs": ["+", "-"], "sample_time": 2.0e-5},
    pins=[
        pin(0, "IN1", -30, -15),
        pin(1, "IN2", -30, 15),
        pin(2, "OUT",  30, 0),
    ],
)
components.append(sub_v)

pi_v = comp(
    type="PI_CONTROLLER", name="PI_V", x=-520, y=-260,
    parameters={
        # Outer voltage loop — generates the inductor-current
        # reference. Slow loop (~5 Hz crossover) so it doesn't react
        # to 100 Hz DC-bus ripple. Output limited to 0..3 A peak
        # inductor current command.
        "kp": 0.015,
        "ki": 1.5,
        "output_min": 0.0,
        "output_max": 3.0,         # max inner I_L reference [A]
        "anti_windup": True,
        "sample_time": 2.0e-5,
    },
    pins=[pin(0, "IN", -30, 0), pin(1, "OUT", 30, 0)],
)
components.append(pi_v)

sub_i = comp(
    type="SUBTRACTOR", name="SUB_I", x=-360, y=-260,
    parameters={"input_count": 2, "signs": ["+", "-"], "sample_time": 2.0e-5},
    pins=[
        pin(0, "IN1", -30, -15),   # setpoint side (from PI_V.OUT)
        pin(1, "IN2", -30, 15),    # feedback side (from I_L probe)
        pin(2, "OUT",  30, 0),
    ],
)
components.append(sub_i)

pi_i = comp(
    type="PI_CONTROLLER", name="PI_I", x=-200, y=-260,
    parameters={
        # Inner current loop — generates the duty command. Fast
        # (~ kHz crossover). Steady-state duty for 220 Vrms → 400 V
        # is D ≈ 0.23, so clamp 0..0.45 leaves the integrator headroom
        # without letting it run away.
        "kp": 0.10,
        "ki": 500.0,
        "output_min": 0.0,
        "output_max": 0.45,
        "anti_windup": True,
        "sample_time": 2.0e-5,
    },
    pins=[pin(0, "IN", -30, 0), pin(1, "OUT", 30, 0)],
)
components.append(pi_i)

pwm_boost = comp(
    type="PWM_GENERATOR", name="PWM_BOOST", x=-40, y=-260,
    parameters={
        "frequency": 50e3,
        "duty_cycle": 0.5,
        "carrier": "sawtooth",
        "amplitude": 12.0,
        "sample_time": 0.0,
        "enable_duty_input": True,
    },
    pins=[pin(0, "OUT", 30, 0), pin(1, "DUTY_IN", -30, 0)],
)
components.append(pwm_boost)

# Goto/From labels — route control signals across the schematic without
# spaghetti wires.
goto_pwm = comp(
    type="GOTO_LABEL", name="Xpwm_out", x=40, y=-260,
    parameters={"net_label": "PWM_GATE"},
    pins=[pin(0, "NET", -25, 0)],
)
components.append(goto_pwm)

goto_v = comp(
    type="GOTO_LABEL", name="Xv_dc", x=-60, y=0,
    parameters={"net_label": "V_DC_MEAS"},
    pins=[pin(0, "NET", -25, 0)],
)
components.append(goto_v)

from_v = comp(
    type="FROM_LABEL", name="Xv_dc_in", x=-640, y=-245,
    parameters={"net_label": "V_DC_MEAS"},
    pins=[pin(0, "NET", 25, 0)],
)
components.append(from_v)

goto_i = comp(
    type="GOTO_LABEL", name="Xi_l", x=-460, y=10,
    parameters={"net_label": "I_L_MEAS"},
    pins=[pin(0, "NET", -25, 0)],
)
components.append(goto_i)

from_i = comp(
    type="FROM_LABEL", name="Xi_l_in", x=-380, y=-245,
    parameters={"net_label": "I_L_MEAS"},
    pins=[pin(0, "NET", 25, 0)],
)
components.append(from_i)

from_pwm = comp(
    type="FROM_LABEL", name="Xpwm_gate", x=-470, y=20,
    parameters={"net_label": "PWM_GATE"},
    pins=[pin(0, "NET", 25, 0)],
)
components.append(from_pwm)

# ------------------ 3-phase VSI + PMSM motor ------------------
vsi = comp(
    type="THREE_PHASE_VSI", name="VSI", x=100, y=0,
    parameters={
        "switching_frequency_hz": 10000.0,
        "modulation_index": 0.8,
        "modulation_frequency_hz": 50.0,
        "phase_a_deg": 0.0,
        "positive_sequence": True,
        "v_gate_on": 12.0,
        "v_gate_off": 0.0,
        "mosfet_r_on_ohm": 0.01,
        "mosfet_vth": 1.0,
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

# Pulsim 1.5+ dropped the native PMSM (dynamic) builder. We stand in
# the motor with a Y-connected 3φ R+L load sized to roughly mimic a
# small PMSM (R_s ≈ 0.5 Ω, L_s ≈ 2 mH per phase). The neutral is
# tied to ground so the inverter can settle. A future revision can
# swap this group for ComponentType.PMSM once the kernel ships a
# replacement helper.
phase_x = 300        # column where the load network sits
phase_y_a = -40
phase_y_b = 0
phase_y_c = 40
neutral_x = 460

motor_rs = []
motor_ls = []
for phase_label, py in (("A", phase_y_a), ("B", phase_y_b), ("C", phase_y_c)):
    r = comp(
        type="RESISTOR", name=f"R_{phase_label}", x=phase_x, y=py,
        parameters={"resistance": 0.5},
        pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    )
    components.append(r)
    motor_rs.append(r)

    l = comp(
        type="INDUCTOR", name=f"L_{phase_label}", x=phase_x + 100, y=py,
        parameters={"inductance": 2.0e-3, "initial_current": 0.0},
        pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    )
    components.append(l)
    motor_ls.append(l)

gnd_motor = comp(
    type="GROUND", name="GND_motor", x=neutral_x, y=80,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_motor)

# ------------------ Scopes ------------------
scope_bus = comp(
    type="ELECTRICAL_SCOPE", name="Scope_PFC", x=560, y=-200,
    parameters={
        "channel_count": 3,
        "channels": [
            {"label": "V_DC",  "overlay": False},
            {"label": "I_L",   "overlay": False},
            {"label": "DUTY",  "overlay": False},
        ],
    },
    pins=[
        pin(0, "CH1", -40, -25),
        pin(1, "CH2", -40, 0),
        pin(2, "CH3", -40, 25),
    ],
)
components.append(scope_bus)

scope_mot = comp(
    type="ELECTRICAL_SCOPE", name="Scope_Motor", x=560, y=60,
    parameters={
        "channel_count": 3,
        "channels": [
            {"label": "V(A)",   "overlay": False},
            {"label": "I_d",    "overlay": False},
            {"label": "I_q",    "overlay": False},
        ],
    },
    pins=[
        pin(0, "CH1", -40, -25),
        pin(1, "CH2", -40, 0),
        pin(2, "CH3", -40, 25),
    ],
)
components.append(scope_mot)

# Pull a scope probe directly off the motor's A phase via a voltage probe
vp_motor_a = comp(
    type="VOLTAGE_PROBE_GND", name="V_motor_A", x=420, y=-25,
    parameters={"display_name": "V(A)", "scale": 1.0},
    pins=[pin(0, "1", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_motor_a)

# ---------------------------------------------------------------------------
# Wires
# ---------------------------------------------------------------------------
comp_by_id = {c["id"]: c for c in components}
wires: list[dict] = []

# Smart router: pre-seeded with every component as an obstacle.
# Generates clean orthogonal routes with unique corners (so no two
# wires collide at a shared L-corner, which would otherwise merge
# their nets via the netlist union-find).
router = WireRouter(grid=20.0)
router.add_obstacles_from_components(
    components,
    # Tight per-component bbox — the example uses small symbols so a
    # 30×25 half-extent fits most of them without over-blocking the
    # surrounding routing channels.
    body_half_w=30.0,
    body_half_h=25.0,
    padding=6.0,
)


def w(a, ap, b, bp, *, node_name="", alias=""):
    wires.append(wire(a["id"], ap, b["id"], bp, comp_by_id, router,
                      node_name=node_name, alias=alias))


# ===== Power stage =====
# AC source → bridge AC inputs
w(v_ac, 0, br1, 0, node_name="VAC_P")
w(v_ac, 1, br1, 1, node_name="VAC_N")
# AC return to ground (so we have a reference; doesn't carry significant current)
w(v_ac, 1, gnd_ac, 0, node_name="VAC_N")

# Bridge DC+ → current-probe inductor → L_boost → MID node
w(br1, 2, ip_l, 0, node_name="VRECT")
w(ip_l, 1, l_boost, 0, node_name="VRECT_POST")
w(l_boost, 1, m_boost, 0, node_name="MID")
w(l_boost, 1, d_boost, 0, node_name="MID")

# MOSFET source → bridge DC- (negative rail)
w(m_boost, 2, br1, 3, node_name="DC_NEG")
# DC_NEG joins motor / DC bus return through cap & VSI:
w(m_boost, 2, c_bus, 1, node_name="DC_NEG")
w(c_bus, 1, vsi, 1, node_name="DC_NEG")
w(c_bus, 1, gnd_dc, 0, node_name="DC_NEG")

# Boost diode K (cathode) → DC bus positive
w(d_boost, 1, c_bus, 0, node_name="VBUS")
w(c_bus, 0, vsi, 0, node_name="VBUS")

# DC bus load resistor (in parallel with C_bus)
w(c_bus, 0, r_bus_load, 0, node_name="VBUS")
w(r_bus_load, 1, c_bus, 1, node_name="DC_NEG")

# DC bus voltage probe (between VBUS and GND)
w(c_bus, 0, vp_dc, 0, node_name="VBUS")

# ===== VSI → 3φ RL star (motor stand-in) =====
# Phase A: VSI.A → V_probe → R_A → L_A → neutral
w(vsi, 2, vp_motor_a, 0, node_name="MOT_A")
w(vp_motor_a, 0, motor_rs[0], 0, node_name="MOT_A")
w(motor_rs[0], 1, motor_ls[0], 0, node_name="MOT_RA")
w(motor_ls[0], 1, gnd_motor, 0, node_name="MOT_N")
# Phase B
w(vsi, 3, motor_rs[1], 0, node_name="MOT_B")
w(motor_rs[1], 1, motor_ls[1], 0, node_name="MOT_RB")
w(motor_ls[1], 1, gnd_motor, 0, node_name="MOT_N")
# Phase C
w(vsi, 4, motor_rs[2], 0, node_name="MOT_C")
w(motor_rs[2], 1, motor_ls[2], 0, node_name="MOT_RC")
w(motor_ls[2], 1, gnd_motor, 0, node_name="MOT_N")

# ===== Cascaded control: V_REF → SUB_V → PI_V → SUB_I → PI_I → PWM → MOSFET =====
# V_DC probe out → Goto VDC_MEAS (routes the signal to control row)
w(vp_dc, 1, goto_v, 0, node_name="V_DC_SIG")
# From VDC_MEAS → SUB_V.IN2 (negative input — outer feedback)
w(from_v, 0, sub_v, 1, node_name="V_DC_SIG")
# V_REF → SUB_V.IN1 (positive input — outer setpoint)
w(v_ref, 0, sub_v, 0, node_name="V_REF_SIG")
# SUB_V.OUT (= V_REF - V_DC) → PI_V.IN
w(sub_v, 2, pi_v, 0, node_name="V_ERR")
# PI_V.OUT → SUB_I.IN1 (current reference fed to inner loop)
w(pi_v, 1, sub_i, 0, node_name="I_REF")
# Inductor current probe → Goto I_L_MEAS
w(ip_l, 2, goto_i, 0, node_name="I_L_SIG")
# From I_L_MEAS → SUB_I.IN2 (inner feedback)
w(from_i, 0, sub_i, 1, node_name="I_L_SIG")
# SUB_I.OUT (= I_REF - I_L) → PI_I.IN
w(sub_i, 2, pi_i, 0, node_name="I_ERR")
# PI_I.OUT → PWM duty input (the cascaded chain detector wires the
# inner PI to the MOSFET via bind_pi_to_switch, while the outer PI
# ticks in Python every PWM cycle feeding the inner setpoint).
w(pi_i, 1, pwm_boost, 1, node_name="DUTY_CMD")
# PWM gate output → Goto PWM_GATE label
w(pwm_boost, 0, goto_pwm, 0, node_name="GATE_SIG")
# From PWM_GATE → MOSFET gate
w(from_pwm, 0, m_boost, 1, node_name="GATE_SIG")

# ===== Scope wires =====
# Scope_PFC channels (V_DC, I_L, DUTY)
# Re-fan the signals from the labels — add small FROM labels for the scope
from_v_scope = comp(
    type="FROM_LABEL", name="Xscope_vdc", x=470, y=-225,
    parameters={"net_label": "V_DC_MEAS"},
    pins=[pin(0, "NET", 25, 0)],
)
components.append(from_v_scope)
comp_by_id[from_v_scope["id"]] = from_v_scope

from_i_scope = comp(
    type="FROM_LABEL", name="Xscope_il", x=470, y=-200,
    parameters={"net_label": "I_L_MEAS"},
    pins=[pin(0, "NET", 25, 0)],
)
components.append(from_i_scope)
comp_by_id[from_i_scope["id"]] = from_i_scope

# Connect them to scope inputs
w(from_v_scope, 0, scope_bus, 0)
w(from_i_scope, 0, scope_bus, 1)
# DUTY signal: tap from PI_I.OUT directly (won't fan-out conflict — pyqtgraph scope tolerates multi-source)
w(pi_i, 1, scope_bus, 2)

# Scope_Motor — V(A) from voltage probe, plus PMSM internal currents.
# (For internal motor currents, easiest is to wire the motor phases via
# current probes — here we just expose phase-A voltage; d/q currents are
# kernel-side traces auto-published by PMSM that the scope picks up via
# its signal_keys.)
w(vp_motor_a, 1, scope_mot, 0)

# ---------------------------------------------------------------------------
# Simulation settings (pulsim 1.5 compatible — only valid kwargs)
# ---------------------------------------------------------------------------
sim_settings = {
    "tstop": 0.20,
    "dt": 1.0e-6,
    "tstart": 0.0,
    "output_points": 50000,
    "control_sample_time": 5.0e-6,
    "control_mode": "discrete",
    # Newton tuning (pulsim 1.5 fields)
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
# Project shell
# ---------------------------------------------------------------------------
now = datetime.now().isoformat(timespec="seconds")
project = {
    "version": "1.0",
    "name": "16 PFC Drive — 1φ Rectifier + Boost PFC + VSI + 3φ Load (motor stand-in)",
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

out_path = Path("/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGUI/examples/16_pfc_drive_full_chain.pulsim")
out_path.write_text(json.dumps(project, indent=2))
print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
print(f"  {len(components)} components, {len(wires)} wires")
