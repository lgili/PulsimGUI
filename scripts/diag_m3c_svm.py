#!/usr/bin/env python3
"""Probe: SVM cost-function balancing strength vs k_svm and horizon."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pulsim as p
from pulsim import mmc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pulsimgui.models.project import Project  # noqa: E402
from pulsimgui.services.circuit_converter import CircuitConverter  # noqa: E402
from pulsimgui.services.pulsim_v0_compat import make_compat_module  # noqa: E402
from pulsimgui.utils.net_utils import (  # noqa: E402
    build_node_alias_map, build_node_map)

EXAMPLE = ROOT / "examples" / "32_m3c_thesis_svm.pulsim"


def _convert():
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


def run(k_svm: float, i_circ_max: float, t_end: float, ki_svm: float = 6.0):
    built = _convert()
    ctrl = built._mmc_controller
    ctrl.k_svm = k_svm
    ctrl.ki_svm = ki_svm
    ctrl.i_circ_max = i_circ_max
    specs = [s for s in built.nonlinear_observer_specs
             if s.get("kind") == "mmc_arm"]
    pairs = [(s["name"], s["handle"]) for s in specs]
    b = built._builder
    src_idx = {nm: b.pool.branch_var_id_for_source(h.source_branch_id, b.graph)
               for nm, h in pairs}
    dt = 1.0e-5
    so, b_extra = mmc.make_mmc_arm_detailed_observers(
        b, [h for _, h in pairs], dt=dt)
    spreads = []
    times = []

    def observer(t, x):
        currents = {nm: float(x[src_idx[nm]]) for nm, _ in pairs}
        vcap = {nm: float(h.v_C) for nm, h in pairs}
        ctrl.update(float(t), currents, vcap)
        so(t, x)
        if len(times) == 0 or t - times[-1] >= 2e-3:
            vc = [float(h.v_C) for _, h in pairs]
            spreads.append(max(vc) - min(vc))
            times.append(t)

    res = p.simulate(b, t_end=t_end, dt=dt, b_extra_fn=b_extra,
                     step_observer=observer)
    vc = [float(h.v_C) for _, h in pairs]

    def amp(name):
        s = np.asarray(res.i(name))
        return float(math.sqrt(2.0) * np.std(s[len(s) // 2:]))
    in_amps = [amp(f"I_in_{X}") for X in "ABC"]
    out_amps = [amp(f"I_out_{y}") for y in "abc"]
    return spreads, times, vc, in_amps, out_amps


if __name__ == "__main__":
    # Long-run boundedness at the chosen defaults (the modal law's whole point).
    for k, ki in ((0.6, 6.0),):
        sp, tm, vc, ia, oa = run(k, 120.0, 0.15, ki_svm=ki)
        traj = " ".join(f"{t*1e3:.0f}ms:{s/1e3:.2f}k" for t, s in
                        zip(tm[::5], sp[::5]))
        peak = max(sp[len(sp) // 3:])    # peak spread after the initial transient
        print(f"k_svm={k} ki_svm={ki}: final_spread={max(vc)-min(vc):.0f}V  "
              f"peak(after transient)={peak:.0f}V  mean={sum(vc)/9:.0f}V")
        print(f"   in={[f'{a:.0f}' for a in ia]}  out={[f'{a:.0f}' for a in oa]}")
        print(f"   traj: {traj}")
