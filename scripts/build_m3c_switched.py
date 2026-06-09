#!/usr/bin/env python3
"""Builder for example 31 — switched (L3) closed-loop M3C.

Reads ``examples/30_m3c_closed_loop.pulsim`` (closed-loop M3C, L0 average arms)
and re-emits the same converter + controller with every arm switched to
``model_fidelity = "L3 Detailed"`` — real submodules (N full-bridge cells with
clamped capacitors, PSC-PWM at f_carrier, sort-and-select intra-module
balancing) instead of the L0 average source.

The closed-loop M3C controller drives it unchanged: it reads each arm's
aggregate ``v_C`` and branch current and writes the nine modulation indices, so
the converter-level loops (input/output current, energy, inter-branch
capacitor balancing) transfer directly. The L3 arm's internal sort-and-select
then equalises the submodule caps WITHIN each module (the thesis's "Etapa 5"),
reported per branch via ``v_C_spread`` — completing the control hierarchy:
inter-module balancing (controller) + intra-module balancing (arm).

A small initial submodule imbalance is seeded (``v_c0_spread``) so the
intra-module balancing is visible converging on the SM-balance telemetry.

Run::  PYTHONPATH=src python3 scripts/build_m3c_switched.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "30_m3c_closed_loop.pulsim"
DST = ROOT / "examples" / "31_m3c_switched_closed_loop.pulsim"


def main() -> None:
    project = json.loads(SRC.read_text())
    n_arm = 0
    for circ in project["circuits"].values():
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {}).update({
                    "model_fidelity": "L3 Detailed",
                    "balancing": "sort_and_select",
                    "v_c0_spread": 400.0,   # seed a submodule imbalance so the
                                            # intra-module balancing is visible
                })
                n_arm += 1
    if not n_arm:
        raise SystemExit("No MMC_ARM found in example 30.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "31 M3C Switched (L3) Closed-Loop — submodule detail"
    project["modified"] = now
    project["simulation_settings"]["tstop"] = 0.08
    project["simulation_settings"]["output_points"] = 16000

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_arm} arms → L3 Detailed (switched), tstop=0.08s")


if __name__ == "__main__":
    main()
