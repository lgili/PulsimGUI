# PulsimGui Example Projects

This directory contains runnable `.pulsim` examples for PulsimGui.

## Available Examples

### Core tutorials (generated)

| File | Description |
|------|-------------|
| `01_voltage_divider.pulsim` | DC voltage divider |
| `02_rc_lowpass.pulsim` | RC low-pass response |
| `03_rc_transient.pulsim` | RC transient charging |
| `04_mosfet_switch.pulsim` | MOSFET switching stage |
| `05_diode_rectifier.pulsim` | Half-wave rectifier |
| `06_rl_circuit.pulsim` | RL transient response |

### Additional validation/demo

| File | Description |
|------|-------------|
| `07_rc_backend_smoke.pulsim` | Backend smoke test circuit |
| `08_probe_scope_thermal_demo.pulsim` | Probe + electrical/thermal scope routing |
| `09_buck_closed_loop_loss_thermal_validation.pulsim` | Closed-loop buck with losses + thermal scope validation |
| `09_buck_closed_loop_loss_thermal_validation_expected.md` | Theoretical targets and pass criteria for example 09 |
| `PulsimProjects.pulsim` | Minimal starter project |
| `simple_rc.pulsim` | Legacy simple RC example |
| `rc_circuit.pulsim` | RC example variant |
| `rlc_circuit.pulsim` | RLC resonant example |

### Power converters

| File | Description |
|------|-------------|
| `buck_converter.pulsim` | Buck converter |
| `buck_converter_closed_loop.pulsim` | Buck converter with closed-loop control |
| `boost_converter.pulsim` | Boost converter |
| `flyback_converter.pulsim` | Flyback converter |

## How to Run

1. Open PulsimGui.
2. Click **File > Open** (or `Ctrl+O`).
3. Select any `.pulsim` file in this folder.
4. Press `F5` for transient, `F6` for DC, or `F7` for AC.

## Notes

- All examples use the current project simulation settings schema.
- Each project includes at least one scope block for quick waveform inspection.
- In `08_probe_scope_thermal_demo.pulsim`, connect electrical probe outputs to electrical scopes and the `TH` pin to thermal scope channels.
- In `09_buck_closed_loop_loss_thermal_validation.pulsim`, compare results against `09_buck_closed_loop_loss_thermal_validation_expected.md`.
