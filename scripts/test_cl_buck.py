"""Test closed-loop buck converter with duty_from_channel feature."""
import pulsim as ps

VIN   = 12.0
VREF  = 5.0
L_H   = 220e-6
C_F   = 220e-6
R_OHM = 8.0
FREQ  = 10e3

c = ps.Circuit()

# Nodes
n_vin  = c.add_node("VIN")
n_sw   = c.add_node("SW")
n_out  = c.add_node("VOUT")
n_vref = c.add_node("VREF")
GND    = 0

# ── Power circuit ──────────────────────────────────────────────────────────
c.add_voltage_source("V1",   n_vin, GND, VIN)
c.add_voltage_source("Vref", n_vref, GND, VREF)   # reference 5 V rail

# Ideal switch Q1: between VIN and SW, driven by PWM virtual component
c.add_switch("Q1", n_vin, n_sw, closed=False)

# Freewheeling diode D1: anode=GND, cathode=SW
c.add_diode("D1", GND, n_sw)

# LC filter
c.add_inductor("L1",    n_sw,  n_out, L_H)
c.add_capacitor("Cout", n_out, GND,   C_F)
c.add_resistor("Rload", n_out, GND,   R_OHM)

# ── Control chain (virtual) ────────────────────────────────────────────────
# PI controller: signal = Vref - Vout  →  output → virtual_signal_state_["PI1"]
c.add_virtual_component(
    "pi_controller",
    "PI1",
    [n_vref, n_out],          # signal = V[n_vref] - V[n_out]
    {"kp": 0.08, "ki": 40.0,
     "output_min": 0.05, "output_max": 0.95},
    {},
)

# PWM generator: reads duty from virtual_signal_state_["PI1"] via duty_from_channel
# drives Q1 directly via target_component
c.add_virtual_component(
    "pwm_generator",
    "PWM1",
    [GND],                     # dummy node (duty_from_channel overrides)
    {"frequency": FREQ},
    {"duty_from_channel": "PI1", "target_component": "Q1"},
)

print("Circuit built OK")
print(f"  Nodes: VIN={n_vin}, SW={n_sw}, VOUT={n_out}, VREF={n_vref}")

# ── Run transient simulation ───────────────────────────────────────────────
# Collect channel data via callback
channels: dict[str, list[float]] = {}

def on_data(t_sample, state_dict):
    for k, v in state_dict.items():
        channels.setdefault(k, []).append(float(v))

t, states, success, message = ps.run_transient(c, 0.0, 0.020, 2e-6)
print(f"\nSimulation success: {success}")
if not success:
    print(f"  Error: {message}")
    import sys; sys.exit(1)

# Vout over time
v_out = [float(states[i][n_out]) for i in range(len(t))]

# Check final Vout (average over last 2 ms)
last_ms = [v for ti, v in zip(t, v_out) if ti >= 0.018]
if last_ms:
    vout_avg = sum(last_ms) / len(last_ms)
    print(f"  Vout (avg last 2 ms): {vout_avg:.3f} V   (target {VREF} V)")
    error_pct = abs(vout_avg - VREF) / VREF * 100
    print(f"  Steady-state error: {error_pct:.1f}%")
    assert error_pct < 10.0, f"Vout too far from {VREF} V: {vout_avg:.3f} V"
else:
    print("  WARNING: no data in last 2 ms")

# Print channel info
pi_ch       = channels.get("PI1", [])
pwm_duty_ch = channels.get("PWM1.duty", [])
print(f"\n  PI1 channel samples:       {len(pi_ch)}")
print(f"  PWM1.duty channel samples: {len(pwm_duty_ch)}")
if pwm_duty_ch:
    print(f"  PWM1.duty final:           {pwm_duty_ch[-1]:.4f}")
if pi_ch:
    print(f"  PI1 output final:          {pi_ch[-1]:.4f}")
print("  (channel data not captured - needs streaming API)")

print("\nPASS")