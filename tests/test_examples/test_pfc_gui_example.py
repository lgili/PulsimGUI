"""Example 38 — the standalone PFC boost must regulate the 400 V bus.

Runs the exact GUI path: the converter binds the PFC_BOOST_CONTROLLER to the
boost MOSFET through the PWM wire, the backend closes the cascaded loops, and
the bus must hold near the 400 V reference while drawing rectified-line
current.
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
           / "examples" / "38_pfc_boost_standalone.pulsim")


def _payload():
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
    return {"components": comps, "node_map": nmap, "node_aliases": alias}


def test_pfc_bus_regulates_near_400v() -> None:
    if not EXAMPLE.is_file():
        pytest.skip("example 38 not present (run scripts/build_pfc_boost_example.py)")
    backend = BackendLoader().backend
    settings = SimulationSettings(t_start=0.0, t_stop=60e-3, t_step=1e-6,
                                  output_points=6000)
    callbacks = BackendCallbacks(
        progress=lambda *a, **k: None, data_point=lambda *a, **k: None,
        check_cancelled=lambda: False, wait_if_paused=lambda: None)
    res = backend.run_transient(_payload(), settings, callbacks)
    assert not res.error_message, res.error_message

    vbus_key = next(k for k in res.signals
                    if k.startswith("V(") and "VBUS" in k.upper())
    v = np.asarray(res.signals[vbus_key])
    v_ss = v[2 * len(v) // 3:]
    mean = float(np.mean(v_ss))
    # regulated near the 400 V reference (allow soft-start tail + ripple)
    assert 360.0 < mean < 440.0, mean
    # 100 Hz bus ripple bounded (C=470 µF at ~1 A load → a few volts)
    assert float(np.max(v_ss) - np.min(v_ss)) < 60.0

    # inductor current flows and is non-negative (rectified-line side)
    il_key = next((k for k in res.signals if "IP_L" in k or "I(L_BOOST)" in k),
                  None)
    if il_key:
        i = np.asarray(res.signals[il_key])[len(v) // 2:]
        assert float(np.mean(i)) > 0.2          # real power drawn
