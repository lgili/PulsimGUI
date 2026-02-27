"""Catalog of component groups exposed in GUI insertion flows."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType


COMPONENT_LIBRARY = {
    "Circuit": [
        {"type": ComponentType.RESISTOR, "name": "Resistor", "shortcut": "R"},
        {"type": ComponentType.CAPACITOR, "name": "Capacitor", "shortcut": "C"},
        {"type": ComponentType.INDUCTOR, "name": "Inductor", "shortcut": "L"},
        {"type": ComponentType.TRANSFORMER, "name": "Transformer", "shortcut": "T"},
        {"type": ComponentType.VOLTAGE_SOURCE, "name": "Voltage", "shortcut": "V"},
        {"type": ComponentType.CURRENT_SOURCE, "name": "Current", "shortcut": "I"},
        {"type": ComponentType.GROUND, "name": "Ground", "shortcut": "G"},
        {"type": ComponentType.DIODE, "name": "Diode", "shortcut": "D"},
        {"type": ComponentType.ZENER_DIODE, "name": "Zener", "shortcut": "Z"},
        {"type": ComponentType.LED, "name": "LED", "shortcut": ""},
        {"type": ComponentType.MOSFET_N, "name": "NMOS", "shortcut": "M"},
        {"type": ComponentType.MOSFET_P, "name": "PMOS", "shortcut": "Shift+M"},
        {"type": ComponentType.IGBT, "name": "IGBT", "shortcut": "B"},
        {"type": ComponentType.SWITCH, "name": "Switch", "shortcut": "S"},
        {"type": ComponentType.SNUBBER_RC, "name": "Snubber", "shortcut": ""},
    ],
    "Signal & Control": [
        {"type": ComponentType.PWM_GENERATOR, "name": "PWM", "shortcut": "Ctrl+W"},
        {"type": ComponentType.GAIN, "name": "Gain", "shortcut": ""},
        {"type": ComponentType.PI_CONTROLLER, "name": "PI", "shortcut": "Ctrl+P"},
        {"type": ComponentType.SUM, "name": "Sum", "shortcut": ""},
        {"type": ComponentType.SUBTRACTOR, "name": "Subtractor", "shortcut": ""},
        {"type": ComponentType.VOLTAGE_PROBE, "name": "V Probe", "shortcut": ""},
        {"type": ComponentType.CURRENT_PROBE, "name": "I Probe", "shortcut": ""},
        {"type": ComponentType.ELECTRICAL_SCOPE, "name": "Scope", "shortcut": "Ctrl+E"},
        {"type": ComponentType.SIGNAL_MUX, "name": "Mux", "shortcut": "Ctrl+Alt+M"},
        {"type": ComponentType.SIGNAL_DEMUX, "name": "Demux", "shortcut": "Ctrl+Alt+D"},
    ],
    "Thermal": [
        {"type": ComponentType.THERMAL_SCOPE, "name": "Thermal Scope", "shortcut": "Ctrl+Shift+E"},
    ],
}


QUICK_ADD_COMPONENTS = [
    (ComponentType.RESISTOR, "Resistor", ["r", "res", "resistance", "ohm"]),
    (ComponentType.CAPACITOR, "Capacitor", ["c", "cap", "capacitance", "farad"]),
    (ComponentType.INDUCTOR, "Inductor", ["l", "ind", "inductance", "henry"]),
    (ComponentType.VOLTAGE_SOURCE, "Voltage Source", ["v", "vs", "volt", "voltage", "vdc"]),
    (ComponentType.CURRENT_SOURCE, "Current Source", ["i", "is", "curr", "current", "idc"]),
    (ComponentType.GROUND, "Ground", ["gnd", "ground", "0"]),
    (ComponentType.DIODE, "Diode", ["d", "diode", "rectifier"]),
    (ComponentType.ZENER_DIODE, "Zener Diode", ["zener", "breakdown"]),
    (ComponentType.LED, "LED", ["led", "light"]),
    (ComponentType.MOSFET_N, "N-Channel MOSFET", ["nmos", "nfet", "mosfet", "transistor"]),
    (ComponentType.MOSFET_P, "P-Channel MOSFET", ["pmos", "pfet"]),
    (ComponentType.IGBT, "IGBT", ["igbt", "transistor"]),
    (ComponentType.SWITCH, "Switch", ["sw", "switch"]),
    (ComponentType.TRANSFORMER, "Transformer", ["xfmr", "transformer", "trafo"]),
    (ComponentType.SNUBBER_RC, "RC Snubber", ["snubber", "rc", "clamp"]),
    (ComponentType.PWM_GENERATOR, "PWM", ["pwm", "pulse", "modulator"]),
    (ComponentType.GAIN, "Gain", ["gain", "k"]),
    (ComponentType.PI_CONTROLLER, "PI Controller", ["pi", "controller"]),
    (ComponentType.SUM, "Sum", ["sum", "adder", "sigma"]),
    (ComponentType.SUBTRACTOR, "Subtractor", ["subtract", "sub", "minus"]),
    (ComponentType.VOLTAGE_PROBE, "Voltage Probe", ["probe", "measure", "voltage"]),
    (ComponentType.CURRENT_PROBE, "Current Probe", ["probe", "measure", "current"]),
    (ComponentType.ELECTRICAL_SCOPE, "Electrical Scope", ["scope", "waveform", "plot"]),
    (ComponentType.SIGNAL_MUX, "Signal Mux", ["mux", "multiplexer"]),
    (ComponentType.SIGNAL_DEMUX, "Signal Demux", ["demux", "demultiplexer"]),
    (ComponentType.THERMAL_SCOPE, "Thermal Scope", ["thermal", "temp", "temperature"]),
]
