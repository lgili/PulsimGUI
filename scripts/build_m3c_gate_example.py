#!/usr/bin/env python3
"""Builder for example 33 — M3C with gate-driven arms (control 100% external).

Reads ``examples/32_m3c_thesis_svm.pulsim`` (thesis Fast-SVM control, L3 arms)
and re-emits the same converter + controller with every arm switched to
``model_fidelity = "External Gates"`` — the new GUI dropdown option that builds
a gate-driven arm (services/gate_driven_arm.py).

The arm then does NO internal modulation or balancing: the wired M3C SVM
controller's per-branch modulation index is turned into per-submodule insertion
GATES (level quantisation + carrier PWM + EXTERNAL sort-and-select on the arm's
live capacitors), and the arm only integrates its capacitors. This is the
HIL/Simulink "I feed the gates, the model represents" workflow, now selectable
from the GUI — open it and the scopes show the switched arm voltage, the
submodule caps balanced externally, and the branch caps held by the cost
function.

Run::  PYTHONPATH=src python3 scripts/build_m3c_gate_example.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "32_m3c_thesis_svm.pulsim"
DST = ROOT / "examples" / "33_m3c_gate_driven.pulsim"


def main() -> None:
    project = json.loads(SRC.read_text())
    n_arm = 0
    for circ in project["circuits"].values():
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {}).update({
                    "model_fidelity": "External Gates",
                    "v_c0_spread": 600.0,   # seed a submodule imbalance so the
                                            # EXTERNAL sort-and-select is visible
                })
                n_arm += 1
    if not n_arm:
        raise SystemExit("No MMC_ARM found in example 32.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "33 M3C Gate-Driven — control 100% external (HIL-style)"
    project["modified"] = now
    project["simulation_settings"]["tstop"] = 0.06
    project["simulation_settings"]["output_points"] = 12000

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_arm} arms → External Gates (gate-driven), "
          "tstop=0.06s")


if __name__ == "__main__":
    main()
