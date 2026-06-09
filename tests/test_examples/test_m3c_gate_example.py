"""Regression test for the GUI gate-driven M3C example (example 33).

Exercises the FULL GUI path: the converter builds gate-driven arms when an
MMC_ARM's model_fidelity is "External Gates", and the backend
(``_build_nonlinear_device_observers``) auto-wires their behavioural observers
+ the controller feedback — no manual observer wiring. Asserts the switched run
regulates balanced currents, the EXTERNAL sort-and-select collapses the seeded
submodule spread, and the cost function keeps the branch caps bounded.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pulsim as p
import pytest

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendInfo, PulsimBackend
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.gate_driven_arm import GateDrivenArm
from pulsimgui.services.m3c_control import M3CSvmController
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "33_m3c_gate_driven.pulsim")


def _convert():
    if not EXAMPLE.is_file():
        pytest.skip("example 33 not present (run scripts/build_m3c_gate_example.py)")
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
    mod = make_compat_module(p)
    built = CircuitConverter(mod).build(
        {"components": comps, "node_map": nmap, "node_aliases": alias})
    return mod, built


def test_converter_builds_gate_driven_arms() -> None:
    _mod, built = _convert()
    specs = [s for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    assert len(specs) == 9
    assert {s.get("level") for s in specs} == {"GATE"}
    assert all(isinstance(s["handle"], GateDrivenArm) for s in specs)
    assert isinstance(getattr(built, "_mmc_controller", None), M3CSvmController)
    # each arm carries per-submodule capacitor state (no aggregate lump)
    assert all(len(s["handle"].v_C_per_sm) == 6 for s in specs)


def test_backend_autowires_and_runs() -> None:
    """The backend auto-wires the gate-driven observers + controller feedback —
    the exact path the GUI 'Run' button takes."""
    mod, built = _convert()
    b = built._builder
    backend = PulsimBackend(mod, BackendInfo("pulsim", "Pulsim", "1.x",
                                             "available"))
    dt = 1.0e-5
    step_obs, b_extra = backend._build_nonlinear_device_observers(built, b, dt)
    assert callable(b_extra)
    assert len(step_obs) >= 2          # control + arm observers (+ recorder)

    def observer(t, x):
        for so in step_obs:
            so(t, x)

    res = p.simulate(b, t_end=0.04, dt=dt, b_extra_fn=b_extra,
                     step_observer=observer)

    def amp(name):
        s = np.asarray(res.i(name))
        return float(math.sqrt(2.0) * np.std(s[len(s) // 2:]))

    in_amps = [amp(f"I_in_{X}") for X in "ABC"]
    out_amps = [amp(f"I_out_{y}") for y in "abc"]
    assert all(60.0 < a < 200.0 for a in in_amps), in_amps
    assert all(70.0 < a < 230.0 for a in out_amps), out_amps

    specs = [s for s in built.nonlinear_observer_specs
             if s.get("kind") == "mmc_arm"]
    vc = [float(s["handle"].v_C) for s in specs]
    spread = [float(s["handle"].v_C_spread) for s in specs]
    # external sort-and-select collapses the seeded 600 V submodule spread
    assert max(spread) < 150.0, spread
    # inter-module (cost function) bounded; mean near the 24 kV target
    assert (max(vc) - min(vc)) < 6000.0, vc
    assert 0.85 * 24000.0 < (sum(vc) / 9.0) < 1.15 * 24000.0
