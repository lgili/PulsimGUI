#!/usr/bin/env python3
"""Builder for example 29 — Modular Multilevel Matrix Converter (M3C).

Emits ``examples/29_m3c_matrix_converter.pulsim`` — a GUI-loadable, simulating
M3C from Luiz Carlos Gili's thesis ("Contribuições Para o Conversor Modular
Matricial Multinível - M3C", UFSC 2024): the 3×3 matrix of Figure 34 with the
Table 15 simulation parameters.

Topology (direct AC↔AC, no DC link)::

          OUT a      OUT b      OUT c
   IN A   M_Aa       M_Ab       M_Ac
   IN B   M_Ba       M_Bb       M_Bc
   IN C   M_Ca       M_Cb       M_Cc

The nine branches ``M_<X><y>`` each tie input phase X (TOP) through a chain of
6 full-bridge submodules + a branch inductor (BOT → Lb_Xy) to output phase y.
Input phase X feeds the three arms in its row; output phase y collects the
three arms in its column. Both sides are stiff three-phase sources (Sistema 1 =
13.8 kV/50 Hz grid, Sistema 2 = 11 kV/45 Hz), each via a current probe.

The mesh is wired with GOTO/FROM net-labels (IN_A.. / OUT_a..) so the 3×3
interconnect carries no crossing power wires (no false junctions).

Modulation: a single ``MMC_CONTROLLER`` set to ``topology="m3c"`` (placed, not
pin-wired) makes the converter drive the nine arms by name with the open-loop
feed-forward m_Xy = (v_in_X − v_out_y − L·di_ref/dt)/v_C_live — the M3C analogue
of the open-loop MMC example 24. The per-branch capacitor voltages drift
(open-loop, no balancing); that is the residual the thesis's closed-loop SVM +
balancing control removes.

Run::  PYTHONPATH=src python3 scripts/build_m3c_example.py
"""
from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime
from pathlib import Path

_WANT_SCOPES = os.environ.get("M3C_SCOPES", "1") == "1"

import pulsimgui.models  # noqa: F401 — defuse circular import

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "examples" / "29_m3c_matrix_converter.pulsim"

# --- Thesis Table 15 parameters --------------------------------------------
P_RATED = 2.0e6
N_SM = 6
V_CAP_SM = 4.0e3
C_SM = 680.0e-6
V_C_AGG = N_SM * V_CAP_SM          # 24 kV aggregate branch cap voltage
L_BRANCH = 25.0e-3
R_BRANCH = 0.5                     # per-branch series R [Ω] — damps the
                                   # open-loop DC circulating current (the M3C
                                   # mesh has zero-resistance circulating loops)
V_IN_LINE, F_IN = 13.8e3, 50.0
V_OUT_LINE, F_OUT = 11.0e3, 45.0

V_IN_PK = V_IN_LINE * math.sqrt(2.0 / 3.0)
V_OUT_PK = V_OUT_LINE * math.sqrt(2.0 / 3.0)
I_IN_PK = 2.0 * P_RATED / (3.0 * V_IN_PK)
I_OUT_PK = 2.0 * P_RATED / (3.0 * V_OUT_PK)
PH = (0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0)


def uid() -> str:
    return str(uuid.uuid4())


def comp(*, type, name, x, y, parameters, pins, rotation=0):
    return {
        "id": uid(), "type": type, "name": name, "x": float(x), "y": float(y),
        "rotation": rotation, "mirrored_h": False, "mirrored_v": False,
        "parameters": parameters, "pins": pins,
    }


def pin(index, name, x, y):
    return {"index": index, "name": name, "x": float(x), "y": float(y)}


