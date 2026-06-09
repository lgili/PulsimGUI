"""Regression test for the GUI gate-driven MMC example (example 34).

Confirms the converter builds gate-driven arms when an MMC_ARM's model_fidelity
is "External Gates" on a standard six-arm MMC (example 26's topology), with the
closed-loop controller wired. The arm is a controlled voltage source either way,
so example 34 runs through the GUI backend exactly like the L3 example 26
(gmin-stepped); the switched-physics validation lives in the standalone
``tests/test_examples/test_mmc_gate_driven.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pulsim as p
import pytest

from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.gate_driven_arm import GateDrivenArm
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "34_mmc_gate_driven.pulsim")


def _convert():
    if not EXAMPLE.is_file():
        pytest.skip("example 34 not present (run scripts/build_mmc_gate_example.py)")
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
    return CircuitConverter(make_compat_module(p)).build(
        {"components": comps, "node_map": nmap, "node_aliases": alias})


def test_converter_builds_gate_driven_mmc_arms() -> None:
    built = _convert()
    specs = [s for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    assert len(specs) == 6                                  # six MMC arms
    assert {s.get("level") for s in specs} == {"GATE"}
    assert all(isinstance(s["handle"], GateDrivenArm) for s in specs)
    # closed-loop controller wired (drives the gates externally)
    assert getattr(built, "_mmc_controller", None) is not None
    # each arm exposes per-submodule capacitor state + an external gate source
    for s in specs:
        arm = s["handle"]
        assert len(arm.v_C_per_sm) == arm.params.n_sm
        assert callable(arm.gate_source)
        assert not hasattr(arm, "m_b_fn")                   # no internal m_ref
