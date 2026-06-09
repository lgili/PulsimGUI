#!/usr/bin/env python3
"""Builder for example 32 — switched (L3) M3C with the **thesis Fast-SVM**.

Reads ``examples/31_m3c_switched_closed_loop.pulsim`` (switched L3 arms + the
default heuristic modal balancing) and re-emits an *identical* converter whose
controller runs the thesis's own modulation instead: ``control_mode = "svm"``.

This swaps the capacitor-balancing law for the thesis Fast-SVM cost function
(L. C. Gili, UFSC 2024, Etapas 3-4):

* **Etapa 3** — the reference input/output phase voltages are taken into the
  non-orthogonal lgγ plane and the nearest lattice vectors found by floor/ceil
  (Celanovic's fast SVM, kept common-mode-aware). The smallest input phase is
  tied to the smallest output phase, reducing the 81 valid connections to 45.
* **Etapa 4** — each switching period the connection (a spanning tree of K₃,₃)
  minimising ``J = Σ(ε_xy + ΔV_xy)²`` with ``ΔV_xy = Sn·I_xy·Ts/C`` is selected
  predictively from the live module voltages and currents.

The dq energy + current loops (Etapas 1-2) and the L3 arm's intra-module
sort-and-select + PWM (Etapas 5-6) are unchanged, so this completes the full
six-stage thesis scheme on the behavioural model.

Run::  PYTHONPATH=src python3 scripts/build_m3c_svm.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "31_m3c_switched_closed_loop.pulsim"
DST = ROOT / "examples" / "32_m3c_thesis_svm.pulsim"


def main() -> None:
    project = json.loads(SRC.read_text())
    n_ctrl = 0
    for circ in project["circuits"].values():
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_CONTROLLER":
                comp.setdefault("parameters", {}).update({
                    "control_mode": "svm",
                    "m3c_f_switch": 2000.0,       # thesis Table 15: 2 kHz
                    "m3c_sm_capacitance": 680.0e-6,  # 680 µF / SM
                    "m3c_n_sm": 6.0,              # 6 SM / branch
                    "m3c_k_svm": 0.25,
                })
                n_ctrl += 1
    if not n_ctrl:
        raise SystemExit("No MMC_CONTROLLER found in example 31.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "32 M3C Thesis Fast-SVM — switched (L3), cost-function balancing"
    project["modified"] = now
    project["simulation_settings"]["tstop"] = 0.08
    project["simulation_settings"]["output_points"] = 16000

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_ctrl} controller → control_mode=svm "
          "(thesis Fast-SVM cost-function balancing)")


if __name__ == "__main__":
    main()
