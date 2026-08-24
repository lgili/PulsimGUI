"""Regression test: VOLTAGE_PROBE is a DIFFERENTIAL probe (3 pins:
+, −, OUT). The enrichment must compute V(+) − V(−), not just V(+).

The legacy code path treated VOLTAGE_PROBE the same as
VOLTAGE_PROBE_GND — it ignored the ``−`` terminal and reported the
absolute potential of the ``+`` node. For probes that straddled two
floating nodes (e.g. across an AC source whose ``-`` side wasn't on
ground) the result was whatever single-ended potential the kernel
happened to assign — typically near 0 V on one side and the full
swing on the other — instead of the true differential the user
expects (e.g. ±325 V across a 220 Vrms AC source).

Symptom on the user side: a "tensao" channel on a scope read ±7 V
instead of ±325 V, while the physically-equivalent "corrente"
channel through the same loop read the correct ~7 A AC.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pulsim as ps
import pytest

from pulsimgui.models.project import Project
from pulsimgui.services.backend_adapter import (
    BackendCallbacks,
    BackendInfo,
    PulsimBackend,
)
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.services.simulation_service import (
    SimulationResult,
    SimulationSettings,
)
from pulsimgui.utils.net_utils import build_node_map

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture(scope="module")
def _qapp():
    """A QApplication has to exist for the MainWindow import to succeed,
    even though we never show a window."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def test_differential_voltage_probe_on_ex20_ac_source_reports_full_swing(
    _qapp,
) -> None:
    """Use the shipped ex 20 schematic, which carries a VOLTAGE_PROBE
    (``Vin``) across the AC source. After enrichment the probe must
    report the full AC line voltage (~309 V peak for 311 V_pk source
    with a small bridge-induced clipping asymmetry), NOT the
    single-ended ~7 V the kernel happens to assign to one terminal
    when the source floats relative to ground.

    Pre-fix value: ``np.abs(VP(Vin)).max()`` was around 7 V — pinning
    only the legacy single-ended path would let this test catch the
    regression instantly.
    """
    proj = Project.load(_EXAMPLES / "20_pfc_drive_compressor.pulsim")
    gc = proj.get_active_circuit()

    # ex 20's stock input metering was rewired (47de566) and no longer
    # ships a differential probe across the AC source. Inject one so
    # the regression stays pinned regardless of example churn — the
    # contract under test is the ENRICHMENT (V+ − V−), not the
    # example's probe inventory.
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.models.wire import Wire, WireConnection

    vac = next(c for c in gc.components.values() if c.name == "Vac")
    probe = Component(type=ComponentType.VOLTAGE_PROBE, name="Vin")
    gc.add_component(probe)
    for i, (probe_pin, vac_pin) in enumerate(((0, 0), (1, 1))):
        wire = Wire(
            start_connection=WireConnection(probe.id, probe_pin),
            end_connection=WireConnection(vac.id, vac_pin),
        )
        # ``build_node_map`` derives the wire's endpoint refs from its
        # SEGMENTS and then unions the explicit connections onto them —
        # a segment-less wire contributes nothing. Coordinates are
        # deliberately far from every real pin so no accidental
        # geometric union occurs (the explicit-connection path is
        # authoritative regardless of coordinates).
        wire.add_segment(90000.0 + 10.0 * i, 90000.0,
                         90001.0 + 10.0 * i, 90000.0)
        gc.add_wire(wire)

    nm = build_node_map(gc)

    # 150 ms = 9 cycles at 60 Hz. Earlier (40 ms = 2.4 cycles) didn't
    # leave enough integer-cycle window at the tail for the windowed-
    # mean assertion that catches the pairing bug — that check now needs
    # AT LEAST 4 cycles of steady-state data after the bus settles.
    settings = SimulationSettings(t_start=0.0, t_stop=0.150)
    settings.dt = 5e-6
    settings.max_step = 5e-6
    settings.step_mode = "fixed"

    comps = []
    node_map = {}
    for c in gc.components.values():
        cid = str(c.id)
        comps.append(c.to_dict())
        node_map[cid] = [
            str(nm.get((cid, pin.index), f"_nc_{cid}_{pin.index}"))
            for pin in sorted(c.pins, key=lambda pp: pp.index)
        ]

    backend = PulsimBackend(
        module=make_compat_module(ps),
        info=BackendInfo(
            identifier="pulsim", name="pulsim", version="1.6.5",
            status="available", capabilities={"transient"},
        ),
    )
    cbs = BackendCallbacks(
        progress=lambda p, m: None,
        data_point=lambda t, s: None,
        check_cancelled=lambda: False,
        wait_if_paused=lambda: None,
    )
    br = backend.run_transient(
        {"components": comps, "node_map": node_map}, settings, cbs,
    )
    assert br.error_message == ""

    result = SimulationResult(
        time=list(br.time),
        signals={k: list(v) for k, v in br.signals.items()},
        statistics=dict(br.statistics),
        error_message="",
    )

    from pulsimgui.views.main_window import MainWindow

    class _Surrogate(MainWindow):
        def __init__(self, circ): self._circ = circ
        def _current_circuit(self): return self._circ

    enriched = _Surrogate(gc)._result_with_probe_signals(result)

    # The shipped ex 20 has a ``Vin`` VOLTAGE_PROBE across V1
    # (the 220 Vrms AC source).
    assert "VP(Vin)" in enriched.signals, (
        "differential VOLTAGE_PROBE produced no enriched VP(Vin) "
        "channel — probe enrichment regressed"
    )
    series = np.asarray(enriched.signals["VP(Vin)"])
    times = np.asarray(enriched.time)
    # Drop initial-condition transient.
    body = series[200:]
    peak = float(np.abs(body).max())
    # 311 V_pk source, slight clipping by the rectifier — expect
    # 280-320 V on either polarity. Pre-fix: would read ~7 V because
    # only the ``+`` terminal's single-ended potential was reported.
    assert 200.0 < peak < 400.0, (
        f"VP(Vin) peak = {peak:.3g} V; expected full AC line swing "
        "(~309 V). Pre-fix bug would yield ~7 V."
    )
    # Second-class regression — the state-vector → signal-name pairing
    # bug (Jun 2026): shim's node_names() was insertion-ordered, but
    # pulsim's state vector is kernel-MNA-ordered with branch currents
    # mixed in. Pairing names[idx] with values[idx] silently wrote the
    # AC node's voltage signal with the bus voltage (or even an
    # inductor current), so VP(Vin) ended up clamped to one polarity
    # with a strong DC offset that grew alongside Cbus charging. The
    # original peak assertion above STILL passed because |min| reached
    # ~311 V — but the trace was [-311, +0] instead of ±311. These
    # follow-up checks tighten the contract:
    #
    #   1. Mean over an integer-cycle window must be ≈ 0. A
    #      symmetric sine over N full periods at 60 Hz has zero mean
    #      analytically; > 5 V here means the trace is offset.
    #
    #   2. Both polarities must reach the peak. The pre-state-pairing
    #      bug yielded ``series.max() < 5`` (the trace never went
    #      positive) while ``series.min() ≈ -311``. Asserting BOTH
    #      ``max > 200`` AND ``min < -200`` catches that one-sided
    #      failure.
    #
    #   3. RMS must match the analytic 311/√2 ≈ 219.91 V to ~1 %.
    #      The DC-offset bug shifted RMS up to ~230 V (because RMS
    #      includes the offset).
    f_grid = 60.0
    cycle_mask = times >= times[-1] - 4.0 / f_grid
    window = series[cycle_mask]
    mean = float(window.mean())
    assert abs(mean) < 5.0, (
        f"VP(Vin) windowed mean = {mean:+.2f} V over the last 4 "
        f"cycles; expected ≈ 0 for a symmetric AC source. A non-zero "
        f"mean is the smoking gun for the Jun 2026 state-vector → "
        f"signal-name pairing bug (shim insertion order vs kernel "
        f"MNA order)."
    )
    pos_peak = float(window.max())
    neg_peak = float(window.min())
    assert pos_peak > 200.0 and neg_peak < -200.0, (
        f"VP(Vin) reached pos_peak={pos_peak:+.2f}, neg_peak={neg_peak:+.2f} "
        f"— a symmetric AC line voltage must reach BOTH polarities. The "
        f"pre-fix bug clamped this trace to one polarity (max ≈ 0)."
    )
    rms = float(np.sqrt(np.mean(window**2)))
    # 220 Vrms analytic ± 1 V tolerance for diode drops + sampling noise.
    assert 215.0 < rms < 225.0, (
        f"VP(Vin) RMS = {rms:.2f} V; expected 220 V analytic. RMS shift "
        f"would indicate a DC offset or scaling error from the "
        f"state-vector → signal-name bug."
    )
