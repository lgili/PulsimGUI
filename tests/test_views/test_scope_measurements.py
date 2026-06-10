"""Scope measurement table — pure math + capability wiring.

Pins W1.4: the '+ Measure' button now computes per-signal Avg/RMS/Min/Max/
Pk-Pk/Freq/THD over the cursor span (or visible range) — the PSIM SIMVIEW /
PLECS Scope analysis-table workflow.
"""
from __future__ import annotations

import math

import numpy as np

from pulsimgui.views.scope_v2.capabilities.measurements import (
    compute_signal_measurements,
)


def test_sine_measurements_textbook_values() -> None:
    """A 50 Hz, 10 V sine over EXACTLY 2 periods: avg≈0, RMS=A/√2, THD≈0."""
    a, f = 10.0, 50.0
    t = np.linspace(0.0, 2.0 / f, 4001)
    y = a * np.sin(2 * math.pi * f * t)
    m = compute_signal_measurements(t, y)
    assert abs(m["avg"]) < 1e-3
    assert abs(m["rms"] - a / math.sqrt(2)) < 0.01
    assert abs(m["min"] + a) < 1e-6 and abs(m["max"] - a) < 1e-6
    assert abs(m["pkpk"] - 2 * a) < 1e-6
    assert abs(m["freq"] - f) < 1.0
    assert m["thd"] < 1.0                       # pure sine ⇒ ~0 % THD


def test_square_wave_thd_and_rms() -> None:
    """Ideal ±1 square wave: RMS = 1, THD ≈ 48.3 % (odd harmonics 1/n)."""
    f = 1000.0
    t = np.linspace(0.0, 4.0 / f, 8001)
    y = np.sign(np.sin(2 * math.pi * f * t))
    y[y == 0] = 1.0
    m = compute_signal_measurements(t, y)
    assert abs(m["rms"] - 1.0) < 0.01
    assert abs(m["freq"] - f) < f * 0.02
    assert 40.0 < m["thd"] < 55.0               # theory: 48.3 %


def test_dc_signal_has_no_fundamental() -> None:
    t = np.linspace(0.0, 1.0, 1001)
    y = np.full_like(t, 5.0)
    m = compute_signal_measurements(t, y)
    assert abs(m["avg"] - 5.0) < 1e-9
    assert abs(m["rms"] - 5.0) < 1e-9
    assert m["pkpk"] == 0.0
    assert math.isnan(m["freq"]) and math.isnan(m["thd"])


def test_offset_sine_avg_and_rms() -> None:
    """DC offset + sine: avg = offset, RMS = sqrt(dc² + a²/2)."""
    dc, a, f = 3.0, 4.0, 60.0
    t = np.linspace(0.0, 3.0 / f, 6001)
    y = dc + a * np.sin(2 * math.pi * f * t)
    m = compute_signal_measurements(t, y)
    assert abs(m["avg"] - dc) < 0.01
    assert abs(m["rms"] - math.sqrt(dc * dc + a * a / 2)) < 0.02


def test_degenerate_inputs_are_nan_safe() -> None:
    m = compute_signal_measurements(np.array([0.0]), np.array([1.0]))
    assert math.isnan(m["rms"])
    m = compute_signal_measurements(np.array([]), np.array([]))
    assert math.isnan(m["avg"])


def test_capability_attaches_and_fills_table(qapp) -> None:
    """End-to-end through a real scope shell: attach, feed a signal, click
    measure — the table fills and the drawer expands."""
    from pulsimgui.views.scope_v2 import MeasurementsCapability
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow
    from pulsimgui.views.scope_v2.variants import ElectricalScopeVariant

    cap = MeasurementsCapability()
    window = BaseScopeWindow(
        variant=ElectricalScopeVariant(name="Scope: test"),
        capabilities=[cap],
    )
    try:
        f = 50.0
        t = np.linspace(0.0, 2.0 / f, 2001)
        window.plot_canvas.replace_signal("V(out)", t, 10 * np.sin(2 * math.pi * f * t))
        assert callable(getattr(window, "measure_handler", None))
        window._timeline_add_measure()           # the + Measure click path
        table = cap._table
        assert table is not None and table.rowCount() == 1
        assert table.item(0, 0).text() == "V(out)"
        rms = float(table.item(0, 2).text())
        assert abs(rms - 10 / math.sqrt(2)) < 0.1
        assert window._drawer_expanded            # drawer auto-opened
    finally:
        window.close()
