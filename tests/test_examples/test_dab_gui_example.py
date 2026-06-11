"""Example 35 — the GUI DAB must simulate and obey the phase-shift law.

Loads the .pulsim through the standard GUI pipeline (Project → node maps →
CircuitConverter) and runs the kernel: the gate pulses (diagonal pairs via
GOTO/FROM nets, secondary delayed by φ) must drive the 8 three-pin switches —
this also exercises the SWITCH CTL-pin fix end-to-end — and the transferred
power must match P = V1·V2'·φ(1−φ/π)/(2πfL) ≈ 12.5 kW.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pulsim as p
import pytest

from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE = (Path(__file__).resolve().parents[2]
           / "examples" / "35_dab_phase_shift.pulsim")


def _convert():
    if not EXAMPLE.is_file():
        pytest.skip("example 35 not present (run scripts/build_dab_example.py)")
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


def test_converts_with_eight_vcswitches() -> None:
    built = _convert()
    b = built._builder
    assert b.graph.num_switches >= 8          # the two full bridges


def test_dab_power_matches_theory_through_full_backend() -> None:
    """The exact GUI Run path: run_transient builds the gate switch_fn from
    the PWM generators (incl. the phase shift) and the power must follow the
    phase-shift law."""
    from pulsimgui.services.backend_adapter import (
        BackendCallbacks, BackendLoader,
    )
    from pulsimgui.services.simulation_service import SimulationSettings

    if not EXAMPLE.is_file():
        pytest.skip("example 35 not present")
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
    settings = SimulationSettings(t_start=0.0, t_stop=1.5e-3, t_step=2e-7,
                                  output_points=3000)
    callbacks = BackendCallbacks(
        progress=lambda *a, **k: None, data_point=lambda *a, **k: None,
        check_cancelled=lambda: False, wait_if_paused=lambda: None)
    res = backend.run_transient(
        {"components": comps, "node_map": nmap, "node_aliases": alias},
        settings, callbacks)
    assert not res.error_message, res.error_message

    sig = res.signals.get("Is(V_IN)") or res.signals.get("I(V_IN)")
    assert sig, f"V_IN current missing; have {list(res.signals)[:10]}"
    i_in = np.asarray(sig)[len(sig) // 2:]
    p_in = -float(np.mean(i_in)) * 400.0
    phi = math.pi / 4
    p_theory = (400.0 * 200.0 * 2.0) * phi * (1 - phi / math.pi) / (
        2 * math.pi * 20e3 * 60e-6)
    # GUI plumbing + output decimation; allow 20 %.
    assert abs(p_in - p_theory) / p_theory < 0.20, (p_in, p_theory)
