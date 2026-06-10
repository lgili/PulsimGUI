"""PV panel + battery components — model, palette and simulated physics."""
from __future__ import annotations

import numpy as np
import pulsim as p

from pulsimgui.models.component import (
    DEFAULT_PARAMETERS,
    DEFAULT_PINS,
    Component,
    ComponentType,
)
from pulsimgui.models.component_catalog import COMPONENT_LIBRARY
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module

_PINS2 = [{"index": 0, "name": "+", "x": 0, "y": -20},
          {"index": 1, "name": "-", "x": 0, "y": 20}]


def _build(comps, node_map):
    return CircuitConverter(make_compat_module(p)).build(
        {"components": comps, "node_map": node_map, "node_aliases": {}})


def test_types_modelled_and_in_palette() -> None:
    for ctype in (ComponentType.PV_PANEL, ComponentType.BATTERY):
        assert ctype in DEFAULT_PINS and ctype in DEFAULT_PARAMETERS
        comp = Component(type=ctype, name="X1")
        assert len(comp.pins) == 2
    exposed = {e["type"] for grp in COMPONENT_LIBRARY.values() for e in grp}
    assert ComponentType.PV_PANEL in exposed
    assert ComponentType.BATTERY in exposed


def _pv_operating_point(r_load: float, irradiance: float = 1.0) -> tuple[float, float]:
    comps = [
        {"id": "pv", "type": "PV_PANEL", "name": "PV1",
         "parameters": {"isc": 8.0, "voc": 37.0, "rs": 0.3, "rsh": 300.0,
                        "irradiance": irradiance}, "pins": _PINS2},
        {"id": "r", "type": "RESISTOR", "name": "RL",
         "parameters": {"resistance": r_load}, "pins": _PINS2},
        {"id": "g", "type": "GROUND", "name": "GND", "parameters": {},
         "pins": [{"index": 0, "name": "gnd", "x": 0, "y": 0}]},
    ]
    node_map = {"pv": ["np", "0"], "r": ["np", "0"], "g": ["0"]}
    built = _build(comps, node_map)
    res = p.simulate(built._builder, t_end=1e-3, dt=1e-6)
    v = float(np.asarray(res.v("Nnp"))[-1])
    return v, v / r_load


def test_pv_short_circuit_region_delivers_isc() -> None:
    """Small load (left of the knee): the panel acts as the photocurrent."""
    v, i = _pv_operating_point(1.0)
    assert abs(i - 8.0) < 0.5                  # ≈ Isc
    assert v < 15.0                            # far below the knee


def test_pv_open_circuit_region_clamps_at_voc() -> None:
    """Huge load: the knee diode clamps the terminal near Voc."""
    v, _i = _pv_operating_point(10_000.0)
    assert 35.0 < v < 40.0                     # ≈ Voc


def test_pv_scales_with_irradiance() -> None:
    _v, i_full = _pv_operating_point(1.0, irradiance=1.0)
    _v, i_half = _pv_operating_point(1.0, irradiance=0.5)
    assert abs(i_half - i_full / 2) < 0.5


def test_battery_ocv_and_internal_drop() -> None:
    """48 V OCV, 0.05 Ω internal: 1 Ω load ⇒ V = 48·R/(R+Rint) ≈ 45.7 V."""
    comps = [
        {"id": "b", "type": "BATTERY", "name": "BAT1",
         "parameters": {"voltage": 48.0, "r_internal": 0.05},
         "pins": _PINS2},
        {"id": "r", "type": "RESISTOR", "name": "RL",
         "parameters": {"resistance": 1.0}, "pins": _PINS2},
        {"id": "g", "type": "GROUND", "name": "GND", "parameters": {},
         "pins": [{"index": 0, "name": "gnd", "x": 0, "y": 0}]},
    ]
    node_map = {"b": ["nb", "0"], "r": ["nb", "0"], "g": ["0"]}
    built = _build(comps, node_map)
    res = p.simulate(built._builder, t_end=1e-3, dt=1e-6)
    v = float(np.asarray(res.v("Nnb"))[-1])
    assert abs(v - 48.0 * 1.0 / 1.05) < 0.1
