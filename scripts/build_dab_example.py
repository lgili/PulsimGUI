#!/usr/bin/env python3
"""Builder for example 35 — Dual Active Bridge (DAB), single phase shift.

Two full bridges (8 three-pin SWITCHes) around an HF transformer + series
(leakage) inductor. Gates are PULSE voltage sources — diagonal pairs share a
gate net via GOTO/FROM labels, and the secondary pair lags by the phase shift
φ (delay = φ/2π · T). The classic transfer law (validated against the kernel
in scripts/validate_dab.py, 0.7 % error):

    P = V1·V2′·φ(1−φ/π) / (2π·f·L)    ≈ 12.5 kW at φ = 45°

Layout: each bridge leg is a horizontal row (rail+ → Sh → mid → Sl → GND);
midpoints feed the magnetic link through the leakage inductor / transformer.

Run::  PYTHONPATH=src python3 scripts/build_dab_example.py
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
DST = REPO / "examples" / "35_dab_phase_shift.pulsim"

V1, V2 = 400.0, 200.0
N_RATIO = 2.0
F_SW = 20e3
T_SW = 1.0 / F_SW
L_LK = 60e-6
PHI = math.pi / 4
V_GATE = 15.0

components: list[dict] = []
wires: list[dict] = []
_by_id: dict[str, dict] = {}
_router = WireRouter()


def uid() -> str:
    return str(uuid.uuid4())


def comp(type_, name, x, y, parameters, pins) -> dict:
    c = {"id": uid(), "type": type_, "name": name, "x": float(x), "y": float(y),
         "rotation": 0, "mirrored_h": False, "mirrored_v": False,
         "parameters": parameters, "pins": pins}
    components.append(c)
    _by_id[c["id"]] = c
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


def vsrc(name, x, y, waveform) -> dict:
    return comp("VOLTAGE_SOURCE", name, x, y, {"waveform": waveform},
                [pin(0, "+", 0, -20), pin(1, "-", 0, 20)])


def gnd(name, x, y) -> dict:
    return comp("GROUND", name, x, y, {}, [pin(0, "gnd", 0, -20)])


def switch(name, x, y) -> dict:
    return comp("SWITCH", name, x, y,
                {"v_threshold": 2.5, "ron": 1e-3, "roff": 1e9},
                [pin(0, "1", -20, 0), pin(1, "2", 20, 0), pin(2, "CTL", 0, -20)])


def goto(net, x, y) -> dict:
    return comp("GOTO_LABEL", f"GOTO_{net}_{uid()[:4]}", x, y,
                {"net_label": net}, [pin(0, "NET", -40, 0)])


def from_(net, x, y) -> dict:
    return comp("FROM_LABEL", f"FROM_{net}_{uid()[:4]}", x, y,
                {"net_label": net}, [pin(0, "NET", 40, 0)])


def bridge_leg(prefix, x, y, rail_net, phase_hi, phase_lo) -> dict:
    """rail+ → S{prefix}h → mid → S{prefix}l → GND, one PWM per switch gate.
    Returns the HIGH switch (its pin 1 is the leg midpoint)."""
    sh = switch(f"S{prefix}h", x, y)
    sl = switch(f"S{prefix}l", x + 160, y)
    rail = from_(rail_net, x - 100, y)
    wire(rail, 0, sh, 0)
    wire(sh, 1, sl, 0)                       # midpoint
    g = gnd(f"GND_{prefix}", x + 220, y + 50)
    wire(sl, 1, g, 0)
    for sw, phase, dx in ((sh, phase_hi, 0), (sl, phase_lo, 160)):
        pg = pwm_gen(f"PWM_{sw['name']}", x + dx - 60, y - 80, phase,
                     sw["name"])
        wire(pg, 0, sw, 2)
    return sh


def pwm_gen(name, x, y, phase_frac: float, target: str) -> dict:
    """Per-switch PWM gate drive: 50 % duty square at F_SW shifted by
    ``phase_frac`` of a period. ``target_component`` binds it EXPLICITLY to
    its switch, which routes it through the virtual-PWM record path — the
    backend derives the switch gating (frequency/duty/phase) from the record.
    One PWM per switch: gate-node→switch maps are 1:1, so diagonal pairs
    must NOT share a generator."""
    return comp("PWM_GENERATOR", name, x, y,
                {"frequency": F_SW, "duty_cycle": 0.5, "duty": 0.5,
                 "amplitude": V_GATE, "carrier": "sawtooth",
                 "phase": phase_frac, "sample_time": 0.0,
                 "target_component": target},
                [pin(0, "OUT", 40, 0)])


def main() -> None:
    # DC buses (negatives grounded — common reference keeps the MNA well-posed
    # without affecting the differential physics; see validate_dab.py).
    v_in = vsrc("V_IN", -950, -60, {"type": "dc", "value": V1})
    wire(v_in, 1, gnd("GND_VIN", -950, 60), 0)
    wire(v_in, 0, goto("VP", -950, -140), 0)

    v_out = vsrc("V_OUT", 1050, -60, {"type": "dc", "value": V2})
    wire(v_out, 1, gnd("GND_VOUT", 1050, 60), 0)
    wire(v_out, 0, goto("VS", 1050, -140), 0)

    # Bridges: legs A/B (primary, rail VP) and C/D (secondary, rail VS).
    # PWM phase is in RADIANS (kernel make_pwm_switch_fn): diagonal pairs
    # {Ah,Bl} at 0 and {Al,Bh} at π; the secondary lags by φ.
    sa = bridge_leg("A", -680, -200, "VP", 0.0, math.pi)
    sb = bridge_leg("B", -680, 0, "VP", math.pi, 0.0)
    sc = bridge_leg("C", 460, -200, "VS", PHI, math.pi + PHI)
    sd = bridge_leg("D", 460, 0, "VS", math.pi + PHI, PHI)

    # Magnetic link: pa →Llk→ I-probe → TX(P1,P2 : S1,S2) → sa/sb midpoints.
    llk = comp("INDUCTOR", "Llk", -360, -160,
               {"inductance": L_LK, "initial_current": 0.0},
               [pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
    ip = comp("CURRENT_PROBE", "IP_lk", -220, -160, {},
              [pin(0, "1", -30, 0), pin(1, "2", 30, 0)])
    tx = comp("TRANSFORMER", "TX", -40, -80,
              {"turns_ratio": N_RATIO, "lm": 10e-3, "n_secondaries": 1},
              [pin(0, "P1", -40, -20), pin(1, "P2", -40, 20),
               pin(2, "S1", 40, -20), pin(3, "S2", 40, 20)])
    wire(sa, 1, llk, 0)                      # pa → Llk
    wire(llk, 1, ip, 0)
    wire(ip, 1, tx, 0)                       # → P1
    wire(sb, 1, tx, 1)                       # pb → P2
    wire(tx, 2, sc, 1)                       # S1 → sa midpoint
    wire(tx, 3, sd, 1)                       # S2 → sb midpoint

    # (Per-switch PWM gate drives are created inside bridge_leg.)

    # Probes for the scope-less default signal set.
    vp1 = comp("VOLTAGE_PROBE_GND", "VP_pa", -420, -260, {},
               [pin(0, "IN", 0, 20)])
    wire(vp1, 0, sa, 1)
    vp2 = comp("VOLTAGE_PROBE_GND", "VP_sa", 320, -260, {},
               [pin(0, "IN", 0, 20)])
    wire(vp2, 0, sc, 1)

    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0", "name": "35 DAB — Dual Active Bridge (phase shift)",
        "created": now, "modified": now,
        "description": (
            "Dual Active Bridge: two full bridges (8 switches) around an HF "
            "transformer + 60 µH leakage, single-phase-shift modulation "
            "(φ=45° via pulse-source delays). Transfers ≈12.5 kW from the "
            "400 V to the 200 V bus per P = V1·V2'·φ(1−φ/π)/(2πfL)."),
        "active_circuit": "main",
        "circuits": {"main": {"name": "main", "components": components,
                              "wires": wires, "subcircuits": []}},
        "simulation_settings": {"tstop": 2e-3, "dt": 2e-7,
                                "output_points": 10000, "engine": "pwl"},
    }
    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {len(components)} components, "
          f"{len(wires)} wires")


if __name__ == "__main__":
    main()
