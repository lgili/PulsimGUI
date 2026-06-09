"""Regression test for the GUI-loadable M3C example (example 29).

Pins that ``examples/29_m3c_matrix_converter.pulsim`` keeps loading + converting
through the GUI pipeline into a well-posed circuit whose ``topology="m3c"``
controller drives the nine 3×3-matrix arms by name with the open-loop
feed-forward, producing balanced AC↔AC conversion with bounded capacitors.

This guards the converter's M3C support (``_build_m3c_overrides`` + the
arm-build box-filling) and the example build together — the two singular/
unstable build pitfalls fixed during development (a ground on a source
terminal; the sine ``phase`` in radians) must not regress.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pulsim as p
import pytest

from pulsimgui.models.circuit import _heal_double_rotated_components
from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "29_m3c_matrix_converter.pulsim")
ARM_NAMES = {f"M_{X}{y}" for X in "ABC" for y in "abc"}


def _load_circuit():
    if not EXAMPLE.is_file():
        pytest.skip("example 29 not present (run scripts/build_m3c_example.py)")
    proj = Project.from_dict(json.loads(EXAMPLE.read_text()), path=EXAMPLE)
    return proj.circuits[proj.active_circuit]


def _convert(circuit):
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
    built = conv.build({"components": comps, "node_map": nmap,
                        "node_aliases": alias})
    return built


def test_file_exists() -> None:
    assert EXAMPLE.is_file()


def test_loads_clean_and_builds_nine_overrides() -> None:
    """Loads without deformation and the M3C controller resolves all 9 arms."""
    circuit = _load_circuit()
    assert _heal_double_rotated_components(circuit) == 0
    n_arms = sum(1 for c in circuit.components.values()
                 if c.type.name == "MMC_ARM")
    assert n_arms == 9
    built = _convert(circuit)
    overrides = getattr(built, "mmc_mref_overrides", {})
    assert set(overrides) == ARM_NAMES
    # Each override is a live callable returning a sane modulation index.
    assert all(abs(overrides[n](0.005)) <= 1.0 for n in ARM_NAMES)


def test_simulates_balanced_ac_ac() -> None:
    """A short transient through the GUI-built circuit yields balanced
    sinusoidal currents on both sides and bounded capacitor voltages."""
    from pulsim import mmc

    built = _convert(_load_circuit())
    arm_h = [s["handle"] for s in getattr(built, "nonlinear_observer_specs", [])
             if s.get("kind") == "mmc_arm"]
    assert len(arm_h) == 9
    dt = 1.0e-5
    step_obs, b_extra = mmc.make_mmc_arms_observer(built._builder, arm_h, dt=dt)
    res = p.simulate(built._builder, t_end=0.06, dt=dt,
                     b_extra_fn=b_extra, step_observer=step_obs)

    def amp(name):
        s = np.asarray(res.i(name))
        return float(math.sqrt(2.0) * np.std(s[len(s) // 2:]))

    in_amps = [amp(f"I_in_{X}") for X in "ABC"]
    out_amps = [amp(f"I_out_{y}") for y in "abc"]
    # Balanced, non-trivial AC currents near the open-loop operating point
    # (input ≈105 A, output ≈155 A) — NOT the exploding circulating current.
    assert all(40.0 < a < 300.0 for a in in_amps), in_amps
    assert all(60.0 < a < 400.0 for a in out_amps), out_amps
    for amps in (in_amps, out_amps):
        mean = sum(amps) / 3.0
        assert (max(amps) - min(amps)) < 0.3 * mean, amps
    # Capacitors stay bounded (open-loop drift, no divergence).
    vc = [float(a.v_C) for a in arm_h]
    assert all(0.5 * 24000.0 < v < 1.5 * 24000.0 for v in vc), vc
