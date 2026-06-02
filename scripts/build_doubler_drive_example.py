#!/usr/bin/env python3
"""Builder for example 19 — Voltage-Doubler Compressor Drive.

Run from the repo root::

    PYTHONPATH=src .venv/bin/python scripts/build_doubler_drive_example.py

Regenerates ``examples/19_doubler_drive_compressor.pulsim`` deterministically
(component IDs are stable across runs so diffs stay clean).

This reproduces the backend "doubler" front-end (127 V low-line, North-
American compressor application) feeding a Field-Oriented-Control (FOC)
inverter that drives an Embraco VLT403U PMSM:

    Vac (1φ, 179.6 V peak ≈ 127 Vrms, 60 Hz)
        → source R/L + PFC choke R/L
        → 1φ Diode Bridge (Graetz)
        → DC bus: two SERIES caps (470 µF each, 20 mΩ ESR)
        → DOUBLER tap: R_doubler_tap = 1 mΩ from the cap midpoint to the
          AC return (ground). Tying the cap midpoint to the rectified-AC
          return is exactly what turns a full-bridge front-end into a
          voltage doubler at low line.
        → 3φ 2-level VSI (six ideal switches)
        → PMSM (dynamic, VLT403U), neutral FLOATING (isolated star point —
          opens the common-mode/zero-sequence path)
        + FOC controller (a C_BLOCK marker, control_kind="foc")

Caps are pre-charged to ~175 V each (near the doubler steady-state, where
each cap sits at the AC peak ≈ 180 V) so the bridge has already settled the
bus before t=0 — this avoids a huge inrush transient that would otherwise
dominate a short ms-scale validation run.

WHY FOC instead of open-loop V/f
--------------------------------
Open-loop V/f pole-slips a PMSM: the imposed stator-field angle and the
true rotor angle drift apart, the motor never locks, and the phase current
runs to 17-29 A of useless garbage on a ~1.6 A (FLA) motor. Closing the
i_d (=0) / i_q current loops + an outer speed PI is what lets the rotor
actually track a speed reference drawing only rated current (~1.6 A phase).

The FOC controller is represented (lowest-friction option) as a C_BLOCK
carrying ``control_kind="foc"`` plus the loop gains / speed-reference ramp
/ limits in its ``parameters``. It is a pure *marker* — no pins, NOT wired
into the power stage — that the converter detects (``_infer_foc_loops``)
and the backend executes (``_build_foc_loops``): an outer speed PI →
``iq_ref``, inner i_d/i_q PIs (with back-EMF + cross-coupling decoupling)
→ ``v_d``/``v_q``, then inverse Park (electrical angle pp·θ_mech) → inverse
Clarke → per-phase carrier compare at f_sw drives the VSI's six switches,
REPLACING its open-loop SPWM. The VSI's SPWM params below are inert.

DC-bus reference (v_bus)
------------------------
The FOC normalises modulation + clamps v_d/v_q by the descriptor ``v_bus``
(the backend can't infer the live, rippling bus). With FOC drawing only
~1.6 A (vs 17-29 A open-loop) the doubler bus sags far LESS than the old
open-loop run; under FOC load it settles near ~337 V (rails +166 / -171),
so ``v_bus`` is set to ~340 V (the ripple center). A slightly-off value is
fine — the inner current PI compensates.

The native switched VSI (now FOC-commanded) emits a ``switch_fn`` and the
dynamic PMSM emits a ``step_observer`` — the FOC descriptor is NOT a
``closed_loops`` entry, so the ``closed_loops`` vs ``switch_fn`` conflict
that pulsim ≥1.4 rejects never arises here.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401  — defuse circular import
from pulsimgui.utils.wire_router import WireRouter

REPO = Path("/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGUI")
OUT_PATH = REPO / "examples" / "19_doubler_drive_compressor.pulsim"

# Deterministic IDs: a fixed namespace + per-component name keeps the
# generated JSON byte-stable across runs.
_NS = uuid.UUID("19000000-0d0b-1e72-d21e-000000000000")

FSW = 20000.0     # inverter switching frequency [Hz]
# Nominal DC bus the FOC uses to normalise modulation + clamp v_d/v_q.
# Measured under FOC load (~1.6 A draw) the doubler bus settles ~337 V
# (rails +166 / -171, mid-tap pinned at 0); ~340 V is the ripple center.
VBUS_FOC = 340.0


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

# Layout rows (20-px grid; generous spacing for the orthogonal router):
#   y =    0   power row  (Vac → R_src → L_src → R_choke → L_choke → BR1 …)
#   y = +120   grounds / doubler tap
#   y = ±200   scopes on the far right

# ------------------ AC mains + line impedance ------------------
v_ac = comp(
    type="VOLTAGE_SOURCE", name="Vac", x=-1240, y=0,
    parameters={
        "waveform": {
            "type": "sine",
            "amplitude": 179.6,    # 127 Vrms · √2
            "frequency": 60.0,
            "offset": 0.0,
            "phase": 0.0,
        },
    },
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
)
components.append(v_ac)

gnd_ac = comp(
    type="GROUND", name="GND_ac", x=-1180, y=120,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_ac)

r_src = comp(
    type="RESISTOR", name="R_src", x=-1080, y=0,
    parameters={"resistance": 0.5},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_src)

l_src = comp(
    type="INDUCTOR", name="L_src", x=-940, y=0,
    parameters={"inductance": 200e-6, "initial_current": 0.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(l_src)

r_choke = comp(
    type="RESISTOR", name="R_choke", x=-800, y=0,
    parameters={"resistance": 0.30},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_choke)

l_choke = comp(
    type="INDUCTOR", name="L_choke", x=-660, y=0,
    parameters={"inductance": 2.5e-3, "initial_current": 0.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(l_choke)

# ------------------ 1φ diode bridge ------------------
br1 = comp(
    type="SINGLE_PHASE_DIODE_BRIDGE", name="BR1", x=-500, y=0,
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

# ------------------ DC bus: two series caps with ESR ------------------
# vbus_pos → R_ESR_C1 → n_C1_top → C1 → vbus_mid → R_ESR_C2 → n_C2_top
#          → C2 → vbus_neg
r_esr_c1 = comp(
    type="RESISTOR", name="R_ESR_C1", x=-280, y=-40,
    parameters={"resistance": 20e-3},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    rotation=90,
)
components.append(r_esr_c1)

c1 = comp(
    type="CAPACITOR", name="C1", x=-280, y=80,
    parameters={"capacitance": 470e-6, "initial_voltage": 175.0},
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
    rotation=90,
)
components.append(c1)

r_esr_c2 = comp(
    type="RESISTOR", name="R_ESR_C2", x=-280, y=200,
    parameters={"resistance": 20e-3},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
    rotation=90,
)
components.append(r_esr_c2)

c2 = comp(
    type="CAPACITOR", name="C2", x=-280, y=320,
    parameters={"capacitance": 470e-6, "initial_voltage": 175.0},
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
    rotation=90,
)
components.append(c2)

# ------------------ DOUBLER tap ------------------
# 1 mΩ from the cap midpoint (vbus_mid) to the AC return (ground "0").
# This is the defining feature: tying the series-cap midpoint to the
# rectified-AC return makes the front-end a voltage doubler.
r_doubler_tap = comp(
    type="RESISTOR", name="R_doubler_tap", x=-120, y=160,
    parameters={"resistance": 1e-3},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_doubler_tap)

gnd_mid = comp(
    type="GROUND", name="GND_mid", x=40, y=200,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_mid)

# ------------------ Voltage probe: V_bus ------------------
vp_bus = comp(
    type="VOLTAGE_PROBE", name="V_bus", x=120, y=0,
    parameters={"display_name": "V_bus", "scale": 1.0},
    pins=[
        pin(0, "+", 0, -20),
        pin(1, "-", 0, 20),
        pin(2, "OUT", 25, 0),
    ],
)
components.append(vp_bus)

# ------------------ 3φ VSI ------------------
# The SPWM drive params below are inert — the FOC controller commands the
# six switches via inverse Park/Clarke and the converter excludes a FOC-
# controlled VSI from the open-loop SPWM path.
vsi = comp(
    type="THREE_PHASE_VSI", name="VSI", x=360, y=0,
    parameters={
        "switching_frequency_hz": FSW,
        "modulation_index": 0.8,
        "modulation_frequency_hz": 90.0,   # ≈1800 rpm × 3 pole pairs
        "phase_a_deg": 0.0,
        "positive_sequence": True,
        "v_gate_on": 12.0,
        "v_gate_off": 0.0,
        "mosfet_r_on_ohm": 0.01,
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

# ------------------ Motor phase voltage probe (phase A) ------------------
vp_motor_a = comp(
    type="VOLTAGE_PROBE_GND", name="V_motor_A", x=540, y=-140,
    parameters={"display_name": "V(A)", "scale": 1.0},
    pins=[pin(0, "IN", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_motor_a)

# ------------------ PMSM (Embraco VLT403U) ------------------
pmsm = comp(
    type="PMSM", name="M1", x=620, y=0,
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

# NOTE: the PMSM neutral ("N", pin 3) is deliberately LEFT FLOATING — a
# real PMSM compressor has an ISOLATED star point (the backend YAML uses a
# floating ``neutral_node``). It is NOT wired to ground: the star point
# sits on its own net, referenced through the machine windings to the three
# VSI phases, with its potential fixed by KCL (i_a + i_b + i_c = 0). A
# floating neutral opens the common-mode (zero-sequence) path so no bus
# ripple can drive zero-sequence current through the phases. No
# ``GND_motor`` component exists.

# ------------------ FOC controller (C_BLOCK marker) ------------------
# control_kind="foc" → the converter emits a foc_loop_descriptor binding
# this marker to the VSI (commanded) + the PMSM (observed). It carries no
# pins and is NOT wired into the power stage; the backend reads the loop
# gains / speed-reference ramp / limits / v_bus below and closes the loops
# at simulate time, driving the VSI's six switches (replacing its open-loop
# SPWM). Gains match the validated VLT403U FOC recipe (example 21).
foc = comp(
    type="C_BLOCK", name="FOC", x=620, y=-220,
    parameters={
        "control_kind": "foc",
        "vsi_name": "VSI",
        "pmsm_name": "M1",
        # Nominal DC bus for modulation normalisation / voltage clamp.
        "v_bus": VBUS_FOC,
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

# ------------------ Scopes ------------------
scope_bus = comp(
    type="ELECTRICAL_SCOPE", name="Scope_Bus", x=900, y=-180,
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
components.append(scope_bus)

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


# ===== AC line: Vac → R_src → L_src → R_choke → L_choke → BR1.AC+ =====
w(v_ac, 0, r_src, 0, node_name="VAC_P")
w(r_src, 1, l_src, 0, node_name="N_RSRC")
w(l_src, 1, r_choke, 0, node_name="AC_L0")
w(r_choke, 1, l_choke, 0, node_name="N_RCHOKE")
w(l_choke, 1, br1, 0, node_name="AC_L")
# AC return: Vac- → ground; BR1.AC- → ground (node "0")
w(v_ac, 1, gnd_ac, 0, node_name="0")
w(v_ac, 1, br1, 1, node_name="0")

# ===== DC bus series-cap string =====
# BR1.DC+ → vbus_pos → R_ESR_C1 → n_C1_top → C1 → vbus_mid
w(br1, 2, r_esr_c1, 0, node_name="VBUS_POS")
w(r_esr_c1, 1, c1, 0, node_name="N_C1_TOP")
w(c1, 1, r_esr_c2, 0, node_name="VBUS_MID")
# vbus_mid → R_ESR_C2 → n_C2_top → C2 → vbus_neg
w(r_esr_c2, 1, c2, 0, node_name="N_C2_TOP")
w(c2, 1, br1, 3, node_name="VBUS_NEG")

# ===== DOUBLER tap: vbus_mid → R_doubler_tap → ground "0" =====
w(c1, 1, r_doubler_tap, 0, node_name="VBUS_MID")
w(r_doubler_tap, 1, gnd_mid, 0, node_name="0")

# ===== V_bus probe across vbus_pos / vbus_neg =====
w(r_esr_c1, 0, vp_bus, 0, node_name="VBUS_POS")
w(c2, 1, vp_bus, 1, node_name="VBUS_NEG")

# ===== DC bus → VSI =====
w(r_esr_c1, 0, vsi, 0, node_name="VBUS_POS")
w(c2, 1, vsi, 1, node_name="VBUS_NEG")

# ===== VSI → PMSM (3 phases) =====
# Phase A taps a ground-referenced voltage probe on the way to the motor.
w(vsi, 2, vp_motor_a, 0, node_name="MOT_A")
w(vp_motor_a, 0, pmsm, 0, node_name="MOT_A")
w(vsi, 3, pmsm, 1, node_name="MOT_B")
w(vsi, 4, pmsm, 2, node_name="MOT_C")
# PMSM neutral ("N", pin 3) is LEFT FLOATING — isolated star point. No wire
# to ground: the node is referenced through the machine windings to the VSI
# phases and pinned by KCL (sum of phase currents = 0), opening the common-
# mode (zero-sequence) path.

# ===== Scope wires =====
w(vp_bus, 2, scope_bus, 0)
w(vp_motor_a, 1, scope_bus, 1)

# ---------------------------------------------------------------------------
# Simulation settings (pulsim 1.6 compatible)
# ---------------------------------------------------------------------------
# t_stop = 0.22 s lets the FOC speed loop ramp (0.10 s) + overshoot + settle
# to ~1800 rpm. dt = 2 µs resolves the 20 kHz carrier (25 samples/period).
# The FOC switch_fn is plain Python, so the run is tens of seconds of wall.
sim_settings = {
    "tstop": 0.22,
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
    "enable_newton_lm": True,
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
    "name": "19 Doubler Drive — 127 V 1φ Voltage-Doubler Front-End + FOC VSI + PMSM (Embraco VLT403U)",
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
