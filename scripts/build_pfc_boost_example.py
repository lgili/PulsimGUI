#!/usr/bin/env python3
"""Builder for example 38 — standalone CCM boost PFC (dedicated controller).

The textbook universal-input PFC stage, isolated from the motor-drive chain
of examples 16/20: 230 V·rms line → diode bridge → 5 mH boost inductor →
MOSFET + boost diode → 400 V bus (C ∥ R load), closed by the drop-in
PFC_BOOST_CONTROLLER block — VBUS/IL/VAC feedback pins wired to the bus, the
inductor current probe and the rectified line; the PWM pin wired to the boost
MOSFET's gate binds the switch (no hidden inference).

Authoring rules (learned on examples 35–37):
* label stubs sit at the SAME x as the pin they tap (vertical wires only);
* never put a net label on a grounded node.

Run::  PYTHONPATH=src python3 scripts/build_pfc_boost_example.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401 — defuse circular import
from pulsimgui.utils.wire_router import WireRouter

REPO = Path(__file__).resolve().parent.parent
DST = REPO / "examples" / "38_pfc_boost_standalone.pulsim"

V_AC_PK = 325.0        # 230 V rms line
F_LINE = 50.0
L_BOOST = 5e-3         # the controller-default recipe (Kp/Ki tuned for this)
C_BUS = 470e-6
R_LOAD = 400.0         # ≈400 W at 400 V
V_BUS0 = 370.0         # pre-charged near target to shorten the transient

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


def gnd(name, x, y) -> dict:
    return comp("GROUND", name, x, y, {}, [pin(0, "gnd", 0, -20)])


def goto(net, name, x, y) -> dict:
    return comp("GOTO_LABEL", name, x, y, {"net_label": net},
                [pin(0, "NET", -40, 0)])


def from_(net, name, x, y) -> dict:
    return comp("FROM_LABEL", name, x, y, {"net_label": net},
                [pin(0, "NET", 40, 0)])


def main() -> None:
    # AC line → diode bridge (negative DC rail grounded).
    v_ac = comp("VOLTAGE_SOURCE", "V_AC", -980, -60,
                {"waveform": {"type": "sine", "amplitude": V_AC_PK,
                              "frequency": F_LINE, "offset": 0.0,
                              "phase": 0.0}},
                [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    br = comp("SINGLE_PHASE_DIODE_BRIDGE", "BR1", -840, -60, {},
              [pin(0, "AC+", -40, -20), pin(1, "AC-", -40, 20),
               pin(2, "DC+", 40, -20), pin(3, "DC-", 40, 20)])
    wire(v_ac, 0, br, 0)
    wire(v_ac, 1, br, 1)
    g_br = gnd("GND_BR", -800, 20)
    wire(br, 3, g_br, 0)                     # DC− rail = ground
    # rectified-line net name (vertical stub: pin x = -800)
    wire(br, 2, goto("VRECT", "LBL_VRECT", -760, -140), 0)

    # Boost stage: VRECT → L → I-probe → SW node (MOSFET drain + diode).
    lb = comp("INDUCTOR", "L_BOOST", -660, -80,
              {"inductance": L_BOOST, "initial_current": 0.0},
              [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    wire(from_("VRECT", "F_VRECT", -740, -80), 0, lb, 0)
    ip = comp("CURRENT_PROBE", "IP_L", -520, -80, {},
              [pin(0, "1", -30, 0), pin(1, "2", 30, 0), pin(2, "SIG", 0, -20)])
    wire(lb, 1, ip, 0)

    q = comp("MOSFET_N", "Q_BOOST", -380, 0, {},
             [pin(0, "D", 0, -30), pin(1, "G", -30, 0), pin(2, "S", 0, 30)])
    wire(ip, 1, q, 0)                        # SW node at the drain
    g_q = gnd("GND_Q", -380, 90)
    wire(q, 2, g_q, 0)

    d_b = comp("DIODE", "D_BOOST", -280, -80, {},
               [pin(0, "A", -30, 0), pin(1, "K", 30, 0)])
    wire(ip, 1, d_b, 0)                      # SW → boost diode
    wire(d_b, 1, goto("VBUS", "LBL_VBUS", -210, -160), 0)   # pin x = -250

    # 400 V bus: C ∥ R to ground, fed via the VBUS net.
    cb = comp("CAPACITOR", "C_BUS", -60, -80,
              {"capacitance": C_BUS, "initial_voltage": V_BUS0},
              [pin(0, "+", -20, 0), pin(1, "-", 20, 0)])
    wire(from_("VBUS", "F_VBUS1", -160, -80), 0, cb, 0)
    g_cb = gnd("GND_CB", -20, 0)
    wire(cb, 1, g_cb, 0)
    rl = comp("RESISTOR", "R_LOAD", 100, -80, {"resistance": R_LOAD},
              [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    wire(from_("VBUS", "F_VBUS2", 0, -120), 0, rl, 0)
    g_rl = gnd("GND_RL", 160, -20)
    wire(rl, 1, g_rl, 0)

    # Feedback probes: bus voltage + rectified line voltage.
    vp_bus = comp("VOLTAGE_PROBE_GND", "VP_BUS", -60, -200, {},
                  [pin(0, "IN", 0, 20)])
    wire(vp_bus, 0, from_("VBUS", "F_VBUS3", -100, -180), 0)
    vp_ac = comp("VOLTAGE_PROBE_GND", "VP_VAC", -740, -220, {},
                 [pin(0, "IN", 0, 20)])
    wire(vp_ac, 0, from_("VRECT", "F_VRECT2", -780, -200), 0)

    # The drop-in controller: VBUS/IL/VAC feedback in, PWM out → gate.
    pfc = comp("PFC_BOOST_CONTROLLER", "PFC1", -560, 200,
               {"mode": "CCM", "v_bus_ref": 400.0, "f_sw": 65000.0,
                "voltage_kp": 0.30, "voltage_ki": 6.0,
                "current_kp": 0.4, "current_ki": 1200.0},
               [pin(0, "VBUS", -40, -20), pin(1, "IL", -40, 0),
                pin(2, "VAC", -40, 20), pin(3, "PWM", 40, 0)])
    wire(from_("VBUS", "F_VBUS4", -680, 180), 0, pfc, 0)
    wire(ip, 2, pfc, 1)                      # IL ← current-probe SIG
    wire(from_("VRECT", "F_VRECT3", -680, 220), 0, pfc, 2)
    wire(pfc, 3, q, 1)                       # PWM → MOSFET gate

    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0", "name": "38 PFC Boost (standalone, CCM)",
        "created": now, "modified": now,
        "description": (
            "Universal-input boost PFC isolated from the drive chain: 230 V "
            "rms line → bridge → 5 mH boost → 400 V bus (470 µF ∥ 400 Ω), "
            "closed by the PFC_BOOST_CONTROLLER block (65 kHz CCM, cascaded "
            "voltage/current loops shaping the line current to |sin|)."),
        "active_circuit": "main",
        "circuits": {"main": {"name": "main", "components": components,
                              "wires": wires, "subcircuits": []}},
        "simulation_settings": {"tstop": 80e-3, "dt": 1e-6,
                                "output_points": 16000, "engine": "pwl"},
    }
    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {len(components)} components, {len(wires)} wires")


if __name__ == "__main__":
    main()
