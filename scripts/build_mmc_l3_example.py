#!/usr/bin/env python3
"""Builder for example 26 — closed-loop 3-phase MMC with DETAILED (L3) arms.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_mmc_l3_example.py

Reads ``examples/25_mmc_three_phase_closed_loop.pulsim`` (the L0 closed-loop
inverter) and re-emits the *same* circuit + controller with every arm switched
to ``model_fidelity = "L3 Detailed"`` — real submodules (N caps + half-bridge
switches, PSC-PWM at f_carrier, sort-and-select submodule balancing) instead of
the L0 average source.

The same closed-loop controller (arm-energy balancing + circulating-current
suppression + soft-start) drives it unchanged: the L3 arm exposes the same
aggregate ``v_C`` and ``source_branch_id`` the L0 arm does, so the control law
transfers directly. The submodule-level balancing is handled *inside* each L3
arm (the modulator's sort-and-select), and the per-arm ``v_C_spread`` telemetry
reports how tightly the submodule caps track each other.

L3 switches every submodule every step, so it's much heavier than L0 — the
window is kept short (20 ms ≈ 1.2 cycles) to keep the run quick while still
showing stable caps + balanced AC.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "25_mmc_three_phase_closed_loop.pulsim"
DST = ROOT / "examples" / "26_mmc_three_phase_l3_closed_loop.pulsim"


def main() -> None:
    project = json.loads(SRC.read_text())
    circuits = list(project["circuits"].values())

    n_arm = 0
    for circ in circuits:
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {})["model_fidelity"] = "L3 Detailed"
                n_arm += 1
    if not n_arm:
        raise SystemExit("No MMC_ARM found in example 25 — build it first.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "26 MMC 3-Phase Closed-Loop — DETAILED L3 arms (switching)"
    project["modified"] = now

    # L3 switches every submodule each step → keep the window short.
    sim = project["simulation_settings"]
    sim["tstop"] = 0.02
    sim["output_points"] = 10000

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_arm} arms → L3 Detailed, tstop={sim['tstop']}s")


if __name__ == "__main__":
    main()
