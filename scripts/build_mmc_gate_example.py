#!/usr/bin/env python3
"""Builder for example 34 — 3-phase MMC with gate-driven arms (control external).

Reads ``examples/26_mmc_three_phase_l3_closed_loop.pulsim`` (six-arm DC→AC MMC,
L3 detailed arms, closed-loop controller) and re-emits the SAME circuit with
every arm switched to ``model_fidelity = "External Gates"`` — the new GUI
dropdown option (services/gate_driven_arm.py).

The arms then do NO internal modulation/balancing: the wired MMC controller's
per-arm modulation index is turned into per-submodule insertion GATES (level +
carrier PWM + EXTERNAL sort-and-select), and each arm only integrates its
capacitors. Open it in the GUI and the scopes show the switched arm voltage
(multilevel staircase), the AC output, and the submodule caps balanced by the
external sort-and-select — the HIL/Simulink "I feed the gates, the model
represents" workflow, now selectable on the same MMC_ARM block.

The circuit is structurally identical to example 26 (the arm is a controlled
voltage source either way), so it runs through the GUI backend exactly like the
L3 example (gmin-stepped transient solve).

Run::  PYTHONPATH=src python3 scripts/build_mmc_gate_example.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "26_mmc_three_phase_l3_closed_loop.pulsim"
DST = ROOT / "examples" / "34_mmc_gate_driven.pulsim"


def main() -> None:
    project = json.loads(SRC.read_text())
    n_arm = 0
    for circ in project["circuits"].values():
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {}).update({
                    "model_fidelity": "External Gates",
                    "v_c0_spread": 300.0,   # seed a submodule imbalance so the
                                            # EXTERNAL sort-and-select is visible
                })
                n_arm += 1
    if not n_arm:
        raise SystemExit("No MMC_ARM found in example 26.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "34 MMC Gate-Driven — control 100% external (HIL-style)"
    project["modified"] = now

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_arm} arms → External Gates (gate-driven)")


if __name__ == "__main__":
    main()
