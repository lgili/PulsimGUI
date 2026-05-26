"""Live streaming scope widget — multi-panel + cursors + trigger +
SMPS measurement macros, on top of ``pulsim.NativeLiveStream``.

The kernel ships ``pulsim.LiveScope``, a stand-alone Qt window that
polls a :class:`pulsim.stream.NativeLiveStream` ring buffer (zero-copy,
GIL-free, kernel-decimated) and draws with pyqtgraph at 30–60 Hz.
``LiveScope.start()`` spawns its own ``QApplication.exec()``, which
clashes with the GUI's already-running event loop.

:class:`LiveScopeWidget` is the embeddable cousin — same polling
strategy, but a :class:`QWidget` you stitch into the GUI's layout
(a scope window, a dock, a modal). It also goes beyond the kernel's
``LiveScope`` with PLECS-style live-analysis features:

  * **Multi-panel** stacked layout (e.g. ``Voltage`` / ``Current`` /
    ``Control``) with independent Y axes but a linked X axis.
  * **Cursors A/B** with ΔT, frequency = 1/ΔT, and per-trace ΔY
    readouts.
  * **Trigger** modes (``Free Run`` / ``Single``) on a chosen source
    + level + edge.
  * **SMPS macros** for power-electronics-specific measurements:
    auto-detect ``Tsw`` (switching period), ``Duty``, and ``Ripple``
    (V_pp / I_pp) in the current visible window.

Threading contract:
    The widget lives on the GUI thread. The QTimer that drives
    ``_tick`` fires on the same thread. ``stream.get_new_samples()``
    is safe to call from any thread because the underlying ring
    buffer is C++-backed and atomic — the kernel writes from the
    worker thread, the GUI reads here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_LOG = logging.getLogger(__name__)


# Default colour cycle — mirrors the ScopeWindow palette so the live
# view doesn't visually clash with the post-run static view.
DEFAULT_PALETTE: tuple[str, ...] = (
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759",
    "#76b7b2", "#edc949", "#af7aa1", "#ff9da7",
)

_BG_COLOR = "#16181c"
_GRID_COLOR = "#2c3038"
_TEXT_COLOR = "#d6d8db"
_ACCENT_COLOR = "#4e79a7"
_CURSOR_A_COLOR = "#ffb300"
_CURSOR_B_COLOR = "#ff5252"


@dataclass
class LiveSignalSpec:
    """One curve to display.

    Attributes
    ----------
    name
        Display name + legend label. Also used as the panel key in
        per-signal lookups.
    state_idx
        Column index into the kernel state vector that the ring
        buffer pushes; resolved once at registration so the per-tick
        path is a single numpy slice.
    color
        Hex string for the curve pen.
    unit
        SI-ish unit for the Y axis + readout formatting.
    panel
        Which sub-panel the curve goes into. Default ``"Main"``.
        Pass a custom name (e.g. ``"Voltage"`` / ``"Current"``) when
        you want multi-panel layout; panels are created on first
        registration in registration order.
    """

    name: str
    state_idx: int
    color: str = "#4e79a7"
    unit: str = "V"
    panel: str = "Main"


# ============================================================================
# SMPS / cursor numpy helpers — pure-numpy, easy to unit-test offline.
# ============================================================================


def _zero_crossings(t: np.ndarray, y: np.ndarray,
                     level: float = 0.0,
                     direction: str = "rising") -> np.ndarray:
    """Return the (interpolated) time stamps where ``y(t)`` crosses
    ``level``. ``direction`` ∈ {``"rising"``, ``"falling"``,
    ``"both"``}. Empty array when no crossing in the window.
    """
    if t.size < 2:
        return np.empty(0, dtype=np.float64)
    y0 = y - level
    # sign change tests
    if direction == "rising":
        cross = (y0[:-1] <= 0.0) & (y0[1:] > 0.0)
    elif direction == "falling":
        cross = (y0[:-1] >= 0.0) & (y0[1:] < 0.0)
    else:  # "both"
        cross = ((y0[:-1] <= 0.0) & (y0[1:] > 0.0)) | \
                ((y0[:-1] >= 0.0) & (y0[1:] < 0.0))
    idx = np.nonzero(cross)[0]
    if idx.size == 0:
        return np.empty(0, dtype=np.float64)
    # Linear interpolation between samples for sub-sample precision.
    t0, t1 = t[idx], t[idx + 1]
    y_a, y_b = y0[idx], y0[idx + 1]
    # avoid div-by-zero when y_a == y_b exactly (rare)
    denom = (y_b - y_a)
    frac = np.where(np.abs(denom) > 1e-30, -y_a / denom, 0.5)
    return t0 + frac * (t1 - t0)


def _detect_period(t: np.ndarray, y: np.ndarray) -> float | None:
    """Estimate the period of ``y(t)`` via consecutive same-direction
    zero crossings of the mean-subtracted signal. Returns ``None``
    when no period can be inferred (<2 crossings)."""
    if y.size < 4:
        return None
    y_dc = y - float(np.mean(y))
    crosses = _zero_crossings(t, y_dc, level=0.0, direction="rising")
    if crosses.size < 2:
        # Fall back to peak-to-peak detection for square-ish signals.
        crosses = _zero_crossings(t, y_dc, level=0.0, direction="both")
        if crosses.size < 3:
            return None
        return float(2.0 * np.median(np.diff(crosses)))
    return float(np.median(np.diff(crosses)))


def _detect_duty(t: np.ndarray, y: np.ndarray) -> float | None:
    """Estimate the duty cycle of a switching signal: fraction of
    each period where ``y > median(y)``. Returns ``None`` if no
    meaningful switching is detected in the window."""
    if y.size < 8:
        return None
    threshold = float(np.median(y))
    high = y > threshold
    # Need at least one full cycle.
    if high.all() or (~high).all():
        return None
    return float(np.mean(high))


def _ripple_stats(y: np.ndarray) -> dict[str, float]:
    """Min/max/mean/p-p/RMS over the window."""
    if y.size == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0,
                "pp": 0.0, "rms": 0.0}
    y_min = float(np.min(y))
    y_max = float(np.max(y))
    return {
        "min":  y_min,
        "max":  y_max,
        "mean": float(np.mean(y)),
        "pp":   y_max - y_min,
        "rms":  float(np.sqrt(np.mean(y * y))),
    }


# ============================================================================
# LiveScopeWidget
# ============================================================================


class LiveScopeWidget(QWidget):
    """Embeddable live-scope widget with multi-panel layout, cursors,
    trigger, and SMPS measurement macros.

    Parameters
    ----------
    stream
        The :class:`pulsim.stream.NativeLiveStream`.
    signals
        Curves to draw at construction time. Empty list valid —
        register later via :meth:`add_signal`.
    panels
        Panel names (top → bottom). Default ``("Main",)``. Panels
        share a linked X axis with independent Y.
    window_seconds
        Rolling-window width on the time axis during free-run mode.
    update_hz
        Redraw rate. 60 Hz is the sweet spot.
    """

    # Emitted when the user clicks the in-widget Stop button.
    stop_requested = Signal()

    def __init__(
        self,
        stream: Any,
        signals: list[LiveSignalSpec] | None = None,
        *,
        panels: tuple[str, ...] | list[str] | None = None,
        window_seconds: float = 2.0,
        update_hz: float = 60.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._stream = stream
        self._window_seconds = float(window_seconds)
        self._update_interval_ms = max(10, int(1000.0 / float(update_hz)))

        self._max_points = 300_000

        # Panel + curve registry.
        self._panel_names = list(panels) if panels else ["Main"]
        self._panel_plots: dict[str, pg.PlotItem] = {}
        self._sig_specs: list[LiveSignalSpec] = []
        self._ring_t: dict[str, np.ndarray] = {}
        self._ring_y: dict[str, np.ndarray] = {}
        self._ring_n: dict[str, int] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}

        # Streaming / lifecycle state.
        self._paused = False
        self._finalised = False
        self._sample_count = 0
        self._dropped = 0

        # Trigger state.
        self._trigger_mode: str = "free"   # "free" | "single"
        self._trigger_source: str | None = None
        self._trigger_level: float = 0.0
        self._trigger_edge: str = "rising"  # "rising" | "falling"
        self._trigger_fired_at: float | None = None  # t of last fire
        self._trigger_armed: bool = True

        # Cursor state.
        self._cursors_enabled = False
        self._cursor_a_pos: float = 0.0
        self._cursor_b_pos: float = 0.0
        self._cursor_a_line: pg.InfiniteLine | None = None
        self._cursor_b_line: pg.InfiniteLine | None = None
        self._cursor_panel: str | None = None  # which panel they live in

        self._build_ui()
        for spec in signals or []:
            self.add_signal(spec)
        # Drop any "Main" panel that was created automatically if the
        # caller registered signals into custom panels only.
        if not self._sig_specs and "Main" not in self._panel_names:
            pass

        self._timer = QTimer(self)
        self._timer.setInterval(self._update_interval_ms)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # UI scaffolding
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # OpenGL render path. Falls back to raster on systems without
        # an OpenGL stack.
        try:
            pg.setConfigOptions(
                antialias=True,
                background=_BG_COLOR,
                foreground=_TEXT_COLOR,
                useOpenGL=True,
                enableExperimental=True,
            )
        except Exception:  # noqa: BLE001
            pg.setConfigOptions(
                antialias=True,
                background=_BG_COLOR,
                foreground=_TEXT_COLOR,
                useOpenGL=False,
            )

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Left: stacked panels.
        plot_col = QVBoxLayout()
        plot_col.setSpacing(4)

        self._graphics = pg.GraphicsLayoutWidget()
        self._graphics.setBackground(_BG_COLOR)
        plot_col.addWidget(self._graphics, stretch=1)

        # Build each panel as a PlotItem.
        prev_plot: pg.PlotItem | None = None
        for i, name in enumerate(self._panel_names):
            self._add_panel_plot(name, prev_plot, is_bottom=(i == len(self._panel_names) - 1))
            prev_plot = self._panel_plots[name]

        # Status row.
        status_row = QHBoxLayout()
        self._status_label = QLabel("waiting for stream…")
        self._status_label.setStyleSheet(
            f"color: {_TEXT_COLOR}; font: 11px monospace;"
        )
        status_row.addWidget(self._status_label, stretch=1)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.toggled.connect(self._on_pause_toggled)
        status_row.addWidget(self._pause_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self.clear)
        status_row.addWidget(self._clear_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        status_row.addWidget(self._stop_btn)

        plot_col.addLayout(status_row)
        root.addLayout(plot_col, stretch=1)

        # Right: side panel with cursor / trigger / SMPS controls.
        side = self._build_side_panel()
        root.addWidget(side, stretch=0)

    def _add_panel_plot(self, name: str,
                          prev_plot: pg.PlotItem | None,
                          *, is_bottom: bool) -> None:
        if name in self._panel_plots:
            return
        plot = self._graphics.addPlot(row=len(self._panel_plots), col=0)
        plot.setBackground(_BG_COLOR) if hasattr(plot, "setBackground") else None
        plot.showGrid(x=True, y=True, alpha=0.2)
        plot.getAxis("left").setPen(_GRID_COLOR)
        plot.getAxis("bottom").setPen(_GRID_COLOR)
        plot.getAxis("left").setTextPen(_TEXT_COLOR)
        plot.getAxis("bottom").setTextPen(_TEXT_COLOR)
        plot.setLabel("left", name)
        if is_bottom:
            plot.setLabel("bottom", "t", units="s")
        else:
            plot.getAxis("bottom").setStyle(showValues=False)
        plot.setDownsampling(auto=True, mode="peak")
        plot.setClipToView(True)
        plot.addLegend(offset=(8, 8))
        if prev_plot is not None:
            plot.setXLink(prev_plot)
        self._panel_plots[name] = plot

    def _build_side_panel(self) -> QWidget:
        """Right-side stack: Cursors / Trigger / SMPS macros."""
        side = QWidget()
        side.setFixedWidth(240)
        side.setStyleSheet(
            f"QGroupBox {{ color: {_TEXT_COLOR}; border: 1px solid {_GRID_COLOR}; "
            f"border-radius: 3px; margin-top: 8px; padding-top: 8px; }} "
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 6px; }} "
            f"QLabel {{ color: {_TEXT_COLOR}; }} "
            f"QPushButton {{ background: {_GRID_COLOR}; color: {_TEXT_COLOR}; "
            f"border: 1px solid {_GRID_COLOR}; padding: 4px 8px; border-radius: 3px; }} "
            f"QPushButton:checked {{ background: {_ACCENT_COLOR}; }} "
            f"QPushButton:hover {{ background: {_ACCENT_COLOR}; }} "
            f"QComboBox, QDoubleSpinBox {{ background: {_BG_COLOR}; "
            f"color: {_TEXT_COLOR}; border: 1px solid {_GRID_COLOR}; padding: 2px 4px; }}"
        )
        col = QVBoxLayout(side)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        col.addWidget(self._build_cursor_group())
        col.addWidget(self._build_trigger_group())
        col.addWidget(self._build_smps_group())
        col.addStretch(1)
        return side

    def _build_cursor_group(self) -> QGroupBox:
        box = QGroupBox("Cursors")
        v = QVBoxLayout(box)
        v.setSpacing(4)

        self._cursor_toggle = QPushButton("Show A/B Cursors")
        self._cursor_toggle.setCheckable(True)
        self._cursor_toggle.toggled.connect(self._on_cursor_toggle)
        v.addWidget(self._cursor_toggle)

        self._cursor_readout = QLabel("(cursors off)")
        self._cursor_readout.setStyleSheet(
            f"color: {_TEXT_COLOR}; font: 11px monospace;"
        )
        self._cursor_readout.setWordWrap(True)
        v.addWidget(self._cursor_readout)
        return box

    def _build_trigger_group(self) -> QGroupBox:
        box = QGroupBox("Trigger")
        form = QFormLayout(box)
        form.setSpacing(4)
        form.setContentsMargins(8, 12, 8, 8)

        self._trigger_mode_combo = QComboBox()
        self._trigger_mode_combo.addItems(["Free Run", "Single"])
        self._trigger_mode_combo.currentTextChanged.connect(self._on_trigger_mode)
        form.addRow("Mode:", self._trigger_mode_combo)

        self._trigger_source_combo = QComboBox()
        self._trigger_source_combo.currentTextChanged.connect(
            lambda name: setattr(self, "_trigger_source", name or None)
        )
        form.addRow("Source:", self._trigger_source_combo)

        self._trigger_edge_combo = QComboBox()
        self._trigger_edge_combo.addItems(["rising", "falling"])
        self._trigger_edge_combo.currentTextChanged.connect(
            lambda val: setattr(self, "_trigger_edge", val)
        )
        form.addRow("Edge:", self._trigger_edge_combo)

        self._trigger_level_spin = QDoubleSpinBox()
        self._trigger_level_spin.setRange(-1e9, 1e9)
        self._trigger_level_spin.setDecimals(4)
        self._trigger_level_spin.setSingleStep(0.1)
        self._trigger_level_spin.valueChanged.connect(
            lambda val: setattr(self, "_trigger_level", float(val))
        )
        form.addRow("Level:", self._trigger_level_spin)

        self._trigger_rearm_btn = QPushButton("Re-arm")
        self._trigger_rearm_btn.clicked.connect(self._rearm_trigger)
        form.addRow("", self._trigger_rearm_btn)

        return box

    def _build_smps_group(self) -> QGroupBox:
        box = QGroupBox("SMPS Measure")
        v = QVBoxLayout(box)
        v.setSpacing(4)

        self._meas_source_combo = QComboBox()
        v.addWidget(QLabel("On signal:"))
        v.addWidget(self._meas_source_combo)

        for name, slot in (
            ("Measure Tsw + Fsw", self._measure_tsw),
            ("Measure Duty",      self._measure_duty),
            ("Measure Ripple",    self._measure_ripple),
        ):
            btn = QPushButton(name)
            btn.clicked.connect(slot)
            v.addWidget(btn)

        self._smps_readout = QLabel("—")
        self._smps_readout.setStyleSheet(
            f"color: {_TEXT_COLOR}; font: 11px monospace;"
        )
        self._smps_readout.setWordWrap(True)
        v.addWidget(self._smps_readout)
        return box

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_signal(self, spec: LiveSignalSpec) -> None:
        """Register a curve. Safe to call before or after :meth:`start`.

        The curve goes into ``spec.panel`` (defaults to ``"Main"``);
        the panel is created on first reference in registration
        order.
        """
        if spec.name in self._curves:
            _LOG.debug("LiveScopeWidget: signal %r already registered",
                       spec.name)
            return
        # Lazily create the panel if the signal references a new one.
        if spec.panel not in self._panel_plots:
            self._panel_names.append(spec.panel)
            prev_panels = list(self._panel_plots.values())
            self._add_panel_plot(
                spec.panel, prev_panels[-1] if prev_panels else None,
                is_bottom=True,
            )
            # Bottom-axis swap: previous "bottom" panel now hides
            # its tick labels.
            if len(prev_panels) > 0:
                prev_panels[-1].getAxis("bottom").setStyle(showValues=False)
        self._sig_specs.append(spec)
        self._ring_t[spec.name] = np.empty(self._max_points, dtype=np.float64)
        self._ring_y[spec.name] = np.empty(self._max_points, dtype=np.float64)
        self._ring_n[spec.name] = 0
        pen = pg.mkPen(color=spec.color, width=1.8)
        plot = self._panel_plots[spec.panel]
        self._curves[spec.name] = plot.plot(pen=pen, name=spec.name)

        # Add to trigger-source + SMPS-source dropdowns.
        self._trigger_source_combo.addItem(spec.name)
        self._meas_source_combo.addItem(spec.name)
        if self._trigger_source is None:
            self._trigger_source = spec.name
            self._trigger_source_combo.setCurrentText(spec.name)

    def start(self) -> None:
        """Begin polling. Idempotent."""
        if not self._timer.isActive():
            self._timer.start()

    def stop_polling(self) -> None:
        """Stop the redraw timer (does NOT halt the kernel)."""
        self._timer.stop()

    def request_kernel_stop(self) -> None:
        """Ask the kernel to halt at the next step boundary."""
        if self._stream is None:
            return
        stop = getattr(self._stream, "stop", None)
        if callable(stop):
            stop()

    def clear(self) -> None:
        """Drop all sample history."""
        for name in self._ring_n:
            self._ring_n[name] = 0
        for curve in self._curves.values():
            curve.clear()
        self._sample_count = 0
        self._dropped = 0
        self._trigger_fired_at = None
        self._trigger_armed = True
        self._update_status()

    def finalize(self, t_full: np.ndarray, x_full: np.ndarray) -> None:
        """Replace the streaming buffer with the full-resolution
        simulation result."""
        self.stop_polling()
        if t_full.size == 0 or x_full.size == 0:
            self._finalised = True
            self._update_status(extra=" — finalised (no samples)")
            return
        for spec in self._sig_specs:
            if spec.state_idx >= x_full.shape[1]:
                continue
            curve = self._curves.get(spec.name)
            if curve is None:
                continue
            curve.setData(t_full, x_full[:, spec.state_idx])
            # Update ring caches so cursor / measurement helpers work
            # against the full-res arrays afterwards.
            n = t_full.size
            if n > self._max_points:
                # Down-sample to fit the preallocated ring.
                step = max(1, n // self._max_points)
                t_clip = t_full[::step][: self._max_points]
                y_clip = x_full[::step, spec.state_idx][: self._max_points]
                n_clip = t_clip.size
                self._ring_t[spec.name][:n_clip] = t_clip
                self._ring_y[spec.name][:n_clip] = y_clip
                self._ring_n[spec.name] = n_clip
            else:
                self._ring_t[spec.name][:n] = t_full
                self._ring_y[spec.name][:n] = x_full[:, spec.state_idx]
                self._ring_n[spec.name] = n
        # Use the first / last plot for the X range.
        plots = list(self._panel_plots.values())
        if plots:
            plots[0].setXRange(
                float(t_full[0]), float(t_full[-1]), padding=0.02,
            )
            for p in plots:
                p.enableAutoRange(axis="y")
        self._finalised = True
        self._update_status(extra=f" — finalised ({t_full.size} pts)")
        self._update_cursor_readout()

    # ------------------------------------------------------------------
    # QTimer tick — hot path
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self._stream is None or self._paused or self._finalised:
            return
        # In single-trigger mode, once we've fired and showed the
        # window we freeze. The Re-arm button clears that state.
        if self._trigger_mode == "single" and self._trigger_fired_at is not None:
            self._update_status()
            return
        samples = self._stream.get_new_samples()
        if samples is None:
            self._update_status()
            return
        t_new, x_new = samples
        if t_new.size == 0:
            return
        # Append per-signal ring.
        for spec in self._sig_specs:
            if spec.state_idx >= x_new.shape[1]:
                continue
            t_ring = self._ring_t[spec.name]
            y_ring = self._ring_y[spec.name]
            n = self._ring_n[spec.name]
            n_new = t_new.size
            if n + n_new > self._max_points:
                keep = self._max_points // 2
                t_ring[:keep] = t_ring[n - keep:n]
                y_ring[:keep] = y_ring[n - keep:n]
                n = keep
            end = n + n_new
            t_ring[n:end] = t_new
            y_ring[n:end] = x_new[:, spec.state_idx]
            self._ring_n[spec.name] = end

        # Trigger detection — only when armed in single mode.
        if self._trigger_mode == "single" and self._trigger_armed:
            self._check_trigger_in_new_samples(t_new, x_new)

        # Push to pyqtgraph curves + adjust X range.
        latest_t = float(t_new[-1])
        x_min = max(0.0, latest_t - self._window_seconds)
        for spec in self._sig_specs:
            n = self._ring_n[spec.name]
            if n == 0:
                continue
            curve = self._curves[spec.name]
            curve.setData(
                self._ring_t[spec.name][:n],
                self._ring_y[spec.name][:n],
            )
        # X-range update (any panel — they're X-linked).
        plots = list(self._panel_plots.values())
        if plots:
            if self._trigger_fired_at is not None and self._trigger_mode == "single":
                # Show ½ window before, ½ after the trigger.
                t_trig = self._trigger_fired_at
                half = self._window_seconds / 2.0
                plots[0].setXRange(t_trig - half, t_trig + half, padding=0.0)
            else:
                plots[0].setXRange(x_min, latest_t, padding=0.02)

        self._sample_count += int(t_new.size)
        dropped = getattr(self._stream, "_dropped_samples", None)
        if isinstance(dropped, int):
            self._dropped = dropped
        self._update_status()
        if self._cursors_enabled:
            self._update_cursor_readout()

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------
    def _on_trigger_mode(self, label: str) -> None:
        self._trigger_mode = "single" if label.lower().startswith("single") else "free"
        if self._trigger_mode == "free":
            self._trigger_fired_at = None
            self._trigger_armed = True

    def _rearm_trigger(self) -> None:
        self._trigger_fired_at = None
        self._trigger_armed = True
        self._update_status()

    def _check_trigger_in_new_samples(self, t_new: np.ndarray,
                                         x_new: np.ndarray) -> None:
        if not self._trigger_source:
            return
        spec = next((s for s in self._sig_specs
                      if s.name == self._trigger_source), None)
        if spec is None or spec.state_idx >= x_new.shape[1]:
            return
        y = x_new[:, spec.state_idx]
        crosses = _zero_crossings(
            t_new, y, level=self._trigger_level, direction=self._trigger_edge,
        )
        if crosses.size == 0:
            return
        self._trigger_fired_at = float(crosses[0])
        self._trigger_armed = False

    # ------------------------------------------------------------------
    # Cursors
    # ------------------------------------------------------------------
    def _on_cursor_toggle(self, on: bool) -> None:
        self._cursors_enabled = on
        if on:
            # Place cursors at 25% / 75% of the current visible X range.
            plots = list(self._panel_plots.values())
            if not plots:
                return
            (xmin, xmax), _ = plots[0].viewRange()
            self._cursor_a_pos = xmin + 0.25 * (xmax - xmin)
            self._cursor_b_pos = xmin + 0.75 * (xmax - xmin)
            panel_name = self._panel_names[0]
            plot = plots[0]
            self._cursor_panel = panel_name
            self._cursor_a_line = pg.InfiniteLine(
                pos=self._cursor_a_pos, angle=90, movable=True,
                pen=pg.mkPen(color=_CURSOR_A_COLOR, width=1.5),
                label="A", labelOpts={"position": 0.92, "color": _CURSOR_A_COLOR},
            )
            self._cursor_b_line = pg.InfiniteLine(
                pos=self._cursor_b_pos, angle=90, movable=True,
                pen=pg.mkPen(color=_CURSOR_B_COLOR, width=1.5),
                label="B", labelOpts={"position": 0.92, "color": _CURSOR_B_COLOR},
            )
            self._cursor_a_line.sigPositionChanged.connect(
                lambda line: self._on_cursor_moved(line, which="a")
            )
            self._cursor_b_line.sigPositionChanged.connect(
                lambda line: self._on_cursor_moved(line, which="b")
            )
            plot.addItem(self._cursor_a_line)
            plot.addItem(self._cursor_b_line)
            self._update_cursor_readout()
        else:
            for line in (self._cursor_a_line, self._cursor_b_line):
                if line is None:
                    continue
                for plot in self._panel_plots.values():
                    try:
                        plot.removeItem(line)
                    except Exception:  # noqa: BLE001
                        pass
            self._cursor_a_line = None
            self._cursor_b_line = None
            self._cursor_panel = None
            self._cursor_readout.setText("(cursors off)")

    def _on_cursor_moved(self, line: pg.InfiniteLine, *, which: str) -> None:
        pos = float(line.value())
        if which == "a":
            self._cursor_a_pos = pos
        else:
            self._cursor_b_pos = pos
        self._update_cursor_readout()

    def _update_cursor_readout(self) -> None:
        if not self._cursors_enabled:
            return
        t_a, t_b = self._cursor_a_pos, self._cursor_b_pos
        dt = t_b - t_a
        f = (1.0 / dt) if abs(dt) > 1e-30 else float("inf")
        lines = [f"t_A = {t_a:.6g} s",
                 f"t_B = {t_b:.6g} s",
                 f"ΔT  = {dt:.6g} s",
                 f"1/ΔT = {f:.6g} Hz",
                 ""]
        # Per-trace ΔY.
        for spec in self._sig_specs:
            n = self._ring_n[spec.name]
            if n < 2:
                continue
            t_ring = self._ring_t[spec.name][:n]
            y_ring = self._ring_y[spec.name][:n]
            y_a = float(np.interp(t_a, t_ring, y_ring))
            y_b = float(np.interp(t_b, t_ring, y_ring))
            dy = y_b - y_a
            lines.append(f"{spec.name}:  ΔY = {dy:+.4g} {spec.unit}")
        self._cursor_readout.setText("\n".join(lines))

    # ------------------------------------------------------------------
    # SMPS macros — operate on the SOURCE selected in the SMPS combo,
    # over the visible X range (or, when cursors are on, between them).
    # ------------------------------------------------------------------
    def _get_meas_window(self) -> tuple[np.ndarray, np.ndarray] | None:
        name = self._meas_source_combo.currentText()
        if not name or name not in self._ring_n:
            return None
        n = self._ring_n[name]
        if n < 4:
            return None
        t_full = self._ring_t[name][:n]
        y_full = self._ring_y[name][:n]
        # Default: visible X range from first panel.
        plots = list(self._panel_plots.values())
        if not plots:
            return t_full, y_full
        (xmin, xmax), _ = plots[0].viewRange()
        # Override with cursor span when both cursors are on.
        if self._cursors_enabled and self._cursor_a_line and self._cursor_b_line:
            xmin = min(self._cursor_a_pos, self._cursor_b_pos)
            xmax = max(self._cursor_a_pos, self._cursor_b_pos)
        mask = (t_full >= xmin) & (t_full <= xmax)
        if not mask.any():
            return t_full, y_full
        return t_full[mask], y_full[mask]

    def _measure_tsw(self) -> None:
        window = self._get_meas_window()
        if window is None:
            self._smps_readout.setText("Need ≥4 samples in source")
            return
        t, y = window
        Tsw = _detect_period(t, y)
        if Tsw is None or Tsw <= 0.0:
            self._smps_readout.setText("Tsw: not detected\n(no clear period)")
            return
        fsw = 1.0 / Tsw
        self._smps_readout.setText(
            f"Tsw = {Tsw*1e6:.3f} µs\n"
            f"Fsw = {fsw/1e3:.3f} kHz"
        )

    def _measure_duty(self) -> None:
        window = self._get_meas_window()
        if window is None:
            self._smps_readout.setText("Need ≥8 samples in source")
            return
        _, y = window
        D = _detect_duty(*window)
        if D is None:
            self._smps_readout.setText(
                "Duty: not detected\n(signal not switching)"
            )
            return
        self._smps_readout.setText(
            f"Duty = {D*100:.2f} %\n(t_high / Tsw)"
        )

    def _measure_ripple(self) -> None:
        window = self._get_meas_window()
        if window is None:
            self._smps_readout.setText("Need samples in source")
            return
        _, y = window
        s = _ripple_stats(y)
        self._smps_readout.setText(
            f"mean = {s['mean']:+.4g}\n"
            f"min  = {s['min']:+.4g}\n"
            f"max  = {s['max']:+.4g}\n"
            f"p-p  = {s['pp']:.4g}\n"
            f"RMS  = {s['rms']:.4g}"
        )

    # ------------------------------------------------------------------
    # Misc / status
    # ------------------------------------------------------------------
    def _on_pause_toggled(self, paused: bool) -> None:
        self._paused = bool(paused)
        self._pause_btn.setText("Resume" if paused else "Pause")

    def _on_stop_clicked(self) -> None:
        self.request_kernel_stop()
        self.stop_requested.emit()

    def _update_status(self, *, extra: str = "") -> None:
        if not self._sig_specs:
            self._status_label.setText("no signals registered" + extra)
            return
        if self._sample_count == 0:
            self._status_label.setText("waiting for stream…" + extra)
            return
        drop_part = f"  dropped={self._dropped}" if self._dropped else ""
        trig_part = ""
        if self._trigger_mode == "single":
            if self._trigger_fired_at is not None:
                trig_part = f"  trig@{self._trigger_fired_at:.4g}s"
            else:
                trig_part = "  trig-armed"
        self._status_label.setText(
            f"samples={self._sample_count}{drop_part}{trig_part}{extra}",
        )


__all__ = ["LiveScopeWidget", "LiveSignalSpec", "DEFAULT_PALETTE"]
