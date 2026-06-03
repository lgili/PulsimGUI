"""``PlotCanvas`` — the multi-pane plot area used by the scope shell.

A thin wrapper around ``pyqtgraph.GraphicsLayoutWidget`` that the shell
hands off to capabilities. Capabilities ask the canvas to:

  * add a panel (one independent Y axis, shared X)
  * register a signal (one curve in a panel)
  * append new samples (live streaming hot path)
  * replace data with a full array (post-sim finalisation)

The empty-state hint is rendered on top of the canvas via an overlay
``QLabel`` so it disappears the moment the first curve is registered.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QFrame, QLabel, QStackedWidget, QVBoxLayout, QWidget


# Dark plot tokens — mirror the shell._DARK palette to keep visuals
# coherent across the shell chrome + plot area.
_PLOT_BG = "#16181d"
_PLOT_GRID = "#2c313a"
_PLOT_AXIS = "#5a6273"
_PLOT_TEXT = "#cdd6e3"

# Default 8-step palette — same as LiveScopeWidget so live and post-sim
# views show the same colour for the same signal.
DEFAULT_PALETTE: tuple[str, ...] = (
    "#5b8def", "#f59e0b", "#4ade80", "#f87171",
    "#22d3ee", "#a78bfa", "#fb923c", "#34d399",
)


@dataclass
class _SignalState:
    """Bookkeeping for one registered signal."""

    name: str
    panel: str
    color: str
    unit: str
    curve: pg.PlotDataItem
    t: list[np.ndarray] = field(default_factory=list)
    y: list[np.ndarray] = field(default_factory=list)
    _len: int = 0

    def append(self, t_new: np.ndarray, y_new: np.ndarray) -> None:
        """Append new samples to the in-memory cache (lazy concat)."""
        if t_new.size == 0:
            return
        self.t.append(np.asarray(t_new, dtype=np.float64))
        self.y.append(np.asarray(y_new, dtype=np.float64))
        self._len += int(t_new.size)

    def merged(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the concatenated (t, y) arrays. Cheap when chunked."""
        if not self.t:
            return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
        if len(self.t) == 1:
            return self.t[0], self.y[0]
        t_full = np.concatenate(self.t)
        y_full = np.concatenate(self.y)
        # Collapse the chunked cache so repeated calls stay O(1).
        self.t = [t_full]
        self.y = [y_full]
        return t_full, y_full

    def replace(self, t_full: np.ndarray, y_full: np.ndarray) -> None:
        """Replace cached data with a complete vector (post-sim path)."""
        self.t = [np.asarray(t_full, dtype=np.float64)]
        self.y = [np.asarray(y_full, dtype=np.float64)]
        self._len = int(self.t[0].size)


