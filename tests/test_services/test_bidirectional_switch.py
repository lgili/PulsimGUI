"""Pin the BIDIRECTIONAL_SWITCH component end-to-end.

A matrix-converter cell needs a TRUE 4-quadrant bidirectional switch:
it must conduct current in both directions when ON and block voltage of
both polarities when OFF. A single ``MOSFET_N`` cannot do this — the GUI
shim always gives a MOSFET an anti-parallel body diode (to keep the
half-bridge "off" mask non-singular), and an array of those body diodes
forms an uncontrolled rectifier that clamps the output regardless of the
gate commands.

``BIDIRECTIONAL_SWITCH`` lowers instead to pulsim's ``add_switch`` — a
pure symmetric conductance ``i = (V_p1 - V_p2)·G`` with NO body diode:
``G = 1/R_on`` (both directions) when ON, ``G = 1/R_off`` (both
polarities) when OFF. These tests pin:

  1. The model layer: ComponentType, the P1/P2/G pin layout, the
     default R_on / R_off / v_th parameters, and the pin connection
     domains (P1/P2 circuit, G signal).
  2. The converter lowering: ONE switch bit (not two — no hidden body
     diode), and the device name registered in ``switch_indices`` so
     the C_BLOCK gate-drive path can bind it.
  3. The gate-drive inference: a C_BLOCK voltage output wired to the G
     pin emits exactly one ``cblock_gate_drive_descriptor`` binding the
     switch to that output, with the right v_threshold.
  4. The palette + graphics registration so the user can place it.
"""
from __future__ import annotations

import pulsim as p

from pulsimgui.models.component import (
    Component,
    ComponentType,
    DEFAULT_PARAMETERS,
    DEFAULT_PINS,
    pin_connection_domain,
)
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module


def _converter() -> CircuitConverter:
    return CircuitConverter(make_compat_module(p))


# ----------------------------------------------------------------------
# Model layer
# ----------------------------------------------------------------------

def test_default_pins_are_p1_p2_gate() -> None:
    pins = DEFAULT_PINS[ComponentType.BIDIRECTIONAL_SWITCH]
    assert [pin.name for pin in pins] == ["P1", "P2", "G"]
    # P1/P2 are the symmetric power terminals; G is the gate at the
    # bottom (index 2, NOT 1 like a MOSFET).
    assert pins[2].name == "G"


def test_default_parameters_carry_switch_conductances() -> None:
    params = DEFAULT_PARAMETERS[ComponentType.BIDIRECTIONAL_SWITCH]
    assert params["R_on"] == 0.05
    assert params["R_off"] == 1e9
    # The gate threshold the switch_fn compares the C_BLOCK output to.
    assert params["v_th"] == 3.0


def test_pin_connection_domains() -> None:
    comp = Component(
        id="s1", type=ComponentType.BIDIRECTIONAL_SWITCH, name="S1", x=0, y=0,
        parameters=dict(DEFAULT_PARAMETERS[ComponentType.BIDIRECTIONAL_SWITCH]),
    )
    assert pin_connection_domain(comp, 0) == "circuit"   # P1
    assert pin_connection_domain(comp, 1) == "circuit"   # P2
    assert pin_connection_domain(comp, 2) == "signal"    # G (gate)


# ----------------------------------------------------------------------
# Converter lowering — the heart of the fix
# ----------------------------------------------------------------------

