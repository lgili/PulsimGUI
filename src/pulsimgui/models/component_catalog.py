"""Catalog of component groups exposed in GUI insertion flows."""

from __future__ import annotations

from pulsimgui.models.component import ComponentType

COMPONENT_LIBRARY = {
    "Circuit": [
        {"type": ComponentType.RESISTOR, "name": "Resistor", "shortcut": "R"},
        {"type": ComponentType.CAPACITOR, "name": "Capacitor", "shortcut": "C"},
        {"type": ComponentType.INDUCTOR, "name": "Inductor", "shortcut": "L"},
        {"type": ComponentType.SATURABLE_INDUCTOR, "name": "Sat. Inductor", "shortcut": ""},
        {"type": ComponentType.HYSTERETIC_INDUCTOR, "name": "Hyst. Inductor", "shortcut": ""},
        {"type": ComponentType.COUPLED_INDUCTOR, "name": "Coupled Inductor", "shortcut": ""},
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
        {"type": ComponentType.CONSTANT, "name": "Constant", "shortcut": "Ctrl+K"},
        {"type": ComponentType.PWM_GENERATOR, "name": "PWM", "shortcut": "Ctrl+W"},
        {"type": ComponentType.C_BLOCK, "name": "C-Block", "shortcut": ""},
        {"type": ComponentType.GAIN, "name": "Gain", "shortcut": ""},
        {"type": ComponentType.PI_CONTROLLER, "name": "PI", "shortcut": "Ctrl+P"},
        {"type": ComponentType.SUM, "name": "Sum", "shortcut": ""},
        {"type": ComponentType.SUBTRACTOR, "name": "Subtractor", "shortcut": ""},
        {"type": ComponentType.LIMITER, "name": "Limiter", "shortcut": ""},
        {"type": ComponentType.VOLTAGE_PROBE, "name": "V Probe", "shortcut": ""},
        {"type": ComponentType.VOLTAGE_PROBE_GND, "name": "V Probe (GND)", "shortcut": ""},
        {"type": ComponentType.CURRENT_PROBE, "name": "I Probe", "shortcut": ""},
        {"type": ComponentType.ELECTRICAL_SCOPE, "name": "Scope", "shortcut": "Ctrl+E"},
        {"type": ComponentType.SIGNAL_MUX, "name": "Mux", "shortcut": "Ctrl+Alt+M"},
        {"type": ComponentType.SIGNAL_DEMUX, "name": "Demux", "shortcut": "Ctrl+Alt+D"},
        {"type": ComponentType.GOTO_LABEL, "name": "Goto", "shortcut": ""},
        {"type": ComponentType.FROM_LABEL, "name": "From", "shortcut": ""},
    ],
    "Three-Phase / Vector Control": [
        {"type": ComponentType.THREE_PHASE_SOURCE, "name": "3φ Src", "shortcut": ""},
        {"type": ComponentType.CLARKE_TRANSFORM, "name": "Clarke", "shortcut": ""},
        {"type": ComponentType.INVERSE_CLARKE_TRANSFORM, "name": "iClarke", "shortcut": ""},
        {"type": ComponentType.PARK_TRANSFORM, "name": "Park", "shortcut": ""},
        {"type": ComponentType.INVERSE_PARK_TRANSFORM, "name": "iPark", "shortcut": ""},
        {"type": ComponentType.PLL, "name": "PLL", "shortcut": ""},
        {"type": ComponentType.SVM, "name": "SVM", "shortcut": ""},
    ],
    "Motors & Drives": [
        {"type": ComponentType.THREE_PHASE_VSI, "name": "3φ VSI", "shortcut": ""},
        {"type": ComponentType.DC_MOTOR, "name": "DC Motor", "shortcut": ""},
        {"type": ComponentType.PMSM_STEADY_STATE, "name": "PMSM ss", "shortcut": ""},
        {"type": ComponentType.PMSM, "name": "PMSM dyn", "shortcut": ""},
        {"type": ComponentType.INDUCTION_MOTOR, "name": "Induction", "shortcut": ""},
        {"type": ComponentType.THREE_PHASE_RL_LOAD, "name": "3φ RL", "shortcut": ""},
        # Drop-in field-oriented-control block. Wire SP ← speed reference,
        # FB ← PMSM SIG bus, and the converter auto-binds the 3φ VSI.
        {"type": ComponentType.FOC_CONTROLLER, "name": "FOC Drive", "shortcut": ""},
    ],
    "Power Conversion": [
        {"type": ComponentType.SINGLE_PHASE_DIODE_BRIDGE, "name": "1φ Bridge", "shortcut": ""},
        {"type": ComponentType.THREE_PHASE_DIODE_BRIDGE, "name": "3φ Bridge", "shortcut": ""},
        {"type": ComponentType.MMC_CELL, "name": "MMC Cell", "shortcut": ""},
        {"type": ComponentType.MMC_ARM, "name": "MMC Arm", "shortcut": ""},
        # Closed-loop boost PFC controller (CCM, 240–1000 W defaults).
        # Wire VBUS ← bus voltage probe, IL ← inductor current probe,
        # VAC ← rectified-line voltage probe. Converter auto-detects the
        # boost MOSFET by topology.
        {"type": ComponentType.PFC_BOOST_CONTROLLER, "name": "PFC Boost", "shortcut": ""},
    ],
    "Thermal": [
        {"type": ComponentType.THERMAL_SCOPE, "name": "Thermal Scope", "shortcut": "Ctrl+Shift+E"},
    ],
    "Hierarchy": [
        # Port marker for subcircuit editing. Only meaningful when
        # placed inside a SubcircuitDefinition's body — at root it
        # silently no-ops. Kept always-visible so the user can drop
        # one in after descending without re-opening the palette.
        {"type": ComponentType.SUBCIRCUIT_PORT, "name": "Port", "shortcut": ""},
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
    (ComponentType.SATURABLE_INDUCTOR, "Saturable Inductor", ["sat", "saturable", "nonlinear", "magnetic", "core", "lsat"]),
    (ComponentType.COUPLED_INDUCTOR, "Coupled Inductor", ["coupled", "coupling", "mutual", "lm"]),
    (ComponentType.SNUBBER_RC, "RC Snubber", ["snubber", "rc", "clamp"]),
    (ComponentType.PWM_GENERATOR, "PWM", ["pwm", "pulse", "modulator"]),
    (ComponentType.C_BLOCK, "C-Block", ["c", "cblock", "c-block", "custom", "dll", "so", "dylib"]),
    (ComponentType.GAIN, "Gain", ["gain", "k"]),
    (ComponentType.PI_CONTROLLER, "PI Controller", ["pi", "controller"]),
    (ComponentType.SUM, "Sum", ["sum", "adder", "sigma"]),
    (ComponentType.SUBTRACTOR, "Subtractor", ["subtract", "sub", "minus"]),
    (ComponentType.CONSTANT, "Constant", ["const", "constant", "ref", "reference", "value"]),
    (ComponentType.LIMITER, "Limiter", ["limiter", "clamp", "limit", "sat", "saturator"]),
    (ComponentType.VOLTAGE_PROBE, "Voltage Probe", ["probe", "measure", "voltage"]),
    (ComponentType.VOLTAGE_PROBE_GND, "Voltage Probe (GND)", ["probe", "measure", "voltage", "gnd"]),
    (ComponentType.CURRENT_PROBE, "Current Probe", ["probe", "measure", "current"]),
    (ComponentType.ELECTRICAL_SCOPE, "Electrical Scope", ["scope", "waveform", "plot"]),
    (ComponentType.SIGNAL_MUX, "Signal Mux", ["mux", "multiplexer"]),
    (ComponentType.SIGNAL_DEMUX, "Signal Demux", ["demux", "demultiplexer"]),
    (ComponentType.GOTO_LABEL, "Goto Label", ["goto", "net", "label"]),
    (ComponentType.FROM_LABEL, "From Label", ["from", "net", "label"]),
    (ComponentType.THERMAL_SCOPE, "Thermal Scope", ["thermal", "temp", "temperature"]),
    # Three-phase / vector control (Pulsim Phase 28)
    (ComponentType.THREE_PHASE_SOURCE, "Three-Phase Source", ["3 phase", "three phase", "3 phase source", "grid", "vab", "vac", "abc", "trifasico", "trifásico"]),
    (ComponentType.THREE_PHASE_VSI, "3-Phase VSI", ["vsi", "3 phase inverter", "three phase inverter", "spwm", "inverter", "6 switch", "inversor trifasico", "inversor", "vsi trifasico", "voltage source inverter"]),
    (ComponentType.DC_MOTOR, "DC Motor", ["dc motor", "motor", "armature", "rotor", "back-emf", "shaft", "torque", "drive", "motor cc", "motor dc"]),
    (ComponentType.PMSM_STEADY_STATE, "PMSM (steady-state)", ["pmsm", "permanent magnet", "synchronous motor", "synch motor", "brushless", "bldc", "motor pmsm", "motor sync"]),
    (ComponentType.PMSM, "PMSM (dynamic)", ["pmsm dynamic", "pmsm dq", "pmsm motor", "permanent magnet dynamic", "synchronous dynamic", "motor pmsm dinamico", "dynamic pmsm", "rotor inertia", "motor sync dinamico"]),
    (ComponentType.THREE_PHASE_RL_LOAD, "3-Phase RL Load", ["3 phase load", "three phase load", "rl load", "carga trifasica", "carga 3 fases", "star load", "delta load", "y load", "wye load"]),
    (ComponentType.CLARKE_TRANSFORM, "Clarke Transform", ["clarke", "abc", "alpha", "beta", "three phase", "3 phase"]),
    (ComponentType.INVERSE_CLARKE_TRANSFORM, "Inverse Clarke", ["inverse clarke", "alpha beta abc", "iclarke"]),
    (ComponentType.PARK_TRANSFORM, "Park Transform", ["park", "dq", "dq0", "rotating", "three phase"]),
    (ComponentType.INVERSE_PARK_TRANSFORM, "Inverse Park", ["inverse park", "ipark", "dq abc"]),
    (ComponentType.PLL, "PLL", ["pll", "phase lock", "grid sync", "synchronization"]),
    (ComponentType.SVM, "SVM", ["svm", "space vector", "svpwm", "modulation", "inverter"]),
    # Power conversion bridges & MMC sub-modules
    (ComponentType.SINGLE_PHASE_DIODE_BRIDGE, "Single-Phase Diode Bridge",
        ["bridge", "rectifier", "diode bridge", "graetz", "single phase", "1 phase",
         "monofasico", "monofásico", "ponte de diodo", "ponte retificadora",
         "retificador", "full wave", "ac dc"]),
    (ComponentType.THREE_PHASE_DIODE_BRIDGE, "Three-Phase Diode Bridge",
        ["bridge", "rectifier", "diode bridge", "three phase", "3 phase",
         "trifasico", "trifásico", "ponte trifasica", "ponte retificadora",
         "6 pulse", "retificador trifasico", "ac dc"]),
    (ComponentType.MMC_CELL, "MMC Sub-Module Cell",
        ["mmc", "half bridge", "full bridge", "submodule", "sub-module", "cell",
         "modular multilevel", "celula", "célula", "ponte h", "hvdc",
         "media ponte", "ponte completa"]),
    (ComponentType.MMC_ARM, "MMC Arm (L0..L3)",
        ["mmc", "arm", "braço", "braco", "modular multilevel", "hvdc",
         "averaged", "average value", "multilevel", "equivalent",
         "detailed", "l0", "l1", "l2", "l3", "thevenin",
         "n submodules", "cadeia"]),
    # Dedicated control blocks (wired alternatives to the legacy C_BLOCK
    # markers — visible pins, editable parameters, auto-detected bindings).
    (ComponentType.FOC_CONTROLLER, "FOC Drive Controller",
        ["foc", "field oriented", "vector control", "motor control",
         "pmsm drive", "speed loop", "current loop", "id iq", "park",
         "controle vetorial", "acionamento", "controle de motor",
         "drive pmsm", "ipd"]),
    (ComponentType.PFC_BOOST_CONTROLLER, "PFC Boost Controller",
        ["pfc", "power factor correction", "boost pfc", "boost",
         "ccm", "dcm", "fator de potencia", "correção fator potencia",
         "elevador", "input current shaping", "sine reference",
         "voltage loop", "current loop", "cascaded pi"]),
]


# Map every ComponentType to its long-form descriptive name (used for
# schematic-canvas hover tooltips and palette card tooltips). Built once
# from QUICK_ADD_COMPONENTS so the descriptions stay in one place; the
# short palette labels live in COMPONENT_LIBRARY above.
_DESCRIPTIVE_NAMES: dict[ComponentType, str] = {
    ct: name for ct, name, _aliases in QUICK_ADD_COMPONENTS
}


def get_descriptive_name(comp_type: ComponentType) -> str:
    """Return the long-form name for ``comp_type``.

    Used by the schematic canvas to surface the full component name on
    hover (vs. the short label rendered in the library palette card).
    Falls back to a title-cased version of the enum name for any type
    that isn't catalogued in QUICK_ADD_COMPONENTS.
    """
    cached = _DESCRIPTIVE_NAMES.get(comp_type)
    if cached:
        return cached
    return comp_type.name.replace("_", " ").title()
