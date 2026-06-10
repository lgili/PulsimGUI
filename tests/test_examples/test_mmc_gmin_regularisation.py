"""Switched-converter examples must run through the full GUI backend path.

Two converter families leave pulsim's PWL cache singular for masks it
PRE-ENUMERATES at build time — so they crash before any time-step, on a mask
the modulation may never even use:

* a three-phase MMC of ideal controlled-source arms (reactive leg loop floats,
  rank-deficient by one), and
* a direct matrix converter (CMC) of bidirectional switches (singular for any
  mask that opens an output column).

The converter's connectivity-based ghost-resistor healing can't see either
(every node looks grounded through the sources), and the observer-path
``p.simulate`` bypasses the Simulator's transient-gmin fallback — so without the
backend's gmin regulariser these examples fail with ``PwlStateSpaceCache:
numerically singular``. This pins that the regulariser keeps them runnable
end-to-end via ``run_transient`` (the exact GUI Run path).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import BackendCallbacks, BackendLoader
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

ROOT = Path(__file__).resolve().parents[2]


def _run(example: str, t_stop: float = 0.02):
    path = ROOT / "examples" / example
    if not path.is_file():
        pytest.skip(f"{example} not present")
    proj = Project.from_dict(json.loads(path.read_text()), path=path)
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
    # Use the real detected backend (correct version → C-Block path enabled).
    backend = BackendLoader().backend
    settings = SimulationSettings(t_start=0.0, t_stop=t_stop, t_step=2.0e-6,
                                  output_points=1000)
    cb = BackendCallbacks(progress=lambda *a, **k: None,
                          data_point=lambda *a, **k: None,
                          check_cancelled=lambda: False,
                          wait_if_paused=lambda: None)
    return backend.run_transient(
        {"components": comps, "node_map": nmap, "node_aliases": alias},
        settings, cb)


@pytest.mark.parametrize("example", [
    "25_mmc_three_phase_closed_loop.pulsim",      # MMC L0 average
    "26_mmc_three_phase_l3_closed_loop.pulsim",   # MMC L3 detailed
    "34_mmc_gate_driven.pulsim",                  # MMC gate-driven (External Gates)
    "25_cmc_switched_svm_cblock.pulsim",          # CMC matrix conv. (bidir switches)
])
def test_switched_converter_runs_via_backend(example: str) -> None:
    res = _run(example)
    # No singular-matrix (or any) error, and a populated time axis + signals.
    assert not res.error_message, res.error_message
    assert len(res.time or []) > 100
    assert len(res.signals or {}) > 0
    # at least one signal actually varies (the sim did real work)
    varied = any(
        (max(v) - min(v)) > 1e-6
        for v in res.signals.values() if isinstance(v, list) and v)
    assert varied
