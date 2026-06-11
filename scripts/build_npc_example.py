#!/usr/bin/env python3
"""Builder for example 37 — NPC three-level inverter leg (diode-clamped).

Split DC bus (±200 V around the neutral), one phase leg of four series
switches with the two clamp diodes to the neutral, RL load. Staircase
(line-frequency square-wave) modulation through per-switch PWMs:

    state +V/2 : S1+S2     [T/8 , 3T/8]
    state  0   : S2+S3     (around the zero crossings, clamped by D1/D2)
    state −V/2 : S3+S4     [5T/8, 7T/8]

so the output steps through the classic three levels +200 / 0 / −200 V.
PWM phase is in radians: S1(d=0.25, π/4), S2(d=0.75, 7π/4),
S3(d=0.75, 3π/4), S4(d=0.25, 5π/4) — S2/S3 are the complements of S4/S1.

Run::  PYTHONPATH=src python3 scripts/build_npc_example.py
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401 — defuse circular import
from pulsimgui.utils.wire_router import WireRouter

REPO = Path(__file__).resolve().parent.parent
DST = REPO / "examples" / "37_npc_three_level.pulsim"

V_HALF = 200.0          # each half of the split bus [V]
F_LINE = 50.0           # staircase fundamental [Hz]
R_LOAD = 10.0
L_LOAD = 10e-3
V_GATE = 15.0

components: list[dict] = []
wires: list[dict] = []
_router = WireRouter()


def uid() -> str:
    return str(uuid.uuid4())


def comp(type_, name, x, y, parameters, pins) -> dict:
    c = {"id": uid(), "type": type_, "name": name, "x": float(x), "y": float(y),
         "rotation": 0, "mirrored_h": False, "mirrored_v": False,
         "parameters": parameters, "pins": pins}
    components.append(c)
    return c


def pin(index, name, x, y) -> dict:
    return {"index": index, "name": name, "x": float(x), "y": float(y)}


def wire(ca, a_pin, cb, b_pin) -> None:
    ax = ca["x"] + next(p["x"] for p in ca["pins"] if p["index"] == a_pin)
    ay = ca["y"] + next(p["y"] for p in ca["pins"] if p["index"] == a_pin)
    bx = cb["x"] + next(p["x"] for p in cb["pins"] if p["index"] == b_pin)
    by = cb["y"] + next(p["y"] for p in cb["pins"] if p["index"] == b_pin)
    segs = [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}
            for (x1, y1, x2, y2) in _router.route(ax, ay, bx, by)]
    wires.append({"id": uid(), "segments": segs,
                  "start_connection": {"component_id": ca["id"], "pin_index": a_pin},
                  "end_connection": {"component_id": cb["id"], "pin_index": b_pin},
                  "junctions": [], "node_name": "", "alias": ""})


def switch(name, x, y) -> dict:
    return comp("SWITCH", name, x, y,
                {"v_threshold": 2.5, "ron": 1e-3, "roff": 1e9},
                [pin(0, "1", -20, 0), pin(1, "2", 20, 0),
                 pin(2, "CTL", 0, -20)])


def pwm(name, x, y, duty, phase, target) -> dict:
    return comp("PWM_GENERATOR", name, x, y,
                {"frequency": F_LINE, "duty_cycle": duty, "duty": duty,
                 "amplitude": V_GATE, "carrier": "sawtooth", "phase": phase,
                 "sample_time": 0.0, "target_component": target},
                [pin(0, "OUT", 40, 0)])


def diode(name, x, y) -> dict:
    return comp("DIODE", name, x, y, {},
                [pin(0, "A", -30, 0), pin(1, "K", 30, 0)])


def gnd(name, x, y) -> dict:
    return comp("GROUND", name, x, y, {}, [pin(0, "gnd", 0, -20)])


def goto(net, name, x, y) -> dict:
    return comp("GOTO_LABEL", name, x, y, {"net_label": net},
                [pin(0, "NET", -40, 0)])


def from_(net, name, x, y) -> dict:
    return comp("FROM_LABEL", name, x, y, {"net_label": net},
                [pin(0, "NET", 40, 0)])


def main() -> None:
    # Split DC bus: +200 V and −200 V around the grounded neutral. Long nets
    # (DC+/DC−) are distributed via GOTO/FROM labels with SHORT local wires —
    # long wires crossing the switch chain overlap its colinear segments and
    # build_node_map would merge the touching nets into one node.
    v_pos = comp("VOLTAGE_SOURCE", "V_POS", -980, -200,
                 {"waveform": {"type": "dc", "value": V_HALF}},
                 [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    v_neg = comp("VOLTAGE_SOURCE", "V_NEG", -980, 0,
                 {"waveform": {"type": "dc", "value": V_HALF}},
                 [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    g_mid = gnd("GND_MID", -900, -60)
    wire(v_pos, 1, g_mid, 0)                 # neutral = ground
    wire(v_neg, 0, g_mid, 0)
    # Label stubs sit at the SAME x as the pin they tap, so their wire is a
    # single vertical segment — an angled stub would route its horizontal
    # portion along the component row and overlap neighbouring wires (the
    # node map merges touching segments).
    wire(v_pos, 0, goto("DCP", "LBL_DCP", -940, -260), 0)   # pin x = -980
    wire(v_neg, 1, goto("DCN", "LBL_DCN", -940, 80), 0)     # pin x = -980

    # The leg: DC+ → S1 → S2 → out → S3 → S4 → DC−, a horizontal chain with
    # only SHORT pin-to-pin wires. Clamp junctions drop to a lower row.
    gating = (("S1", 0.25, math.pi / 4), ("S2", 0.75, 7 * math.pi / 4),
              ("S3", 0.75, 3 * math.pi / 4), ("S4", 0.25, 5 * math.pi / 4))
    sw = []
    for k, (name, duty, phase) in enumerate(gating):
        s = switch(name, -620 + 170 * k, -160)
        sw.append(s)
        pg = pwm(f"PWM_{name}", -680 + 170 * k, -260, duty, phase, name)
        wire(pg, 0, s, 2)
    wire(from_("DCP", "F_DCP", -740, -160), 0, sw[0], 0)   # DC+ → S1
    wire(sw[0], 1, sw[1], 0)                 # j12
    wire(sw[1], 1, sw[2], 0)                 # output node
    wire(sw[2], 1, sw[3], 0)                 # j34
    wire(sw[3], 1, from_("DCN", "F_DCN", -10, -160), 0)    # S4 → DC−

    # Clamp diodes on their own row, tied by labels (no long crossing wires):
    # D1: neutral→j12, D2: j34→neutral. j12/j34 named via VERTICAL stubs
    # (label pin x = junction pin x).
    wire(sw[0], 1, goto("J12", "LBL_J12", -560, -100), 0)   # pin x = -600
    wire(sw[2], 1, goto("J34", "LBL_J34", -220, -100), 0)   # pin x = -260
    # The neutral is GROUND — tie the clamp ends to local GROUND symbols
    # directly. (Do NOT put a net label on a grounded node: the alias takes
    # over the node name and it stops being identified as the kernel ground.)
    d1 = diode("D1", -560, 60)
    g_d1 = gnd("GND_D1", -560 - 30, 140)     # below D1's anode (x = -590)
    wire(g_d1, 0, d1, 0)                     # anode at neutral (ground)
    wire(d1, 1, from_("J12", "F_J12", -480, 60), 0)        # cathode at j12
    d2 = diode("D2", -300, 60)
    g_d2 = gnd("GND_D2", -300 + 30, 140)     # below D2's cathode (x = -270)
    wire(from_("J34", "F_J34", -390, 60), 0, d2, 0)        # anode at j34
    wire(d2, 1, g_d2, 0)                     # cathode at neutral (ground)

    # RL load from the output to ground (= neutral) + a stable net name. The
    # VOUT stub drops VERTICALLY from S2's right pin (same x = -430).
    wire(sw[1], 1, goto("VOUT", "LBL_VOUT", -390, -220), 0)  # pin x = -430
    rl = comp("RESISTOR", "R_LOAD", 160, -200, {"resistance": R_LOAD},
              [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    ll = comp("INDUCTOR", "L_LOAD", 320, -200,
              {"inductance": L_LOAD, "initial_current": 0.0},
              [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    g_load = gnd("GND_LOAD", 420, -140)
    wire(from_("VOUT", "F_VOUT", 20, -200), 0, rl, 0)      # short, own row
    wire(rl, 1, ll, 0)
    wire(ll, 1, g_load, 0)
    vp = comp("VOLTAGE_PROBE_GND", "VP_out", 160, -320, {},
              [pin(0, "IN", 0, 20)])
    wire(vp, 0, from_("VOUT", "F_VOUT2", 120, -300), 0)    # pin x = 160

    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0", "name": "37 NPC Three-Level Inverter Leg",
        "created": now, "modified": now,
        "description": (
            "Diode-clamped (NPC) three-level leg on a ±200 V split bus with "
            "staircase line-frequency modulation: the output steps through "
            "+200 / 0 / −200 V (zero state clamped to the neutral through "
            "D1/D2), driving an RL load."),
        "active_circuit": "main",
        "circuits": {"main": {"name": "main", "components": components,
                              "wires": wires, "subcircuits": []}},
        "simulation_settings": {"tstop": 60e-3, "dt": 2e-6,
                                "output_points": 12000, "engine": "pwl"},
    }
    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {len(components)} components, {len(wires)} wires")


if __name__ == "__main__":
    main()
