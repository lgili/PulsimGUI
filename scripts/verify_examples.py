#!/usr/bin/env python3
"""Smoke-verify example .pulsim files through the EXACT GUI Run path.

For each file passed on argv: load the Project, build node/alias maps, and run
a SHORT transient through BackendLoader.run_transient (the same path the Run
button uses). Reports per-file JSON: ok / error / nan / empty. Short duration
is enough to catch converter failures, singular-mask errors and NaNs (which
fire at build / first steps); physics correctness is covered by dedicated
tests.

Usage::  PYTHONPATH=src python3 scripts/verify_examples.py FILE [FILE ...]
Outputs one JSON object to stdout: {"results": [{"file":..,"status":..,..}]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendCallbacks, BackendLoader
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

REPO = Path(__file__).resolve().parent.parent
EX_DIR = REPO / "examples"
MAX_STEPS = 400          # smoke: enough to clear build + initial masks


def _payload(circuit):
    nmr = build_node_map(circuit)
    alias = build_node_alias_map(circuit, nmr)
    comps, nmap = [], {}
    for c in circuit.components.values():
        cid = str(c.id)
        comps.append({
            "id": cid, "type": c.type.name, "name": c.name,
            "x": c.x, "y": c.y, "rotation": c.rotation,
            "parameters": dict(c.parameters),
            "pins": [{"index": pp.index, "name": pp.name, "x": pp.x, "y": pp.y}
                     for pp in c.pins],
        })
        nmap[cid] = [alias.get(nmr.get((cid, i), f"p_{cid}_{i}"),
                               nmr.get((cid, i), f"p_{cid}_{i}"))
                     for i in range(len(c.pins))]
    return {"components": comps, "node_map": nmap, "node_aliases": alias}


def verify_one(path: Path) -> dict:
    try:
        proj = Project.from_dict(json.loads(path.read_text()), path=path)
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "status": "load_error", "detail": str(exc)[:200]}

    try:
        circuit = proj.circuits[proj.active_circuit]
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "status": "no_circuit", "detail": str(exc)[:200]}

    if not circuit.components:
        return {"file": path.name, "status": "empty_circuit", "detail": ""}

    # configured timestep, capped to a short smoke window
    sim = getattr(proj, "simulation_settings", None) or {}
    dt = 1e-6
    try:
        dt = float((sim or {}).get("dt", 1e-6)) or 1e-6
    except Exception:  # noqa: BLE001
        pass
    t_stop = dt * MAX_STEPS

    try:
        backend = BackendLoader().backend
        settings = SimulationSettings(t_start=0.0, t_stop=t_stop, t_step=dt,
                                      output_points=min(MAX_STEPS, 400))
        callbacks = BackendCallbacks(
            progress=lambda *a, **k: None, data_point=lambda *a, **k: None,
            check_cancelled=lambda: False, wait_if_paused=lambda: None)
        res = backend.run_transient(_payload(circuit), settings, callbacks)
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "status": "exception", "detail": str(exc)[:200]}

    if res.error_message:
        return {"file": path.name, "status": "sim_error",
                "detail": str(res.error_message)[:200]}

    sigs = getattr(res, "signals", {}) or {}
    if not sigs:
        return {"file": path.name, "status": "no_signals", "detail": ""}

    nan_sigs = []
    for k, v in sigs.items():
        arr = np.asarray(v, dtype=float)
        if arr.size and not np.all(np.isfinite(arr)):
            nan_sigs.append(k)
    if nan_sigs:
        return {"file": path.name, "status": "nan",
                "detail": f"{len(nan_sigs)} non-finite signals: {nan_sigs[:5]}"}

    return {"file": path.name, "status": "ok",
            "detail": f"{len(sigs)} signals"}


def main(argv: list[str]) -> None:
    names = argv or sorted(p.name for p in EX_DIR.glob("*.pulsim"))
    results = [verify_one(EX_DIR / n) for n in names]
    print(json.dumps({"results": results}))


if __name__ == "__main__":
    main(sys.argv[1:])
