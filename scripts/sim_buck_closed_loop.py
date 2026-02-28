"""Closed-loop buck converter simulation — standalone script.

Circuit:  Vin=12 V  →  MOSFET/Diode switch + L=220 µH + Cout=220 µF + Rload=8 Ω
Control:  Vout feedback → SUB1(error = 6V − Vout) → PI(kp=1,ki=100) → PWM1 duty

Runs through PulsimBackend so the full closed-loop signal evaluator pipeline
(CONSTANT → SUBTRACTOR → PI_CONTROLLER → PWM_GENERATOR.DUTY_IN) is exercised
exactly as it would be in the GUI.

Usage
-----
    cd PulsimGui
    PYTHONPATH=src .venv/bin/python scripts/sim_buck_closed_loop.py

Optional: add --plot to render a Vout waveform with matplotlib.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pulsim as ps
from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo, PulsimBackend
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map
from pulsimgui.models.project import Project

# ---------------------------------------------------------------------------
# Load circuit
# ---------------------------------------------------------------------------
CIRCUIT_FILE = REPO_ROOT / "examples" / "buck_converter_closed_loop.pulsim"


def load_circuit_data(path: Path) -> dict:
    """Load a .pulsim file and return the flat circuit_data dict for the backend."""
    with path.open() as f:
        raw = json.load(f)

    project = Project.from_dict(raw)
    gui_circuit = project.get_active_circuit()
    node_map_raw = build_node_map(gui_circuit)
    alias_map = build_node_alias_map(gui_circuit, node_map_raw)

    circuit_data: dict = {
        "components": [],
        "node_map": {},
        "node_aliases": alias_map,
    }
    for comp in gui_circuit.components.values():
        d = comp.to_dict()
        d["parameters"] = copy.deepcopy(comp.parameters)
        cid = str(comp.id)
        d["pin_nodes"] = [
            node_map_raw.get((cid, i)) or ""
            for i in range(len(comp.pins))
        ]
        circuit_data["components"].append(d)
        circuit_data["node_map"][cid] = d["pin_nodes"]

    return circuit_data


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
def run(t_stop: float = 5e-3, dt: float = 0.2e-6) -> None:
    print(f"Loading circuit: {CIRCUIT_FILE.name}")
    circuit_data = load_circuit_data(CIRCUIT_FILE)

    # Print signal block summary
    from pulsim.signal_evaluator import SIGNAL_TYPES
    sig_comps = [c for c in circuit_data["components"] if c["type"] in SIGNAL_TYPES]
    print(f"Signal blocks found: {len(sig_comps)}")
    for c in sig_comps:
        print(f"  [{c['type']:20s}] {c['name']}  params={c.get('parameters', {})}")

    # Backend setup
    info = BackendInfo(
        identifier="pulsim",
        name="pulsim",
        version="dev",
        status="available",
        capabilities={"transient"},
        message="",
    )
    backend = PulsimBackend(ps, info)

    # Collect waveform samples
    time_pts: list[float] = []
    vout_pts: list[float] = []

    # Find Xout probe id for feedback tracking
    xout_id = next(
        (c["id"] for c in circuit_data["components"] if c["name"] == "Xout"),
        None,
    )

    def on_data(t: float, signals: dict) -> None:
        time_pts.append(t)
        if xout_id and xout_id in signals:
            vout_pts.append(signals[xout_id])

    callbacks = BackendCallbacks(
        progress=lambda pct, msg: print(f"  [{pct:3.0f}%] {msg}", end="\r", flush=True),
        data_point=on_data,
        check_cancelled=lambda: False,
        wait_if_paused=lambda: None,
    )

    settings = SimulationSettings()
    settings.t_start = 0.0
    settings.t_stop = t_stop
    settings.t_step = dt
    settings.solver = "bdf1"
    settings.step_mode = "fixed"
    settings.max_newton_iterations = 100
    settings.enable_events = True
    settings.max_step_retries = 8

    print(f"\nRunning simulation: t_stop={t_stop*1e3:.1f} ms, dt={dt*1e6:.1f} µs ...")
    result = backend.run_transient(circuit_data, settings, callbacks)
    print()  # newline after progress

    # ---------------------------------------------------------------------------
    # Results
    # ---------------------------------------------------------------------------
    if result.error_message:
        print(f"\nSIMULATION FAILED: {result.error_message}")
        sys.exit(1)

    t = result.time
    print(f"\n{'='*55}")
    print(f"  Simulation SUCCESS  —  {len(t)} time points")
    print(f"  Time span : {t[0]:.3e} s → {t[-1]:.3e} s")
    print(f"{'='*55}")

    # Look for Vout in result signals
    vout_key = next(
        (k for k, v in result.signals.items() if "out" in k.lower() or "vout" in k.lower()),
        None,
    )
    if vout_key is None and xout_id:
        # Try by component id
        vout_key = next((k for k in result.signals if k == xout_id), None)

    if vout_key and result.signals[vout_key]:
        vout = result.signals[vout_key]
        v_start = vout[0] if vout else 0.0
        v_end   = vout[-1] if vout else 0.0
        v_max   = max(vout)
        v_min   = min(vout)
        print(f"  Vout @ t=0     : {v_start:.4f} V")
        print(f"  Vout @ t=end   : {v_end:.4f} V")
        print(f"  Vout range     : [{v_min:.4f}, {v_max:.4f}] V")
        print(f"  Target (Vref)  : 6.0000 V")
        error_pct = abs(v_end - 6.0) / 6.0 * 100
        print(f"  Steady-state ε : {error_pct:.2f}%")
        converged = error_pct < 5.0
        print(f"  Converged      : {'YES ✓' if converged else 'NO ✗'}")
    else:
        print(f"  Available signals: {list(result.signals.keys())[:8]}")

    print(f"{'='*55}\n")

    # Optional plot
    if "--plot" in sys.argv and vout_key:
        try:
            import matplotlib.pyplot as plt
            vout = result.signals[vout_key]
            plt.figure(figsize=(10, 4))
            plt.plot([tt * 1e3 for tt in t], vout, lw=0.8, label="Vout")
            plt.axhline(6.0, color="red", ls="--", lw=1, label="Vref = 6 V")
            plt.xlabel("Time (ms)")
            plt.ylabel("Voltage (V)")
            plt.title("Closed-Loop Buck Converter — Vout")
            plt.legend()
            plt.grid(True)
            plt.tight_layout()
            plt.show()
        except ImportError:
            print("matplotlib not installed — skipping plot")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Closed-loop buck converter simulation")
    parser.add_argument("--t-stop", type=float, default=5e-3, help="Stop time in seconds (default: 5 ms)")
    parser.add_argument("--dt", type=float, default=0.2e-6, help="Time step in seconds (default: 0.2 µs)")
    parser.add_argument("--plot", action="store_true", help="Show Vout waveform with matplotlib")
    args, _ = parser.parse_known_args()

    run(t_stop=args.t_stop, dt=args.dt)
