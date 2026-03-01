# First RC Circuit

Quick tutorial to validate installation, schematic connectivity, and simulation flow.

![RC response example](../assets/images/rc-waveform.svg)

## Objective

Build a simple RC low-pass circuit and confirm the exponential `Vout` response.

## Topology

- `Vin` (source)
- `R1 = 1kΩ`
- `C1 = 1uF`
- `GND`

Connections:

1. `Vin+ -> R1`
2. `R1 -> Vout`
3. `Vout -> C1`
4. `C1 -> GND`
5. `Vin- -> GND`

## Step-by-step in the GUI

1. Create a new project.
2. Insert `Voltage Source`, `Resistor`, `Capacitor`, and `Ground`.
3. Wire the topology above.
4. Set `R1` and `C1` parameters.
5. Configure source as step or pulse.
6. Open `Simulation Settings` and use:
   - `Start time = 0`
   - `Stop time = 10ms`
   - `Step size = 1us`
   - `Output points = 10000`
7. Click **Run**.
8. In the viewer, plot `V(vout)` and `V(vin)`.

## Expected Result

- `V(vout)` rises exponentially.
- `τ = R × C = 1k × 1u = 1ms`.
- Around `5τ` (about `5ms`), output is close to final value.

## Validation Checklist

- Simulation finishes without errors.
- `V(vout)` shows consistent first-order behavior.
- Changing `R` or `C` shifts `τ` as expected.
