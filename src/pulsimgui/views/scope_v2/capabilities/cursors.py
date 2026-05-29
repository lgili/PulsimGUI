"""``CursorsCapability`` — A/B vertical markers + ΔT / Δf / ΔY readouts.

Adds the classic two-cursor analysis to any scope window: drop a
toggle on the toolbar, two draggable vertical lines on every panel,
and a live readout pane in the Inspector's ``Cursors`` group showing
A position, B position, ΔT, 1/ΔT (frequency), and per-signal ΔY.

The capability owns no data — it samples the plot canvas's existing
curves at the cursor positions whenever a marker moves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


_CURSOR_A_COLOR = "#fbbf24"  # amber
_CURSOR_B_COLOR = "#f87171"  # red — high-contrast pairing on dark surfaces


@dataclass
class _CursorState:
    """Bookkeeping for one of the two cursors."""

    name: str
    color: str
    position: float = 0.0
    lines: list[pg.InfiniteLine] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.lines is None:
            self.lines = []


class CursorsCapability:
    """Two-cursor analysis: A/B vertical markers + Inspector readouts."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None
        self._enabled = False
        self._a = _CursorState(name="A", color=_CURSOR_A_COLOR)
        self._b = _CursorState(name="B", color=_CURSOR_B_COLOR)
        # Inspector readouts populated on attach().
        self._lbl_a: QLabel | None = None
        self._lbl_b: QLabel | None = None
        self._lbl_dt: QLabel | None = None
        self._lbl_freq: QLabel | None = None
        self._per_signal_host: QWidget | None = None
        self._per_signal_grid: QGridLayout | None = None
        self._per_signal_labels: dict[str, tuple[QLabel, QLabel]] = {}

    # ── ScopeCapability protocol ────────────────────────────────────────

    def attach(self, shell: BaseScopeWindow) -> None:
        """Hook the capability into the toolbar + inspector group."""
        self._shell = shell

        # Replace the Cursors inspector group's placeholder hint with
        # the readout widgets.
        self._build_readouts(shell.inspector.cursor_group)

        # Wire the toolbar toggle.
        shell.toolbar.cursor_toggled.connect(self._on_toggle)

    # ── UI construction ─────────────────────────────────────────────────

    def _build_readouts(self, group_frame: QWidget) -> None:
        """Tear down the hint label and add A/B/ΔT/Δf readouts."""
        # Strip whatever the shell put inside (the hint paragraph); keep
        # only the section title (the first widget).
        layout = group_frame.layout()
        # Index 0 is the title label installed by the shell — keep it.
        # Remove everything after it.
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        # A position
        self._lbl_a = self._mk_row(layout, "A", "—")
        # B position
        self._lbl_b = self._mk_row(layout, "B", "—")
        # ΔT
        self._lbl_dt = self._mk_row(layout, "ΔT", "—")
        # 1/ΔT
        self._lbl_freq = self._mk_row(layout, "1/ΔT", "—")

        # Per-signal ΔY host — a grid populated lazily as cursors move.
        self._per_signal_host = QWidget(group_frame)
        self._per_signal_grid = QGridLayout(self._per_signal_host)
        self._per_signal_grid.setContentsMargins(0, 6, 0, 0)
        self._per_signal_grid.setHorizontalSpacing(8)
        self._per_signal_grid.setVerticalSpacing(2)
        layout.addWidget(self._per_signal_host)

    def _mk_row(self, parent_layout, key: str, value: str) -> QLabel:
        """Render a ``key: value`` row inside the cursor group."""
        row = QWidget()
        row_layout = QGridLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setHorizontalSpacing(8)
        k = QLabel(key)
        kf = QFont()
        kf.setPointSize(10)
        kf.setWeight(QFont.Weight.DemiBold)
        k.setFont(kf)
        k.setMinimumWidth(36)
        v = QLabel(value)
        vf = QFont()
        vf.setPointSize(10)
        vf.setFamily("Menlo, Consolas, monospace")
        v.setFont(vf)
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(k, 0, 0)
        row_layout.addWidget(v, 0, 1)
        row_layout.setColumnStretch(1, 1)
        parent_layout.addWidget(row)
        return v

    # ── Toggle wiring ───────────────────────────────────────────────────

    def _on_toggle(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self._spawn_cursors()
        else:
            self._remove_cursors()
        self._update_readouts()

    def _spawn_cursors(self) -> None:
        """Add A/B InfiniteLine items to every panel of the plot canvas."""
        if self._shell is None:
            return
        canvas = self._shell.plot_canvas
        panels = canvas._panels  # noqa: SLF001 - intentional access
        if not panels:
            return

        # Anchor positions: 25 % and 75 % across the current visible X
        # range so the user lands on something useful on first toggle.
        first_panel = next(iter(panels.values()))
        x_range, _ = first_panel.viewRange()
        x_lo, x_hi = float(x_range[0]), float(x_range[1])
        if x_hi <= x_lo:
            x_lo, x_hi = 0.0, 1.0
        self._a.position = x_lo + 0.25 * (x_hi - x_lo)
        self._b.position = x_lo + 0.75 * (x_hi - x_lo)

        for plot in panels.values():
            for state in (self._a, self._b):
                line = pg.InfiniteLine(
                    pos=state.position,
                    angle=90,
                    movable=True,
                    pen=pg.mkPen(color=state.color, width=1.4, style=Qt.PenStyle.DashLine),
                    hoverPen=pg.mkPen(color=state.color, width=2.0),
                )
                line.sigPositionChanged.connect(
                    lambda ln, st=state: self._on_cursor_moved(st, float(ln.value()))
                )
                plot.addItem(line)
                state.lines.append(line)

    def _remove_cursors(self) -> None:
        """Drop every InfiniteLine the capability added."""
        if self._shell is None:
            return
        panels = self._shell.plot_canvas._panels  # noqa: SLF001
        for state in (self._a, self._b):
            for line in state.lines:
                for plot in panels.values():
                    try:
                        plot.removeItem(line)
                    except Exception:  # noqa: BLE001
                        pass
            state.lines = []

    # ── Updates on cursor move ──────────────────────────────────────────

    def _on_cursor_moved(self, state: _CursorState, position: float) -> None:
        state.position = position
        # Sync the other lines belonging to the same cursor across panels.
        for line in state.lines:
            if abs(line.value() - position) > 1e-12:
                line.blockSignals(True)
                line.setValue(position)
                line.blockSignals(False)
        self._update_readouts()

    def _update_readouts(self) -> None:
        if self._lbl_a is None:
            return
        if not self._enabled:
            self._lbl_a.setText("—")
            self._lbl_b.setText("—")
            self._lbl_dt.setText("—")
            self._lbl_freq.setText("—")
            self._clear_per_signal_rows()
            return

        a = self._a.position
        b = self._b.position
        dt = b - a
        self._lbl_a.setText(_fmt_time(a))
        self._lbl_b.setText(_fmt_time(b))
        self._lbl_dt.setText(_fmt_time(dt))
        if abs(dt) > 1e-15:
            self._lbl_freq.setText(_fmt_freq(1.0 / abs(dt)))
        else:
            self._lbl_freq.setText("—")

        self._refresh_per_signal_rows(a, b)

    def _refresh_per_signal_rows(self, a: float, b: float) -> None:
        if self._shell is None or self._per_signal_grid is None:
            return
        canvas = self._shell.plot_canvas
        signals = canvas._signals  # noqa: SLF001

        # Ensure one row per registered signal.
        existing = set(self._per_signal_labels.keys())
        current = set(signals.keys())
        for stale in existing - current:
            for w in self._per_signal_labels.pop(stale):
                w.setParent(None)
                w.deleteLater()
        for new_name in current - existing:
            row = len(self._per_signal_labels)
            name_lbl = QLabel(new_name)
            nf = QFont()
            nf.setPointSize(9)
            name_lbl.setFont(nf)
            val_lbl = QLabel("ΔY: —")
            vf = QFont()
            vf.setPointSize(9)
            vf.setFamily("Menlo, Consolas, monospace")
            val_lbl.setFont(vf)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._per_signal_grid.addWidget(name_lbl, row, 0)
            self._per_signal_grid.addWidget(val_lbl, row, 1)
            self._per_signal_grid.setColumnStretch(1, 1)
            self._per_signal_labels[new_name] = (name_lbl, val_lbl)

        # Update each value.
        for name, (_, val_lbl) in self._per_signal_labels.items():
            state = signals.get(name)
            if state is None:
                val_lbl.setText("ΔY: —")
                continue
            t_arr, y_arr = state.merged()
            if t_arr.size < 2:
                val_lbl.setText("ΔY: —")
                continue
            ya = float(np.interp(a, t_arr, y_arr))
            yb = float(np.interp(b, t_arr, y_arr))
            val_lbl.setText(f"ΔY: {yb - ya:+.4g}")

    def _clear_per_signal_rows(self) -> None:
        for _name, (lbl, val) in list(self._per_signal_labels.items()):
            lbl.setParent(None)
            lbl.deleteLater()
            val.setParent(None)
            val.deleteLater()
        self._per_signal_labels.clear()


# ── Formatting helpers ─────────────────────────────────────────────────


def _fmt_time(value: float) -> str:
    """Format a time value with engineering prefix (s / ms / µs / ns)."""
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
    """Format a frequency value with engineering prefix."""
    av = abs(value)
    if av >= 1e9:
        return f"{value / 1e9:.4g} GHz"
    if av >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if av >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"


__all__ = ["CursorsCapability"]
