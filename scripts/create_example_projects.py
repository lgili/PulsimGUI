#!/usr/bin/env python3
"""Create example .pulsim project files for GUI testing.

Usage:
    python scripts/create_example_projects.py [output_directory]

Default output is ./examples/
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def create_pin(index: int, name: str, x: float, y: float) -> dict:
    """Create a pin dictionary."""
    return {"index": index, "name": name, "x": x, "y": y}


def create_component(
    comp_type: str,
    name: str,
    x: float,
    y: float,
    parameters: dict,
    pins: list[dict],
    rotation: int = 0,
) -> dict:
    """Create a component dictionary."""
    return {
        "id": str(uuid4()),
        "type": comp_type,
        "name": name,
        "x": x,
        "y": y,
        "rotation": rotation,
        "mirrored_h": False,
        "mirrored_v": False,
        "parameters": parameters,
        "pins": pins,
    }


def create_wire(segments: list[tuple[float, float, float, float]], node_name: str = "") -> dict:
    """Create a wire dictionary.

    Args:
        segments: List of (x1, y1, x2, y2) tuples for each segment
        node_name: Optional node name for the wire
    """
    return {
        "id": str(uuid4()),
        "segments": [
            {"x1": s[0], "y1": s[1], "x2": s[2], "y2": s[3]}
            for s in segments
        ],
        "start_connection": None,
        "end_connection": None,
        "junctions": [],
        "node_name": node_name,
        "alias": "",
    }


def create_project(name: str, circuit_name: str, components: list, wires: list) -> dict:
    """Create a complete project dictionary."""
    now = datetime.now().isoformat()
    return {
        "version": "1.0",
        "name": name,
        "created": now,
        "modified": now,
        "active_circuit": circuit_name,
        "simulation_settings": {
            "tstop": 0.005,
            "dt": 1e-6,
            "tstart": 0.0,
            "abstol": 1e-12,
            "reltol": 0.001,
            "max_iterations": 50,
        },
        "circuits": {
            circuit_name: {
                "name": circuit_name,
                "components": components,
                "wires": wires,
            }
        },
        "subcircuits": [],
        "scope_windows": {},
    }


# Standard pin configurations
RESISTOR_PINS = [
    create_pin(0, "1", -30, 0),
    create_pin(1, "2", 30, 0),
]

CAPACITOR_PINS = [
    create_pin(0, "1", -20, 0),
    create_pin(1, "2", 20, 0),
]

INDUCTOR_PINS = [
    create_pin(0, "1", -30, 0),
    create_pin(1, "2", 30, 0),
]

VOLTAGE_SOURCE_PINS = [
    create_pin(0, "+", 0, -30),
    create_pin(1, "-", 0, 30),
]

DIODE_PINS = [
    create_pin(0, "A", -20, 0),
    create_pin(1, "K", 20, 0),
]

MOSFET_N_PINS = [
    create_pin(0, "D", 0, -30),
    create_pin(1, "G", -30, 0),
    create_pin(2, "S", 0, 30),
]

GROUND_PINS = [
    create_pin(0, "gnd", 0, -10),
]


def voltage_divider_project() -> dict:
    """Voltage divider: V1=10V, R1=R2=1k, expect V(out)=5V."""
    components = [
        create_component(
            "VOLTAGE_SOURCE", "V1", 100, 200,
            {"waveform": {"type": "dc", "value": 10.0}},
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "RESISTOR", "R1", 200, 100,
            {"resistance": 1000.0},
            RESISTOR_PINS,
        ),
        create_component(
            "RESISTOR", "R2", 200, 300,
            {"resistance": 1000.0},
            RESISTOR_PINS,
        ),
        create_component(
            "GROUND", "GND1", 100, 400,
            {},
            GROUND_PINS,
        ),
    ]

    wires = [
        # V1+ to R1 left
        create_wire([
            (100, 170, 100, 100),
            (100, 100, 170, 100),
        ], "VIN"),
        # R1 right to OUT junction, down to R2 left
        create_wire([
            (230, 100, 280, 100),
            (280, 100, 280, 300),
            (280, 300, 230, 300),
        ], "OUT"),
        # R2 left to V1-
        create_wire([
            (170, 300, 100, 300),
            (100, 300, 100, 230),
        ], "0"),
        # V1- to GND
        create_wire([
            (100, 300, 100, 390),
        ], "0"),
    ]

    return create_project("Voltage Divider", "main", components, wires)


def rc_lowpass_project() -> dict:
    """RC lowpass filter: R=1k, C=159nF, fc~1kHz."""
    components = [
        create_component(
            "VOLTAGE_SOURCE", "V1", 100, 200,
            {"waveform": {"type": "sine", "amplitude": 1.0, "frequency": 1000.0, "phase": 0.0, "offset": 0.0}},
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "RESISTOR", "R1", 200, 100,
            {"resistance": 1000.0},
            RESISTOR_PINS,
        ),
        create_component(
            "CAPACITOR", "C1", 350, 200,
            {"capacitance": 159e-9},
            CAPACITOR_PINS,
            rotation=90,
        ),
        create_component(
            "GROUND", "GND1", 100, 350,
            {},
            GROUND_PINS,
        ),
    ]

    wires = [
        create_wire([
            (100, 170, 100, 100),
            (100, 100, 170, 100),
        ], "VIN"),
        create_wire([
            (230, 100, 350, 100),
            (350, 100, 350, 180),
        ], "OUT"),
        create_wire([
            (350, 220, 350, 300),
            (350, 300, 100, 300),
            (100, 300, 100, 230),
        ], "0"),
        create_wire([
            (100, 300, 100, 340),
        ], "0"),
    ]

    return create_project("RC Lowpass Filter", "main", components, wires)


def rc_transient_project() -> dict:
    """RC transient: R=1k, C=1uF, tau=1ms."""
    components = [
        create_component(
            "VOLTAGE_SOURCE", "V1", 100, 200,
            {
                "waveform": {
                    "type": "pulse",
                    "v1": 0.0,
                    "v2": 5.0,
                    "delay": 0.0,
                    "rise_time": 1e-9,
                    "fall_time": 1e-9,
                    "pulse_width": 0.01,
                    "period": 0.02,
                }
            },
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "RESISTOR", "R1", 200, 100,
            {"resistance": 1000.0},
            RESISTOR_PINS,
        ),
        create_component(
            "CAPACITOR", "C1", 350, 200,
            {"capacitance": 1e-6},
            CAPACITOR_PINS,
            rotation=90,
        ),
        create_component(
            "GROUND", "GND1", 100, 350,
            {},
            GROUND_PINS,
        ),
    ]

    wires = [
        create_wire([
            (100, 170, 100, 100),
            (100, 100, 170, 100),
        ], "VIN"),
        create_wire([
            (230, 100, 350, 100),
            (350, 100, 350, 180),
        ], "OUT"),
        create_wire([
            (350, 220, 350, 300),
            (350, 300, 100, 300),
            (100, 300, 100, 230),
        ], "0"),
        create_wire([
            (100, 300, 100, 340),
        ], "0"),
    ]

    return create_project("RC Transient", "main", components, wires)


def mosfet_switch_project() -> dict:
    """MOSFET switch: Vdd=12V, Vgate=10V, R_load=10ohm."""
    components = [
        create_component(
            "VOLTAGE_SOURCE", "Vdd", 100, 100,
            {"waveform": {"type": "dc", "value": 12.0}},
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "VOLTAGE_SOURCE", "Vgate", 100, 350,
            {"waveform": {"type": "dc", "value": 10.0}},
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "RESISTOR", "R_load", 250, 50,
            {"resistance": 10.0},
            RESISTOR_PINS,
        ),
        create_component(
            "MOSFET_N", "M1", 350, 200,
            {"vth": 2.0, "kp": 0.5, "rds_on": 0.1},
            MOSFET_N_PINS,
        ),
        create_component(
            "GROUND", "GND1", 100, 200,
            {},
            GROUND_PINS,
        ),
        create_component(
            "GROUND", "GND2", 100, 450,
            {},
            GROUND_PINS,
        ),
        create_component(
            "GROUND", "GND3", 350, 300,
            {},
            GROUND_PINS,
        ),
    ]

    wires = [
        # Vdd+ to R_load
        create_wire([
            (100, 70, 100, 50),
            (100, 50, 220, 50),
        ], "VDD"),
        # R_load to MOSFET drain
        create_wire([
            (280, 50, 350, 50),
            (350, 50, 350, 170),
        ], "DRAIN"),
        # Vdd- to GND1
        create_wire([
            (100, 130, 100, 190),
        ], "0"),
        # Vgate+ to MOSFET gate
        create_wire([
            (100, 320, 100, 200),
            (100, 200, 320, 200),
        ], "GATE"),
        # Vgate- to GND2
        create_wire([
            (100, 380, 100, 440),
        ], "0"),
        # MOSFET source to GND3
        create_wire([
            (350, 230, 350, 290),
        ], "0"),
    ]

    return create_project("MOSFET Switch", "main", components, wires)


def diode_rectifier_project() -> dict:
    """Half-wave rectifier: AC source, diode, load resistor."""
    components = [
        create_component(
            "VOLTAGE_SOURCE", "V1", 100, 200,
            {
                "waveform": {
                    "type": "sine",
                    "amplitude": 10.0,
                    "frequency": 60.0,
                    "phase": 0.0,
                    "offset": 0.0,
                }
            },
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "DIODE", "D1", 200, 100,
            {"is_": 1e-14, "n": 1.0, "vf": 0.7},
            DIODE_PINS,
        ),
        create_component(
            "RESISTOR", "R_load", 350, 200,
            {"resistance": 1000.0},
            RESISTOR_PINS,
            rotation=90,
        ),
        create_component(
            "GROUND", "GND1", 100, 350,
            {},
            GROUND_PINS,
        ),
    ]

    wires = [
        create_wire([
            (100, 170, 100, 100),
            (100, 100, 180, 100),
        ], "VIN"),
        create_wire([
            (220, 100, 350, 100),
            (350, 100, 350, 170),
        ], "OUT"),
        create_wire([
            (350, 230, 350, 300),
            (350, 300, 100, 300),
            (100, 300, 100, 230),
        ], "0"),
        create_wire([
            (100, 300, 100, 340),
        ], "0"),
    ]

    return create_project("Diode Rectifier", "main", components, wires)


def rl_circuit_project() -> dict:
    """RL circuit: R=100ohm, L=10mH, tau=100us."""
    components = [
        create_component(
            "VOLTAGE_SOURCE", "V1", 100, 200,
            {
                "waveform": {
                    "type": "pulse",
                    "v1": 0.0,
                    "v2": 10.0,
                    "delay": 0.0,
                    "rise_time": 1e-9,
                    "fall_time": 1e-9,
                    "pulse_width": 0.001,
                    "period": 0.002,
                }
            },
            VOLTAGE_SOURCE_PINS,
        ),
        create_component(
            "RESISTOR", "R1", 200, 100,
            {"resistance": 100.0},
            RESISTOR_PINS,
        ),
        create_component(
            "INDUCTOR", "L1", 350, 200,
            {"inductance": 10e-3},
            INDUCTOR_PINS,
            rotation=90,
        ),
        create_component(
            "GROUND", "GND1", 100, 350,
            {},
            GROUND_PINS,
        ),
    ]

    wires = [
        create_wire([
            (100, 170, 100, 100),
            (100, 100, 170, 100),
        ], "VIN"),
        create_wire([
            (230, 100, 350, 100),
            (350, 100, 350, 170),
        ], "OUT"),
        create_wire([
            (350, 230, 350, 300),
            (350, 300, 100, 300),
            (100, 300, 100, 230),
        ], "0"),
        create_wire([
            (100, 300, 100, 340),
        ], "0"),
    ]

    return create_project("RL Circuit", "main", components, wires)


# Registry of all example projects
EXAMPLE_PROJECTS = {
    "01_voltage_divider": voltage_divider_project,
    "02_rc_lowpass": rc_lowpass_project,
    "03_rc_transient": rc_transient_project,
    "04_mosfet_switch": mosfet_switch_project,
    "05_diode_rectifier": diode_rectifier_project,
    "06_rl_circuit": rl_circuit_project,
}


def export_all_projects(output_dir: Path | str) -> None:
    """Export all example projects to .pulsim files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating example projects in {output_dir}/\n")

    for name, project_fn in EXAMPLE_PROJECTS.items():
        project_data = project_fn()
        output_file = output_dir / f"{name}.pulsim"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(project_data, f, indent=2)

        print(f"  Created: {output_file.name}")
        print(f"    - {project_data['name']}")

    print(f"\nDone! Open these files in PulsimGui to test.")
    print("\nValidation instructions:")
    print("  1. voltage_divider: Run DC (F6), check V(out) = 5V")
    print("  2. rc_lowpass: Run AC (F7) 10Hz-100kHz, check -3dB at 1kHz")
    print("  3. rc_transient: Run Transient 0-5ms, see exponential charge")
    print("  4. mosfet_switch: Run DC, check MOSFET conducting")
    print("  5. diode_rectifier: Run Transient 0-33ms, see half-wave")
    print("  6. rl_circuit: Run Transient 0-500us, see current rise")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "examples"
    export_all_projects(output)