class PlotCanvas(QFrame):
    """Multi-pane scope plot canvas with stacked, X-linked panels.

    Parameters
    ----------
    accent_color
        Variant accent (drives axis hover colour + cursor lines later).
    parent
        Standard Qt parent.
    """

    def __init__(self, *, accent_color: str = "#5b8def", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopePlotCanvas")
        self.setMinimumHeight(280)
        self._accent = accent_color

        # pyqtgraph global setup. Falls back to raster if OpenGL is not
        # available (headless CI / WSL).
        try:
            pg.setConfigOptions(
                antialias=True,
                background=_PLOT_BG,
                foreground=_PLOT_TEXT,
                useOpenGL=True,
                enableExperimental=True,
            )
        except Exception:  # pragma: no cover - GL not available
            pg.setConfigOptions(
                antialias=True,
                background=_PLOT_BG,
                foreground=_PLOT_TEXT,
                useOpenGL=False,
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Two stacked GraphicsLayoutWidgets — one for the time-domain
        # view (default), one for the frequency-domain FFT view. The
        # capability layer swaps the active page via ``set_view()``.
        self._stack = QStackedWidget(self)
        self._graphics = pg.GraphicsLayoutWidget()
        self._graphics.setBackground(_PLOT_BG)
        self._stack.addWidget(self._graphics)
        self._fft_graphics = pg.GraphicsLayoutWidget()
        self._fft_graphics.setBackground(_PLOT_BG)
        self._stack.addWidget(self._fft_graphics)
        layout.addWidget(self._stack)

        # Panel registry — keyed by panel name, in stacked order.
        self._panels: dict[str, pg.PlotItem] = {}
        self._signals: dict[str, _SignalState] = {}
        self._fft_plot: pg.PlotItem | None = None
        self._fft_curves: dict[str, pg.PlotDataItem] = {}
        self._view_mode: str = "time"

        # Empty-state overlay shown until the first signal is registered.
        self._empty_overlay = QFrame(self)
        self._empty_overlay.setObjectName("ScopePlotEmptyOverlay")
        ov = QVBoxLayout(self._empty_overlay)
        ov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(6)
        self._empty_title = QLabel("No signals yet")
        self._empty_title.setObjectName("ScopeEmptyTitle")
        f = QFont()
        f.setPointSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        self._empty_title.setFont(f)
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov.addWidget(self._empty_title)
        self._empty_hint = QLabel("Drop a signal here from the sidebar, or click Run to start streaming.")
        self._empty_hint.setObjectName("ScopeEmptyHint")
        fh = QFont()
        fh.setPointSize(10)
        self._empty_hint.setFont(fh)
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov.addWidget(self._empty_hint)
        self._empty_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._empty_overlay.raise_()
        self._empty_overlay.setStyleSheet(
            f"#ScopePlotEmptyOverlay {{ background: transparent; }}"
            f"QLabel#ScopeEmptyTitle {{ color: {_PLOT_TEXT}; }}"
            f"QLabel#ScopeEmptyHint  {{ color: {_PLOT_AXIS}; }}"
        )

    # ── Panel + signal API ──────────────────────────────────────────────

    def add_panel(self, name: str, *, unit: str = "") -> pg.PlotItem:
        """Add a new stacked panel. Returns the underlying ``PlotItem``."""
        if name in self._panels:
            return self._panels[name]

        plot = self._graphics.addPlot(row=len(self._panels), col=0)
        plot.showGrid(x=True, y=True, alpha=0.18)
        plot.setMenuEnabled(False)
        plot.hideButtons()
        # Style axes to match the shell tokens.
        for axis_name in ("left", "bottom"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen(_PLOT_AXIS))
            axis.setTextPen(pg.mkPen(_PLOT_TEXT))
        plot.setLabel("left", name, units=unit) if unit else plot.setLabel("left", name)
        # Only the bottom-most panel shows the time axis label/ticks.
        plot.getAxis("bottom").setStyle(showValues=True)
        plot.setLabel("bottom", "t", units="s")
        # ``mode="mean"`` averages each pixel-bin's samples instead of
        # showing min/max — this is what the user expects when looking
        # at a PWM-driven current / voltage at zoom-out: the smooth
        # half-rect-sine average, not a "filled" envelope of switching
        # ripple that visually reads as noise. The application can flip
        # back to "peak" (envelope) via ``set_decimation_mode`` when
        # short-transient inspection (turn-off spikes, single-cycle
        # disturbances) is wanted instead.
        plot.setDownsampling(auto=True, mode="mean")
        plot.setClipToView(True)
        plot.addLegend(offset=(8, 8))

        # Link X with the previous panel (creates the shared-X stack).
        if self._panels:
            last = list(self._panels.values())[-1]
            plot.setXLink(last)
            # Hide the previous panel's bottom labels (the new one owns
            # the X axis at the bottom of the column).
            last.getAxis("bottom").setStyle(showValues=False)
            last.setLabel("bottom", "")

        self._panels[name] = plot
        return plot

    def add_signal(
        self,
        name: str,
        *,
        color: str = "",
        panel: str = "Main",
        unit: str = "",
    ) -> None:
        """Register a curve. Idempotent — re-registering keeps the same instance."""
        if name in self._signals:
            return
        plot = self.add_panel(panel, unit=unit)
        # Pick a colour from the default palette if none provided.
        if not color:
            color = DEFAULT_PALETTE[len(self._signals) % len(DEFAULT_PALETTE)]
        pen = pg.mkPen(color=QColor(color), width=1.6)
        curve = plot.plot([], [], pen=pen, name=name)
        # Per-curve downsampling. Default to ``method='mean'`` (the same
        # as the parent PlotItem set in ``add_panel``): when a power-
        # electronics waveform is zoomed out, the user wants the smooth
        # average — half-rect-sine, sinusoid, DC level — not the min/max
        # envelope of every PWM switching cycle. Explicit per-curve
        # settings are still more reliable across pyqtgraph versions.
        try:
            curve.setDownsampling(auto=True, method="mean")
            curve.setClipToView(True)
        except Exception:  # noqa: BLE001 — old pyqtgraph fallback
            pass
        self._signals[name] = _SignalState(
            name=name, panel=panel, color=color, unit=unit, curve=curve,
        )
        self._update_empty_overlay()

    def set_decimation_mode(self, mode: str) -> None:
        """Change how every curve downsamples at zoom-out.

        Accepted modes (passed through to pyqtgraph):

        * ``"mean"`` — average each pixel-bin's samples. Default.
          Best for displaying the slow envelope (half-rect sine,
          DC level) of a PWM-driven waveform; switching ripple
          averages away cleanly.
        * ``"peak"`` — show min + max per bin. PLECS-style envelope
          rendering; preserves transient spikes (turn-off
          overshoot, single-cycle disturbances) at zoom-out.
        * ``"subsample"`` — take 1 in every N samples. Cheapest;
          can hide spikes between samples but the trace stays
          single-line at all zoom levels.

        Updates both the panel-level default (for any future curve
        added without an override) and every already-registered curve
        so the change is immediate.
        """
        mode = (mode or "mean").lower()
        if mode not in ("mean", "peak", "subsample"):
            raise ValueError(
                f"Unknown decimation mode {mode!r}; "
                f"expected one of mean / peak / subsample."
            )
        for plot in self._panels.values():
            try:
                plot.setDownsampling(auto=True, mode=mode)
            except Exception:  # noqa: BLE001
                pass
        for state in self._signals.values():
            try:
                state.curve.setDownsampling(auto=True, method=mode)
            except Exception:  # noqa: BLE001
                pass

    def append_signal(self, name: str, t_new: np.ndarray, y_new: np.ndarray) -> None:
        """Append new samples to a signal (live streaming hot path)."""
        state = self._signals.get(name)
        if state is None:
            return
        state.append(t_new, y_new)
        t, y = state.merged()
        state.curve.setData(t, y)

    def has_signal(self, name: str) -> bool:
        """Return True when a curve named ``name`` is registered."""
        return name in self._signals

    def replace_signal(self, name: str, t_full: np.ndarray, y_full: np.ndarray) -> None:
        """Replace a signal's data with the full-resolution array (post-sim).

        Creates the curve on demand when it does not exist yet — a post-sim-
        only channel (e.g. a direct-signal motor scope: ``M1.speed_rpm`` /
        ``M1.i_a``) has no live-stream spec, so nothing registered a curve up
        front. Without this it would silently render nothing.
        """
        state = self._signals.get(name)
        if state is None:
            self.add_signal(name)
            state = self._signals.get(name)
            if state is None:
                return
        state.replace(t_full, y_full)
        state.curve.setData(t_full, y_full)

    def clear(self) -> None:
        """Remove all signals and panels — used when a new run starts."""
        for state in self._signals.values():
            state.curve.clear()
        self._signals.clear()
        for plot in self._panels.values():
            self._graphics.removeItem(plot)
        self._panels.clear()
        self._update_empty_overlay()

    def signals(self) -> Sequence[str]:
        """Return the registered signal names in registration order."""
        return list(self._signals.keys())

    # ── View mode (time / fft) ──────────────────────────────────────────

    def set_view(self, mode: str) -> None:
        """Swap between the time-domain and the FFT page.

        ``mode`` is ``"time"`` or ``"fft"``. The FFT page rebuilds from
        the cached signal data on each switch — that's cheap (O(N log N)
        per signal) and avoids stale FFTs when the user re-runs the sim
        while the FFT page is hidden.
        """
        mode = "fft" if str(mode).lower() == "fft" else "time"
        self._view_mode = mode
        if mode == "fft":
            self._stack.setCurrentWidget(self._fft_graphics)
            self.refresh_fft()
        else:
            self._stack.setCurrentWidget(self._graphics)

    def refresh_fft(self) -> None:
        """Recompute and redraw the FFT panel from the cached signal data."""
        # Create the FFT plot lazily on the first switch.
        if self._fft_plot is None:
            plot = self._fft_graphics.addPlot(row=0, col=0)
            plot.showGrid(x=True, y=True, alpha=0.18)
            plot.setMenuEnabled(False)
            plot.hideButtons()
            for axis_name in ("left", "bottom"):
                axis = plot.getAxis(axis_name)
                axis.setPen(pg.mkPen(_PLOT_AXIS))
                axis.setTextPen(pg.mkPen(_PLOT_TEXT))
            plot.setLabel("left", "Magnitude", units="dB")
            plot.setLabel("bottom", "Frequency", units="Hz")
            plot.setLogMode(x=True, y=False)
            plot.setDownsampling(auto=True, mode="peak")
            plot.setClipToView(True)
            plot.addLegend(offset=(8, 8))
            self._fft_plot = plot

        plot = self._fft_plot

        # Sync curves: keep one per signal name, drop stale ones.
        wanted = set(self._signals.keys())
        existing = set(self._fft_curves.keys())
        for stale in existing - wanted:
            curve = self._fft_curves.pop(stale)
            plot.removeItem(curve)

        # Recompute each signal's FFT and update its curve.
        for name, state in self._signals.items():
            t, y = state.merged()
            if t.size < 4:
                continue
            f, mag_db = _signal_fft(t, y)
            if name not in self._fft_curves:
                pen = pg.mkPen(color=QColor(state.color), width=1.6)
                self._fft_curves[name] = plot.plot([], [], pen=pen, name=name)
            self._fft_curves[name].setData(f, mag_db)

    # ── Empty-state helpers ─────────────────────────────────────────────

    def set_empty_message(self, title: str, hint: str = "") -> None:
        """Update the overlay text (e.g. when streaming hasn't started yet)."""
        self._empty_title.setText(title)
        self._empty_hint.setText(hint)

    def _update_empty_overlay(self) -> None:
        self._empty_overlay.setVisible(not self._signals)

    def resizeEvent(self, event):  # noqa: D401 - Qt override
        super().resizeEvent(event)
        # Keep the overlay covering the plot area.
        self._empty_overlay.setGeometry(self.rect())


def _signal_fft(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(frequencies, magnitude_db)`` for a real-valued signal.

    Uses a uniform time grid built from ``t[0] → t[-1]`` so unevenly
    sampled streams (live mode) FFT cleanly. Skips DC (``f == 0``) so
    the log-frequency axis doesn't blow up.
    """
    n = int(t.size)
    if n < 4 or y.size < 4:
        return np.empty(0), np.empty(0)
    # Resample onto a uniform grid for FFT correctness.
    t_uniform = np.linspace(float(t[0]), float(t[-1]), n)
    y_uniform = np.interp(t_uniform, t, y)
    dt = float(t_uniform[1] - t_uniform[0]) if n > 1 else 1.0
    if dt <= 0.0:
        return np.empty(0), np.empty(0)
    spectrum = np.fft.rfft(y_uniform - float(np.mean(y_uniform)))
    freqs = np.fft.rfftfreq(n, d=dt)
    mag = np.abs(spectrum) / max(1, n // 2)
    # Convert to dB, floor at -120 dB so log axis stays finite.
    mag_db = 20.0 * np.log10(np.maximum(mag, 1e-12))
    # Drop the DC bin (f == 0) — log X scale can't render it.
    if freqs.size > 0 and freqs[0] == 0.0:
        freqs = freqs[1:]
        mag_db = mag_db[1:]
    return freqs, mag_db


__all__ = ["PlotCanvas", "DEFAULT_PALETTE"]
