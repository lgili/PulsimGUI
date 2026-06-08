#!/usr/bin/env python3
"""Builder for example 25 — closed-loop 3-phase MMC DC→AC inverter.

Run from the repo root::

    PYTHONPATH=src python3 scripts/build_mmc_closed_loop_example.py

Reads ``examples/24_mmc_three_phase_controlled.pulsim`` (the open-loop stepping
stone) and re-emits the *same* power circuit with the MMC_CONTROLLER switched
to ``control_mode="closed_loop"``. That turns on:

  * arm-energy balancing — a slow PI loop holds the mean arm-capacitor voltage
    at ``vc_ref`` by commanding a DC circulating-current reference;
  * circulating-current suppression (CCSC) — a fast per-phase PI loop forces
    the circulating current to that reference, killing the 2nd-harmonic
    component that unbalances the arms;
  * insertion indices normalised by the *measured* cap voltage.

Unlike the open-loop example (whose arm caps run away in a few ms), the caps
now stay parked near 800 V, so the 3-phase AC output is clean and *sustained*
— run it as long as you like. Flip ``current_control`` on (with id_ref/iq_ref)
to also regulate the load current in the dq frame.

Build example 24 first (``build_mmc_controlled_example.py``); this script reads
its geometry so the closed-loop version inherits the GUI-robust wiring.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "24_mmc_three_phase_controlled.pulsim"
DST = ROOT / "examples" / "25_mmc_three_phase_closed_loop.pulsim"

# Closed-loop controller settings layered onto the open-loop block.
CLOSED_LOOP_PARAMS = {
    "control_mode": "closed_loop",
    "vdc_half": 400.0,
    "vc_ref": 800.0,
    "arm_inductance": 5.0e-3,
    "arm_resistance": 0.1,
    "modulation_index": 0.6,
    "frequency": 60.0,
    "current_control": False,   # energy + CCSC; AC voltage stays open-loop M·sin
    "id_ref": 0.0,
    "iq_ref": 0.0,
    "load_inductance": 10.0e-3,
    "load_resistance": 15.0,
    "sample_time": 1.0e-5,
}


def main() -> None:
    project = json.loads(SRC.read_text())
    circuits = list(project["circuits"].values())  # {"main": {...}}

    n_ctrl = 0
    for circ in circuits:
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_CONTROLLER":
                comp.setdefault("parameters", {}).update(CLOSED_LOOP_PARAMS)
                n_ctrl += 1
    if not n_ctrl:
        raise SystemExit("No MMC_CONTROLLER found in example 24 — build it first.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "25 MMC 3-Phase Closed-Loop — energy balancing + CCSC (L0)"
    project["modified"] = now

    # Longer window: with the caps held stable we can show sustained balanced AC.
    sim = project["simulation_settings"]
    sim["tstop"] = 0.05
    sim["output_points"] = 25000

    DST.write_text(json.dumps(project, indent=2))
    n_comp = sum(len(c.get("components", [])) for c in circuits)
    n_wire = sum(len(c.get("wires", [])) for c in circuits)
    print(f"wrote {DST.name}: {n_comp} components, {n_wire} wires, {n_ctrl} controller(s) → closed_loop")


if __name__ == "__main__":
    main()
