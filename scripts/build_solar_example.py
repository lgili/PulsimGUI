#!/usr/bin/env python3
"""Builder for example 39 — PV panel charging a battery through a boost.

The showcase for the two renewables components added in W3.12: a PV_PANEL
(Isc 8 A, Voc 37 V ≈ 230 W at full irradiance) feeds a boost converter whose
output charges a 48 V BATTERY. A fixed-duty PWM (D≈0.45 at 25 kHz) drives the
low-side MOSFET, so with the stiff battery clamping the output the PV settles
on its current-source region and pushes ~5 A of charging current into the
pack — a clean PV→DC-DC→storage power chain.

Authoring rules (from examples 35-38):
* label stubs sit at the SAME x as the pin they tap (vertical wires only);
* never put a net label on a grounded node.

Run::  PYTHONPATH=src python3 scripts/build_solar_example.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pulsimgui.models  # noqa: F401 — defuse circular import
from pulsimgui.utils.wire_router import WireRouter

REPO = Path(__file__).resolve().parent.parent
DST = REPO / "examples" / "39_solar_pv_battery_charger.pulsim"

ISC, VOC = 8.0, 37.0
F_SW = 25e3
DUTY = 0.45
L_BOOST = 1e-3
C_IN = 220e-6
C_OUT = 470e-6
V_BATT = 48.0
R_INT = 0.08
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


def gnd(name, x, y) -> dict:
    return comp("GROUND", name, x, y, {}, [pin(0, "gnd", 0, -20)])


def goto(net, name, x, y) -> dict:
    return comp("GOTO_LABEL", name, x, y, {"net_label": net},
                [pin(0, "NET", -40, 0)])


def from_(net, name, x, y) -> dict:
    return comp("FROM_LABEL", name, x, y, {"net_label": net},
                [pin(0, "NET", 40, 0)])


def main() -> None:
    # PV source + input capacitor (PVP node, return to ground).
    pv = comp("PV_PANEL", "PV1", -900, -60,
              {"isc": ISC, "voc": VOC, "rs": 0.3, "rsh": 300.0,
               "irradiance": 1.0},
              [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    g_pv = gnd("GND_PV", -900, 60)
    wire(pv, 1, g_pv, 0)
    wire(pv, 0, goto("PVP", "LBL_PVP", -860, -140), 0)     # pin x = -900
    cin = comp("CAPACITOR", "C_IN", -760, -60,
               {"capacitance": C_IN, "initial_voltage": 30.0},
               [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    wire(from_("PVP", "F_PVP1", -840, -80), 0, cin, 0)
    g_cin = gnd("GND_CIN", -760, 60)
    wire(cin, 1, g_cin, 0)

    # Boost: PVP → L → I-probe → SW node (low-side MOSFET + boost diode).
    lb = comp("INDUCTOR", "L_BOOST", -620, -120,
              {"inductance": L_BOOST, "initial_current": 0.0},
              [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    wire(from_("PVP", "F_PVP2", -700, -120), 0, lb, 0)
    ipl = comp("CURRENT_PROBE", "IP_L", -480, -120, {},
               [pin(0, "IN", -20, 0), pin(1, "OUT", 20, 0),
                pin(2, "SIG", 0, -20)])
    wire(lb, 1, ipl, 0)

    q = comp("MOSFET_N", "Q_SW", -340, -40, {},
             [pin(0, "D", 0, -30), pin(1, "G", -30, 0), pin(2, "S", 0, 30)])
    wire(ipl, 1, q, 0)                        # SW node at drain
    g_q = gnd("GND_Q", -340, 50)
    wire(q, 2, g_q, 0)

    d_b = comp("DIODE", "D_BOOST", -240, -120, {},
               [pin(0, "A", -30, 0), pin(1, "K", 30, 0)])
    wire(ipl, 1, d_b, 0)                      # SW → boost diode
    wire(d_b, 1, goto("VBUS", "LBL_VBUS", -170, -200), 0)  # pin x = -210

    # Fixed-duty gate drive for the boost MOSFET (target_component binds it).
    pwm = comp("PWM_GENERATOR", "PWM_SW", -340, 160,
               {"frequency": F_SW, "duty_cycle": DUTY, "duty": DUTY,
                "amplitude": V_GATE, "carrier": "sawtooth", "phase": 0.0,
                "sample_time": 0.0, "target_component": "Q_SW"},
               [pin(0, "OUT", 40, 0)])
    wire(pwm, 0, q, 1)                         # OUT → gate

    # Output cap + battery (charging current probe in series with the pack).
    cout = comp("CAPACITOR", "C_OUT", -60, -120,
                {"capacitance": C_OUT, "initial_voltage": V_BATT},
                [pin(0, "+", -20, 0), pin(1, "-", 20, 0)])
    wire(from_("VBUS", "F_VBUS1", -140, -120), 0, cout, 0)
    g_cout = gnd("GND_COUT", -60, -40)
    wire(cout, 1, g_cout, 0)

    ipb = comp("CURRENT_PROBE", "IP_BATT", 120, -120, {},
               [pin(0, "IN", -20, 0), pin(1, "OUT", 20, 0),
                pin(2, "SIG", 0, -20)])
    wire(from_("VBUS", "F_VBUS2", 40, -120), 0, ipb, 0)
    bat = comp("BATTERY", "BAT1", 260, -120,
               {"voltage": V_BATT, "r_internal": R_INT, "capacity_ah": 10.0},
               [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    wire(ipb, 1, bat, 0)
    g_bat = gnd("GND_BAT", 260, 0)
    wire(bat, 1, g_bat, 0)

    # Feedback probes + a pre-wired scope (PV V, battery V, charge I, L I).
    vp_pv = comp("VOLTAGE_PROBE_GND", "VP_PV", -700, -240, {},
                 [pin(0, "IN", -20, 0), pin(1, "SIG", 20, 0)])
    wire(vp_pv, 0, from_("PVP", "F_PVP3", -760, -240), 0)
    wire(vp_pv, 1, goto("SIG_VPV", "LBL_SVPV", -640, -300), 0)  # pin x = -680
    vp_b = comp("VOLTAGE_PROBE_GND", "VP_BATT", 40, -240, {},
                [pin(0, "IN", -20, 0), pin(1, "SIG", 20, 0)])
    wire(vp_b, 0, from_("VBUS", "F_VBUS3", -20, -240), 0)
    wire(vp_b, 1, goto("SIG_VB", "LBL_SVB", 100, -300), 0)      # pin x = 60
    wire(ipb, 2, goto("SIG_IB", "LBL_SIB", 160, -200), 0)       # pin x = 120
    wire(ipl, 2, goto("SIG_IL", "LBL_SIL", -440, -200), 0)      # pin x = -480

    scope = comp("ELECTRICAL_SCOPE", "SCOPE1", 560, -260,
                 {"channel_count": 4,
                  "channels": [{"label": "V_pv", "overlay": False},
                               {"label": "V_batt", "overlay": False},
                               {"label": "I_charge", "overlay": False},
                               {"label": "I_L", "overlay": False}]},
                 [pin(0, "CH1", -40, -30), pin(1, "CH2", -40, -10),
                  pin(2, "CH3", -40, 10), pin(3, "CH4", -40, 30)])
    for k, net in enumerate(("SIG_VPV", "SIG_VB", "SIG_IB", "SIG_IL")):
        lbl = from_(net, f"F_{net}", 440, -290 + 20 * k)       # pin x = 480
        wire(lbl, 0, scope, k)

    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0", "name": "39 Solar PV Battery Charger (boost)",
        "created": now, "modified": now,
        "description": (
            "Photovoltaic charging chain: a PV panel (Isc 8 A, Voc 37 V, "
            "~230 W) feeds a 25 kHz boost converter (fixed D≈0.45) charging a "
            "48 V battery. The stiff pack clamps the output, so the PV sits "
            "in its current region and delivers several amps of charge — a "
            "showcase of the PV_PANEL and BATTERY components."),
        "active_circuit": "main",
        "circuits": {"main": {"name": "main", "components": components,
                              "wires": wires, "subcircuits": []}},
        "simulation_settings": {"tstop": 40e-3, "dt": 1e-6,
                                "output_points": 8000, "engine": "pwl"},
    }
    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {len(components)} components, {len(wires)} wires")


if __name__ == "__main__":
    main()
