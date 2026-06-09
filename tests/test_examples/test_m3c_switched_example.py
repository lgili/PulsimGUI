"""Regression test for the switched (L3) closed-loop M3C example (example 31).

The nine arms run the L3 *detailed* submodule model (full-bridge cells + PSC-PWM
+ sort-and-select intra-module balancing) while the M3C closed-loop controller
runs the converter-level loops. Asserts the full control hierarchy holds under
real switching: balanced regulated phase currents, the nine branch capacitors
kept together (inter-module balancing, controller) and the submodule caps
equalised within each module (intra-module balancing, arm) — the seeded spread
collapsing toward zero.
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
           / "examples" / "31_m3c_switched_closed_loop.pulsim")


def _convert():
    if not EXAMPLE.is_file():
        pytest.skip("example 31 not present (run scripts/build_m3c_switched.py)")
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


def test_arms_are_switched_l3() -> None:
    built = _convert()
    specs = [s for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    assert len(specs) == 9
    assert {s.get("level") for s in specs} == {"L3"}
    assert isinstance(getattr(built, "_mmc_controller", None),
                      M3CClosedLoopController)


def test_switched_closed_loop_full_hierarchy() -> None:
    built = _convert()
    ctrl = built._mmc_controller
    specs = [s for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    pairs = [(s["name"], s["handle"]) for s in specs]
    b = built._builder
    src_idx = {nm: b.pool.branch_var_id_for_source(h.source_branch_id, b.graph)
               for nm, h in pairs}
    dt = 1.0e-5
    so, b_extra = mmc.make_mmc_arm_detailed_observers(
        b, [h for _, h in pairs], dt=dt)

    def observer(t, x):
        currents = {nm: float(x[src_idx[nm]]) for nm, _ in pairs}
        vcap = {nm: float(h.v_C) for nm, h in pairs}
        ctrl.update(float(t), currents, vcap)
        so(t, x)

    res = p.simulate(b, t_end=0.05, dt=dt, b_extra_fn=b_extra,
                     step_observer=observer)

    def amp(name):
        s = np.asarray(res.i(name))
        return float(math.sqrt(2.0) * np.std(s[len(s) // 2:]))

    in_amps = [amp(f"I_in_{X}") for X in "ABC"]
    out_amps = [amp(f"I_out_{y}") for y in "abc"]
    assert all(60.0 < a < 200.0 for a in in_amps), in_amps
    assert all(70.0 < a < 220.0 for a in out_amps), out_amps

    vc = [float(h.v_C) for _, h in pairs]
    # Inter-module balancing (controller): nine branch caps stay together.
    assert (max(vc) - min(vc)) < 3500.0, vc
    # Intra-module balancing (L3 sort-and-select): submodule spread, seeded at
    # 400 V, collapses well below the seed within each module.
    spread = [abs(float(getattr(h, "v_C_spread", 0.0))) for _, h in pairs]
    assert max(spread) < 200.0, spread
