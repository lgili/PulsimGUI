"""Regression test for the thesis Fast-SVM switched M3C example (example 32).

Identical converter to example 31 (switched L3 arms) but the controller runs
the thesis's own modulation — ``control_mode="svm"``: the Fast-SVM cost
function (Etapas 3-4) selects, each switching period, the spanning-tree
connection minimising ``J = Σ(ε_xy + ΔV_xy)²``. Asserts the full six-stage
hierarchy holds under real switching: balanced regulated phase currents, the
nine branch capacitors kept together by the cost-function inter-module
balancing, and the submodule caps equalised within each module by the L3
sort-and-select.
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
from pulsimgui.services.m3c_control import M3CSvmController
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "32_m3c_thesis_svm.pulsim")


def _convert():
    if not EXAMPLE.is_file():
        pytest.skip("example 32 not present (run scripts/build_m3c_svm.py)")
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


def test_builds_svm_controller() -> None:
    built = _convert()
    ctrl = getattr(built, "_mmc_controller", None)
    assert isinstance(ctrl, M3CSvmController)
    assert len(ctrl.branches) == 9
    specs = [s for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    assert len(specs) == 9
    assert {s.get("level") for s in specs} == {"L3"}


def test_svm_switched_full_hierarchy() -> None:
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
    assert all(60.0 < a < 220.0 for a in in_amps), in_amps
    assert all(70.0 < a < 240.0 for a in out_amps), out_amps

    # The cost function actually selected real connections during the run.
    assert len(ctrl.last_connection) == 5

    vc = [float(h.v_C) for _, h in pairs]
    # Inter-module balancing (SVM cost function): the nine branch caps stay
    # BOUNDED together. The thesis cost function is discrete (one of 45 spanning-
    # tree connections per Ts) so its spread is choppier than the smooth modal
    # law — typically 1–3 kV with spikes to ~5 kV — but bounded (the row/column
    # stabilizer arrests the long-run divergence the pure cost function shows).
    assert (max(vc) - min(vc)) < 5000.0, vc
    assert 0.85 * 24000.0 < (sum(vc) / 9.0) < 1.15 * 24000.0
    # Intra-module balancing (L3 sort-and-select) keeps submodule spread small.
    spread = [abs(float(getattr(h, "v_C_spread", 0.0))) for _, h in pairs]
    assert max(spread) < 250.0, spread
