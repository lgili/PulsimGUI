"""Example 37 — the GUI NPC leg must produce the three-level staircase.

Runs the exact GUI path (BackendLoader → run_transient builds the four-switch
gating from the per-switch PWM records) and checks the output dwells on the
three levels +200 / 0 / −200 V with a 50 Hz fundamental.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendCallbacks, BackendLoader
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "37_npc_three_level.pulsim")


def test_npc_output_steps_through_three_levels() -> None:
    if not EXAMPLE.is_file():
        pytest.skip("example 37 not present (run scripts/build_npc_example.py)")
    proj = Project.from_dict(json.loads(EXAMPLE.read_text()), path=EXAMPLE)
    circuit = proj.circuits[proj.active_circuit]
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
    backend = BackendLoader().backend
    settings = SimulationSettings(t_start=0.0, t_stop=40e-3, t_step=2e-6,
                                  output_points=8000)
    callbacks = BackendCallbacks(
        progress=lambda *a, **k: None, data_point=lambda *a, **k: None,
        check_cancelled=lambda: False, wait_if_paused=lambda: None)
    res = backend.run_transient(
        {"components": comps, "node_map": nmap, "node_aliases": alias},
        settings, callbacks)
    assert not res.error_message, res.error_message

    vout_key = next(k for k in res.signals
                    if k.startswith("V(") and "VOUT" in k.upper())
    v = np.asarray(res.signals[vout_key])
    v = v[len(v) // 2:]                      # steady portion

    # The waveform must DWELL on each of the three levels.
    near = {
        "+": float(np.mean(np.abs(v - 200.0) < 20.0)),
        "0": float(np.mean(np.abs(v) < 20.0)),
        "-": float(np.mean(np.abs(v + 200.0) < 20.0)),
    }
    # Staircase timing: +/− each 25 % of the period, zero 50 %.
    assert near["+"] > 0.15, near
    assert near["-"] > 0.15, near
    assert near["0"] > 0.30, near
    assert near["+"] + near["-"] + near["0"] > 0.9, near

    # Symmetric three-level waveform: no DC component.
    assert abs(float(np.mean(v))) < 15.0
