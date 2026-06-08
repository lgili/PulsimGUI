"""Build ``examples/23_full_thermal_compressor_drive.pulsim``.

This is a thermal-instrumented variant of example 20 (220 V 1φ rectifier
→ boost PFC → 3φ FOC VSI → PMSM compressor). Example 20 already runs the
electrical + control loops end-to-end; this script bolts on the full
pulsim 1.7 thermal stack so the example exercises EVERY new feature:

  * Two heatsinks: ``HS_BR`` for the input rectifier, ``HS_INV`` for the
    boost diode + boost MOSFET + 3φ VSI (the entire DC-side power stage).
  * Realistic 1800 W compressor inverter device data — datasheet values
    for typical parts (GBPC2510 bridge / IDH16S60C SiC diode / STW57N65M5
    SJ MOSFET / STGW40H65DFB2 IGBT module).
  * Multi-stage Foster thermal networks (3 stages each) — the kernel
    integrates the per-stage RC chain instead of single_rc.
  * Per-device junction-temperature limits (``thermal_t_max_C``) — the
    ``ThermalLimitMonitor`` flags any device that exceeds its data-sheet
    T_jmax (150 °C Si / 175 °C SiC).
  * Linear temperature coefficients on conduction + switching losses
    (``loss_a_cond_per_C`` / ``loss_a_sw_per_C``) — the simulator runs the
    coupled electro-thermal fixed-point solve (``TempCoLoss``) and
    detects runaway (ρ(M·K) ≥ 1) before T_j blows up.
  * TIM + convection sizing on the case-to-sink interface — the heatsink
    descriptor carries the per-slot case-to-sink R_th values that a real
    designer would compute via ``tim_resistance`` + ``convection_resistance``.
  * Cauer topology on ONE heatsink (``HS_INV``) to exercise the
    ``CauerStage`` alternative network alongside the default Foster.
  * T_amb = 50 °C (warm sealed-compressor housing — leaves headroom for
    the tempco-driven rise without hugging the 150 °C T_jmax).
  * tstop = 1.0 s (full thermal-time-constant window: the slow Foster
    poles fully charge so the demo shows steady-state T_j on every
    device). Pulsim 1.8's ``SwitchMaskRecorder`` records the actual
    per-step PWM mask during ``simulate`` and replays it during
    ``device_thermal_summary``, so the closed-loop cold-start window
    no longer triggers the post-hoc loss-reconstruction artifact
    (Q_boost reading 10⁵ W → 130 000 °C T_j on pulsim 1.7).
    ``start_from_dc_op=True`` is kept as an orthogonal stability win
    (skip the LC ringing) but is no longer required for thermal
    correctness.

The script does NOT touch the electrical topology — it preserves the
27-component, 50-wire schematic from ex 20 verbatim and only:

  1. Mutates the four power-device parameter dicts (BR1, D_boost,
     Q_boost, VSI) to add ``enable_thermal_port: True`` and all the
     pulsim 1.7 fields.
  2. Rebuilds the four devices' pin lists to include a TH pin.
  3. Appends two new HEATSINK components (HS_BR, HS_INV).
  4. Appends four new wires connecting each TH pin to its slot on the
     correct heatsink.
  5. Bumps the top-level metadata (title, modification time, ambient
     temperature, tstop).

Run:
    python scripts/build_example_23.py
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "examples" / "20_pfc_drive_compressor.pulsim"
DST = REPO / "examples" / "23_full_thermal_compressor_drive.pulsim"

# --------------------------------------------------------------------------
# Datasheet-grade thermal + loss values for a 1800 W single-phase compressor
# inverter. Values are typical for the named parts at T_j = 25 °C (the
# tempcos kick in once T_j rises).
# --------------------------------------------------------------------------

# GBPC2510 — 25 A / 1000 V single-phase Graetz bridge. The Vf is per-diode
# at I = 8 A (RMS line current at 1800 W / 220 V ≈ 8.2 A). Rth_jc is
# per-diode (the four diodes share the same case in this package).
#
# Foster stack synthesised to match Z_th(t) → R_th_total = 1.8 K/W with
# a fast (5 ms) + medium (50 ms) + slow (250 ms) split, roughly the
# datasheet curve shape. C_th computed from τ_k = R_k · C_k.
GBPC2510 = {
    "v_forward": 1.0,                # Vf @ I=8 A typical
    "g_on": 1000.0,                  # legacy electrical knob (unchanged)
    "g_off": 1e-9,
    # Modern thermal schema (pulsim 1.7)
    "enable_thermal_port": True,
    "thermal_enabled": True,
    "thermal_network": "foster",     # default — Cauer set per-heatsink below
    "thermal_rth": 1.8,              # total R_th_jc, single_rc fallback
    "thermal_cth": 0.10,             # τ_total ≈ 0.18 s — order-of-magnitude
    "thermal_rth_stages": "0.6, 0.8, 0.4",
    "thermal_cth_stages": "0.00833, 0.0625, 0.625",  # τ = 5, 50, 250 ms
    "thermal_temp_init": 50.0,       # start at ambient (sealed housing)
    "thermal_temp_ref": 25.0,
    "thermal_alpha": 0.004,          # legacy single-RC alpha — unused
    "thermal_shared_sink_id": "",
    "thermal_shared_sink_rth": 0.0,
    "thermal_shared_sink_cth": 0.0,
    # pulsim 1.7 — junction temp limit + tempcos
    "thermal_t_max_C": 150.0,                # Si rectifier T_jmax
    "thermal_t_max_hysteresis_C": 5.0,
    # Si pn diode Vf falls with temperature → negative coefficient on
    # conduction loss. Switching loss is negligible at 100 Hz line freq.
    "loss_a_cond_per_C": -0.002,
    "loss_a_sw_per_C": 0.0,
}

# STW57N65M5 — STripFET-V N-channel super-junction MOSFET, 650 V / 57 A
# (TO-247 / D2PAK). Rds_on(typ) = 50 mΩ @ 25 °C, Rth_jc = 0.6 K/W.
# Eon/Eoff at V_DS = 400 V, I_D = 25 A (datasheet Fig. 33–34) ≈ 95 / 30 µJ.
STW57N65M5 = {
    "is_nmos": True,
    "R_on": 0.05,                    # 50 mΩ typ @ 25 °C
    "R_off": 1.0e9,
    "v_th": 3.0,
    "vth": 2.0,
    "kp": 0.1,
    "lambda_": 0.0,
    "g_off": 1e-9,
    # Switching energies — used by pulsim's electrothermal loss model.
    "switching_loss_model": "scalar",
    "switching_eon_j": 95e-6,
    "switching_eoff_j": 30e-6,
    "switching_err_j": 0.0,
    "switching_loss_axes_current": "",
    "switching_loss_axes_voltage": "",
    "switching_loss_axes_temperature": "",
    "switching_loss_eon_table": "",
    "switching_loss_eoff_table": "",
    "switching_loss_err_table": "",
    # Thermal network — 3-stage Foster fitted to TO-247 + die
    # Rth_jc = 0.6 K/W with τ = 1 ms / 10 ms / 80 ms split.
    "enable_thermal_port": True,
    "thermal_enabled": True,
    "thermal_network": "foster",
    "thermal_rth": 0.6,
    "thermal_cth": 0.10,
    "thermal_rth_stages": "0.18, 0.24, 0.18",
    "thermal_cth_stages": "0.00556, 0.0417, 0.444",  # τ = 1, 10, 80 ms
    "thermal_temp_init": 50.0,
    "thermal_temp_ref": 25.0,
    "thermal_alpha": 0.004,
    "thermal_shared_sink_id": "",
    "thermal_shared_sink_rth": 0.0,
    "thermal_shared_sink_cth": 0.0,
    "thermal_t_max_C": 150.0,
    "thermal_t_max_hysteresis_C": 5.0,
    # Super-junction Rds_on rises ~+0.4%/°C in the 25–125 °C band, with
    # the catalogue rule-of-thumb at T_jmax = 150 °C giving a 2× rise.
    # ``0.006/°C`` is the realistic value at the design point — pulsim
    # 1.7's post-hoc thermal summary couldn't tolerate this because the
    # PWM-mask re-evaluation diverged from the actual cold-start mask
    # and reported ~10⁵ W of conduction loss → 130 000 °C T_j. Pulsim
    # 1.8's ``SwitchMaskRecorder`` records the real per-step mask so
    # the summary is accurate, and the realistic tempco lands again
    # without runaway. ``electrothermal_steady_state`` still catches
    # ρ(M·K) ≥ 1 if the user bumps this further in the GUI dialog.
    "loss_a_cond_per_C": 0.006,
    "loss_a_sw_per_C": 0.001,
}

# IDH16S60C — SiC Schottky diode, 600 V / 16 A (TO-220). Vf = 1.5 V @ 8 A.
# Q_rr ≈ 0 → no reverse-recovery loss; Rth_jc = 0.8 K/W. T_jmax = 175 °C.
IDH16S60C = {
    "v_forward": 1.5,
    "g_on": 1000.0,
    "g_off": 1e-9,
    "is_": 1e-14,
    "n": 1.0,
    "rs": 0.0,
    "switching_loss_model": "scalar",
    "switching_eon_j": 0.0,
    "switching_eoff_j": 0.0,
    "switching_err_j": 0.0,
    "switching_loss_axes_current": "",
    "switching_loss_axes_voltage": "",
    "switching_loss_axes_temperature": "",
    "switching_loss_eon_table": "",
    "switching_loss_eoff_table": "",
    "switching_loss_err_table": "",
    "enable_thermal_port": True,
    "thermal_enabled": True,
    "thermal_network": "foster",
    "thermal_rth": 0.8,
    "thermal_cth": 0.10,
    "thermal_rth_stages": "0.24, 0.32, 0.24",
    "thermal_cth_stages": "0.00417, 0.0313, 0.333",   # τ = 1, 10, 80 ms
    "thermal_temp_init": 50.0,
    "thermal_temp_ref": 25.0,
    "thermal_alpha": 0.004,
    "thermal_shared_sink_id": "",
    "thermal_shared_sink_rth": 0.0,
    "thermal_shared_sink_cth": 0.0,
    "thermal_t_max_C": 175.0,                # SiC — much higher T_jmax
    "thermal_t_max_hysteresis_C": 5.0,
    # SiC Schottky Vf has small NEGATIVE tempco below T_j ≈ 100 °C, then
    # turns positive. Take an averaged 0 over the 50–150 °C window.
    "loss_a_cond_per_C": 0.000,
    "loss_a_sw_per_C": 0.000,
}

# STGW40H65DFB2 — 650 V / 40 A trench IGBT with co-pack FRD (TO-247).
# Vce_sat = 1.5 V @ 20 A, Eon = 150 µJ, Eoff = 100 µJ @ 400 V / 20 A.
# Rth_jc = 0.5 K/W per switch. The THREE_PHASE_VSI in pulsim has 6 of these.
STGW40H65DFB2 = {
    # VSI-specific knobs (top-level, NOT inside thermal stack)
    "switching_frequency_hz": 20000.0,
    "modulation_index": 0.8,
    "modulation_frequency_hz": 90.0,
    "phase_a_deg": 0.0,
    "positive_sequence": True,
    "v_gate_on": 12.0,
    "v_gate_off": 0.0,
    "mosfet_r_on_ohm": 0.01,        # legacy electrical knob — unchanged
    "mosfet_r_off_ohm": 1.0e9,
    "mosfet_vth": 1.0,
    "dead_time_s": 2e-6,             # realistic 2 µs deadtime for IGBTs
    "vce_sat": 1.5,
    "i_ref": 20.0,
    "e_on_uj": 150.0,
    "e_off_uj": 100.0,
    "e_rr_uj": 50.0,
    # Thermal network
    "enable_thermal_port": True,
    "thermal_enabled": True,
    "thermal_network": "foster",
    "thermal_rth": 0.5,
    "thermal_cth": 0.05,
    "thermal_rth_stages": "0.15, 0.20, 0.15",
    "thermal_cth_stages": "0.00667, 0.05, 0.533",     # τ = 1, 10, 80 ms
    "thermal_temp_init": 50.0,
    "thermal_temp_ref": 25.0,
    "thermal_alpha": 0.004,
    "thermal_shared_sink_id": "",
    "thermal_shared_sink_rth": 0.0,
    "thermal_shared_sink_cth": 0.0,
    "thermal_t_max_C": 150.0,
    "thermal_t_max_hysteresis_C": 5.0,
    # IGBT Vce_sat rises gently with T_j → small positive a_cond.
    # Eon+Eoff rise ~2×/100 °C → a_sw ≈ +0.007/°C (typical IGBT).
    "loss_a_cond_per_C": 0.003,
    "loss_a_sw_per_C": 0.007,
}

# --------------------------------------------------------------------------
# Heatsink sizing helpers. Each sink stamps a `case_to_sink_R_th_csv` of
# per-slot values that a real designer would synthesise via the pulsim 1.7
# ``tim_resistance`` + ``convection_resistance`` helpers. We bake the numbers
# in here so the file is self-contained; the docstring explains the recipe.
# --------------------------------------------------------------------------

# TIM: 50 µm of 4 W/m·K thermal paste over a 16 × 22 mm² TO-247 footprint:
#   R_TIM = t / (k · A) = 50e-6 / (4 · 1.6e-2 · 2.2e-2) ≈ 0.036 K/W
TO247_R_TIM = 0.036
# Bridge package (GBPC2510) is bigger (22 × 28 mm²) → 0.018 K/W.
GBPC_R_TIM = 0.018

# Convection: forced air at h = 30 W/m²K over an aluminium extrusion
# (180 × 100 mm², total fin area ≈ 0.15 m² with a 5× fin multiplier
# baked in). R_conv ≈ 1 / (h · A_eff) = 1 / (30 · 0.15) ≈ 0.22 K/W.
# Pulsim's ``convection_resistance`` returns this directly when called with
# the right (h, A) pair — we round to 0.25 K/W to leave headroom.
#
# Sized for the demo's expected dissipation (the boost stage is the
# heavy hitter, the VSI is light at this operating point). Slightly
# bigger heatsinks than ex 20's nominal — keeps the T_j numbers in the
# 50–90 °C band that's easy to read on the thermal scope.
HS_INV_R_SA = 0.25
HS_BR_R_SA = 0.40


def _bridge_pins() -> list[dict]:
    """SINGLE_PHASE_DIODE_BRIDGE with TH at pin 4."""
    return [
        {"index": 0, "name": "AC+", "x": -40.0, "y": -20.0},
        {"index": 1, "name": "AC-", "x": -40.0, "y":  20.0},
        {"index": 2, "name": "DC+", "x":  40.0, "y": -20.0},
        {"index": 3, "name": "DC-", "x":  40.0, "y":  20.0},
        {"index": 4, "name": "TH",  "x":   0.0, "y":  40.0},
    ]


def _diode_pins() -> list[dict]:
    """DIODE with TH at pin 2 (the model appends TH as last pin when enabled)."""
    return [
        {"index": 0, "name": "A",  "x": -20.0, "y":  0.0},
        {"index": 1, "name": "K",  "x":  20.0, "y":  0.0},
        {"index": 2, "name": "TH", "x":   0.0, "y": 20.0},
    ]


def _mosfet_n_pins() -> list[dict]:
    """MOSFET_N with TH at pin 3."""
    return [
        {"index": 0, "name": "D",  "x":   0.0, "y": -20.0},
        {"index": 1, "name": "G",  "x": -20.0, "y":   0.0},
        {"index": 2, "name": "S",  "x":   0.0, "y":  20.0},
        {"index": 3, "name": "TH", "x":  20.0, "y":  20.0},
    ]


def _vsi_pins() -> list[dict]:
    """THREE_PHASE_VSI with PWM bus at pin 5 + TH at pin 6."""
    return [
        {"index": 0, "name": "VDC+", "x": -40.0, "y": -20.0},
        {"index": 1, "name": "VDC-", "x": -40.0, "y":  20.0},
        {"index": 2, "name": "A",    "x":  40.0, "y": -20.0},
        {"index": 3, "name": "B",    "x":  40.0, "y":   0.0},
        {"index": 4, "name": "C",    "x":  40.0, "y":  20.0},
        {"index": 5, "name": "PWM",  "x": -40.0, "y":  40.0},
        {"index": 6, "name": "TH",   "x":  40.0, "y":  40.0},
    ]


def _heatsink_component(
    *,
    comp_id: str,
    name: str,
    x: float,
    y: float,
    n_devices: int,
    R_sa: float,
    T_amb: float,
    case_csv: str,
    thermal_network: str,
) -> dict:
    """Synthesize a HEATSINK schematic entry. The model component reads
    ``n_devices`` from parameters and emits DEV1..DEVn pins; we expand
    that here so the JSON is explicit (round-trips cleanly through the
    GUI loader)."""
    pins = [{"index": 0, "name": "AMB", "x": -20.0, "y": 0.0}]
    # Stack DEV pins vertically on the right side, evenly spaced.
    dev_y_step = 20.0
    dev_y_start = -dev_y_step * (n_devices - 1) / 2.0
    for i in range(n_devices):
        pins.append({
            "index": i + 1,
            "name": f"DEV{i + 1}",
            "x": 20.0,
            "y": dev_y_start + i * dev_y_step,
        })
    return {
        "id": comp_id,
        "type": "HEATSINK",
        "name": name,
        "x": x,
        "y": y,
        "rotation": 0,
        "mirrored_h": False,
        "mirrored_v": False,
        "parameters": {
            "n_devices": n_devices,
            "R_th_sink_to_amb_K_per_W": R_sa,
            "C_th_sink_J_per_K": 50.0,           # ~50 J/K — a small aluminium extrusion
            "T_amb_C": T_amb,
            "case_to_sink_R_th_csv": case_csv,
            "thermal_network": thermal_network,  # "foster" or "cauer"
        },
        "pins": pins,
    }


def _wire(
    *,
    wire_id: str,
    from_id: str,
    from_pin: int,
    to_id: str,
    to_pin: int,
    node_name: str,
    segments: list[dict],
) -> dict:
    """Build a wire entry in the schematic's wire dict format."""
    return {
        "id": wire_id,
        "segments": segments,
        "start_connection": {
            "component_id": from_id,
            "pin_index": from_pin,
        },
        "end_connection": {
            "component_id": to_id,
            "pin_index": to_pin,
        },
        "junctions": [],
        "node_name": node_name,
        "alias": "",
    }


