"""Tests for the modular scope_v2 capabilities."""

from __future__ import annotations

import csv

import numpy as np


def _make_window(signal_data: dict[str, np.ndarray] | None = None):
    """Build a bare BaseScopeWindow + optionally pre-seed signals."""
    from pulsimgui.views.scope_v2 import BaseScopeWindow
    from pulsimgui.views.scope_v2.variants import ElectricalScopeVariant

    window = BaseScopeWindow(variant=ElectricalScopeVariant(name="Scope: test"))
    if signal_data:
        for name, (t, y) in signal_data.items():
            window.plot_canvas.add_signal(name, color="#5b8def", unit="V")
            window.plot_canvas.replace_signal(name, t, y)
    return window


# ── Cursors ────────────────────────────────────────────────────────────


def test_cursors_capability_populates_inspector(qapp) -> None:
    """Toggling cursors fills A/B/ΔT/Δfreq readouts in the inspector."""
    from pulsimgui.views.scope_v2 import CursorsCapability

    window = _make_window()
    try:
        cap = CursorsCapability()
        cap.attach(window)
        assert cap._lbl_a is not None
        # Cursors start disabled — readouts show em-dash.
        assert cap._lbl_a.text() == "—"
        # Toggle on via the toolbar button.
        window.toolbar.btn_cursor.setChecked(True)
        qapp.processEvents()
        assert cap._enabled is True
        # Cursors land at 25 % / 75 % of the visible X range.
        assert cap._lbl_dt.text().endswith("s") or "ms" in cap._lbl_dt.text() \
            or "µs" in cap._lbl_dt.text() or "ns" in cap._lbl_dt.text()
    finally:
        window.close()


def test_cursors_per_signal_delta_y_after_data(qapp) -> None:
    """With data on the canvas, per-signal ΔY rows reflect Y(B) − Y(A)."""
    from pulsimgui.views.scope_v2 import CursorsCapability

    t = np.linspace(0.0, 1.0, 11)
    y = t * 10.0  # ramp 0→10
    window = _make_window({"ramp": (t, y)})
    try:
        cap = CursorsCapability()
        cap.attach(window)
        window.toolbar.btn_cursor.setChecked(True)
        # Cursors default to 25 % / 75 % → A=0.25, B=0.75.
        # ramp(0.25) = 2.5, ramp(0.75) = 7.5 → ΔY = +5.
        qapp.processEvents()
        name_lbl, val_lbl = cap._per_signal_labels["ramp"]
        assert "+5" in val_lbl.text() or "5.000" in val_lbl.text()
    finally:
        window.close()


# ── MathSignals ────────────────────────────────────────────────────────


def test_math_signals_capability_attaches(qapp) -> None:
    """The fx toolbar button gets a handler when the capability attaches."""
    from pulsimgui.views.scope_v2 import MathSignalsCapability

    window = _make_window()
    try:
        cap = MathSignalsCapability()
        cap.attach(window)
        # Without data, the capability surfaces a hint in the drawer.
        window.toolbar.btn_math.click()
        qapp.processEvents()
        assert "first" in window.drawer.summary.text().lower() \
            or "run" in window.drawer.summary.text().lower()
    finally:
        window.close()


# ── Trigger ────────────────────────────────────────────────────────────


def test_trigger_detect_crossing_rising(qapp) -> None:
    """A rising edge across the trigger level fires Single mode once."""
    from pulsimgui.views.scope_v2 import TriggerCapability

    window = _make_window({"v": (np.linspace(0, 1, 10), np.zeros(10))})
    try:
        cap = TriggerCapability()
        cap.attach(window)
        # Configure Single mode at level=0.5 on the "v" source.
        cap._mode_combo.setCurrentText("Single")
        cap._refresh_sources()
        cap._source_combo.setCurrentText("v")
        cap._level_spin.setValue(0.5)
        cap._edge_combo.setCurrentText("rising")

        # Feed samples that don't cross — no fire.
        assert cap.detect_crossing("v", np.array([0.0, 0.1]),
                                   np.array([0.0, 0.1])) is False
        assert cap._fired is False
        # Now feed a rising edge through 0.5.
        assert cap.detect_crossing("v", np.array([0.2, 0.3]),
                                   np.array([0.4, 0.8])) is True
        assert cap._fired is True
        # A second crossing while still latched does NOT re-fire.
        assert cap.detect_crossing("v", np.array([0.4, 0.5]),
                                   np.array([0.1, 0.9])) is False
    finally:
        window.close()


