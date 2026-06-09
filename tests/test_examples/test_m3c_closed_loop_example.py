"""Regression test for the closed-loop M3C example (example 30).

Loads example 30 through the GUI pipeline, confirms the topology="m3c" +
control_mode="closed_loop" controller is built, and drives a short transient
with the same control observer the backend uses — asserting the closed loop
regulates balanced phase currents and holds the nine branch capacitors tightly
together (the open-loop drift removed).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pulsim as p
import pytest
from pulsim import mmc

from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.m3c_control import M3CClosedLoopController
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "30_m3c_closed_loop.pulsim")


def _convert():
    if not EXAMPLE.is_file():
        pytest.skip("example 30 not present (run scripts/build_m3c_closed_loop.py)")
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
    conv = CircuitConverter(make_compat_module(p))
    return conv.build({"components": comps, "node_map": nmap,
                       "node_aliases": alias})


def test_builds_closed_loop_controller() -> None:
    built = _convert()
    ctrl = getattr(built, "_mmc_controller", None)
    assert isinstance(ctrl, M3CClosedLoopController)
    assert len(ctrl.branches) == 9


def test_closed_loop_regulates_and_balances() -> None:
    built = _convert()
    ctrl = built._mmc_controller
    specs = [s for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    pairs = [(s["name"], s["handle"]) for s in specs]
    assert len(pairs) == 9
    b = built._builder
    src_idx = {nm: b.pool.branch_var_id_for_source(h.source_branch_id, b.graph)
               for nm, h in pairs}
    dt = 1.0e-5
    so_arms, b_extra = mmc.make_mmc_arms_observer(b, [h for _, h in pairs], dt=dt)

    def observer(t, x):
        currents = {nm: float(x[src_idx[nm]]) for nm, _ in pairs}
        vcap = {nm: float(h.v_C) for nm, h in pairs}
        ctrl.update(float(t), currents, vcap)
        so_arms(t, x)

    res = p.simulate(b, t_end=0.1, dt=dt, b_extra_fn=b_extra,
                     step_observer=observer)

    def amp(name):
        s = np.asarray(res.i(name))
        return float(math.sqrt(2.0) * np.std(s[len(s) // 2:]))

    in_amps = [amp(f"I_in_{X}") for X in "ABC"]
    out_amps = [amp(f"I_out_{y}") for y in "abc"]
    # Balanced, non-trivial regulated currents.
    assert all(80.0 < a < 200.0 for a in in_amps), in_amps
    assert all(80.0 < a < 220.0 for a in out_amps), out_amps
    assert (max(in_amps) - min(in_amps)) < 0.15 * (sum(in_amps) / 3.0)
    # Closed-loop holds the nine capacitors together (open-loop spread is ~6 kV;
    # the loop keeps it well under 3 kV around the 24 kV target).
    vc = [float(h.v_C) for _, h in pairs]
    assert (max(vc) - min(vc)) < 3000.0, vc
    assert 0.85 * 24000.0 < (sum(vc) / 9.0) < 1.15 * 24000.0
