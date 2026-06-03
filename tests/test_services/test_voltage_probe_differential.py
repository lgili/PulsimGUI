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
    nm = build_node_map(gc)

    settings = SimulationSettings(t_start=0.0, t_stop=0.040)
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