def _switch_circuit():
    """V source → bidirectional switch → R load to gnd. Gate floats."""
    components = [
        {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
         "parameters": {"waveform": {"type": "dc", "value": 10.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": "s1", "type": "BIDIRECTIONAL_SWITCH", "name": "S1",
         "parameters": {"R_on": 0.05, "R_off": 1e9, "v_th": 3.0},
         "pins": [{"index": 0, "name": "P1"}, {"index": 1, "name": "P2"},
                  {"index": 2, "name": "G"}]},
        {"id": "r1", "type": "RESISTOR", "name": "R1",
         "parameters": {"resistance": 10.0},
         "pins": [{"index": 0, "name": "1"}, {"index": 1, "name": "2"}]},
        {"id": "g", "type": "GROUND", "name": "G", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
    ]
    node_map = {
        "v1": ["in", "0"],
        "s1": ["in", "out", "gate_net"],
        "r1": ["out", "0"],
        "g": ["0"],
    }
    return components, node_map


def test_lowers_to_a_single_switch_not_a_body_diode_pair() -> None:
    """The whole point: a bidirectional switch is ONE pulsim ``add_switch``
    branch (1 switch-mask bit). A MOSFET_N here would consume TWO bits
    (switch + anti-parallel body diode) and the body diode would
    rectify. One bit == no body diode."""
    components, node_map = _switch_circuit()
    circ = _converter().build({"components": components, "node_map": node_map})
    builder = circ.builder
    assert builder.graph.num_switches == 1, (
        "A bidirectional switch must lower to exactly ONE switch bit — "
        f"got {builder.graph.num_switches}. >1 means a body diode crept in."
    )
    assert builder.switch_index_of("S1") == 0


def test_switch_name_registered_for_gate_drive_binding() -> None:
    """The device name must appear in the shim's ``switch_indices`` map
    (keyed by name) so the backend's C_BLOCK gate-drive switch_fn can
    resolve the switch bit by name."""
    components, node_map = _switch_circuit()
    conv = _converter()
    circ = conv.build({"components": components, "node_map": node_map})
    switch_indices = dict(getattr(circ, "switch_indices", {}) or {})
    assert switch_indices.get("S1") == 0


# ----------------------------------------------------------------------
# Gate-drive inference: a C_BLOCK output drives the G pin
# ----------------------------------------------------------------------

def test_cblock_output_drives_bidirectional_switch_gate() -> None:
    """A C_BLOCK whose voltage output is wired to the switch's G pin
    must produce exactly one gate-drive descriptor binding S1 to that
    output index — proving the inference resolves the gate by the pin
    NAMED 'G' (index 2 here), not the MOSFET's hardcoded index 1."""
    components = [
        {"id": "v1", "type": "VOLTAGE_SOURCE", "name": "V1",
         "parameters": {"waveform": {"type": "dc", "value": 10.0}},
         "pins": [{"index": 0, "name": "+"}, {"index": 1, "name": "-"}]},
        {"id": "s1", "type": "BIDIRECTIONAL_SWITCH", "name": "S1",
         "parameters": {"R_on": 0.05, "R_off": 1e9, "v_th": 3.0},
         "pins": [{"index": 0, "name": "P1"}, {"index": 1, "name": "P2"},
                  {"index": 2, "name": "G"}]},
        {"id": "r1", "type": "RESISTOR", "name": "R1",
         "parameters": {"resistance": 10.0},
         "pins": [{"index": 0, "name": "1"}, {"index": 1, "name": "2"}]},
        {"id": "g", "type": "GROUND", "name": "G", "parameters": {},
         "pins": [{"index": 0, "name": "gnd"}]},
        # Voltage probe feeding the C_BLOCK input (a valid control-signal
        # source — the C_BLOCK input channel inference requires a probe,
        # not a raw electrical node).
        {"id": "vp", "type": "VOLTAGE_PROBE_GND", "name": "VP",
         "parameters": {"display_name": "vout", "scale": 1.0},
         "pins": [{"index": 0, "name": "IN"}, {"index": 1, "name": "OUT"}]},
        # C_BLOCK: 1 input (the probe), 1 output driving the gate.
        {"id": "cb", "type": "C_BLOCK", "name": "CTRL",
         "parameters": {
             "n_inputs": 1, "n_outputs": 1, "implementation": "source",
             "source_code": "out[0] = (t > 0.0) ? 15.0 : 0.0;",
             "sample_time": 1e-5, "n_states": 0,
         },
         "pins": [{"index": 0, "name": "IN0"}, {"index": 1, "name": "OUT0"}]},
    ]
    node_map = {
        "v1": ["in", "0"],
        "s1": ["in", "out", "gate_S1"],
        "r1": ["out", "0"],
        "g": ["0"],
        "vp": ["out", "vout_sig"],   # probe measures 'out', emits signal
        "cb": ["vout_sig", "gate_S1"],   # IN0 from probe, OUT0 drives gate
    }
    conv = _converter()
    circ = conv.build({"components": components, "node_map": node_map})
    descs = list(getattr(circ, "cblock_gate_drive_descriptors", []) or [])
    bound = {d["mosfet_name"]: d for d in descs}
    assert "S1" in bound, (
        "The bidirectional switch's gate (pin 'G', index 2) wired to a "
        "C_BLOCK output must emit a gate-drive descriptor."
    )
    desc = bound["S1"]
    assert desc["c_block_output_index"] == 0
    assert desc["v_threshold"] == 3.0


# ----------------------------------------------------------------------
# Palette + graphics registration
# ----------------------------------------------------------------------

def test_registered_in_quick_add_catalog() -> None:
    from pulsimgui.models.component_catalog import QUICK_ADD_COMPONENTS

    types = {ct for ct, _name, _aliases in QUICK_ADD_COMPONENTS}
    assert ComponentType.BIDIRECTIONAL_SWITCH in types


def test_graphics_factory_creates_bidirectional_item() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from pulsimgui.views.schematic.items import (
        BidirectionalSwitchItem,
        create_component_item,
    )

    comp = Component(
        id="s1", type=ComponentType.BIDIRECTIONAL_SWITCH, name="S1", x=0, y=0,
    )
    item = create_component_item(comp)
    assert isinstance(item, BidirectionalSwitchItem)
