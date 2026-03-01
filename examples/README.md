# PulsimGui Example Projects

This directory contains example project files demonstrating various power electronics circuits and PulsimGui features.

## Example Projects

### Basic Circuits

| File | Description |
|------|-------------|
| `rc_circuit.pulsim` | Simple RC low-pass filter |
| `rl_circuit.pulsim` | Simple RL circuit with step response |
| `rlc_circuit.pulsim` | RLC resonant circuit |

### Power Converters

| File | Description |
|------|-------------|
| `buck_converter.pulsim` | 12V to 5V buck converter |
| `boost_converter.pulsim` | 5V to 12V boost converter |
| `buck_boost_converter.pulsim` | Inverting buck-boost converter |
| `full_bridge_inverter.pulsim` | Full-bridge DC-AC inverter |

### Application Examples

| File | Description |
|------|-------------|
| `led_driver.pulsim` | Constant current LED driver |
| `battery_charger.pulsim` | Simple battery charging circuit |

## Opening Examples

1. Launch PulsimGui
2. Go to **File > Open** (or press `Ctrl+O`)
3. Navigate to this examples directory
4. Select the example file to open

## Simulation Tips

- Press `F5` to run a transient simulation
- Adjust simulation time in **Simulation > Simulation Settings**
- Use the Waveform Viewer to analyze results
- Try modifying component values to see how they affect performance

## Creating Your Own Examples

Feel free to modify these examples or create new ones:

1. Open an example as a starting point
2. Make your modifications
3. Save with a new name using **File > Save As**

## Example Specifications

### Buck Converter
- Input: 12V DC
- Output: 5V DC @ 1A
- Switching frequency: 100 kHz
- Inductor: 100 µH
- Output capacitor: 100 µF

### Boost Converter
- Input: 5V DC
- Output: 12V DC @ 0.5A
- Switching frequency: 100 kHz
- Inductor: 47 µH
- Output capacitor: 100 µF

### Full-Bridge Inverter
- DC bus: 24V
- Output: ~17V RMS AC (bipolar PWM)
- Switching frequency: 20 kHz
- LC filter: 1 mH / 10 µF