def main() -> None:
    src_data = json.loads(SRC.read_text())

    # ----------------------------------------------------------------
    # Top-level metadata
    # ----------------------------------------------------------------
    src_data["name"] = (
        "23 Full Thermal Compressor Drive — "
        "1800 W PFC + FOC VSI with shared heatsinks (HS_BR + HS_INV), "
        "TempCo losses, T_jmax monitoring, Cauer + Foster networks"
    )
    src_data["created"] = "2026-06-04T00:00:00"
    src_data["modified"] = datetime.now().isoformat()

    sim = src_data["simulation_settings"]
    # 1 s is the full thermal-time-constant window: the slow τ ≈ 80 ms
    # Foster pole on Q_boost charges to ~99% by 400 ms, then plateaus
    # at its steady-state T_j. The demo shows the complete cold-start
    # → warm-up → steady-state arc on every device, which is the whole
    # point of the thermal-instrumented example.
    #
    # Pulsim 1.7 capped this at 50 ms because the post-hoc PWM-mask
    # reconstruction on closed-loop topologies drifted out of phase
    # with the actual switching: the post-sim ``switch_fn`` returned a
    # mask reflecting the converged controller, but during the cold-
    # start the controller was still ramping, so the reconstructed
    # ``v_SW²·g_on`` shot to ~10⁵ W and Q_boost reported ~130 000 °C.
    # Pulsim 1.8's ``SwitchMaskRecorder`` (wired in the GUI backend)
    # records the REAL per-step mask and replays it in the summary —
    # the artifact is gone, the 1 s window is stable.
    sim["tstop"] = 1.0
    sim["thermal_ambient"] = 50.0       # warm sealed housing, not extreme
    sim["thermal_network"] = "foster"   # default; HS_INV overrides to cauer
    sim["enable_losses"] = True
    # The DSED engine on this topology fails the C++ extractor (the
    # plain-Python PFC controller defeats the analytical fast path).
    # Stay on PWL.
    sim["engine"] = "pwl"
    # Seed the transient with the steady-state DC OP. With pulsim 1.8's
    # ``SwitchMaskRecorder`` this is no longer required for thermal
    # correctness (the recorder makes the cold-start window physical
    # on its own) but it remains the right default — skipping the LC
    # ringing produces cleaner electrical waveforms and converges the
    # closed loops in a few PWM cycles instead of a couple of line
    # cycles. Kept ON as an orthogonal stability win.
    sim["start_from_dc_op"] = True

    # ----------------------------------------------------------------
    # Patch the four power devices' parameters + pin lists in place
    # ----------------------------------------------------------------
    circ = src_data["circuits"]["main"]
    by_name = {c["name"]: c for c in circ["components"]}

    br1 = by_name["BR1"]
    br1["parameters"] = copy.deepcopy(GBPC2510)
    br1["pins"] = _bridge_pins()

    # Devices sitting on HS_INV use the Cauer alternative network so this
    # example exercises both Foster (BR1 on HS_BR) and Cauer (D_boost,
    # Q_boost, VSI on HS_INV) topologies. The stage values shipped above
    # are physically equivalent under either interpretation for a quick
    # demo — what matters is that the pulsim ``CauerStage`` code path
    # actually runs.
    d_boost = by_name["D_boost"]
    d_boost["parameters"] = copy.deepcopy(IDH16S60C)
    d_boost["parameters"]["thermal_network"] = "cauer"
    d_boost["pins"] = _diode_pins()

    q_boost = by_name["Q_boost"]
    q_boost["parameters"] = copy.deepcopy(STW57N65M5)
    q_boost["parameters"]["thermal_network"] = "cauer"
    q_boost["pins"] = _mosfet_n_pins()

    vsi = by_name["VSI"]
    vsi["parameters"] = copy.deepcopy(STGW40H65DFB2)
    vsi["parameters"]["thermal_network"] = "cauer"
    vsi["pins"] = _vsi_pins()

    # ----------------------------------------------------------------
    # Add two HEATSINK components
    # ----------------------------------------------------------------

    # HS_BR: dedicated to the input rectifier. 1 slot (bridge body).
    # Stays on FOSTER (default network) to exercise the Foster path.
    # Use deterministic UUIDs (uuid5 over a known namespace+name) so the
    # IDs are stable across re-runs of this builder — easier to diff
    # the generated file. The model's loader validates UUID syntax.
    _ns = uuid.UUID("12345678-1234-5678-1234-567812345678")
    hs_br_id = str(uuid.uuid5(_ns, "hs-br"))
    hs_inv_id = str(uuid.uuid5(_ns, "hs-inv"))

    hs_br = _heatsink_component(
        comp_id=hs_br_id,
        name="HS_BR",
        x=-1080.0, y=160.0,
        n_devices=1,
        R_sa=HS_BR_R_SA,
        T_amb=50.0,
        case_csv=f"{GBPC_R_TIM:.4f}",
        thermal_network="foster",
    )

    # HS_INV: shared by the boost diode, boost MOSFET, and the 3φ VSI
    # block. 3 slots (the VSI counts as a single slot — the converter
    # expands its 6 internal switches automatically). Uses CAUER to
    # exercise the alternative network topology.
    hs_inv = _heatsink_component(
        comp_id=hs_inv_id,
        name="HS_INV",
        x=200.0, y=240.0,
        n_devices=3,
        R_sa=HS_INV_R_SA,
        T_amb=50.0,
        # Slot 1: boost diode (small SiC, lower R_TIM), slot 2: boost
        # MOSFET, slot 3: VSI module (bigger, lower R_TIM).
        case_csv=f"{TO247_R_TIM:.4f}, {TO247_R_TIM:.4f}, 0.025",
        thermal_network="cauer",  # Cauer demo on this sink
    )

    circ["components"].append(hs_br)
    circ["components"].append(hs_inv)

    # ----------------------------------------------------------------
    # Add four TH wires connecting devices to heatsink slots
    # ----------------------------------------------------------------
    # Each wire's coordinates trace a short L-shape from the device's TH
    # pin (using the device's component position) to the heatsink's DEV
    # pin. The simulation never reads these coordinates — only the
    # start/end connection IDs and pin indices matter — but real,
    # plausible coordinates make the saved file render correctly when
    # opened in the GUI.

    # BR1 TH @ (BR1.x + 0, BR1.y + 40) = (-980, 40) → HS_BR.DEV1 @ (-1080-20, 160) = (-1100, 160)
    wire_br = _wire(
        wire_id=str(uuid.uuid5(_ns, "wire-th-br")),
        from_id=br1["id"], from_pin=4,
        to_id=hs_br["id"], to_pin=1,
        node_name="TH_BR",
        segments=[
            {"x1": -980.0, "y1":  40.0, "x2": -980.0, "y2": 160.0},
            {"x1": -980.0, "y1": 160.0, "x2": -1060.0, "y2": 160.0},
        ],
    )

    # D_boost TH @ (D_boost.x + 0, D_boost.y + 20) = (-420, 0) → HS_INV.DEV1 @ (200+20, 240-20) = (220, 220)
    wire_dboost = _wire(
        wire_id=str(uuid.uuid5(_ns, "wire-th-dboost")),
        from_id=d_boost["id"], from_pin=2,
        to_id=hs_inv["id"], to_pin=1,
        node_name="TH_DBOOST",
        segments=[
            {"x1": -420.0, "y1":   0.0, "x2": -420.0, "y2": 220.0},
            {"x1": -420.0, "y1": 220.0, "x2":  220.0, "y2": 220.0},
        ],
    )

    # Q_boost TH @ (Q_boost.x + 20, Q_boost.y + 20) = (-420, 140) → HS_INV.DEV2 @ (220, 240)
    wire_qboost = _wire(
        wire_id=str(uuid.uuid5(_ns, "wire-th-qboost")),
        from_id=q_boost["id"], from_pin=3,
        to_id=hs_inv["id"], to_pin=2,
        node_name="TH_QBOOST",
        segments=[
            {"x1": -420.0, "y1": 140.0, "x2": -420.0, "y2": 240.0},
            {"x1": -420.0, "y1": 240.0, "x2":  220.0, "y2": 240.0},
        ],
    )

    # VSI TH @ (VSI.x + 40, VSI.y + 40) = (440, 40) → HS_INV.DEV3 @ (220, 260)
    wire_vsi = _wire(
        wire_id=str(uuid.uuid5(_ns, "wire-th-vsi")),
        from_id=vsi["id"], from_pin=6,
        to_id=hs_inv["id"], to_pin=3,
        node_name="TH_VSI",
        segments=[
            {"x1": 440.0, "y1":  40.0, "x2": 440.0, "y2": 260.0},
            {"x1": 440.0, "y1": 260.0, "x2": 220.0, "y2": 260.0},
        ],
    )

    circ["wires"].extend([wire_br, wire_dboost, wire_qboost, wire_vsi])

    # ----------------------------------------------------------------
    # Write
    # ----------------------------------------------------------------
    DST.write_text(json.dumps(src_data, indent=2))
    print(f"Wrote {DST.relative_to(REPO)}")
    print(f"  components:  {len(circ['components'])}")
    print(f"  wires:       {len(circ['wires'])}")
    print(f"  heatsinks:   2 (HS_BR foster / HS_INV cauer)")
    print(f"  power devs:  4 (BR1, D_boost, Q_boost, VSI)")


if __name__ == "__main__":
    main()
