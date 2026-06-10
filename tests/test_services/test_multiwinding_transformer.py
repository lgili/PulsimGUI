"""Multi-winding transformer — pin regeneration + converter lowering + sim.

The TRANSFORMER component gains ``n_secondaries`` (1–3): the model regenerates
the pin layout, and the converter lowers N secondaries to N ideal 2-winding
kernel transformers sharing the primary (exactly equivalent for an ideal TX).
"""
from __future__ import annotations

import math

import pulsim as p

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def test_pins_regenerate_with_n_secondaries() -> None:
    comp = Component(type=ComponentType.TRANSFORMER, name="T1")
    assert [pin.name for pin in comp.pins] == ["P1", "P2", "S1", "S2"]

    comp.parameters["n_secondaries"] = 2
    from pulsimgui.models.component import _synchronize_transformer
    _synchronize_transformer(comp)
    assert [pin.name for pin in comp.pins] == [
        "P1", "P2", "S1_1", "S1_2", "S2_1", "S2_2"]

    comp.parameters["n_secondaries"] = 99       # clamped to 3
    _synchronize_transformer(comp)
    assert comp.parameters["n_secondaries"] == 3
    assert len(comp.pins) == 8

    comp.parameters["n_secondaries"] = 1        # back to the classic layout
    _synchronize_transformer(comp)
    assert [pin.name for pin in comp.pins] == ["P1", "P2", "S1", "S2"]


def test_two_secondary_transformer_simulates_with_correct_ratios() -> None:
    """10 V AC primary; turns_ratio is N1/N2 (shim convention), so ratio 2
    ⇒ 5 V secondary and ratio 0.5 ⇒ 20 V secondary. lm large enough that the
    magnetizing branch doesn't load the 1 kHz source."""
    comps = [
        {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
         "parameters": {"waveform": {"type": "sine", "amplitude": 10.0,
                                     "frequency": 1000.0, "offset": 0.0,
                                     "phase": 0.0}},
         "pins": [{"index": 0, "name": "+", "x": 0, "y": -20},
                  {"index": 1, "name": "-", "x": 0, "y": 20}]},
        {"id": "t1", "type": "TRANSFORMER", "name": "T1",
         "parameters": {"turns_ratio": 2.0, "n_secondaries": 2,
                        "turns_ratio_2": 0.5, "lm": 10.0},
         "pins": [{"index": i, "name": n, "x": 0, "y": 0}
                  for i, n in enumerate(
                      ["P1", "P2", "S1_1", "S1_2", "S2_1", "S2_2"])]},
        {"id": "r1", "type": "RESISTOR", "name": "R1",
         "parameters": {"resistance": 100.0},
         "pins": [{"index": 0, "name": "1", "x": 0, "y": 0},
                  {"index": 1, "name": "2", "x": 0, "y": 0}]},
        {"id": "r2", "type": "RESISTOR", "name": "R2",
         "parameters": {"resistance": 100.0},
         "pins": [{"index": 0, "name": "1", "x": 0, "y": 0},
                  {"index": 1, "name": "2", "x": 0, "y": 0}]},
        {"id": "g1", "type": "GROUND", "name": "GND",
         "parameters": {},
         "pins": [{"index": 0, "name": "gnd", "x": 0, "y": 0}]},
    ]
    node_map = {
        "v1": ["nin", "0"],
        "t1": ["nin", "0", "ns1", "0", "ns2", "0"],
        "r1": ["ns1", "0"],
        "r2": ["ns2", "0"],
        "g1": ["0"],
    }
    built = CircuitConverter(make_compat_module(p)).build(
        {"components": comps, "node_map": node_map, "node_aliases": {}})
    res = p.simulate(built._builder, t_end=2e-3, dt=1e-6)

    import numpy as np
    half = len(res.times) // 2

    def amp(node: str) -> float:
        return float(np.sqrt(2.0) * np.std(np.asarray(res.v(node))[half:]))

    assert abs(amp("Nns1") - 5.0) < 0.5       # N1/N2 = 2.0 ⇒ step-down to 5 V
    assert abs(amp("Nns2") - 20.0) < 1.5      # N1/N2 = 0.5 ⇒ step-up to 20 V


def test_single_secondary_unchanged() -> None:
    """The classic 4-pin transformer path must be untouched."""
    comp = Component(type=ComponentType.TRANSFORMER, name="T1")
    assert comp.parameters.get("n_secondaries", 1) == 1
    assert len(comp.pins) == 4
