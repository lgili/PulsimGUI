"""Validate diode-bridge losses & junction temperature across 4 converters.

Loads the four ``examples/validation_bridge_*.pulsim`` files (same files
you open in the GUI), runs each transient, and exports a comparison
table + waveforms. The .pulsim files are the single source of truth —
edit them in the GUI to refine the simulation and the script picks up
the changes automatically.

Converters:
    240 W  / CAP + voltage doubler  → 2 active diodes (D1, D2)
    400 W  / CAP + voltage doubler  → 2 active diodes (D1, D2)
    550 W  / CAP + voltage doubler  → 2 active diodes (D1, D2)
    1000 W / Full bridge + PFC ref  → 4 active diodes (D1..D4), L_in
                                      oversized to approximate PFC
                                      sinusoidal-current shaping

Diode model: GBU2506 (MCC) — R_on ≈ 0.083 Ω from V_F/I_F datasheet point.
Thermal: bench-validated R_θ,HS per power class (25, 16, 14, 5 °C/W from
the H13883 / CR27815 / CR22927 / CR22348 reports), R_θ,JC = 1.0 °C/W
from datasheet, T_amb = 25 °C nominal.

Outputs:
    /tmp/bridge_losses_summary.csv   — one row per converter
    /tmp/bridge_overview.png         — 4-panel V_bus + I_in waveforms

Usage::

    PYTHONPATH=src python3 scripts/validate_bridge_losses.py
"""
from __future__ import annotations

import csv
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, "/Users/lgili/Documents/01 - Codes/01 - Github/Pulsim/build/python")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
QApplication.instance() or QApplication(sys.argv)

import pulsim
from pulsimgui.models.project import Project
from pulsimgui.services.circuit_data_builder import CircuitDataBuilder
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.simulation_service import (
    normalize_step_mode, normalize_formulation_mode,
    normalize_thermal_policy, normalize_control_mode,
    SimulationSettings,
)
from pulsimgui.utils.net_utils import build_node_map, build_node_alias_map


# ---------------------------------------------------------------------------
# GBU2506 (MCC) parameters
# ---------------------------------------------------------------------------
GBU2506_R_ON = 1.0 / 12.0          # 0.083 Ω from datasheet V_F point
GBU2506_R_TH_JC = 1.0              # °C/W per junction
T_AMBIENT = 25.0                   # °C nominal


# Bench-validated thermal-to-heatsink per power class (from production
# thermal reports — see slide 13 of the GBU2506 evaluation deck).
R_TH_HS_BENCH = {
    240: 25.0,    # CF03B03 — 47 datapoints (H13883/H14189/H12930)
    400: 16.0,    # CF03B01 — 19 datapoints (CR27815/VLT403U)
    550: 14.0,    # CF05E   — 12 datapoints (CR22927)
    1000: 5.0,    # CF10B   — 28 datapoints (CR22348/H13710 SuperMaia)
}


# ---------------------------------------------------------------------------
# Spec table
# ---------------------------------------------------------------------------
@dataclass
class SimSpec:
    label: str
    pulsim_file: str
    power_w: float
    topology: str          # "doubler" or "bridge_pfc"
    n_active_diodes: int


SIMS = [
    SimSpec("240W doubler",     "validation_bridge_240W.pulsim",      240,  "doubler",    2),
    SimSpec("400W doubler",     "validation_bridge_400W.pulsim",      400,  "doubler",    2),
    SimSpec("550W doubler",     "validation_bridge_550W.pulsim",      550,  "doubler",    2),
    SimSpec("1000W bridge+PFC", "validation_bridge_1000W_pfc.pulsim", 1000, "bridge_pfc", 4),
]


