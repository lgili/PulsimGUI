#!/usr/bin/env python3
"""Builder for example 36 — LLC resonant converter at resonance.

Half-bridge (2 three-pin SWITCHes, per-switch PWM gate drive at 50 % duty,
complement at phase π) → series resonant tank Lr–Cr → transformer (its ``lm``
IS the magnetizing inductance Lm of the LLC) → diode bridge → C_out ∥ R_load.

Operating AT the series resonance f_s = f_r = 1/(2π√(LrCr)) ≈ 100 kHz the
tank gain is ≈1, so V_out ≈ V_in/(2·n) = 400/(2·4) = 50 V — the textbook
operating point the test checks.

Run::  PYTHONPATH=src python3 scripts/build_llc_example.py
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
DST = REPO / "examples" / "36_llc_resonant.pulsim"

V_IN = 400.0
N_RATIO = 4.0          # transformer N1/N2 → V_out ≈ V_in/(2n) = 50 V
L_R = 25e-6
C_R = 100e-9
F_R = 1.0 / (2 * math.pi * math.sqrt(L_R * C_R))   # ≈ 100.7 kHz
L_M = 125e-6           # magnetizing inductance (the transformer's lm)
C_OUT = 100e-6
R_LOAD = 5.0
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


def main() -> None:
    # Input bus.
    v_in = comp("VOLTAGE_SOURCE", "V_IN", -900, -80,
                {"waveform": {"type": "dc", "value": V_IN}},
                [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])
    g_in = comp("GROUND", "GND_IN", -900, 60, {}, [pin(0, "gnd", 0, -20)])
    wire(v_in, 1, g_in, 0)

    # Half-bridge: V_IN+ → Sh → mid → Sl → GND, per-switch PWM (phase rad).
    def switch(name, x, y):
        return comp("SWITCH", name, x, y,
                    {"v_threshold": 2.5, "ron": 1e-3, "roff": 1e9},
                    [pin(0, "1", -20, 0), pin(1, "2", 20, 0),
                     pin(2, "CTL", 0, -20)])

    def pwm(name, x, y, phase, target):
        return comp("PWM_GENERATOR", name, x, y,
                    {"frequency": F_R, "duty_cycle": 0.48, "duty": 0.48,
                     "amplitude": V_GATE, "carrier": "sawtooth",
                     "phase": phase, "sample_time": 0.0,
                     "target_component": target},
                    [pin(0, "OUT", 40, 0)])

    sh = switch("Sh", -700, -160)
    sl = switch("Sl", -540, -160)
    wire(v_in, 0, sh, 0)
    wire(sh, 1, sl, 0)                       # half-bridge midpoint
    g_hb = comp("GROUND", "GND_HB", -480, -100, {}, [pin(0, "gnd", 0, -20)])
    wire(sl, 1, g_hb, 0)
    for sw, phase, dx in ((sh, 0.0, 0), (sl, math.pi, 160)):
        pg = pwm(f"PWM_{sw['name']}", -760 + dx, -260, phase, sw["name"])
        wire(pg, 0, sw, 2)

    # Resonant tank: mid → Lr → Cr → TX primary; lm = the LLC's Lm.
    lr = comp("INDUCTOR", "Lr", -380, -160,
              {"inductance": L_R, "initial_current": 0.0},
              [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    cr = comp("CAPACITOR", "Cr", -240, -160,
              {"capacitance": C_R, "initial_voltage": 0.0},
              [pin(0, "+", -20, 0), pin(1, "-", 20, 0)])
    tx = comp("TRANSFORMER", "TX", -80, -100,
              {"turns_ratio": N_RATIO, "lm": L_M, "n_secondaries": 1},
              [pin(0, "P1", -40, -20), pin(1, "P2", -40, 20),
               pin(2, "S1", 40, -20), pin(3, "S2", 40, 20)])
    wire(sh, 1, lr, 0)
    wire(lr, 1, cr, 0)
    wire(cr, 1, tx, 0)                       # → P1
    g_tx = comp("GROUND", "GND_TX", -140, 20, {}, [pin(0, "gnd", 0, -20)])
    wire(tx, 1, g_tx, 0)                     # P2 return

    # Rectifier + output filter.
    br = comp("SINGLE_PHASE_DIODE_BRIDGE", "BR1", 120, -100,
              {},
              [pin(0, "AC+", -40, -20), pin(1, "AC-", -40, 20),
               pin(2, "DC+", 40, -20), pin(3, "DC-", 40, 20)])
    wire(tx, 2, br, 0)                       # S1 → AC+
    wire(tx, 3, br, 1)                       # S2 → AC−
    cout = comp("CAPACITOR", "C_OUT", 320, -100,
                {"capacitance": C_OUT, "initial_voltage": 50.0},
                [pin(0, "+", -20, 0), pin(1, "-", 20, 0)])
    rload = comp("RESISTOR", "R_LOAD", 320, 0,
                 {"resistance": R_LOAD},
                 [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    g_out = comp("GROUND", "GND_OUT", 460, 60, {}, [pin(0, "gnd", 0, -20)])
    wire(br, 2, cout, 0)                     # DC+ → C_out+
    wire(br, 2, rload, 0)                    # DC+ → R_load
    wire(br, 3, g_out, 0)                    # DC− → ground
    wire(cout, 1, g_out, 0)
    wire(rload, 1, g_out, 0)

    # Probes + a stable name for the output net.
    vp = comp("VOLTAGE_PROBE_GND", "VP_out", 240, -200, {},
              [pin(0, "IN", 0, 20)])
    wire(vp, 0, br, 2)
    lbl = comp("GOTO_LABEL", "LBL_VOUT", 200, -40, {"net_label": "VOUT"},
               [pin(0, "NET", -40, 0)])
    wire(lbl, 0, br, 2)

    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0", "name": "36 LLC Resonant Converter (at resonance)",
        "created": now, "modified": now,
        "description": (
            "Half-bridge LLC at the series resonance (Lr=25 µH, Cr=100 nF, "
            "f_r≈100 kHz; Lm=125 µH via the transformer's lm). Tank gain ≈1 "
            "⇒ V_out ≈ V_in/(2n) = 50 V into 5 Ω (~500 W)."),
        "active_circuit": "main",
        "circuits": {"main": {"name": "main", "components": components,
                              "wires": wires, "subcircuits": []}},
        "simulation_settings": {"tstop": 1.5e-3, "dt": 5e-8,
                                "output_points": 10000, "engine": "pwl"},
    }
    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {len(components)} components, {len(wires)} wires"
          f" (f_r = {F_R/1e3:.1f} kHz)")


if __name__ == "__main__":
    main()
