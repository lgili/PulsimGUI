"""Standalone smoke-demo for :class:`LiveScopeWidget`.

Builds a simple buck-converter circuit via pulsim, kicks off
``simulate()`` on a daemon thread feeding a :class:`NativeLiveStream`,
and shows the live-scope widget on the main thread. You should see
``V(vin)`` and ``V(vout)`` populate in real time at ~60 Hz.

This script intentionally does NOT use any of PulsimGUI's
``SimulationService`` / ``SimulationWorker`` plumbing. The point is
to validate the widget in isolation so when we wire it into the main
window later, we know any breakage is in the wiring, not in the
widget itself.

Run with:
    cd PulsimGUI
    PYTHONPATH=src python3 scripts/live_scope_demo.py
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pulsim as p

# Allow ``python3 scripts/live_scope_demo.py`` from the repo root —
# no need to set PYTHONPATH manually when invoked that way.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pulsimgui.views.scope.live_scope_widget import (  # noqa: E402
    LiveScopeWidget,
    LiveSignalSpec,
)


# Same plant the closed-loop demo uses (sim_buck_closed_loop.py) so
# the user can eyeball "yes, that's a buck waveform".
V_IN = 12.0
V_REF = 6.0
L_H = 220e-6
C_F = 220e-6
R_OHM = 8.0
F_PWM = 10e3
DT = 2e-6
T_STOP = 30e-3


def build_buck() -> p.CircuitBuilder:
    b = p.CircuitBuilder()
    b.add_voltage_source("V1", "vin", "gnd", V_IN)
    b.add_mosfet_with_body_diode(
        "Q1", "vin", "sw", R_on=1e-3, R_off=1e9, V_F=0.7,
    )
    b.add_diode("D1", "gnd", "sw", 1e3, 1e-9, V_th=0.7)
    b.add_inductor("L1", "sw", "vout", L_H)
    b.add_capacitor("Cout", "vout", "gnd", C_F)
    b.add_resistor("R_L", "vout", "gnd", R_OHM)
    return b


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    builder = build_buck()

    # Closed-loop wrapper — same pattern as scripts/sim_buck_closed_loop.py.
    pi = p.PIController(Kp=0.08, Ki=40.0, output_min=0.05, output_max=0.95)
    loop = p.bind_pi_to_switch(
        builder, pi=pi,
        measured=lambda x: x[builder.node_id_of("vout")],
        setpoint=V_REF,
        switch="Q1",
        freq=F_PWM,
    )

    # NativeLiveStream — kernel writes here without holding the GIL.
    # ``decimate=20`` at dt=2µs ⇒ one sample every 40µs ⇒ 25 kHz visual
    # rate. Plenty for buck-scale dynamics; cheap on the GUI thread.
    stream = p.NativeLiveStream(capacity=200_000, decimate=20)

    # Resolve state-vector slots after the topology is fully built.
    # The ``add_*`` calls on the builder commit node assignments
    # lazily, so this lookup belongs *after* the plant is finalised.
    #
    # Showcase the new ``panel=...`` routing: V_in and V_out share a
    # ``Voltage`` panel (DC + control output), while the switch node
    # V(sw) goes to its own ``Switching`` panel — its PWM transitions
    # would crush the V_in/V_out detail if they shared an axis.
    signals = [
        LiveSignalSpec(
            name="V(vin)",  state_idx=builder.node_id_of("vin"),
            color="#4e79a7", unit="V", panel="Voltage",
        ),
        LiveSignalSpec(
            name="V(vout)", state_idx=builder.node_id_of("vout"),
            color="#f28e2b", unit="V", panel="Voltage",
        ),
        LiveSignalSpec(
            name="V(sw)",   state_idx=builder.node_id_of("sw"),
            color="#59a14f", unit="V", panel="Switching",
        ),
    ]

    widget = LiveScopeWidget(
        stream, signals,
        panels=("Voltage", "Switching"),
        window_seconds=3e-3, update_hz=60.0,
    )
    widget.setWindowTitle(
        "PulsimGUI — LiveScopeWidget demo "
        "(buck CL + multi-panel + cursors + SMPS macros)"
    )
    widget.resize(1280, 720)
    widget.show()
    widget.start()

    print("\nTry these once samples start flowing:")
    print("  • Toggle 'Show A/B Cursors' — drag to measure ΔT, f=1/ΔT")
    print("  • Set Trigger Mode = Single, Source = V(sw), Level = 6.0,")
    print("    Edge = rising — first PWM edge freezes the view")
    print("  • Click 'Measure Tsw + Fsw' with V(sw) selected → ~100 µs / 10 kHz")
    print("  • Click 'Measure Duty' with V(sw) selected → ~50 %")
    print("  • Click 'Measure Ripple' with V(vout) selected — V_pp on output\n")

    # Run the sim on a daemon thread; the kernel will release the GIL
    # while it's crunching, and the widget's QTimer will pull samples
    # in parallel on the main thread.
    def _run_sim() -> None:
        try:
            p.simulate(
                builder, t_end=T_STOP, dt=DT,
                closed_loops=[loop],
                live_stream=stream,
            )
        except Exception as exc:  # noqa: BLE001 — diagnostics only
            print(f"[live_scope_demo] simulate() raised: {exc!r}")

    sim_thread = threading.Thread(target=_run_sim, daemon=True)
    sim_thread.start()

    # When the user clicks Stop, ask the kernel to halt cleanly.
    widget.stop_requested.connect(lambda: print("[live_scope_demo] stop requested"))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