# ---------------------------------------------------------------------------
# Run one .pulsim
# ---------------------------------------------------------------------------
def run_one(spec: SimSpec) -> dict:
    path = ROOT / "examples" / spec.pulsim_file
    print(f"\n=== {spec.label} ===")
    print(f"  Loading {path.name}")
    project = Project.load(path)

    settings = SimulationSettings(
        t_start=project.simulation_settings.tstart,
        t_stop=project.simulation_settings.tstop,
        t_step=project.simulation_settings.dt,
        step_mode=project.simulation_settings.step_mode,
        max_step=project.simulation_settings.max_step,
    )

    data = CircuitDataBuilder().build(
        project, settings=settings,
        normalize_step_mode=normalize_step_mode,
        normalize_formulation_mode=normalize_formulation_mode,
        normalize_thermal_policy=normalize_thermal_policy,
        normalize_control_mode=normalize_control_mode,
        build_node_map=build_node_map,
        build_node_alias_map=build_node_alias_map,
        copy_result=True, cooperative_yield=False,
    )

    circuit = CircuitConverter(pulsim).build(data)
    print(f"  nodes: {circuit.num_nodes()}, branches: {circuit.num_branches()}")

    opts = pulsim.SimulationOptions()
    opts.tstart = project.simulation_settings.tstart
    opts.tstop = project.simulation_settings.tstop
    opts.dt = project.simulation_settings.dt
    opts.dt_min = 1e-9
    opts.dt_max = project.simulation_settings.max_step
    opts.adaptive_timestep = (project.simulation_settings.step_mode == "variable")
    opts.enable_bdf_order_control = False
    opts.newton_options.num_nodes = circuit.num_nodes()
    opts.newton_options.num_branches = circuit.num_branches()
    opts.enable_events = True
    # No pre-charge — let DC OP find initial conditions naturally.

    sim = pulsim.Simulator(circuit, opts)
    result = sim.run_transient()
    print(f"  status: {result.final_status}, success: {result.success}, time pts: {len(result.time)}")
    if not result.success:
        print(f"  message: {result.message}")
        return {"spec": spec, "result": result, "ok": False}

    # Extract steady-state metrics
    aliases = data["node_aliases"]
    name_to_idx = {v: int(k) for k, v in aliases.items()}
    idx_plus = name_to_idx.get("n_dc_plus", -1)
    idx_minus = name_to_idx.get("n_dc_minus", -1)
    n_nodes = circuit.num_nodes()
    ss = len(result.states) // 2

    bus_voltage = [s[idx_plus] - s[idx_minus] for s in result.states] if idx_plus >= 0 and idx_minus >= 0 else [0] * len(result.states)
    # L_in is the second branch (index 1) — V_ac reserves branch 0.
    i_input = [s[n_nodes + 1] for s in result.states]

    v_bus_ss = bus_voltage[ss:]
    i_in_ss = i_input[ss:]
    v_bus_mean = sum(v_bus_ss) / len(v_bus_ss)
    i_in_rms = math.sqrt(sum(x * x for x in i_in_ss) / len(i_in_ss))
    i_in_peak = max(abs(x) for x in i_in_ss)

    # Bridge loss: P_per_active = I_AC_rms² · R_on / 2 (each active diode
    # conducts half-cycle). P_total = N_active · P_per_active.
    p_per_active = 0.5 * i_in_rms * i_in_rms * GBU2506_R_ON
    p_bridge = spec.n_active_diodes * p_per_active

    # Junction temperature: T_J = T_amb + P_bridge · (R_θ,JC + R_θ,HS_bench)
    r_hs = R_TH_HS_BENCH.get(int(spec.power_w), 14.0)
    t_j = T_AMBIENT + p_bridge * (GBU2506_R_TH_JC + r_hs)

    print(f"  V_bus_mean = {v_bus_mean:.1f} V, I_in_rms = {i_in_rms:.2f} A, I_in_peak = {i_in_peak:.2f} A")
    print(f"  P_bridge = {p_bridge:.2f} W ({spec.n_active_diodes} active diodes), T_J = {t_j:.1f} °C")

    return {
        "spec": spec,
        "result": result,
        "ok": True,
        "bus_voltage": bus_voltage,
        "i_input": i_input,
        "v_bus_mean": v_bus_mean,
        "i_in_rms": i_in_rms,
        "i_in_peak": i_in_peak,
        "p_bridge": p_bridge,
        "t_j": t_j,
        "r_hs": r_hs,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"Pulsim {pulsim.__version__}")
    print(f"GBU2506 (MCC): R_on ≈ {GBU2506_R_ON:.4f} Ω, R_θ,JC = {GBU2506_R_TH_JC} °C/W")
    print(f"Bench R_θ,HS: {R_TH_HS_BENCH}")
    print(f"T_ambient: {T_AMBIENT} °C")

    runs = [run_one(spec) for spec in SIMS]
    runs_ok = [r for r in runs if r["ok"]]

    # CSV
    csv_path = Path("/tmp/bridge_losses_summary.csv")
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Converter", "Topology", "P_rated_W", "V_bus_V",
            "I_in_rms_A", "I_in_peak_A",
            "P_bridge_W", "R_th_HS_C_per_W", "T_J_C",
        ])
        for r in runs_ok:
            s = r["spec"]
            w.writerow([
                s.label, s.topology, s.power_w,
                f"{r['v_bus_mean']:.2f}",
                f"{r['i_in_rms']:.3f}", f"{r['i_in_peak']:.3f}",
                f"{r['p_bridge']:.3f}", f"{r['r_hs']:.1f}",
                f"{r['t_j']:.1f}",
            ])
    print(f"\nWrote {csv_path}")

    # Summary table
    print("\n" + "=" * 92)
    print(f"{'Converter':<22}{'V_bus':>10}{'I_rms':>10}{'I_peak':>10}{'P_bridge':>12}{'T_J':>10}")
    print("=" * 92)
    for r in runs_ok:
        s = r["spec"]
        print(f"{s.label:<22}{r['v_bus_mean']:>7.1f} V {r['i_in_rms']:>6.2f} A {r['i_in_peak']:>6.2f} A {r['p_bridge']:>7.2f} W {r['t_j']:>6.1f} °C")
    print("=" * 92)

    # Plots
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(len(runs_ok), 2, figsize=(12, 3 * len(runs_ok)),
                                 sharex=False)
        if len(runs_ok) == 1:
            axes = [axes]
        fig.suptitle("Bridge validation — V_bus(t) and I_input(t) per converter",
                     fontsize=13, y=0.995)
        for row, r in enumerate(runs_ok):
            s = r["spec"]
            t_ms = [t * 1000.0 for t in r["result"].time]
            axes[row][0].plot(t_ms, r["bus_voltage"], color="#1d4ed8", lw=0.7)
            axes[row][0].set_title(f"{s.label} — V_bus(t) [mean = {r['v_bus_mean']:.1f} V]",
                                   fontsize=10)
            axes[row][0].set_ylabel("V [V]")
            axes[row][0].grid(True, alpha=0.3)
            axes[row][1].plot(t_ms, r["i_input"], color="#dc2626", lw=0.5)
            axes[row][1].set_title(f"{s.label} — I_in(t) [RMS = {r['i_in_rms']:.2f} A, peak = {r['i_in_peak']:.1f} A]",
                                   fontsize=10)
            axes[row][1].set_ylabel("I [A]")
            axes[row][1].grid(True, alpha=0.3)
        axes[-1][0].set_xlabel("time [ms]")
        axes[-1][1].set_xlabel("time [ms]")
        fig.tight_layout()
        fig.savefig("/tmp/bridge_overview.png", dpi=110)
        print(f"\nWrote /tmp/bridge_overview.png")
    except ImportError:
        print("\nmatplotlib not available — skipping plots")


if __name__ == "__main__":
    main()