def _pin_world(c, idx):
    px = next(p["x"] for p in c["pins"] if p["index"] == idx)
    py = next(p["y"] for p in c["pins"] if p["index"] == idx)
    if c.get("mirrored_h"):
        px = -px
    if c.get("mirrored_v"):
        py = -py
    for _ in range((int(c.get("rotation", 0) or 0) // 90) % 4):
        px, py = -py, px
    return c["x"] + px, c["y"] + py


def wire_direct(a, ap, b, bp, *, node_name=""):
    ax, ay = _pin_world(a, ap)
    bx, by = _pin_world(b, bp)
    return {
        "id": uid(), "segments": [{"x1": ax, "y1": ay, "x2": bx, "y2": by}],
        "start_connection": {"component_id": a["id"], "pin_index": ap},
        "end_connection": {"component_id": b["id"], "pin_index": bp},
        "junctions": [], "node_name": node_name, "alias": "",
    }


def main() -> None:
    components: list[dict] = []
    wires: list[dict] = []

    def add(*cs):
        components.extend(cs)

    def w(a, ap, b, bp, **kw):
        wires.append(wire_direct(a, ap, b, bp, **kw))

    def net_label(kind, name, x, y, label):
        # GOTO_LABEL / FROM_LABEL single-pin net alias (merge by net_label).
        return comp(type=kind, name=name, x=x, y=y,
                    parameters={"net_label": label}, pins=[pin(0, "NET", 0, 0)])

    # ---- Layout grid -------------------------------------------------------
    # 360 px row/column spacing: the per-branch inductor + FROM_OUT_y net-label
    # sit between rows WITHOUT the FROM_OUT label landing on the next row's arm
    # TOP pin (a position collision would merge OUT_y into IN_<next> and short
    # the converter — the cause of the first singular build).
    COL_X = {"a": 0, "b": 360, "c": 720}      # output phases (columns)
    ROW_Y = {"A": 0, "B": 440, "C": 880}      # input phases (rows; 440 leaves
                                              # room for the series R+L per arm)
    OUT_SRC_Y = 1200                          # output sources below the grid

    # ---- Grounds (shared input/output neutrals) ----------------------------
    # Placed CLEAR of every source position (sources sit at x=-560,y∈ROW_Y and
    # x∈COL_X,y=OUT_SRC_Y): a ground pin landing on a source terminal would
    # short that source to ground (the cause of the first singular build).
    gnd_in = comp(type="GROUND", name="GND_in", x=-720, y=360,
                  pins=[pin(0, "gnd", 0, -20)], parameters={})
    gnd_out = comp(type="GROUND", name="GND_out", x=520, y=OUT_SRC_Y + 120,
                   pins=[pin(0, "gnd", 0, -20)], parameters={})
    add(gnd_in, gnd_out)

    def vsrc(name, x, y, vpk, freq, phase):
        # NOTE: the sine source's ``phase`` is in RADIANS (matches the converter
        # + the M3C feed-forward, which also uses radians). Passing degrees here
        # scrambles the 3-phase balance and explodes the circulating current.
        return comp(type="VOLTAGE_SOURCE", name=name, x=x, y=y,
                    parameters={"waveform": {"type": "sine", "value": 0.0,
                                "amplitude": vpk, "frequency": freq,
                                "offset": 0.0, "phase": phase}},
                    pins=[pin(0, "+", 0, -20), pin(1, "-", 0, 20)])

    def iprobe(name, x, y):
        return comp(type="CURRENT_PROBE", name=name, x=x, y=y,
                    parameters={"display_name": name, "scale": 1.0},
                    pins=[pin(0, "IN", -20, 0), pin(1, "OUT", 20, 0),
                          pin(2, "MEAS", 0, -20)])

    # ---- Input sources (Sistema 1) — left column, into IN_X nets -----------
    in_probes = {}
    for i, X in enumerate("ABC"):
        y = ROW_Y[X]
        vs = vsrc(f"V_in_{X}", -560, y, V_IN_PK, F_IN, PH[i])
        ip = iprobe(f"I_in_{X}", -440, y)              # IN(left)->OUT(right)
        g = net_label("GOTO_LABEL", f"GOTO_IN_{X}", -360, y, f"IN_{X}")
        add(vs, ip, g)
        in_probes[X] = ip
        w(vs, 0, ip, 0)                                # V_in.+ -> probe IN
        w(ip, 1, g, 0)                                 # probe OUT -> GOTO IN_X
        w(vs, 1, gnd_in, 0)                            # V_in.-  -> ground

    # ---- Output sources (Sistema 2) — bottom row, into OUT_y nets ----------
    out_probes = {}
    for j, y_ph in enumerate("abc"):
        x = COL_X[y_ph]
        vs = vsrc(f"V_out_{y_ph}", x, OUT_SRC_Y, V_OUT_PK, F_OUT, PH[j])
        ip = iprobe(f"I_out_{y_ph}", x, OUT_SRC_Y - 100)  # OUT-net -> source
        g = net_label("GOTO_LABEL", f"GOTO_OUT_{y_ph}", x, OUT_SRC_Y - 160,
                      f"OUT_{y_ph}")
        add(vs, ip, g)
        out_probes[y_ph] = ip
        w(g, 0, ip, 0)                                 # GOTO OUT_y -> probe IN
        w(ip, 1, vs, 0)                                # probe OUT  -> V_out.+
        w(vs, 1, gnd_out, 0)                           # V_out.-    -> ground

    # ---- 9 arms (full-bridge) + 9 branch inductors -------------------------
    ARM_PARAMS = {
        "model_fidelity": "L0 Average", "submodule_type": "Full-Bridge",
        "n_submodules": N_SM, "c_sm": C_SM, "v_c0": V_C_AGG, "r_arm": 0.0,
        "m_ref_constant": 0.0, "f_carrier": 2000.0, "modulation_scheme": "PSC",
        "t_dead": 1.0e-6, "t_min": 1.0e-7, "balancing": "sort_and_select",
    }
    arms: dict[str, dict] = {}
    for i, X in enumerate("ABC"):
        for j, y_ph in enumerate("abc"):
            cx, cy = COL_X[y_ph], ROW_Y[X]
            arm = comp(type="MMC_ARM", name=f"M_{X}{y_ph}", x=cx, y=cy,
                       parameters={**ARM_PARAMS},
                       pins=[pin(0, "TOP", -40, -40), pin(1, "BOT", -40, 40),
                             pin(2, "M_REF", 40, 0), pin(3, "V_C", 40, -40),
                             pin(4, "V_C_SPRD", 40, 20)])
            arms[f"{X}{y_ph}"] = arm
            # Branch below the arm: BOT -> series R -> series L -> OUT_y net.
            # R damps the open-loop DC circulating current the M3C mesh would
            # otherwise carry through its zero-resistance loops (vertical
            # elements: canonical pins + rot=90).
            i0 = (I_IN_PK * math.sin(PH[i]) + I_OUT_PK * math.sin(PH[j])) / 3.0
            res = comp(type="RESISTOR", name=f"Rb_{X}{y_ph}",
                       x=cx - 40, y=cy + 95, rotation=90,
                       parameters={"resistance": R_BRANCH},
                       pins=[pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
            ind = comp(type="INDUCTOR", name=f"Lb_{X}{y_ph}",
                       x=cx - 40, y=cy + 185, rotation=90,
                       parameters={"inductance": L_BRANCH, "initial_current": i0},
                       pins=[pin(0, "1", -40, 0), pin(1, "2", 40, 0)])
            f_in = net_label("FROM_LABEL", f"FROM_IN_{X}_{y_ph}",
                             cx - 110, cy - 40, f"IN_{X}")
            f_out = net_label("FROM_LABEL", f"FROM_OUT_{y_ph}_{X}",
                              cx - 40, cy + 265, f"OUT_{y_ph}")
            add(arm, res, ind, f_in, f_out)
            w(arm, 0, f_in, 0)        # TOP -> FROM IN_X
            w(arm, 1, res, 0)         # BOT -> resistor top
            w(res, 1, ind, 0)         # resistor bottom -> inductor top
            w(ind, 1, f_out, 0)       # inductor bottom -> FROM OUT_y

    # ---- M3C modulator (drives the 9 arms by name; placed, not pin-wired) --
    ctrl = comp(type="MMC_CONTROLLER", name="M3C_Ctrl", x=-560, y=760,
                parameters={"topology": "m3c", "m3c_power": P_RATED,
                            "m3c_v_in_line": V_IN_LINE, "m3c_f_in": F_IN,
                            "m3c_v_out_line": V_OUT_LINE, "m3c_f_out": F_OUT,
                            "m3c_v_c": V_C_AGG, "m3c_l_branch": L_BRANCH,
                            "m3c_r_branch": R_BRANCH},
                pins=[pin(0, "A_UP", 40, -60), pin(1, "A_LO", 40, -40),
                      pin(2, "B_UP", 40, -20), pin(3, "B_LO", 40, 20),
                      pin(4, "C_UP", 40, 40), pin(5, "C_LO", 40, 60)])
    add(ctrl)

    # ---- Scopes (right side) via GOTO/FROM signal labels -------------------
    def scope(name, x, y, channels):
        chans = [{"label": lbl, "overlay": True} for lbl in channels]
        return comp(type="ELECTRICAL_SCOPE", name=name, x=x, y=y,
                    parameters={"channel_count": len(channels), "channels": chans},
                    pins=[pin(k, f"CH{k+1}", -40, -40 + k * 40)
                          for k in range(len(channels))])

    def sig(src, src_pin, scope_c, ch, text, goto_xy, from_xy):
        g = net_label("GOTO_LABEL", f"GOTO_{text}", goto_xy[0], goto_xy[1], text)
        fr = net_label("FROM_LABEL", f"FROM_{text}", from_xy[0], from_xy[1], text)
        add(g, fr)
        w(src, src_pin, g, 0)
        w(scope_c, ch, fr, 0)

    if _WANT_SCOPES:
        sc_in = scope("Scope_InputCurrents", 1240, 0,
                      ["I_in_A", "I_in_B", "I_in_C"])
        sc_out = scope("Scope_OutputCurrents", 1240, 240,
                       ["I_out_a", "I_out_b", "I_out_c"])
        sc_vc = scope("Scope_CapVoltages", 1240, 560,
                      [f"vC_{X}{y}" for X in "ABC" for y in "abc"])
        add(sc_in, sc_out, sc_vc)
        for k, X in enumerate("ABC"):
            sig(in_probes[X], 2, sc_in, k, f"SIG_IIN_{X}",
                (-440, ROW_Y[X] - 60), (1160, -40 + k * 40))
        for k, y_ph in enumerate("abc"):
            sig(out_probes[y_ph], 2, sc_out, k, f"SIG_IOUT_{y_ph}",
                (COL_X[y_ph] - 90, OUT_SRC_Y - 100), (1160, 200 + k * 40))
        k = 0
        for X in "ABC":
            for y_ph in "abc":
                sig(arms[f"{X}{y_ph}"], 3, sc_vc, k, f"SIG_VC_{X}{y_ph}",
                    (COL_X[y_ph] + 90, ROW_Y[X] - 40), (1160, 520 + k * 40))
                k += 1

    # ---- Simulation settings ----------------------------------------------
    sim = {
        "engine": "pwl", "tstop": 0.12, "dt": 1.0e-5, "tstart": 0.0,
        "output_points": 12000, "control_sample_time": 1.0e-5,
        "control_mode": "discrete", "tol_newton_dx": 1.0e-6,
        "tol_newton_res": 1.0e-6, "enable_newton_line_search": True,
        "enable_newton_lm": True, "enable_substep_state_correction": True,
        "enable_nonlinear_refresh": True, "start_from_dc_op": False,
        "max_event_iterations": 50,
    }
    now = datetime.now().isoformat(timespec="seconds")
    project = {
        "version": "1.0",
        "name": "29 M3C Matrix Converter — direct AC-AC (13.8kV/50Hz → 11kV/45Hz)",
        "created": now, "modified": now, "active_circuit": "main",
        "simulation_settings": sim,
        "circuits": {"main": {"name": "main", "components": components,
                              "wires": wires}},
    }
    DST.write_text(json.dumps(project, indent=2))
    n_arm = sum(1 for c in components if c["type"] == "MMC_ARM")
    print(f"wrote {DST.name}: {len(components)} components, {len(wires)} wires, "
          f"{n_arm} arms (M3C 3×3), f_out={F_OUT:.0f} Hz")


if __name__ == "__main__":
    main()
