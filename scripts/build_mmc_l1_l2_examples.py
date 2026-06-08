#!/usr/bin/env python3
"""Builder for examples 27 (L1) and 28 (L2) — closed-loop 3-phase MMC at the
intermediate arm fidelities.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_mmc_l1_l2_examples.py

Both read ``examples/25_mmc_three_phase_closed_loop.pulsim`` and re-emit the
same circuit + controller with every arm switched to the target fidelity:

  * 27 — ``L1 Multilevel`` (level-resolved, per-level PWM)
  * 28 — ``L2 Equivalent`` (Thevenin-equivalent switching arm, dead-time aware)

These are the two rungs between L0 (average) and L3 (detailed). All four arm
models expose the same aggregate ``v_C`` + ``source_branch_id`` and integrate
as a controlled source via ``(step_observer, b_extra_fn)``, so the *same*
closed-loop controller (arm-energy balancing + circulating-current suppression
+ soft-start + dq output-current loop, id_ref = 15 A) drives them unchanged —
this just confirms it holds at every fidelity, not only L0 / L3. L1 / L2 carry
no per-submodule state, so there is no ``v_C_spread`` scope (that's L3-only).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "25_mmc_three_phase_closed_loop.pulsim"

VARIANTS = [
    ("L1 Multilevel", "27_mmc_three_phase_l1_closed_loop.pulsim",
     "27 MMC 3-Phase Closed-Loop L1 — multilevel arms"),
    ("L2 Equivalent", "28_mmc_three_phase_l2_closed_loop.pulsim",
     "28 MMC 3-Phase Closed-Loop L2 — equivalent switching arms"),
]


def build(fidelity: str, dst_name: str, display: str) -> None:
    project = json.loads(SRC.read_text())
    circuits = list(project["circuits"].values())

    n_arm = 0
    for circ in circuits:
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {})["model_fidelity"] = fidelity
                n_arm += 1
            elif comp.get("type") == "MMC_CONTROLLER":
                comp.setdefault("parameters", {}).update({
                    "current_control": True, "id_ref": 15.0, "iq_ref": 0.0,
                })
    if not n_arm:
        raise SystemExit("No MMC_ARM found in example 25 — build it first.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = display
    project["modified"] = now
    sim = project["simulation_settings"]
    sim["tstop"] = 0.05
    sim["output_points"] = 25000

    (ROOT / "examples" / dst_name).write_text(json.dumps(project, indent=2))
    print(f"wrote {dst_name}: {n_arm} arms → {fidelity}, dq current control, tstop=0.05s")


def main() -> None:
    for fidelity, dst_name, display in VARIANTS:
        build(fidelity, dst_name, display)


if __name__ == "__main__":
    main()
