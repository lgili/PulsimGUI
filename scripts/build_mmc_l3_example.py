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
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "25_mmc_three_phase_closed_loop.pulsim"
DST = ROOT / "examples" / "26_mmc_three_phase_l3_closed_loop.pulsim"

_ARMS = [f"ARM_{u}{p}" for p in "ABC" for u in ("u", "l")]  # uA,lA,uB,lB,uC,lC


def _sm_balance_scope() -> dict:
    """A direct-signal scope on each arm's ``v_C_spread`` — the submodule-cap
    balance the L3 sort-and-select keeps tight (only L3 publishes this)."""
    return {
        "id": str(uuid.uuid4()),
        "type": "ELECTRICAL_SCOPE",
        "name": "Scope_SMBalance",
        "x": 820.0, "y": 560.0,
        "rotation": 0, "mirrored_h": False, "mirrored_v": False,
        "parameters": {
            "channel_count": 6,
            "channels": [
                {"signal": f"{a}.v_C_spread", "label": f"spread {a[4:]}", "overlay": True}
                for a in _ARMS
            ],
        },
        "pins": [
            {"index": i, "name": f"CH{i+1}", "x": -40.0, "y": -50.0 + i * 20.0}
            for i in range(6)
        ],
    }


def main() -> None:
    project = json.loads(SRC.read_text())
    circuits = list(project["circuits"].values())

    n_arm = n_ctrl = 0
    for circ in circuits:
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_ARM":
                comp.setdefault("parameters", {}).update({
                    "model_fidelity": "L3 Detailed",
                    "v_c0_spread": 60.0,   # seed a submodule imbalance so the
                                           # sort-and-select balancing is visible
                                           # converging to 0 on Scope_SMBalance
                })
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

    # Add a scope on the submodule-cap balance (L3-only telemetry).
    circuits[0]["components"].append(_sm_balance_scope())

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
