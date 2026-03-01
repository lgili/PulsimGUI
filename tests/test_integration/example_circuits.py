"""Example circuit data for integration testing and GUI validation.

Each circuit is defined as a function that returns circuit_data dict.
These can be used in:
1. Integration tests
2. Exported as JSON for GUI testing
3. Manual validation

Circuit naming convention:
- V<n>: Voltage source
- R<n>: Resistor
- C<n>: Capacitor
- L<n>: Inductor
- M<n>: MOSFET
- D<n>: Diode
"""

from __future__ import annotations

import json
from pathlib import Path


def voltage_divider() -> dict:
    """Simple resistive voltage divider for DC analysis.

    Circuit:
        V1 (10V) --- R1 (1k) --- node "out" --- R2 (1k) --- GND

    Expected DC results:
        V(out) = 5.0V (half of input)
        I(R1) = I(R2) = 5mA

    GUI Validation:
        1. Create circuit with V1=10V, R1=1k, R2=1k
        2. Run DC Operating Point (F6)
        3. Verify V(out) ≈ 5.0V
    """
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {"dc_value": 10.0, "ac_magnitude": 1.0},
                "pin_nodes": ["in", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["in", "out"],
            },
            {
                "id": "r2",
                "type": "RESISTOR",
                "name": "R2",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["out", "0"],
            },
        ],
        "node_map": {
            "v1": ["in", "0"],
            "r1": ["in", "out"],
            "r2": ["out", "0"],
        },
        "node_aliases": {
            "in": "in",
            "out": "out",
            "0": "0",
        },
        "wires": [],
        "metadata": {"name": "Voltage Divider"},
    }


def rc_lowpass_filter() -> dict:
    """RC low-pass filter for AC analysis.

    Circuit:
        V1 (AC) --- R1 (1k) --- node "out" --- C1 (159nF) --- GND

    Cutoff frequency: fc = 1/(2*pi*R*C) = 1/(2*pi*1000*159e-9) ≈ 1000 Hz

    Expected AC results:
        - At f << fc: |H| ≈ 0 dB, phase ≈ 0°
        - At f = fc: |H| ≈ -3 dB, phase ≈ -45°
        - At f >> fc: |H| rolls off at -20 dB/decade, phase → -90°

    GUI Validation:
        1. Create circuit with R1=1k, C1=159nF
        2. Run AC Analysis (F7) from 10Hz to 100kHz
        3. Verify -3dB point at ~1kHz
        4. Verify phase is -45° at cutoff
    """
    # R = 1k, C = 159nF gives fc ≈ 1000 Hz
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {"dc_value": 0.0, "ac_magnitude": 1.0},
                "pin_nodes": ["in", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["in", "out"],
            },
            {
                "id": "c1",
                "type": "CAPACITOR",
                "name": "C1",
                "parameters": {"capacitance": 159e-9},
                "pin_nodes": ["out", "0"],
            },
        ],
        "node_map": {
            "v1": ["in", "0"],
            "r1": ["in", "out"],
            "c1": ["out", "0"],
        },
        "node_aliases": {
            "in": "in",
            "out": "out",
            "0": "0",
        },
        "wires": [],
        "metadata": {"name": "RC Low-Pass Filter"},
    }


def rc_transient() -> dict:
    """RC circuit with pulse source for transient analysis.

    Circuit:
        V1 (pulse 0-5V) --- R1 (1k) --- node "out" --- C1 (1uF) --- GND

    Time constant: tau = R*C = 1000 * 1e-6 = 1ms

    Expected transient results:
        - Capacitor charges exponentially
        - V(out) = Vfinal * (1 - e^(-t/tau))
        - At t = tau: V(out) ≈ 63.2% of final
        - At t = 5*tau: V(out) ≈ 99.3% of final

    GUI Validation:
        1. Create circuit with R1=1k, C1=1µF
        2. Set pulse source: 0V to 5V, rise time 1ns
        3. Run Transient from 0 to 5ms
        4. Verify exponential charging curve
        5. At t=1ms: V(out) ≈ 3.16V (63.2% of 5V)
    """
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {
                    "dc_value": 5.0,
                    "waveform": "pulse",
                    "v_low": 0.0,
                    "v_high": 5.0,
                    "delay": 0.0,
                    "rise_time": 1e-9,
                    "fall_time": 1e-9,
                    "pulse_width": 10e-3,
                    "period": 20e-3,
                },
                "pin_nodes": ["in", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["in", "out"],
            },
            {
                "id": "c1",
                "type": "CAPACITOR",
                "name": "C1",
                "parameters": {"capacitance": 1e-6},
                "pin_nodes": ["out", "0"],
            },
        ],
        "node_map": {
            "v1": ["in", "0"],
            "r1": ["in", "out"],
            "c1": ["out", "0"],
        },
        "node_aliases": {
            "in": "in",
            "out": "out",
            "0": "0",
        },
        "wires": [],
        "metadata": {"name": "RC Transient"},
    }


