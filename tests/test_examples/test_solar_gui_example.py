"""Example 39 — PV→boost→battery charger runs through the full GUI path.

Showcases the PV_PANEL + BATTERY components from W3.12: the panel must sit in
its current region (V_pv well below Voc), the boost must hold the bus at the
battery voltage, real charging current must flow into the pack, and PV power
must balance the battery power (lossless-ish boost).
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
           / "examples" / "39_solar_pv_battery_charger.pulsim")


def _run():
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
    settings = SimulationSettings(t_start=0.0, t_stop=30e-3, t_step=1e-6,
                                  output_points=4000)
    callbacks = BackendCallbacks(
        progress=lambda *a, **k: None, data_point=lambda *a, **k: None,
        check_cancelled=lambda: False, wait_if_paused=lambda: None)
    res = backend.run_transient(
        {"components": comps, "node_map": nmap, "node_aliases": alias},
        settings, callbacks)
    assert not res.error_message, res.error_message
    return res


def _ss(res, substr):
    for k in res.signals:
        if substr in k:
            v = np.asarray(res.signals[k])
            return float(np.mean(v[2 * len(v) // 3:]))
    raise KeyError(f"no signal containing {substr!r} in {list(res.signals)}")


def test_solar_charger_power_chain() -> None:
    if not EXAMPLE.is_file():
        pytest.skip("example 39 not present (run scripts/build_solar_example.py)")
    res = _run()

    v_pv = _ss(res, "NPVP")
    v_bus = _ss(res, "NVBUS")
    i_pv = _ss(res, "Is(IP_L)")
    i_batt = _ss(res, "Is(BAT1_E)")

    # PV loaded in its current region (below Voc=37) and delivering current
    assert 10.0 < v_pv < 37.0, v_pv
    assert i_pv > 2.0, i_pv
    # boost output clamped near the 48 V pack
    assert 44.0 < v_bus < 54.0, v_bus
    # real charging current into the battery
    assert abs(i_batt) > 1.0, i_batt
    # power balance PV→battery (boost is near-lossless; allow 25 %)
    p_pv = v_pv * i_pv
    p_batt = 48.0 * abs(i_batt)
    assert abs(p_pv - p_batt) / p_pv < 0.25, (p_pv, p_batt)
