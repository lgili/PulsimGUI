"""Example 36 — the GUI LLC must simulate and sit at the resonant gain point.

At f_s = f_r the LLC tank gain is ≈1, so V_out ≈ V_in/(2·n) = 50 V. The test
runs the EXACT GUI path (BackendLoader → run_transient builds the per-switch
gating from the PWM records, radian phases) and checks the steady output.
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
           / "examples" / "36_llc_resonant.pulsim")


def test_llc_output_near_resonant_gain_point() -> None:
    if not EXAMPLE.is_file():
        pytest.skip("example 36 not present (run scripts/build_llc_example.py)")
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
    settings = SimulationSettings(t_start=0.0, t_stop=1.0e-3, t_step=5e-8,
                                  output_points=4000)
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
    v_ss = float(np.mean(v[3 * len(v) // 4:]))
    # gain ≈ 1 at resonance ⇒ V_out ≈ 400/(2·4) = 50 V; allow drops/ripple.
    assert 38.0 < v_ss < 60.0, v_ss