def mosfet_switch() -> dict:
    """Simple MOSFET switch for thermal analysis.

    Circuit:
        Vdd (12V) --- R_load (10Ω) --- drain
                                        |
        Vgate (10V) --- gate           M1 (N-MOSFET)
                                        |
                                      source --- GND

    Expected results:
        - MOSFET conducts when Vgs > Vth
        - Current through load: I ≈ Vdd / (R_load + Rds_on)
        - Power dissipation in MOSFET: P = I² * Rds_on

    GUI Validation:
        1. Create circuit with Vdd=12V, Vgate=10V, R_load=10Ω
        2. Run DC Operating Point
        3. Run Transient (PWM switching if desired)
        4. Open Thermal Viewer
        5. Verify junction temperature rise from power dissipation
    """
    return {
        "components": [
            {
                "id": "vdd",
                "type": "VOLTAGE_SOURCE",
                "name": "Vdd",
                "parameters": {"dc_value": 12.0},
                "pin_nodes": ["vdd", "0"],
            },
            {
                "id": "vgate",
                "type": "VOLTAGE_SOURCE",
                "name": "Vgate",
                "parameters": {"dc_value": 10.0},
                "pin_nodes": ["gate", "0"],
            },
            {
                "id": "r_load",
                "type": "RESISTOR",
                "name": "R_load",
                "parameters": {"resistance": 10.0},
                "pin_nodes": ["vdd", "drain"],
            },
            {
                "id": "m1",
                "type": "MOSFET_N",
                "name": "M1",
                "parameters": {
                    "vth": 2.0,
                    "kp": 0.5,
                    "rds_on": 0.1,
                },
                "pin_nodes": ["drain", "gate", "0"],  # D, G, S
            },
        ],
        "node_map": {
            "vdd": ["vdd", "0"],
            "vgate": ["gate", "0"],
            "r_load": ["vdd", "drain"],
            "m1": ["drain", "gate", "0"],
        },
        "node_aliases": {
            "vdd": "Vdd",
            "gate": "gate",
            "drain": "drain",
            "0": "0",
        },
        "wires": [],
        "metadata": {"name": "MOSFET Switch"},
    }


def diode_rectifier() -> dict:
    """Half-wave rectifier for convergence testing.

    Circuit:
        V1 (AC sine) --- D1 --- node "out" --- R_load (1k) --- GND

    This circuit tests:
        - Diode model convergence
        - Nonlinear DC analysis
        - Transient with switching

    GUI Validation:
        1. Create circuit with sine source ±10V @ 60Hz
        2. Run DC Operating Point (should converge)
        3. Run Transient for 2 periods (33ms)
        4. Verify half-wave rectified output
    """
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {
                    "dc_value": 0.0,
                    "waveform": "sine",
                    "amplitude": 10.0,
                    "frequency": 60.0,
                    "phase": 0.0,
                },
                "pin_nodes": ["in", "0"],
            },
            {
                "id": "d1",
                "type": "DIODE",
                "name": "D1",
                "parameters": {
                    "is_": 1e-14,
                    "n": 1.0,
                    "vf": 0.7,
                },
                "pin_nodes": ["in", "out"],
            },
            {
                "id": "r_load",
                "type": "RESISTOR",
                "name": "R_load",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["out", "0"],
            },
        ],
        "node_map": {
            "v1": ["in", "0"],
            "d1": ["in", "out"],
            "r_load": ["out", "0"],
        },
        "node_aliases": {
            "in": "in",
            "out": "out",
            "0": "0",
        },
        "wires": [],
        "metadata": {"name": "Half-Wave Rectifier"},
    }


def rl_circuit() -> dict:
    """RL circuit for transient analysis.

    Circuit:
        V1 (step) --- R1 (100Ω) --- L1 (10mH) --- GND

    Time constant: tau = L/R = 10e-3 / 100 = 100µs

    Expected transient results:
        - Current rises exponentially
        - I = I_final * (1 - e^(-t/tau))
        - At t = tau: I ≈ 63.2% of final

    GUI Validation:
        1. Create circuit with R1=100Ω, L1=10mH
        2. Set step voltage from 0 to 10V
        3. Run Transient from 0 to 500µs
        4. Verify exponential current rise
    """
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {
                    "dc_value": 10.0,
                    "waveform": "pulse",
                    "v_low": 0.0,
                    "v_high": 10.0,
                    "delay": 0.0,
                    "rise_time": 1e-9,
                    "fall_time": 1e-9,
                    "pulse_width": 1e-3,
                    "period": 2e-3,
                },
                "pin_nodes": ["in", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 100.0},
                "pin_nodes": ["in", "mid"],
            },
            {
                "id": "l1",
                "type": "INDUCTOR",
                "name": "L1",
                "parameters": {"inductance": 10e-3},
                "pin_nodes": ["mid", "0"],
            },
        ],
        "node_map": {
            "v1": ["in", "0"],
            "r1": ["in", "mid"],
            "l1": ["mid", "0"],
        },
        "node_aliases": {
            "in": "in",
            "mid": "mid",
            "0": "0",
        },
        "wires": [],
        "metadata": {"name": "RL Circuit"},
    }


# Registry of all example circuits
EXAMPLE_CIRCUITS = {
    "voltage_divider": voltage_divider,
    "rc_lowpass_filter": rc_lowpass_filter,
    "rc_transient": rc_transient,
    "mosfet_switch": mosfet_switch,
    "diode_rectifier": diode_rectifier,
    "rl_circuit": rl_circuit,
}


def export_all_to_json(output_dir: Path | str) -> None:
    """Export all example circuits to JSON files for GUI testing.

    Args:
        output_dir: Directory to write JSON files to.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, circuit_fn in EXAMPLE_CIRCUITS.items():
        circuit_data = circuit_fn()
        output_file = output_dir / f"{name}.json"
        with open(output_file, "w") as f:
            json.dump(circuit_data, f, indent=2)
        print(f"Exported: {output_file}")


if __name__ == "__main__":
    # When run directly, export all circuits to examples directory
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "examples"
    export_all_to_json(output)
