#!/usr/bin/env python3
"""Generate the gallery of canonical converter examples.

Produces `.pulsim` project files for the major power-electronics
converter topologies Pulsim supports, ready for the user to open in
PulsimGui and run end-to-end. This is the GUI-side complement to the
``benchmarks/circuits/*.yaml`` files in the Pulsim runtime repo —
same topologies, same parameters, but laid out for a clean schematic
view.

Run from the PulsimGUI repo root::

    PYTHONPATH=src python3 scripts/generate_examples.py

The script writes into ``examples/gallery/`` and overwrites existing
files. Each generated example loads cleanly, simulates end-to-end on
the configured solver, and is wired so the user can press Run
straight away.

Architecture: every topology is a single ``ExampleBuilder`` instance
that knows its components + wires + simulation settings. A small
``ComponentBuilder`` helper keeps pin-aware connection bookkeeping
out of the topology code.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pulsimgui.models.circuit import Circuit  # noqa: E402
from pulsimgui.models.component import Component, ComponentType, Pin  # noqa: E402
from pulsimgui.models.project import Project  # noqa: E402
from pulsimgui.models.wire import Wire, WireConnection, WireSegment  # noqa: E402


GRID = 20.0  # canvas grid step (matches PulsimGui's PIN_GRID_STEP)


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


@dataclass
class PlacedComponent:
    """A component already placed on the canvas — keeps the absolute pin
    coordinates handy for downstream wire building."""

    component: Component
    x: float
    y: float

    # Aliases let the topology code refer to pins by their conventional
    # electrical names (e.g. ``"1"``/``"2"`` for caps, or ``"gnd"``) when
    # the underlying ComponentType uses different glyphs (``"+"``/``"-"``).
    _PIN_ALIASES = {
        ComponentType.CAPACITOR: {"1": "+", "2": "-"},
        ComponentType.VOLTAGE_SOURCE: {"1": "+", "2": "-"},
        ComponentType.GROUND: {"GND": "gnd"},
    }

    def _resolve_pin(self, key: str | int) -> str | int:
        if isinstance(key, str):
            aliases = self._PIN_ALIASES.get(self.component.type, {})
            return aliases.get(key, key)
        return key

    def pin_pos(self, name_or_index: str | int) -> tuple[float, float]:
        key = self._resolve_pin(name_or_index)
        for i, p in enumerate(self.component.pins):
            if (isinstance(key, int) and i == key) or \
               (isinstance(key, str) and p.name == key):
                return (self.x + p.x, self.y + p.y)
        raise KeyError(f"{self.component.name} has no pin {name_or_index}")

    def pin_index(self, name: str) -> int:
        key = self._resolve_pin(name)
        for i, p in enumerate(self.component.pins):
            if p.name == key:
                return i
        raise KeyError(f"{self.component.name} has no pin named {name}")


@dataclass
class CircuitBuilder:
    """High-level circuit builder that handles placement + wiring."""

    name: str
    components: list[PlacedComponent] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)

    def place(
        self,
        type_: ComponentType,
        name: str,
        x: float,
        y: float,
        *,
        rotation: int = 0,
        parameters: dict[str, Any] | None = None,
    ) -> PlacedComponent:
        from pulsimgui.models.component import DEFAULT_PARAMETERS, DEFAULT_PINS

        pins = [Pin(p.index, p.name, p.x, p.y) for p in DEFAULT_PINS.get(type_, [])]
        params = dict(DEFAULT_PARAMETERS.get(type_, {}))
        if parameters:
            params.update(parameters)

        comp = Component(type=type_, name=name, x=x, y=y, rotation=rotation,
                         pins=pins, parameters=params)
        placed = PlacedComponent(component=comp, x=x, y=y)
        self.components.append(placed)
        return placed

    def wire(
        self,
        a: PlacedComponent, a_pin: str,
        b: PlacedComponent, b_pin: str,
        *, label: str = "",
    ) -> Wire:
        """Connect ``a.<a_pin>`` to ``b.<b_pin>`` with a 2-segment
        right-angle wire. Uses the simpler of the two L-shapes."""
        ax, ay = a.pin_pos(a_pin)
        bx, by = b.pin_pos(b_pin)

        segments: list[WireSegment] = []
        if abs(ax - bx) < 0.5 or abs(ay - by) < 0.5:
            segments.append(WireSegment(ax, ay, bx, by))
        else:
            # L-shape — pick the elbow that keeps the path closer to the
            # midpoint visually.
            ex, ey = bx, ay  # default elbow: out horizontally first
            segments.append(WireSegment(ax, ay, ex, ey))
            segments.append(WireSegment(ex, ey, bx, by))

        wire = Wire(
            id=uuid4(),
            segments=segments,
            start_connection=WireConnection(a.component.id, a.pin_index(a_pin)),
            end_connection=WireConnection(b.component.id, b.pin_index(b_pin)),
            alias=label,
        )
        self.wires.append(wire)
        return wire

    def to_circuit(self) -> Circuit:
        ckt = Circuit(name=self.name)
        for placed in self.components:
            ckt.components[placed.component.id] = placed.component
        for w in self.wires:
            ckt.wires[w.id] = w
        return ckt


# ---------------------------------------------------------------------------
# Project writer
# ---------------------------------------------------------------------------


def write_example(
    out_dir: Path,
    filename: str,
    name: str,
    builder: CircuitBuilder,
    *,
    tstop: float = 1e-3,
    dt: float = 1e-6,
    integrator: str = "trapezoidal",
    description: str = "",
) -> Path:
    """Serialise a CircuitBuilder as a .pulsim project file."""
    from pulsimgui.models.project import SimulationSettings

    sim = SimulationSettings(
        tstart=0.0,
        tstop=tstop,
        dt=dt,
        max_step=dt,
        solver=integrator,
        step_mode="variable",
        output_points=5000,
        enable_events=True,
    )

    proj = Project(
        name=name,
        active_circuit="main",
        circuits={"main": builder.to_circuit()},
        simulation_settings=sim,
    )

    path = out_dir / filename
    proj.save_copy(path)
    return path


# ---------------------------------------------------------------------------
# Topology builders
# ---------------------------------------------------------------------------


def build_buck() -> tuple[str, str, CircuitBuilder, dict]:
    """DC-DC buck converter, open-loop, 12 V → 5 V @ 100 kHz, 50 % duty.

    Topology:
        Vin → MOSFET → L → Cout || Rload → GND
        diode catches the inductor current to ground when MOSFET opens.
    """
    b = CircuitBuilder("Buck (open-loop)")
    vin   = b.place(ComponentType.VOLTAGE_SOURCE, "Vin",  120, 140,
                    parameters={"waveform": {"type": "dc", "value": 12.0}})
    pwm   = b.place(ComponentType.PWM_GENERATOR,  "PWM1", 240, 100,
                    parameters={"frequency": 100e3, "duty_cycle": 0.42})
    m1    = b.place(ComponentType.MOSFET_N,        "M1",  340, 140,
                    parameters={"vth": 3.0, "kp": 0.35})
    d1    = b.place(ComponentType.DIODE,           "D1",  340, 240,
                    parameters={"g_on": 1e3, "g_off": 1e-9}, rotation=270)
    l1    = b.place(ComponentType.INDUCTOR,        "L1",  460, 140,
                    parameters={"value": 220e-6, "ic": 0.0})
    cout  = b.place(ComponentType.CAPACITOR,       "Cout",560, 240,
                    parameters={"value": 47e-6, "ic": 0.0})
    r     = b.place(ComponentType.RESISTOR,        "Rload",640, 240,
                    parameters={"value": 5.0})
    gnd1  = b.place(ComponentType.GROUND,          "GND1", 120, 240)
    gnd2  = b.place(ComponentType.GROUND,          "GND2", 640, 320)
    vprobe= b.place(ComponentType.VOLTAGE_PROBE,   "Vout", 540, 140)
    scope = b.place(ComponentType.ELECTRICAL_SCOPE,"Scope1",760, 200)

    # Wiring
    b.wire(vin, "+", m1, "D", label="Vin")
    b.wire(vin, "-", gnd1, "gnd")
    b.wire(pwm, "OUT", m1, "G")
    b.wire(m1, "S", l1, "1", label="sw")
    b.wire(m1, "S", d1, "K")
    b.wire(d1, "A", gnd2, "gnd")
    b.wire(l1, "2", cout, "1", label="vout")
    b.wire(cout, "1", r, "1")
    b.wire(cout, "2", gnd2, "gnd")
    b.wire(r, "2", gnd2, "gnd")
    b.wire(l1, "2", vprobe, "+")
    b.wire(vprobe, "OUT", scope, "CH1")
    return ("buck_open_loop.pulsim", "Buck — open loop", b,
            dict(tstop=2e-3, dt=1e-6))


def build_buck_pi() -> tuple[str, str, CircuitBuilder, dict]:
    """Closed-loop buck with PI controller on V_out → duty cycle."""
    b = CircuitBuilder("Buck (closed-loop, PI)")
    vin    = b.place(ComponentType.VOLTAGE_SOURCE, "Vin",  120, 140,
                     parameters={"waveform": {"type": "dc", "value": 12.0}})
    vref   = b.place(ComponentType.CONSTANT,       "Vref", 120, 80,
                     parameters={"value": 5.0})
    sub    = b.place(ComponentType.SUBTRACTOR,     "Err",  240, 80,
                     parameters={"input_count": 2, "signs": ["+", "-"]})
    pi     = b.place(ComponentType.PI_CONTROLLER,  "PI",   360, 80,
                     parameters={"kp": 0.6, "ki": 1500.0,
                                 "output_min": 0.05, "output_max": 0.95})
    pwm    = b.place(ComponentType.PWM_GENERATOR,  "PWM1", 480, 80,
                     parameters={"frequency": 100e3, "duty_cycle": 0.4,
                                 "enable_duty_input": True})
    m1     = b.place(ComponentType.MOSFET_N,        "M1",  340, 200,
                     parameters={"vth": 3.0, "kp": 0.35})
    d1     = b.place(ComponentType.DIODE,           "D1",  340, 280,
                     parameters={"g_on": 1e3, "g_off": 1e-9}, rotation=270)
    l1     = b.place(ComponentType.INDUCTOR,        "L1",  460, 200,
                     parameters={"value": 220e-6, "ic": 0.0})
    cout   = b.place(ComponentType.CAPACITOR,       "Cout",560, 280,
                     parameters={"value": 47e-6, "ic": 0.0})
    r      = b.place(ComponentType.RESISTOR,        "Rload",640, 280,
                     parameters={"value": 5.0})
    gnd1   = b.place(ComponentType.GROUND,          "GND1",  120, 240)
    gnd2   = b.place(ComponentType.GROUND,          "GND2",  640, 360)
    vprobe = b.place(ComponentType.VOLTAGE_PROBE_GND,"Vout", 540, 200)
    scope  = b.place(ComponentType.ELECTRICAL_SCOPE,"Scope1",760, 240)

    b.wire(vref, "OUT", sub, "IN1")
    b.wire(vprobe, "OUT", sub, "IN2")
    b.wire(sub, "OUT", pi, "IN")
    b.wire(pi, "OUT", pwm, "DUTY_IN")

    b.wire(vin, "+", m1, "D", label="Vin")
    b.wire(vin, "-", gnd1, "gnd")
    b.wire(pwm, "OUT", m1, "G")
    b.wire(m1, "S", l1, "1", label="sw")
    b.wire(m1, "S", d1, "K")
    b.wire(d1, "A", gnd2, "gnd")
    b.wire(l1, "2", cout, "1", label="vout")
    b.wire(cout, "1", r, "1")
    b.wire(cout, "2", gnd2, "gnd")
    b.wire(r, "2", gnd2, "gnd")
    b.wire(l1, "2", vprobe, "IN")
    b.wire(vprobe, "OUT", scope, "CH1")
    return ("buck_pi_closed_loop.pulsim", "Buck — closed-loop PI", b,
            dict(tstop=5e-3, dt=1e-6))


def build_boost() -> tuple[str, str, CircuitBuilder, dict]:
    """Boost converter: 12 V → 24 V, 100 kHz."""
    b = CircuitBuilder("Boost (open-loop)")
    vin   = b.place(ComponentType.VOLTAGE_SOURCE, "Vin",  120, 200,
                    parameters={"waveform": {"type": "dc", "value": 12.0}})
    l1    = b.place(ComponentType.INDUCTOR,       "L1",   240, 140,
                    parameters={"value": 220e-6})
    pwm   = b.place(ComponentType.PWM_GENERATOR,  "PWM1", 240, 60,
                    parameters={"frequency": 100e3, "duty_cycle": 0.50})
    m1    = b.place(ComponentType.MOSFET_N,       "M1",   360, 200,
                    parameters={"vth": 3.0, "kp": 0.35})
    d1    = b.place(ComponentType.DIODE,          "D1",   460, 140)
    cout  = b.place(ComponentType.CAPACITOR,      "Cout", 560, 200,
                    parameters={"value": 100e-6})
    r     = b.place(ComponentType.RESISTOR,       "Rload",640, 200,
                    parameters={"value": 12.0})
    gnd1  = b.place(ComponentType.GROUND,         "GND1", 120, 300)
    gnd2  = b.place(ComponentType.GROUND,         "GND2", 640, 300)
    probe = b.place(ComponentType.VOLTAGE_PROBE_GND,"Vout",540, 140)
    scope = b.place(ComponentType.ELECTRICAL_SCOPE,"Scope1",760, 200)

    b.wire(vin, "+", l1, "1", label="Vin")
    b.wire(vin, "-", gnd1, "gnd")
    b.wire(l1, "2", m1, "D", label="sw")
    b.wire(l1, "2", d1, "A")
    b.wire(m1, "S", gnd2, "gnd")
    b.wire(pwm, "OUT", m1, "G")
    b.wire(d1, "K", cout, "1", label="vout")
    b.wire(cout, "1", r, "1")
    b.wire(cout, "2", gnd2, "gnd")
    b.wire(r, "2", gnd2, "gnd")
    b.wire(d1, "K", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("boost_open_loop.pulsim", "Boost — open loop", b,
            dict(tstop=5e-3, dt=1e-6))


def build_buck_boost() -> tuple[str, str, CircuitBuilder, dict]:
    """Inverting buck-boost: 12 V → −12 V, 200 kHz."""
    b = CircuitBuilder("Buck-Boost (inverting)")
    vin = b.place(ComponentType.VOLTAGE_SOURCE, "Vin", 120, 200,
                  parameters={"waveform": {"type": "dc", "value": 12.0}})
    m1  = b.place(ComponentType.MOSFET_N, "M1", 240, 200)
    l1  = b.place(ComponentType.INDUCTOR, "L1", 360, 260,
                  parameters={"value": 100e-6})
    d1  = b.place(ComponentType.DIODE, "D1", 480, 200, rotation=180)
    cout= b.place(ComponentType.CAPACITOR, "Cout", 580, 260,
                  parameters={"value": 47e-6})
    r   = b.place(ComponentType.RESISTOR, "Rload", 680, 260,
                  parameters={"value": 12.0})
    pwm = b.place(ComponentType.PWM_GENERATOR, "PWM1", 240, 120,
                  parameters={"frequency": 200e3, "duty_cycle": 0.50})
    gnd1= b.place(ComponentType.GROUND, "GND1", 360, 360)
    gnd2= b.place(ComponentType.GROUND, "GND2", 580, 360)
    probe=b.place(ComponentType.VOLTAGE_PROBE_GND, "Vout", 660, 200)
    scope=b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 800, 220)

    b.wire(vin, "+", m1, "D")
    b.wire(vin, "-", gnd1, "gnd")
    b.wire(pwm, "OUT", m1, "G")
    b.wire(m1, "S", l1, "1")
    b.wire(m1, "S", d1, "K")
    b.wire(l1, "2", gnd1, "gnd")
    b.wire(d1, "A", cout, "2")
    b.wire(cout, "2", r, "2")
    b.wire(cout, "1", gnd2, "gnd")
    b.wire(r, "1", gnd2, "gnd")
    b.wire(d1, "A", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("buck_boost_inverting.pulsim", "Buck-Boost (inverting)", b,
            dict(tstop=3e-3, dt=500e-9))


def build_flyback() -> tuple[str, str, CircuitBuilder, dict]:
    """Flyback DC-DC converter using coupled inductors."""
    b = CircuitBuilder("Flyback (coupled inductor)")
    vin = b.place(ComponentType.VOLTAGE_SOURCE, "Vin", 100, 200,
                  parameters={"waveform": {"type": "dc", "value": 36.0}})
    ci  = b.place(ComponentType.COUPLED_INDUCTOR, "T1", 280, 200,
                  parameters={"l1": 200e-6, "l2": 50e-6, "coupling": 0.98})
    m1  = b.place(ComponentType.MOSFET_N, "M1", 220, 320)
    d1  = b.place(ComponentType.DIODE,    "D1", 420, 220)
    cout= b.place(ComponentType.CAPACITOR,"Cout", 540, 260,
                  parameters={"value": 47e-6})
    r   = b.place(ComponentType.RESISTOR, "Rload", 640, 260,
                  parameters={"value": 12.0})
    pwm = b.place(ComponentType.PWM_GENERATOR, "PWM1", 220, 420,
                  parameters={"frequency": 100e3, "duty_cycle": 0.45})
    gnd1= b.place(ComponentType.GROUND, "GND1", 220, 380)
    gnd2= b.place(ComponentType.GROUND, "GND2", 540, 380)
    probe=b.place(ComponentType.VOLTAGE_PROBE_GND, "Vout", 620, 260)
    scope=b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 760, 280)

    b.wire(vin, "+", ci, "L1_1")
    b.wire(vin, "-", gnd1, "gnd")
    b.wire(ci, "L1_2", m1, "D")
    b.wire(m1, "S", gnd1, "gnd")
    b.wire(pwm, "OUT", m1, "G")
    b.wire(ci, "L2_1", d1, "A")
    b.wire(d1, "K", cout, "1")
    b.wire(cout, "1", r, "1")
    b.wire(cout, "2", gnd2, "gnd")
    b.wire(r, "2", gnd2, "gnd")
    b.wire(ci, "L2_2", gnd2, "gnd")
    b.wire(d1, "K", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("flyback_coupled_inductor.pulsim", "Flyback (coupled inductor)", b,
            dict(tstop=5e-3, dt=500e-9))


def build_full_bridge_inverter() -> tuple[str, str, CircuitBuilder, dict]:
    """Full-bridge single-phase inverter with two complementary PWMs."""
    b = CircuitBuilder("Full-bridge inverter (single phase)")
    vdc = b.place(ComponentType.VOLTAGE_SOURCE, "Vdc", 100, 240,
                  parameters={"waveform": {"type": "dc", "value": 200.0}})
    m1  = b.place(ComponentType.MOSFET_N, "M1", 280, 160)  # high-side left
    m2  = b.place(ComponentType.MOSFET_N, "M2", 280, 320)  # low-side left
    m3  = b.place(ComponentType.MOSFET_N, "M3", 500, 160)  # high-side right
    m4  = b.place(ComponentType.MOSFET_N, "M4", 500, 320)  # low-side right
    pwm_a = b.place(ComponentType.PWM_GENERATOR, "PWMa", 180, 80,
                    parameters={"frequency": 20e3, "duty_cycle": 0.50})
    pwm_b = b.place(ComponentType.PWM_GENERATOR, "PWMb", 580, 80,
                    parameters={"frequency": 20e3, "duty_cycle": 0.50, "phase": math.pi})
    rload= b.place(ComponentType.RESISTOR, "Rload", 400, 260,
                   parameters={"value": 10.0})
    gnd  = b.place(ComponentType.GROUND, "gnd", 100, 320)
    gnd2 = b.place(ComponentType.GROUND, "GND2", 280, 420)
    probe= b.place(ComponentType.VOLTAGE_PROBE, "Vload", 400, 220)
    scope= b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 720, 260)

    b.wire(vdc, "+", m1, "D", label="Vbus")
    b.wire(vdc, "+", m3, "D")
    b.wire(vdc, "-", gnd, "gnd")
    b.wire(m1, "S", m2, "D", label="A")
    b.wire(m3, "S", m4, "D", label="B")
    b.wire(m2, "S", gnd2, "gnd")
    b.wire(m4, "S", gnd2, "gnd")
    b.wire(pwm_a, "OUT", m1, "G")
    b.wire(pwm_a, "OUT", m4, "G")
    b.wire(pwm_b, "OUT", m2, "G")
    b.wire(pwm_b, "OUT", m3, "G")
    b.wire(m1, "S", rload, "1")
    b.wire(m3, "S", rload, "2")
    b.wire(rload, "1", probe, "+")
    b.wire(rload, "2", probe, "-")
    b.wire(probe, "OUT", scope, "CH1")
    return ("full_bridge_inverter.pulsim", "Full-bridge inverter", b,
            dict(tstop=200e-6, dt=200e-9))


def build_half_bridge_lc() -> tuple[str, str, CircuitBuilder, dict]:
    """Half-bridge converter with LC output filter."""
    b = CircuitBuilder("Half-bridge with LC filter")
    vdc = b.place(ComponentType.VOLTAGE_SOURCE, "Vdc", 100, 200,
                  parameters={"waveform": {"type": "dc", "value": 100.0}})
    m1  = b.place(ComponentType.MOSFET_N, "M1", 240, 140)
    m2  = b.place(ComponentType.MOSFET_N, "M2", 240, 280)
    l1  = b.place(ComponentType.INDUCTOR, "L1", 380, 200,
                  parameters={"value": 220e-6})
    cout= b.place(ComponentType.CAPACITOR, "Cout", 500, 260,
                  parameters={"value": 47e-6})
    r   = b.place(ComponentType.RESISTOR, "Rload", 600, 260,
                  parameters={"value": 10.0})
    pwm_a = b.place(ComponentType.PWM_GENERATOR, "PWMa", 140, 60,
                    parameters={"frequency": 50e3, "duty_cycle": 0.50})
    pwm_b = b.place(ComponentType.PWM_GENERATOR, "PWMb", 340, 60,
                    parameters={"frequency": 50e3, "duty_cycle": 0.50, "phase": math.pi})
    gnd = b.place(ComponentType.GROUND, "gnd", 100, 360)
    gnd2= b.place(ComponentType.GROUND, "GND2", 500, 360)
    probe=b.place(ComponentType.VOLTAGE_PROBE_GND, "Vout", 580, 200)
    scope=b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 720, 240)

    b.wire(vdc, "+", m1, "D")
    b.wire(vdc, "-", gnd, "gnd")
    b.wire(m1, "S", m2, "D", label="sw")
    b.wire(m1, "S", l1, "1")
    b.wire(m2, "S", gnd2, "gnd")
    b.wire(pwm_a, "OUT", m1, "G")
    b.wire(pwm_b, "OUT", m2, "G")
    b.wire(l1, "2", cout, "1", label="vout")
    b.wire(cout, "1", r, "1")
    b.wire(cout, "2", gnd2, "gnd")
    b.wire(r, "2", gnd2, "gnd")
    b.wire(l1, "2", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("half_bridge_lc.pulsim", "Half-bridge with LC filter", b,
            dict(tstop=1e-3, dt=200e-9))


def build_diode_rectifier_full() -> tuple[str, str, CircuitBuilder, dict]:
    """Single-phase full-wave bridge rectifier with capacitive filter."""
    b = CircuitBuilder("Diode bridge rectifier (full-wave)")
    vac = b.place(ComponentType.VOLTAGE_SOURCE, "Vac", 100, 240,
                  parameters={"waveform": {"type": "sine",
                                           "amplitude": 170.0,
                                           "frequency": 60.0,
                                           "offset": 0.0,
                                           "phase": 0.0}})
    d1 = b.place(ComponentType.DIODE, "D1", 260, 160)
    d2 = b.place(ComponentType.DIODE, "D2", 260, 320, rotation=180)
    d3 = b.place(ComponentType.DIODE, "D3", 380, 160)
    d4 = b.place(ComponentType.DIODE, "D4", 380, 320, rotation=180)
    c1 = b.place(ComponentType.CAPACITOR, "C1", 480, 240,
                 parameters={"value": 1e-3})
    r  = b.place(ComponentType.RESISTOR, "Rload", 580, 240,
                 parameters={"value": 100.0})
    gnd= b.place(ComponentType.GROUND, "gnd", 580, 360)
    probe=b.place(ComponentType.VOLTAGE_PROBE_GND, "Vdc", 560, 240)
    scope=b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 720, 260)

    b.wire(vac, "+", d1, "A")
    b.wire(vac, "+", d2, "K")
    b.wire(vac, "-", d3, "A")
    b.wire(vac, "-", d4, "K")
    b.wire(d1, "K", d3, "K", label="Vdc+")
    b.wire(d2, "A", d4, "A")
    b.wire(d1, "K", c1, "1")
    b.wire(c1, "1", r, "1")
    b.wire(c1, "2", gnd, "gnd")
    b.wire(r, "2", gnd, "gnd")
    b.wire(d2, "A", gnd, "gnd")
    b.wire(c1, "1", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("diode_bridge_rectifier.pulsim", "Diode bridge rectifier", b,
            dict(tstop=100e-3, dt=50e-6))


def build_three_phase_rectifier() -> tuple[str, str, CircuitBuilder, dict]:
    """Three-phase 6-pulse diode rectifier."""
    b = CircuitBuilder("Three-phase 6-pulse diode rectifier")
    va = b.place(ComponentType.VOLTAGE_SOURCE, "Va", 100, 160,
                 parameters={"waveform": {"type": "sine", "amplitude": 311.0,
                                          "frequency": 60.0, "phase": 0.0}})
    vb = b.place(ComponentType.VOLTAGE_SOURCE, "Vb", 100, 280,
                 parameters={"waveform": {"type": "sine", "amplitude": 311.0,
                                          "frequency": 60.0, "phase": -2.0943951}})
    vc = b.place(ComponentType.VOLTAGE_SOURCE, "Vc", 100, 400,
                 parameters={"waveform": {"type": "sine", "amplitude": 311.0,
                                          "frequency": 60.0, "phase": -4.1887902}})
    # 6 diodes: 3 top, 3 bottom
    da1 = b.place(ComponentType.DIODE, "Da1", 280, 80)
    db1 = b.place(ComponentType.DIODE, "Db1", 360, 80)
    dc1 = b.place(ComponentType.DIODE, "Dc1", 440, 80)
    da2 = b.place(ComponentType.DIODE, "Da2", 280, 480, rotation=180)
    db2 = b.place(ComponentType.DIODE, "Db2", 360, 480, rotation=180)
    dc2 = b.place(ComponentType.DIODE, "Dc2", 440, 480, rotation=180)
    c1  = b.place(ComponentType.CAPACITOR, "C1", 560, 240,
                  parameters={"value": 470e-6})
    r   = b.place(ComponentType.RESISTOR, "Rload", 660, 240,
                  parameters={"value": 50.0})
    gnd = b.place(ComponentType.GROUND, "gnd", 660, 560)
    probe=b.place(ComponentType.VOLTAGE_PROBE_GND, "Vdc", 620, 240)
    scope=b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 760, 280)

    b.wire(va, "+", da1, "A")
    b.wire(va, "+", da2, "K")
    b.wire(vb, "+", db1, "A")
    b.wire(vb, "+", db2, "K")
    b.wire(vc, "+", dc1, "A")
    b.wire(vc, "+", dc2, "K")
    b.wire(va, "-", vb, "-")
    b.wire(vb, "-", vc, "-")
    b.wire(vc, "-", gnd, "gnd")
    b.wire(da1, "K", db1, "K", label="DC+")
    b.wire(db1, "K", dc1, "K")
    b.wire(da2, "A", db2, "A")
    b.wire(db2, "A", dc2, "A")
    b.wire(da2, "A", gnd, "gnd")
    b.wire(dc1, "K", c1, "1")
    b.wire(c1, "1", r, "1")
    b.wire(c1, "2", gnd, "gnd")
    b.wire(r, "2", gnd, "gnd")
    b.wire(c1, "1", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("three_phase_diode_rectifier.pulsim",
            "Three-phase 6-pulse diode rectifier", b,
            dict(tstop=100e-3, dt=50e-6))


def build_pll_grid_sync() -> tuple[str, str, CircuitBuilder, dict]:
    """Single-phase PLL locking to a 60 Hz grid sine."""
    b = CircuitBuilder("PLL grid sync (60 Hz)")
    vg = b.place(ComponentType.VOLTAGE_SOURCE, "Vgrid", 120, 200,
                 parameters={"waveform": {"type": "sine", "amplitude": 100.0,
                                          "frequency": 60.0}})
    pll = b.place(ComponentType.PLL, "PLL", 320, 200,
                  parameters={"kp": 200.0, "ki": 2000.0,
                              "f_nominal_hz": 60.0})
    gnd = b.place(ComponentType.GROUND, "gnd", 120, 300)
    scope = b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 540, 200)

    b.wire(vg, "+", pll, "IN", label="grid")
    b.wire(vg, "-", gnd, "gnd")
    b.wire(pll, "THETA", scope, "CH1")
    # PLL also exposes OMEGA and ERR; users can drag those to additional
    # scope channels through the GUI.
    return ("pll_grid_sync.pulsim", "PLL grid sync (60 Hz)", b,
            dict(tstop=200e-3, dt=50e-6))


def build_vector_control_open() -> tuple[str, str, CircuitBuilder, dict]:
    """Open-loop vector-control pipeline: 3-phase → Clarke → PLL → Park
    → identity → InverseParkPipeline → SVM."""
    b = CircuitBuilder("Vector control (open loop)")
    va = b.place(ComponentType.VOLTAGE_SOURCE, "Va", 80, 120,
                 parameters={"waveform": {"type": "sine", "amplitude": 100.0,
                                          "frequency": 60.0, "phase": 0.0}})
    vb = b.place(ComponentType.VOLTAGE_SOURCE, "Vb", 80, 240,
                 parameters={"waveform": {"type": "sine", "amplitude": 100.0,
                                          "frequency": 60.0, "phase": -2.0943951}})
    vc = b.place(ComponentType.VOLTAGE_SOURCE, "Vc", 80, 360,
                 parameters={"waveform": {"type": "sine", "amplitude": 100.0,
                                          "frequency": 60.0, "phase": -4.1887902}})
    pll = b.place(ComponentType.PLL, "PLL", 240, 480,
                  parameters={"kp": 200.0, "ki": 2000.0,
                              "f_nominal_hz": 60.0})
    clk = b.place(ComponentType.CLARKE_TRANSFORM, "CLK", 240, 240)
    park= b.place(ComponentType.PARK_TRANSFORM, "PARK", 420, 240,
                  parameters={"alpha_from_channel": "CLK.alpha",
                              "beta_from_channel":  "CLK.beta",
                              "theta_from_channel": "PLL.theta"})
    ipark=b.place(ComponentType.INVERSE_PARK_TRANSFORM, "IPARK", 600, 240,
                  parameters={"d_from_channel": "PARK.d",
                              "q_from_channel": "PARK.q",
                              "theta_from_channel": "PLL.theta"})
    svm  =b.place(ComponentType.SVM, "SVM", 780, 240,
                  parameters={"v_dc": 200.0,
                              "alpha_from_channel": "IPARK.alpha",
                              "beta_from_channel":  "IPARK.beta"})
    gnd = b.place(ComponentType.GROUND, "gnd", 80, 460)
    scope = b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 940, 240)

    b.wire(va, "+", clk, "A")
    b.wire(vb, "+", clk, "B")
    b.wire(vc, "+", clk, "C")
    b.wire(va, "-", gnd, "gnd")
    b.wire(vb, "-", gnd, "gnd")
    b.wire(vc, "-", gnd, "gnd")
    b.wire(va, "+", pll, "IN")
    b.wire(svm, "DA", scope, "CH1")
    return ("vector_control_open_loop.pulsim",
            "Vector control (open loop)", b,
            dict(tstop=100e-3, dt=50e-6))


def build_synchronous_buck() -> tuple[str, str, CircuitBuilder, dict]:
    """Synchronous buck: replaces the freewheel diode with a low-side
    MOSFET."""
    b = CircuitBuilder("Synchronous buck")
    vin = b.place(ComponentType.VOLTAGE_SOURCE, "Vin", 100, 200,
                  parameters={"waveform": {"type": "dc", "value": 12.0}})
    mh  = b.place(ComponentType.MOSFET_N, "Mh", 240, 160)
    ml  = b.place(ComponentType.MOSFET_N, "Ml", 240, 280)
    l1  = b.place(ComponentType.INDUCTOR, "L1", 380, 200,
                  parameters={"value": 100e-6})
    cout= b.place(ComponentType.CAPACITOR, "Cout", 500, 280,
                  parameters={"value": 47e-6})
    r   = b.place(ComponentType.RESISTOR, "Rload", 600, 280,
                  parameters={"value": 2.5})
    pwm_h= b.place(ComponentType.PWM_GENERATOR, "PWMh", 140, 80,
                   parameters={"frequency": 200e3, "duty_cycle": 0.42})
    pwm_l= b.place(ComponentType.PWM_GENERATOR, "PWMl", 340, 80,
                   parameters={"frequency": 200e3, "duty_cycle": 0.55,
                               "phase": math.pi})
    gnd  = b.place(ComponentType.GROUND, "gnd", 100, 360)
    gnd2 = b.place(ComponentType.GROUND, "GND2", 500, 360)
    probe= b.place(ComponentType.VOLTAGE_PROBE_GND, "Vout", 580, 200)
    scope= b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 720, 240)

    b.wire(vin, "+", mh, "D")
    b.wire(vin, "-", gnd, "gnd")
    b.wire(mh, "S", ml, "D", label="sw")
    b.wire(mh, "S", l1, "1")
    b.wire(ml, "S", gnd2, "gnd")
    b.wire(pwm_h, "OUT", mh, "G")
    b.wire(pwm_l, "OUT", ml, "G")
    b.wire(l1, "2", cout, "1", label="vout")
    b.wire(cout, "1", r, "1")
    b.wire(cout, "2", gnd2, "gnd")
    b.wire(r, "2", gnd2, "gnd")
    b.wire(l1, "2", probe, "IN")
    b.wire(probe, "OUT", scope, "CH1")
    return ("synchronous_buck.pulsim", "Synchronous buck", b,
            dict(tstop=1e-3, dt=200e-9))


def build_llc_resonant_half() -> tuple[str, str, CircuitBuilder, dict]:
    """LLC resonant half-bridge: ZVS-friendly resonant tank."""
    b = CircuitBuilder("LLC resonant half-bridge")
    vdc = b.place(ComponentType.VOLTAGE_SOURCE, "Vdc", 100, 200,
                  parameters={"waveform": {"type": "dc", "value": 400.0}})
    mh  = b.place(ComponentType.MOSFET_N, "Mh", 240, 140)
    ml  = b.place(ComponentType.MOSFET_N, "Ml", 240, 280)
    lr  = b.place(ComponentType.INDUCTOR, "Lr", 380, 200,
                  parameters={"value": 80e-6})
    cr  = b.place(ComponentType.CAPACITOR, "Cr", 480, 200,
                  parameters={"value": 47e-9})
    lm  = b.place(ComponentType.INDUCTOR, "Lm", 580, 200,
                  parameters={"value": 320e-6})
    rload=b.place(ComponentType.RESISTOR, "Rload", 580, 320,
                  parameters={"value": 50.0})
    pwm_h= b.place(ComponentType.PWM_GENERATOR, "PWMh", 140, 60,
                   parameters={"frequency": 130e3, "duty_cycle": 0.48})
    pwm_l= b.place(ComponentType.PWM_GENERATOR, "PWMl", 340, 60,
                   parameters={"frequency": 130e3, "duty_cycle": 0.48,
                               "phase": math.pi})
    gnd  = b.place(ComponentType.GROUND, "gnd", 100, 360)
    gnd2 = b.place(ComponentType.GROUND, "GND2", 580, 400)
    probe= b.place(ComponentType.VOLTAGE_PROBE, "Vout", 560, 320)
    scope= b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 740, 260)

    b.wire(vdc, "+", mh, "D")
    b.wire(vdc, "-", gnd, "gnd")
    b.wire(mh, "S", ml, "D", label="sw")
    b.wire(mh, "S", lr, "1")
    b.wire(ml, "S", gnd2, "gnd")
    b.wire(pwm_h, "OUT", mh, "G")
    b.wire(pwm_l, "OUT", ml, "G")
    b.wire(lr, "2", cr, "1")
    b.wire(cr, "2", lm, "1")
    b.wire(lm, "1", rload, "1")
    b.wire(lm, "2", gnd2, "gnd")
    b.wire(rload, "2", gnd2, "gnd")
    b.wire(rload, "1", probe, "+")
    b.wire(rload, "2", probe, "-")
    b.wire(probe, "OUT", scope, "CH1")
    return ("llc_resonant_half_bridge.pulsim",
            "LLC resonant half-bridge", b,
            dict(tstop=500e-6, dt=100e-9))


def build_npc_three_level() -> tuple[str, str, CircuitBuilder, dict]:
    """3-level NPC half-bridge inverter leg."""
    b = CircuitBuilder("3-level NPC inverter leg")
    vdc1 = b.place(ComponentType.VOLTAGE_SOURCE, "Vdc1", 100, 140,
                   parameters={"waveform": {"type": "dc", "value": 200.0}})
    vdc2 = b.place(ComponentType.VOLTAGE_SOURCE, "Vdc2", 100, 320,
                   parameters={"waveform": {"type": "dc", "value": 200.0}})
    m1 = b.place(ComponentType.MOSFET_N, "M1", 260, 80)
    m2 = b.place(ComponentType.MOSFET_N, "M2", 260, 200)
    m3 = b.place(ComponentType.MOSFET_N, "M3", 260, 320)
    m4 = b.place(ComponentType.MOSFET_N, "M4", 260, 440)
    dc1 = b.place(ComponentType.DIODE, "Dn1", 400, 160, rotation=180)
    dc2 = b.place(ComponentType.DIODE, "Dn2", 400, 320)
    l1 = b.place(ComponentType.INDUCTOR, "Lf", 380, 240,
                 parameters={"value": 1e-3})
    r = b.place(ComponentType.RESISTOR, "Rload", 500, 240,
                parameters={"value": 50.0})
    pwm1 = b.place(ComponentType.PWM_GENERATOR, "PWM1", 160, 40,
                   parameters={"frequency": 5e3, "duty_cycle": 0.50})
    pwm2 = b.place(ComponentType.PWM_GENERATOR, "PWM2", 160, 480,
                   parameters={"frequency": 5e3, "duty_cycle": 0.50,
                               "phase": math.pi})
    gnd = b.place(ComponentType.GROUND, "gnd", 100, 480)
    scope= b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 620, 240)

    b.wire(vdc1, "+", m1, "D", label="DC+")
    b.wire(vdc1, "-", vdc2, "+", label="N")
    b.wire(vdc2, "-", gnd, "gnd")
    b.wire(m1, "S", m2, "D", label="A")
    b.wire(m2, "S", m3, "D", label="phase")
    b.wire(m3, "S", m4, "D", label="B")
    b.wire(m4, "S", gnd, "gnd")
    b.wire(dc1, "A", vdc1, "-")
    b.wire(dc1, "K", m2, "S")
    b.wire(dc2, "A", m3, "D")
    b.wire(dc2, "K", vdc1, "-")
    b.wire(pwm1, "OUT", m1, "G")
    b.wire(pwm1, "OUT", m2, "G")
    b.wire(pwm2, "OUT", m3, "G")
    b.wire(pwm2, "OUT", m4, "G")
    b.wire(m2, "S", l1, "1")
    b.wire(l1, "2", r, "1")
    b.wire(r, "2", gnd, "gnd")
    b.wire(l1, "2", scope, "CH1")
    return ("npc_three_level_leg.pulsim", "3-level NPC inverter leg", b,
            dict(tstop=5e-3, dt=500e-9))


def build_dc_motor() -> tuple[str, str, CircuitBuilder, dict]:
    """DC motor (RL + back-EMF) driven by a PWM voltage source."""
    b = CircuitBuilder("DC brush motor (R-L model)")
    vin = b.place(ComponentType.VOLTAGE_SOURCE, "Vsrc", 100, 200,
                  parameters={"waveform": {"type": "pwm", "v_high": 24.0,
                                            "v_low": 0.0, "frequency": 20e3,
                                            "duty": 0.6}})
    r   = b.place(ComponentType.RESISTOR, "Ra", 260, 200,
                  parameters={"value": 1.0})
    l   = b.place(ComponentType.INDUCTOR, "La", 380, 200,
                  parameters={"value": 5e-3})
    e   = b.place(ComponentType.VOLTAGE_SOURCE, "E_emf", 480, 200,
                  parameters={"waveform": {"type": "dc", "value": 10.0}})
    gnd = b.place(ComponentType.GROUND, "gnd", 100, 320)
    iprobe=b.place(ComponentType.CURRENT_PROBE, "Ia", 200, 200,
                   parameters={"target_component": "Ra"})
    scope = b.place(ComponentType.ELECTRICAL_SCOPE, "Scope1", 620, 220)

    b.wire(vin, "+", iprobe, "IN")
    b.wire(iprobe, "OUT", r, "1")
    b.wire(r, "2", l, "1")
    b.wire(l, "2", e, "+")
    b.wire(e, "-", gnd, "gnd")
    b.wire(vin, "-", gnd, "gnd")
    b.wire(iprobe, "MEAS", scope, "CH1")
    return ("dc_motor_pwm.pulsim", "DC motor with PWM drive", b,
            dict(tstop=10e-3, dt=2e-6))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


TOPOLOGIES = [
    build_buck,
    build_buck_pi,
    build_boost,
    build_buck_boost,
    build_flyback,
    build_synchronous_buck,
    build_full_bridge_inverter,
    build_half_bridge_lc,
    build_llc_resonant_half,
    build_diode_rectifier_full,
    build_three_phase_rectifier,
    build_npc_three_level,
    build_pll_grid_sync,
    build_vector_control_open,
    build_dc_motor,
]


def main() -> int:
    out_dir = ROOT / "examples" / "gallery"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: list[tuple[str, str, int, int]] = []
    for fn in TOPOLOGIES:
        filename, title, builder, sim_kwargs = fn()
        path = write_example(out_dir, filename, title, builder, **sim_kwargs)
        n_components = len(builder.components)
        n_wires = len(builder.wires)
        summary.append((filename, title, n_components, n_wires))
        print(f"  ✓ {filename:40s}  {n_components:2d} components, {n_wires:3d} wires")

    print(f"\nGenerated {len(summary)} examples in {out_dir.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
