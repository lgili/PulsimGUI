"""``SMPSMacrosCapability`` — Tsw / Duty / Ripple measurements on demand.

Power-electronics scopes need three pieces of info often enough that
they get dedicated one-click measurements:

  * **Tsw / Fsw** — switching period (and its reciprocal frequency)
    inferred from same-direction zero crossings of the mean-subtracted
    source signal.
  * **Duty** — fraction of each period the source is above its median
    (catches square-ish PWM signals robustly).
  * **Ripple** — min / max / mean / peak-to-peak / RMS of the current
    visible window.

The capability puts the source picker + three buttons + a readout
inside the shell's ``SMPS Measure`` inspector group. All math runs on
the canvas's cached samples, so the same measurement works in live
mode and after the run finishes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


# ── numpy helpers ──────────────────────────────────────────────────────


def _zero_crossings(t: np.ndarray, y: np.ndarray, *, direction: str = "rising") -> np.ndarray:
    """Linear-interpolated crossing times of ``y(t) = 0``."""
    if t.size < 2:
        return np.empty(0, dtype=np.float64)
    if direction == "rising":
        mask = (y[:-1] <= 0.0) & (y[1:] > 0.0)
    elif direction == "falling":
        mask = (y[:-1] >= 0.0) & (y[1:] < 0.0)
    else:
        mask = ((y[:-1] <= 0.0) & (y[1:] > 0.0)) | ((y[:-1] >= 0.0) & (y[1:] < 0.0))
    idx = np.nonzero(mask)[0]
    if idx.size == 0:
        return np.empty(0, dtype=np.float64)
    t0, t1 = t[idx], t[idx + 1]
    y_a, y_b = y[idx], y[idx + 1]
    denom = y_b - y_a
    frac = np.where(np.abs(denom) > 1e-30, -y_a / denom, 0.5)
    return t0 + frac * (t1 - t0)


def _detect_period(t: np.ndarray, y: np.ndarray) -> float | None:
    if y.size < 4:
        return None
    y_dc = y - float(np.mean(y))
    crosses = _zero_crossings(t, y_dc, direction="rising")
    if crosses.size < 2:
        crosses = _zero_crossings(t, y_dc, direction="both")
        if crosses.size < 3:
            return None
        return float(2.0 * np.median(np.diff(crosses)))
    return float(np.median(np.diff(crosses)))


def _detect_duty(_t: np.ndarray, y: np.ndarray) -> float | None:
    if y.size < 8:
        return None
    threshold = float(np.median(y))
    high = y > threshold
    if high.all() or (~high).all():
        return None
    return float(np.mean(high))


def _ripple_stats(y: np.ndarray) -> dict[str, float]:
    if y.size == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "pp": 0.0, "rms": 0.0}
    return {
        "min": float(np.min(y)),
        "max": float(np.max(y)),
        "mean": float(np.mean(y)),
        "pp": float(np.max(y) - np.min(y)),
        "rms": float(np.sqrt(np.mean(y * y))),
    }


# ── Capability ──────────────────────────────────────────────────────────


class SMPSMacrosCapability:
    """Populate the SMPS Measure inspector group with Tsw / Duty / Ripple."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None
        self._source_combo: QComboBox | None = None
        self._readout: QLabel | None = None

    def attach(self, shell: BaseScopeWindow) -> None:
        self._shell = shell
        self._build_ui(shell.inspector.smps_group)
        # Populate the Source combo with signals already registered
        # on the plot canvas (LiveStreamCapability registers up-front
        # in its own ``attach`` AND the PostSim catch-up has already
        # filled them when re-opening a scope after a finished run).
        # Without this the combo opens stuck on "(none)" until the
        # user manually re-runs.
        self._refresh_sources()
        # ``run_clicked`` keeps it in sync for subsequent runs (e.g.
        # new channels appearing after a schematic edit).
        shell.toolbar.run_clicked.connect(self._refresh_sources)

    def _build_ui(self, group_frame: QWidget) -> None:
        layout = group_frame.layout()
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        # Source picker.
        row1 = QWidget()
        r1 = QHBoxLayout(row1)
        r1.setContentsMargins(0, 0, 0, 0)
        r1.setSpacing(8)
        k = QLabel("Source")
        k.setObjectName("ScopeFormFieldLabel")
        kf = QFont()
        kf.setPointSize(10)
        kf.setWeight(QFont.Weight.Medium)
        k.setFont(kf)
        k.setMinimumWidth(52)
        r1.addWidget(k)
        self._source_combo = QComboBox()
        self._source_combo.addItem("(none)")
        r1.addWidget(self._source_combo, stretch=1)
        layout.addWidget(row1)

        # Three macro buttons. Vertical spacing 6 px between rows so
        # the two Tsw+Fsw / Duty buttons don't crowd the Ripple row.
        row2 = QWidget()
        r2 = QGridLayout(row2)
        r2.setContentsMargins(0, 8, 0, 0)
        r2.setHorizontalSpacing(6)
        r2.setVerticalSpacing(6)

        def _mk_btn(label: str, slot) -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(slot)
            return b

        r2.addWidget(_mk_btn("Tsw + Fsw", self._measure_tsw), 0, 0)
        r2.addWidget(_mk_btn("Duty",       self._measure_duty), 0, 1)
        r2.addWidget(_mk_btn("Ripple",     self._measure_ripple), 1, 0, 1, 2)
        layout.addWidget(row2)

        # Readout.
        self._readout = QLabel("—")
        self._readout.setWordWrap(True)
        rf = QFont()
        rf.setPointSize(9)
        rf.setFamily("Menlo, Consolas, monospace")
        self._readout.setFont(rf)
        self._readout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._readout.setMinimumHeight(48)
        layout.addWidget(self._readout)

    # ── Source list ─────────────────────────────────────────────────────

    def _refresh_sources(self) -> None:
        if self._shell is None or self._source_combo is None:
            return
        existing = {self._source_combo.itemText(i) for i in range(self._source_combo.count())}
        wanted = {"(none)", *self._shell.plot_canvas.signals()}
        if existing == wanted:
            return
        current = self._source_combo.currentText()
        self._source_combo.blockSignals(True)
        self._source_combo.clear()
        self._source_combo.addItem("(none)")
        for s in self._shell.plot_canvas.signals():
            self._source_combo.addItem(s)
        if current in wanted:
            self._source_combo.setCurrentText(current)
        self._source_combo.blockSignals(False)

    # ── Macro implementations ───────────────────────────────────────────

    def _source_data(self) -> tuple[str, np.ndarray, np.ndarray] | None:
        """Return ``(name, t, y)`` for the active source, or ``None``."""
        if self._shell is None or self._source_combo is None:
            return None
        self._refresh_sources()
        name = self._source_combo.currentText()
        if name in ("", "(none)"):
            self._set_readout("Pick a source signal first.")
            return None
        state = self._shell.plot_canvas._signals.get(name)  # noqa: SLF001
        if state is None:
            self._set_readout(f"Signal '{name}' is not on the canvas.")
            return None
        t, y = state.merged()
        if t.size < 4:
            self._set_readout("Not enough samples yet.")
            return None
        return name, t, y

    def _measure_tsw(self) -> None:
        result = self._source_data()
        if result is None:
            return
        name, t, y = result
        period = _detect_period(t, y)
        if period is None or period <= 0.0:
            self._set_readout(f"{name}: no period detected in visible window.")
            return
        fsw = 1.0 / period
        self._set_readout(f"{name}\n  Tsw = {_fmt_time(period)}\n  Fsw = {_fmt_freq(fsw)}")

    def _measure_duty(self) -> None:
        result = self._source_data()
        if result is None:
            return
        name, t, y = result
        duty = _detect_duty(t, y)
        if duty is None:
            self._set_readout(f"{name}: no switching detected (signal not bimodal).")
            return
        self._set_readout(f"{name}\n  Duty = {duty * 100.0:.2f} %")

    def _measure_ripple(self) -> None:
        result = self._source_data()
        if result is None:
            return
        name, _t, y = result
        s = _ripple_stats(y)
        self._set_readout(
            f"{name}\n"
            f"  min  {s['min']:.4g}\n"
            f"  max  {s['max']:.4g}\n"
            f"  mean {s['mean']:.4g}\n"
            f"  p-p  {s['pp']:.4g}\n"
            f"  rms  {s['rms']:.4g}"
        )

    # ── helpers ─────────────────────────────────────────────────────────

    def _set_readout(self, text: str) -> None:
        if self._readout is not None:
            self._readout.setText(text)


def _fmt_time(value: float) -> str:
    av = abs(value)
    if av == 0.0:
        return "0 s"
    if av >= 1.0:
        return f"{value:.4g} s"
    if av >= 1e-3:
        return f"{value * 1e3:.4g} ms"
    if av >= 1e-6:
        return f"{value * 1e6:.4g} µs"
    return f"{value * 1e9:.4g} ns"


def _fmt_freq(value: float) -> str:
    av = abs(value)
    if av >= 1e9:
        return f"{value / 1e9:.4g} GHz"
    if av >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if av >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"


__all__ = ["SMPSMacrosCapability"]
