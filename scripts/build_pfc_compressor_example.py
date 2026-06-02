#!/usr/bin/env python3
"""Builder for example 20 — Active-PFC Compressor Drive (220 V).

Run from the repo root::

    PYTHONPATH=src .venv/bin/python scripts/build_pfc_compressor_example.py

Regenerates ``examples/20_pfc_drive_compressor.pulsim`` deterministically
(stable component IDs -> clean diffs across runs).

This is a *genuine active-PFC* compressor drive: it has TWO independently
PWM'd switching stages composed into one simulation — an OPEN-LOOP boost
PFC pre-regulator AND a Field-Oriented-Control (FOC) inverter —

    Vac (1phi, 311 V peak ~ 220 Vrms, 60 Hz)
        -> source R/L
        -> 1phi Diode Bridge (Graetz)              [v_rect_pos / v_rect_neg]
        -> BOOST PFC PRE-REGULATOR (switched, OPEN-LOOP):
              R_Lboost (0.10 ohm) + L_boost (5 mH)  v_rect_pos -> n_sw_boost
              D_boost  (0.7 V)                       n_sw_boost -> vbus_pos
              Q_boost  (MOSFET_N, R_on 50 mohm)      n_sw_boost -> vbus_neg
              SNUB_boost (RC, 100 ohm / 100 nF)      n_sw_boost -> vbus_neg
           Q_boost gate is driven OPEN-LOOP by PWM_BOOST (PWM_GENERATOR,
           65 kHz, fixed duty ~0.23 -> 311 V mains lifted to ~400 V bus).
           No PI / no SUBTRACTOR -> the converter emits NO ``closed_loops``
           descriptor; the boost PWM mask composes with the FOC VSI
           switch_fn (disjoint switch bits) without tripping the
           ``closed_loops`` + ``switch_fn`` conflict pulsim >=1.4 rejects.
        -> DC bus: two SERIES caps (470 uF, 20 mohm ESR), pre-charged
           ~155 V each (~310 V bus ~ rectified-AC peak), midpoint pinned
           to the rectifier return (ground) through R_mid_tap = 1 mohm for
           a stable split-bus reference the VSI + PMSM observer want.
        -> R_busload across the bus: the load line for the OPEN-LOOP boost
           (see below) — sets the operating point near ~400 V.
        -> 3phi 2-level VSI (six ideal switches)
        -> PMSM (dynamic, Embraco VLT403U), neutral FLOATING (isolated
           star point — breaks the common-mode path the bus ripple would
           otherwise drive through a grounded neutral)
        + FOC controller (a C_BLOCK marker, control_kind="foc")

WHY FOC instead of open-loop V/f
--------------------------------
Open-loop V/f pole-slips a PMSM (imposed stator angle vs true rotor angle
drift apart, the motor never locks, phase current runs to 17-29 A of
garbage on a ~1.6 A motor). Closing the i_d (=0) / i_q current loops + an
outer speed PI lets the rotor track a speed reference at rated current.
The FOC is a pure C_BLOCK *marker* (control_kind="foc", no pins, NOT wired
into the power stage): the converter detects it (``_infer_foc_loops``) and
the backend (``_build_foc_loops``) closes the loops over the PMSM observer
and drives the VSI's six switches via inverse Park/Clarke, REPLACING the
VSI's open-loop SPWM. The VSI's SPWM params below are inert.

TWO switched stages compose
---------------------------
The boost MOSFET (65 kHz, open-loop fixed-duty PWM) and the FOC-commanded
VSI (20 kHz) run at different carrier frequencies and drive DISJOINT switch
bits — the boost PWM mask + the FOC switch_fn are OR'd together through the
Python ``make_combined_switch_fn`` path (a single native
``NativeMultiMaskPwm`` only models one period). The FOC switch_fn replaces
the SPWM on the VSI's six bits (the converter excludes the FOC-controlled
VSI from ``_build_vsi_switch_fns``), while the boost PWM keeps its own bit.

Bus operating point (R_busload) + v_bus
---------------------------------------
The open-loop fixed-duty boost has NO output-voltage regulation. Under the
FOC's light, correct ~100 W draw (vs the old open-loop V/f's KILOWATTS of
pole-slip garbage) the L_boost/D_boost peak-charge pump runs the bus high
with nothing to push against (the boost diode peak-charges the caps almost
independent of MOSFET duty, so the duty is NOT a usable bus knob here).
``R_busload`` is the only effective lever: it restores a defined load line
— it stands in for the heavy downstream draw the broken drive used to
impose — placing the bus near ~390 V (24 Ω; see the ``R_BUSLOAD`` note for
the sweep and why the value dropped from 68 Ω when the motor neutral was
floated). The FOC normalises modulation + clamps v_d/v_q by the descriptor
``v_bus`` (the backend can't infer the live, rippling bus), set to ~400 V;
a slightly-off value is fine — the inner current PI compensates.

ENGINE: ``pwl`` + ``enable_newton_lm=True`` (+ the RC snubber above).
The DSED event-driven scheduler (pulsim 1.6) was tried FIRST -- it is the
persisted, GUI-honored fast path for SMPS -- but it does NOT converge on
THIS two-hard-switched-stage drive: composing the 65 kHz boost MOSFET with
the 20 kHz VSI collapses the bus / motor nodes to NaN under DSED (verified
through the real Run path). The fixed-step PWL engine converges, but the
boost commutation drives Newton into a switch-state limit-cycle stall
(``||dx||_inf`` ~ 1e-14 yet the iteration never clears) that NEITHER
``enable_newton_lm`` alone NOR a tolerance tweak alone breaks. The RC
snubber across the boost MOSFET adds a damped state at the switching node;
with that present, ``enable_newton_lm=True`` clears the residual and the
whole drive converges (~2.7 s for 40 ms).

``enable_newton_lm`` was previously NOT persisted in the .pulsim (it came
only from app preferences); this example required wiring it through the
file schema (``models.project.SimulationSettings``) and the
project->runtime bridges (``SimulationService.apply_project_simulation_
settings`` + ``MainWindow._apply_project_simulation_settings_to_service``)
so a fresh GUI Run honors it straight from the project file.

Two more enabling fixes in ``pulsim_v0_compat`` were needed for the boost
MOSFET to actually switch (they are general bug fixes, not example-only):
  * ``_next_switch_idx`` returned ``len(pending_gate_signals)`` -- which
    ignores diodes / the diode bridge that consume builder switch bits, so
    the boost MOSFET was handed switch bit 0 (a *bridge diode*) and never
    toggled. It now reads the builder-global ``graph.num_switches``.
  * ``gate_node_indices`` keyed only on the symbolic gate name, but the
    virtual PWM record stores its output as an integer node id, so
    ``configs_from_pwm_records`` couldn't match the boost gate. It now
    exposes both the symbolic name and the integer id.
  * (Also fixed ``add_snubber_rc`` to call pulsim 1.6's keyword-only
    ``add_rc_snubber``; the old positional call raised TypeError.)

The boost MOSFET (65 kHz) and VSI (20 kHz) run at different carrier
frequencies, so the switch_fn assembler composes them through the Python
``make_combined_switch_fn`` path (disjoint switch bits OR'd together).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401  -- defuse circular import
from pulsimgui.utils.wire_router import WireRouter

REPO = Path("/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGUI")
OUT_PATH = REPO / "examples" / "20_pfc_drive_compressor.pulsim"

_NS = uuid.UUID("20000000-0fc0-1e72-d21e-000000000000")

FSW = 20000.0     # inverter switching frequency [Hz]
# Nominal DC bus the FOC uses to normalise modulation + clamp v_d/v_q.
# The active boost lifts the ~310 V pre-charge toward ~400 V under FOC
# load; ~400 V is the boosted operating point.
VBUS_FOC = 400.0
# Bus load resistor [ohm]. The open-loop fixed-duty boost has NO output-
# voltage regulation, so its DC-bus operating point is set purely by the
# input-power vs load-power balance. The FOC motor draws only ~100 W
# (1800 rpm × 0.30 N·m mech ≈ 56 W + losses) — far too light to hold the
# bus down: the 220 Vrms doubler-style front-end (grounded mid-tap) plus
# the L_boost/D_boost peak-charge pump integrate the bus high under that
# light draw. Crucially the peak-charge pump is ACTIVE essentially
# independent of MOSFET duty — a build-time GUI sweep at the floating-
# neutral operating point showed duty 0.23 → 0.10 barely moves the bus
# (527 → 496 V mean at R=68 Ω): the boost DIODE conducts the inductor's
# rectified-peak energy into the caps regardless of the gate, so the gate
# duty is NOT a usable bus-control knob here. R_busload is therefore the
# ONLY effective lever on the bus operating point: it restores the load
# line the heavy downstream draw would impose. It models the compressor's
# rated electrical load that the efficient, no-slip FOC does not itself
# draw on an unloaded shaft (a literal bleed of this size dissipates ~kW —
# it stands in for the load, it is not a real bleed resistor).
#
# RE-SIZED FOR THE FLOATING NEUTRAL (see the PMSM wiring below). The motor
# neutral was previously GROUNDED. The 120 Hz bus ripple then drove a
# common-mode (zero-sequence) current through the phases that cancelled in
# d-q (i_d≈0, i_q≈1.3 A rated, rotor locked: torque control was always
# correct) but inflated the abc phase PEAK to ~11-13 A (RMS ~5.5 A) — and
# that CM current was itself a heavy (~0.4 kW I²R) load that helped pin the
# bus near ~375 V at R=68 Ω. FLOATING the neutral (isolated star point, as
# a real PMSM compressor has) opens the zero-sequence path: the phase peak
# collapses to the true ~2 A motor current (~3.2 A incl. switching ripple),
# but it ALSO removes that CM load, so the same R=68 Ω now lets the bus
# climb to ~527 V (out of the 360-410 band). R_busload is dropped to 24 Ω
# to re-impose the load line the CM current used to provide, landing the
# bus mean back at ~390 V (build-time GUI sweep, floating neutral: R=24 →
# 390 V, R=28 → 410 V, R=68 → 527 V; settled bus mean over the last 25 %
# of a 0.22 s run). The phase peak stays ~3.2-3.5 A across that whole sweep
# (the fix is robust to the load value). Trade-off (inherent to an open-
# loop boost feeding a floating-neutral motor at light shaft load): the
# heavier load widens the 120 Hz + 65 kHz bus ripple (p5-p95 ≈ 216-571 V);
# a real drive would close a boost voltage loop instead, but this example
# keeps the boost open-loop (no PI → no ``closed_loops`` descriptor, so the
# boost PWM mask composes with the FOC switch_fn — see the module docstring).
R_BUSLOAD = 24.0


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
#   y = -300   boost-gate drive row (PWM_BOOST -> GOTO label)
#   y =    0   power row (Vac -> R_src -> L_src -> BR1 -> boost -> caps -> VSI -> PMSM)
#   y = +120   grounds / split-bus reference tap
#   y = +20    boost MOSFET + its FROM-gate label
#   y = -180   scopes far right

# ------------------ AC mains + line impedance ------------------
v_ac = comp(
    type="VOLTAGE_SOURCE", name="Vac", x=-1480, y=0,
    parameters={
        "waveform": {
            "type": "sine",
            "amplitude": 311.0,    # 220 Vrms * sqrt(2)
            "frequency": 60.0,
            "offset": 0.0,
            "phase": 0.0,
        },
    },
    pins=[pin(0, "+", -25, 0), pin(1, "-", 25, 0)],
)
components.append(v_ac)

gnd_ac = comp(
    type="GROUND", name="GND_ac", x=-1420, y=120,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_ac)

r_src = comp(
    type="RESISTOR", name="R_src", x=-1320, y=0,
    parameters={"resistance": 0.5},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_src)

l_src = comp(
    type="INDUCTOR", name="L_src", x=-1180, y=0,
    parameters={"inductance": 200e-6, "initial_current": 0.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(l_src)

# ------------------ 1phi diode bridge ------------------
br1 = comp(
    type="SINGLE_PHASE_DIODE_BRIDGE", name="BR1", x=-980, y=0,
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

# ------------------ BOOST PFC pre-regulator (switched) ------------------
# v_rect_pos -> R_Lboost -> L_boost -> n_sw_boost
#   n_sw_boost -> D_boost -> vbus_pos
#   n_sw_boost -> Q_boost -> vbus_neg   (gate = PWM_BOOST, 65 kHz fixed duty)
r_lboost = comp(
    type="RESISTOR", name="R_Lboost", x=-760, y=-20,
    parameters={"resistance": 0.10},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_lboost)

l_boost = comp(
    type="INDUCTOR", name="L_boost", x=-600, y=-20,
    parameters={"inductance": 5.0e-3, "initial_current": 0.0},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(l_boost)

d_boost = comp(
    type="DIODE", name="D_boost", x=-420, y=-20,
    parameters={"g_on": 1.0e3, "g_off": 1.0e-9, "v_forward": 0.7},
    pins=[pin(0, "A", -25, 0), pin(1, "K", 25, 0)],
)
components.append(d_boost)

# Boost MOSFET: drain = n_sw_boost (top), source = vbus_neg (bottom),
# gate driven by PWM_BOOST via a FROM label. MOSFET pins [D, G, S].
q_boost = comp(
    type="MOSFET_N", name="Q_boost", x=-440, y=120,
    parameters={
        "is_nmos": True,
        "R_on": 50e-3,
        "R_off": 1.0e9,
        "v_th": 3.0,
    },
    pins=[pin(0, "D", 0, -25), pin(1, "G", -25, 0), pin(2, "S", 0, 25)],
)
components.append(q_boost)

# RC turn-off snubber across the boost MOSFET (n_sw_boost -> vbus_neg).
# Physically this damps the L_boost/D_boost commutation overshoot; in the
# fixed-step PWL solve it is also what lets the composed two-switch-stage
# (65 kHz boost + 20 kHz VSI) Newton iteration converge. Without it the
# boost-node commutation drives Newton into a limit-cycle stall that even
# LM damping can't break; an RC snubber adds a damped state at the node
# and dissipates only during transitions (negligible steady-state loss,
# unlike a bare bleed resistor). 100 ohm / 100 nF -> tau = 10 us.
snub_boost = comp(
    type="SNUBBER_RC", name="SNUB_boost", x=-300, y=120,
    parameters={"resistance": 100.0, "capacitance": 100e-9},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(snub_boost)

# ------------------ DC bus: two series caps with ESR ------------------
# vbus_pos -> R_ESR_C1 -> n_C1_top -> C1 -> vbus_mid -> R_ESR_C2 ->
#   n_C2_top -> C2 -> vbus_neg.  Pre-charged ~155 V each (~310 V bus,
# roughly the rectified-AC peak) so the active boost visibly PUMPS the bus
# UP from there toward its ~400 V operating point over the run. Boost
# MOSFET chops L_boost current into this string.
r_esr_c1 = comp(
    type="RESISTOR", name="R_ESR_C1", x=-220, y=-40,
    parameters={"resistance": 20e-3},
    pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)],
    rotation=90,
)
components.append(r_esr_c1)

c1 = comp(
    type="CAPACITOR", name="C1", x=-220, y=80,
    parameters={"capacitance": 470e-6, "initial_voltage": 155.0},
    pins=[pin(0, "+", 0, -25), pin(1, "-", 0, 25)],
    rotation=90,
)
components.append(c1)

r_esr_c2 = comp(
    type="RESISTOR", name="R_ESR_C2", x=-220, y=200,
    parameters={"resistance": 20e-3},
    pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)],
    rotation=90,
)
components.append(r_esr_c2)

c2 = comp(
    type="CAPACITOR", name="C2", x=-220, y=320,
    parameters={"capacitance": 470e-6, "initial_voltage": 155.0},
    pins=[pin(0, "+", 0, -25), pin(1, "-", 0, 25)],
    rotation=90,
)
components.append(c2)

# ------------------ Split-bus midpoint reference tap ------------------
# 1 mohm from the cap midpoint (vbus_mid) to the rectifier return
# (ground "0"). Pins the split-bus center for a well-conditioned
# reference the native switched VSI + PMSM observer want.
r_mid_tap = comp(
    type="RESISTOR", name="R_mid_tap", x=-60, y=160,
    parameters={"resistance": 1e-3},
    pins=[pin(0, "1", -25, 0), pin(1, "2", 25, 0)],
)
components.append(r_mid_tap)

gnd_mid = comp(
    type="GROUND", name="GND_mid", x=100, y=200,
    parameters={},
    pins=[pin(0, "gnd", 0, -20)],
)
components.append(gnd_mid)

# ------------------ Voltage probe: V_bus ------------------
vp_bus = comp(
    type="VOLTAGE_PROBE", name="V_bus", x=180, y=0,
    parameters={"display_name": "V_bus", "scale": 1.0},
    pins=[
        pin(0, "+", 0, -20),
        pin(1, "-", 0, 20),
        pin(2, "OUT", 25, 0),
    ],
)
components.append(vp_bus)

# ------------------ Bus load resistor (load line for the open-loop boost) -
# vbus_pos -> R_busload -> vbus_neg. WITHOUT a defined load the open-loop
# fixed-duty boost has no output-voltage operating point and the bus
# integrates up past ~900 V under the light FOC draw. R_busload sets the
# load line so the bus settles near ~400 V at the 0.23 duty (see the
# module-level note on R_BUSLOAD).
r_busload = comp(
    type="RESISTOR", name="R_busload", x=120, y=360,
    parameters={"resistance": R_BUSLOAD},
    pins=[pin(0, "1", 0, -25), pin(1, "2", 0, 25)],
    rotation=90,
)
components.append(r_busload)

# ------------------ Boost-gate PWM (open-loop, fixed duty) ------------------
# 65 kHz, ~0.23 duty.  ``target_component`` set so the converter routes
# the gate drive through the virtual-PWM -> switch_fn path (NOT a closed
# loop -- there is no PI/SUBTRACTOR).  Its OUT pin drives the Q_boost
# gate net via a GOTO/FROM label pair.
pwm_boost = comp(
    type="PWM_GENERATOR", name="PWM_BOOST", x=-700, y=-300,
    parameters={
        "frequency": 65e3,
        "duty_cycle": 0.23,
        "carrier": "sawtooth",
        "amplitude": 12.0,
        "phase": 0.0,
        "sample_time": 0.0,
        "enable_duty_input": False,
        "target_component": "Q_boost",
    },
    pins=[pin(0, "OUT", 30, 0), pin(1, "DUTY_IN", -30, 0)],
)
components.append(pwm_boost)

goto_gate = comp(
    type="GOTO_LABEL", name="Xgate_out", x=-540, y=-300,
    parameters={"net_label": "Q_BOOST_GATE"},
    pins=[pin(0, "NET", -25, 0)],
)
components.append(goto_gate)

from_gate = comp(
    type="FROM_LABEL", name="Xgate_in", x=-540, y=120,
    parameters={"net_label": "Q_BOOST_GATE"},
    pins=[pin(0, "NET", 25, 0)],
)
components.append(from_gate)

# ------------------ 3phi VSI ------------------
# The SPWM drive params below are inert — the FOC controller commands the
# six switches via inverse Park/Clarke and the converter excludes a FOC-
# controlled VSI from the open-loop SPWM path. The boost MOSFET keeps its
# own open-loop PWM bit; the two switched stages compose (disjoint bits).
vsi = comp(
    type="THREE_PHASE_VSI", name="VSI", x=400, y=0,
    parameters={
        "switching_frequency_hz": FSW,
        "modulation_index": 0.8,
        "modulation_frequency_hz": 90.0,   # ~1800 rpm x 3 pole pairs
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
    type="VOLTAGE_PROBE_GND", name="V_motor_A", x=580, y=-140,
    parameters={"display_name": "V(A)", "scale": 1.0},
    pins=[pin(0, "IN", -25, 0), pin(1, "OUT", 25, 0)],
)
components.append(vp_motor_a)

# ------------------ PMSM (Embraco VLT403U) ------------------
pmsm = comp(
    type="PMSM", name="M1", x=660, y=0,
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
# VSI phases, and its potential is fixed by KCL (i_a + i_b + i_c = 0). This
# breaks the common-mode (zero-sequence) path that the 120 Hz bus ripple
# would otherwise drive through a grounded neutral, so the abc phase peak
# collapses to the true ~2 A motor current (vs ~11-13 A with the neutral
# grounded). No ``GND_motor`` component exists.

# ------------------ FOC controller (C_BLOCK marker) ------------------
# control_kind="foc" → the converter emits a foc_loop_descriptor binding
# this marker to the VSI (commanded) + the PMSM (observed). It carries no
# pins and is NOT wired into the power stage; the backend reads the loop
# gains / speed-reference ramp / limits / v_bus below and closes the loops
# at simulate time, driving the VSI's six switches (replacing its open-loop
# SPWM). The boost MOSFET keeps its own open-loop 65 kHz PWM bit — the two
# switched stages compose (disjoint switch bits OR'd together). Gains match
# the validated VLT403U FOC recipe (example 21).
foc = comp(
    type="C_BLOCK", name="FOC", x=660, y=-220,
    parameters={
        "control_kind": "foc",
        "vsi_name": "VSI",
        "pmsm_name": "M1",
        # Nominal DC bus for modulation normalisation / voltage clamp
        # (the active boost lifts the bus to ~400 V under FOC load).
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
    type="ELECTRICAL_SCOPE", name="Scope_Bus", x=940, y=-180,
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


# ===== AC line: Vac -> R_src -> L_src -> BR1.AC+ =====
w(v_ac, 0, r_src, 0, node_name="VAC_P")
w(r_src, 1, l_src, 0, node_name="N_RSRC")
w(l_src, 1, br1, 0, node_name="AC_L")
# AC return: Vac- -> ground; BR1.AC- -> ground (node "0")
w(v_ac, 1, gnd_ac, 0, node_name="0")
w(v_ac, 1, br1, 1, node_name="0")

# ===== Boost: BR1.DC+ -> R_Lboost -> L_boost -> n_sw_boost =====
w(br1, 2, r_lboost, 0, node_name="V_RECT_POS")
w(r_lboost, 1, l_boost, 0, node_name="N_RLBOOST")
w(l_boost, 1, d_boost, 0, node_name="N_SW_BOOST")
w(l_boost, 1, q_boost, 0, node_name="N_SW_BOOST")
# Boost diode K -> vbus_pos ; Q_boost source -> vbus_neg
w(d_boost, 1, r_esr_c1, 0, node_name="VBUS_POS")
w(q_boost, 2, c2, 1, node_name="VBUS_NEG")
# BR1.DC- ties to vbus_neg (rectifier return rail)
w(br1, 3, c2, 1, node_name="VBUS_NEG")
# RC snubber across the boost MOSFET: n_sw_boost -> SNUB -> vbus_neg
w(q_boost, 0, snub_boost, 0, node_name="N_SW_BOOST")
w(snub_boost, 1, c2, 1, node_name="VBUS_NEG")

# ===== Boost-gate drive: PWM_BOOST.OUT -> GOTO -> (label) -> FROM -> Q_boost.G
w(pwm_boost, 0, goto_gate, 0, node_name="Q_BOOST_GATE")
w(from_gate, 0, q_boost, 1, node_name="Q_BOOST_GATE")

# ===== DC bus series-cap string =====
# vbus_pos -> R_ESR_C1 -> n_C1_top -> C1 -> vbus_mid
w(r_esr_c1, 1, c1, 0, node_name="N_C1_TOP")
w(c1, 1, r_esr_c2, 0, node_name="VBUS_MID")
# vbus_mid -> R_ESR_C2 -> n_C2_top -> C2 -> vbus_neg
w(r_esr_c2, 1, c2, 0, node_name="N_C2_TOP")

# ===== Split-bus midpoint reference tap: vbus_mid -> R_mid_tap -> ground "0"
w(c1, 1, r_mid_tap, 0, node_name="VBUS_MID")
w(r_mid_tap, 1, gnd_mid, 0, node_name="0")

# ===== V_bus probe across vbus_pos / vbus_neg =====
w(r_esr_c1, 0, vp_bus, 0, node_name="VBUS_POS")
w(c2, 1, vp_bus, 1, node_name="VBUS_NEG")

# ===== Bus load resistor across vbus_pos / vbus_neg =====
w(r_esr_c1, 0, r_busload, 0, node_name="VBUS_POS")
w(r_busload, 1, c2, 1, node_name="VBUS_NEG")

# ===== DC bus -> VSI =====
w(r_esr_c1, 0, vsi, 0, node_name="VBUS_POS")
w(c2, 1, vsi, 1, node_name="VBUS_NEG")

# ===== VSI -> PMSM (3 phases) =====
w(vsi, 2, vp_motor_a, 0, node_name="MOT_A")
w(vp_motor_a, 0, pmsm, 0, node_name="MOT_A")
w(vsi, 3, pmsm, 1, node_name="MOT_B")
w(vsi, 4, pmsm, 2, node_name="MOT_C")
# PMSM neutral ("N", pin 3) is LEFT FLOATING — isolated star point. No wire
# to ground: the node is referenced through the machine windings to the VSI
# phases and pinned by KCL (sum of phase currents = 0). This breaks the
# common-mode path the bus ripple would drive through a grounded neutral.

# ===== Scope wires =====
w(vp_bus, 2, scope_bus, 0)
w(vp_motor_a, 1, scope_bus, 1)

# ---------------------------------------------------------------------------
# Simulation settings (pulsim 1.6, PWL engine + Newton LM)
# ---------------------------------------------------------------------------
# t_stop = 0.22 s lets the FOC speed loop ramp (0.10 s) + overshoot + settle
# to ~1800 rpm while the boost pumps the bus toward ~400 V. dt = 2 µs
# resolves the 20 kHz VSI carrier (25 samples/period); the 65 kHz boost is
# coarser (~7.7 samples/period) but it only pumps the bus, and the RC
# snubber damps its commutation. The FOC switch_fn is plain Python so the
# run is tens of seconds of wall.
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
    # ENGINE = PWL (fixed-step trapezoidal + PWL cache). The DSED event-
    # driven scheduler was tried first (it is the persisted, GUI-honored
    # default for fast SMPS) but it does NOT converge on THIS two-hard-
    # switched-stage drive: with the 65 kHz boost MOSFET composed with the
    # 20 kHz VSI it collapses the bus/motor nodes to NaN (verified through
    # the real Run path). PWL converges once Newton LM damping is enabled
    # (see ``enable_newton_lm`` below) — without LM, Newton stalls at a
    # near-miss (||dx||_inf ~ 1.5e-5, ||residual||_inf ~ 3e-12).
    "engine": "pwl",
    "tol_newton_dx": 1.0e-6,
    "tol_newton_res": 1.0e-6,
    "enable_newton_line_search": True,
    # REQUIRED for this drive: Levenberg-Marquardt damping clears the
    # Newton near-miss the composed boost+VSI switching produces. Now
    # persisted in the file schema (models.project.SimulationSettings) and
    # mirrored onto the runtime by SimulationService /
    # MainWindow._apply_project_simulation_settings_to_service, so a fresh
    # GUI Run honors it from the project file (it used to come only from
    # app preferences).
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
    "name": "20 PFC Drive — 220 V 1φ Rectifier + switched Boost PFC (~400 V bus) + FOC VSI + PMSM (Embraco VLT403U)",
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
