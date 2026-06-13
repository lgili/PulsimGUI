"""Examples 35–38 ship a pre-wired ELECTRICAL_SCOPE: every channel pin must
land on its probe's SIG net, and the channels must be DISTINCT nets (the
geometric-merge failure mode collapses them into one)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulsimgui.models.component import ComponentType
from pulsimgui.models.project import Project
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

CASES = [
    ("35_dab_phase_shift.pulsim", 3),
    ("36_llc_resonant.pulsim", 1),
    ("37_npc_three_level.pulsim", 2),
    ("38_pfc_boost_standalone.pulsim", 3),
    ("39_solar_pv_battery_charger.pulsim", 4),
]


@pytest.mark.parametrize(("filename", "n_channels"), CASES)
def test_scope_channels_bind_distinct_probe_nets(filename: str,
                                                 n_channels: int) -> None:
    path = _EXAMPLES / filename
    if not path.is_file():
        pytest.skip(f"{filename} not present (run its build script)")
    proj = Project.from_dict(json.loads(path.read_text()), path=path)
    circuit = proj.circuits[proj.active_circuit]
    node_map = build_node_map(circuit)
    alias = build_node_alias_map(circuit, node_map)

    scope = next(c for c in circuit.components.values()
                 if c.type == ComponentType.ELECTRICAL_SCOPE)
    assert len(scope.pins) == n_channels

    def net(comp, idx):
        raw = node_map.get((str(comp.id), idx))
        return alias.get(raw, raw)

    ch_nets = [net(scope, k) for k in range(n_channels)]
    assert all(n for n in ch_nets), ch_nets            # every channel wired
    assert len(set(ch_nets)) == n_channels, ch_nets    # all distinct

    # every channel net is fed by some probe's SIG pin
    probe_sig_nets = set()
    for c in circuit.components.values():
        if c.type in (ComponentType.VOLTAGE_PROBE_GND,
                      ComponentType.VOLTAGE_PROBE,
                      ComponentType.CURRENT_PROBE):
            sig_idx = len(c.pins) - 1 if c.type != ComponentType.CURRENT_PROBE else 2
            probe_sig_nets.add(net(c, sig_idx))
    for n in ch_nets:
        assert n in probe_sig_nets, (n, probe_sig_nets)
