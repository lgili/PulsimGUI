#!/usr/bin/env python3
"""Builder for example 26 — closed-loop 3-phase MMC with DETAILED (L3) arms.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_mmc_l3_example.py

Reads ``examples/25_mmc_three_phase_closed_loop.pulsim`` (the L0 closed-loop
inverter) and re-emits the *same* circuit + controller with every arm switched
to ``model_fidelity = "L3 Detailed"`` — real submodules (N caps + half-bridge
switches, PSC-PWM at f_carrier, sort-and-select submodule balancing) instead of
the L0 average source.

The full closed-loop controller drives it unchanged: arm-energy balancing +
circulating-current suppression + soft-start, AND the dq output-current loop
(``current_control=True``, ``id_ref=15 A``) regulating the load current. The L3
arm exposes the same aggregate ``v_C`` and ``source_branch_id`` the L0 arm does,
so the control law transfers directly. Submodule-level balancing is handled
*inside* each L3 arm (the modulator's sort-and-select), and the per-arm
``v_C_spread`` telemetry reports how tightly the submodule caps track.

L3 switches every submodule every step, but the pulsim detailed step is cheap
enough to run a few cycles (50 ms ≈ 3 cycles) and watch the current loop settle.
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

    n_arm = n_ctrl = 0
    for circ in circuits:
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {})["model_fidelity"] = "L3 Detailed"
                n_arm += 1
            elif comp.get("type") == "MMC_CONTROLLER":
                comp.setdefault("parameters", {}).update({
                    "current_control": True,   # dq output-current loop
                    "id_ref": 15.0,            # d-axis load-current reference [A]
                    "iq_ref": 0.0,
                })
                n_ctrl += 1
    if not n_arm:
        raise SystemExit("No MMC_ARM found in example 25 — build it first.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "26 MMC 3-Phase Closed-Loop L3 — dq current control (switching)"
    project["modified"] = now

    # A few cycles so the dq current loop visibly settles.
    sim = project["simulation_settings"]
    sim["tstop"] = 0.05
    sim["output_points"] = 25000

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_arm} arms → L3 Detailed, {n_ctrl} controller → dq "
          f"current control (id_ref=15 A), tstop={sim['tstop']}s")


if __name__ == "__main__":
    main()
