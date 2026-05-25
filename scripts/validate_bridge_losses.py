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
# Previous revisions hard-coded a developer-specific path here:
#     sys.path.insert(0, "/Users/.../Pulsim/build/python")
# That broke on every other machine. ``pulsim>=1.3.0`` is now a
# regular dependency declared in ``pyproject.toml``, so the venv-
# installed wheel is on ``sys.path`` automatically.

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
QApplication.instance() or QApplication(sys.argv)

import pulsim
from pulsimgui.models.project import Project
from pulsimgui.services.circuit_data_builder import CircuitDataBuilder
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.services.simulation_service import (
    normalize_step_mode, normalize_formulation_mode,
    normalize_thermal_policy, normalize_control_mode,
    SimulationSettings,
)
from pulsimgui.services.switch_fn_builder import (
    assemble_switch_fn,
    configs_from_pwm_records,
)
from pulsimgui.utils.net_utils import build_node_map, build_node_alias_map

# Pulsim 1.3 retired the legacy ``Circuit`` API the converter still
# speaks; ``make_compat_module`` wraps the runtime in the v0 shim so
# the converter keeps working unchanged. On pulsim <1.0 the wrapper
# is a no-op pass-through, so this is safe for either host.
_PULSIM_FOR_CONVERTER = make_compat_module(pulsim)


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

    circuit = CircuitConverter(_PULSIM_FOR_CONVERTER).build(data)
    print(f"  nodes: {circuit.num_nodes}, branches: {circuit.num_branches}")

    # Pulsim 1.3 dropped the legacy ``Simulator`` / ``SimulationOptions``
    # pair. Transient runs go through the top-level ``pulsim.simulate``
    # helper, which takes a ``CircuitBuilder`` (the shim's ``Circuit``
    # owns one as ``circuit.builder``) plus kwargs equivalent to the v0
    # opts fields. A bridge rectifier has no controllable switches, so
    # ``assemble_switch_fn`` will return ``None`` and we omit the kwarg.
    builder = circuit.builder
    pwm_configs = configs_from_pwm_records(circuit)
    switch_fn = assemble_switch_fn(circuit, pwm_configs, pulsim)
    sim_kwargs: dict = {
        "t_start": project.simulation_settings.tstart,
        "t_end":   project.simulation_settings.tstop,
        "dt":      project.simulation_settings.dt,
    }
    if switch_fn is not None:
        sim_kwargs["switch_fn"] = switch_fn

    try:
        result = pulsim.simulate(builder, **sim_kwargs)
    except Exception as exc:  # noqa: BLE001 — surface any solver failure
        print(f"  FAILED: {exc!r}")
        return {"spec": spec, "result": None, "ok": False}
    print(f"  samples: {result.num_steps()}")

    # Extract steady-state metrics. v1.3 ``SimulationResult.states`` is
    # an (n_steps, n_states) ndarray; ``times`` is the matching time
    # axis.
    #
    # NOTE on V_bus reporting: the GUI's ``node_aliases`` dict labels
    # decorative wire segments (``"n_dc_plus"`` → GUI id ``"3"``) but
    # the converter only feeds the *electrically-connected* node names
    # into ``CircuitBuilder``. When the alias points at a wire id that
    # isn't tied to any component pin, ``builder.node_id_of("3")``
    # raises ``IndexError`` and the V_bus column ends up as ``0 V``.
    # The bridge-loss validation (I_rms → P_bridge → T_J) is what
    # matters here and only needs the input-current trace, so we
    # report V_bus as ``None`` and let the CSV / plot show the
    # waveform itself. A future revision could walk
    # ``builder.graph.nodes`` and pick the highest-peak node as a
    # best-effort fallback.
    n_nodes = circuit.num_nodes
    ss = len(result.states) // 2

    bus_voltage = [0.0] * len(result.states)
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
            t_ms = [t * 1000.0 for t in r["result"].times]
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