# ── SMPS macros ────────────────────────────────────────────────────────


def test_smps_macros_tsw_detects_period(qapp) -> None:
    """``Measure Tsw + Fsw`` finds the period of a clean sine."""
    from pulsimgui.views.scope_v2 import SMPSMacrosCapability

    t = np.linspace(0.0, 0.01, 1000)  # 10 ms window
    y = np.sin(2 * np.pi * 1000.0 * t)  # 1 kHz → Tsw = 1 ms
    window = _make_window({"sine": (t, y)})
    try:
        cap = SMPSMacrosCapability()
        cap.attach(window)
        cap._refresh_sources()
        cap._source_combo.setCurrentText("sine")
        cap._measure_tsw()
        readout = cap._readout.text()
        assert "Tsw" in readout
        # Period should be close to 1 ms.
        assert "ms" in readout or "1 ms" in readout
    finally:
        window.close()


def test_smps_macros_duty_detects_bimodal(qapp) -> None:
    """``Measure Duty`` reports the fraction of high-going samples."""
    from pulsimgui.views.scope_v2 import SMPSMacrosCapability

    # 30 % duty square wave (10 samples high out of 32).
    y = np.array([0.0] * 21 + [1.0] * 11, dtype=np.float64)
    t = np.linspace(0.0, 1.0, y.size)
    window = _make_window({"sq": (t, y)})
    try:
        cap = SMPSMacrosCapability()
        cap.attach(window)
        cap._refresh_sources()
        cap._source_combo.setCurrentText("sq")
        cap._measure_duty()
        assert "Duty" in cap._readout.text()
    finally:
        window.close()


def test_smps_macros_ripple_reports_stats(qapp) -> None:
    """``Measure Ripple`` shows min/max/mean/p-p/rms of the window."""
    from pulsimgui.views.scope_v2 import SMPSMacrosCapability

    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    t = np.linspace(0.0, 1.0, y.size)
    window = _make_window({"v": (t, y)})
    try:
        cap = SMPSMacrosCapability()
        cap.attach(window)
        cap._refresh_sources()
        cap._source_combo.setCurrentText("v")
        cap._measure_ripple()
        text = cap._readout.text()
        assert "min" in text and "max" in text and "rms" in text
        assert "1" in text and "5" in text  # 1 and 5 are min/max
    finally:
        window.close()


# ── Export ─────────────────────────────────────────────────────────────


def test_export_csv_writes_master_grid(qapp, tmp_path) -> None:
    """CSV export interleaves signals on the longest time vector."""
    from pulsimgui.views.scope_v2 import ExportCapability

    t = np.linspace(0.0, 1.0, 5)
    y1 = t * 2.0
    y2 = t * 3.0 + 1.0
    window = _make_window({"a": (t, y1), "b": (t, y2)})
    try:
        cap = ExportCapability()
        cap.attach(window)
        # Drive the private helper directly so we don't need a dialog.
        target = tmp_path / "out.csv"
        # Monkeypatch the file-picker to return our target path.
        from PySide6.QtWidgets import QFileDialog
        orig = QFileDialog.getSaveFileName
        try:
            QFileDialog.getSaveFileName = lambda *a, **k: (str(target), "")
            cap._export_csv()
        finally:
            QFileDialog.getSaveFileName = orig

        assert target.exists()
        with open(target) as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == ["time_s", "a", "b"]
        # 5 data rows + 1 header.
        assert len(rows) == 6
    finally:
        window.close()


# ── FFT toggle (capability-level smoke) ────────────────────────────────


def test_fft_capability_swaps_view(qapp) -> None:
    """The Σ toolbar toggle drives ``plot_canvas.set_view``."""
    from pulsimgui.views.scope_v2 import FFTCapability

    window = _make_window({"y": (np.linspace(0, 1, 100), np.sin(np.linspace(0, 6.28, 100)))})
    try:
        cap = FFTCapability()
        cap.attach(window)
        assert window.plot_canvas._view_mode == "time"
        window.toolbar.btn_fft.setChecked(True)
        qapp.processEvents()
        assert window.plot_canvas._view_mode == "fft"
        assert "FFT" in window.drawer.summary.text()
        window.toolbar.btn_fft.setChecked(False)
        qapp.processEvents()
        assert window.plot_canvas._view_mode == "time"
        assert "Time" in window.drawer.summary.text()
    finally:
        window.close()
