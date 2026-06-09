#!/usr/bin/env python3
"""Builder for example 30 — closed-loop M3C matrix converter.

Reads ``examples/29_m3c_matrix_converter.pulsim`` (the open-loop M3C) and
re-emits the same 3×3 matrix with the ``M3C_Ctrl`` flipped to
``control_mode="closed_loop"`` and an output-current command (``id_ref``). The
converter then builds an ``M3CClosedLoopController`` that drives the nine arms
from measured branch currents + capacitor voltages: a per-branch current loop
regulates the input/output phase currents, a slow mean-cap-voltage loop sets
the input active current (energy), and a doubly-centred balancing loop keeps the
nine branch capacitors together — the M3C analogue of the open-loop ex24 →
closed-loop ex25 MMC progression.

Run::  PYTHONPATH=src python3 scripts/build_m3c_closed_loop.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "examples" / "29_m3c_matrix_converter.pulsim"
DST = ROOT / "examples" / "30_m3c_closed_loop.pulsim"

# Output d-axis current command [A] ≈ rated 2 MVA at 11 kV line.
ID_REF = 148.0


def main() -> None:
    project = json.loads(SRC.read_text())
    n_ctrl = 0
    for circ in project["circuits"].values():
        for comp in circ.get("components", []):
            if comp.get("type") == "MMC_CONTROLLER" and \
                    str(comp.get("parameters", {}).get("topology")) == "m3c":
                comp["parameters"].update({
                    "control_mode": "closed_loop",
                    "id_ref": ID_REF,     # output d-axis current [A]
                    "iq_ref": 0.0,        # output q-axis (reactive) current
                    "sample_time": 1.0e-5,
                    "soft_start_time": 1.0e-2,
                })
                n_ctrl += 1
    if not n_ctrl:
        raise SystemExit("No topology='m3c' MMC_CONTROLLER in example 29.")

    now = datetime.now().isoformat(timespec="seconds")
    project["name"] = "30 M3C Closed-Loop — dq current + energy + cap balancing"
    project["modified"] = now
    # A few cycles so the loops visibly settle.
    project["simulation_settings"]["tstop"] = 0.12
    project["simulation_settings"]["output_points"] = 12000

    DST.write_text(json.dumps(project, indent=2))
    print(f"wrote {DST.name}: {n_ctrl} M3C controller → closed_loop "
          f"(id_ref={ID_REF:.0f} A), tstop=0.12s")


if __name__ == "__main__":
    main()
