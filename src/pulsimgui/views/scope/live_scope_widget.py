"""Live streaming scope widget — mirrors ``pulsim.LiveScope`` but as a
plain :class:`QWidget` you can embed in the GUI's existing window
hierarchy.

The kernel ships ``pulsim.LiveScope``, a stand-alone Qt window that
polls a :class:`pulsim.stream.NativeLiveStream` ring buffer (zero-copy,
GIL-free, kernel-decimated) and draws the result with pyqtgraph at
30–60 Hz. Calling ``LiveScope.start()`` is convenient for headless
scripts (e.g. ``examples/scripts/run_live_scope_buck.py``) but it
spawns its own ``QApplication.exec()`` loop — which clashes with the
GUI's already-running event loop.

:class:`LiveScopeWidget` is the embeddable cousin: same polling
strategy, same numpy ring buffers, but presented as a widget the
caller stitches into a layout (a scope window, a dock, a modal, …).

Public surface kept minimal on purpose. Add helpers as the GUI grows
needs — multi-panel layouts, math channels, cursors — instead of
porting the kernel's full ``LiveScope`` up-front; the kernel's
``LiveScope`` keeps polishing those (see Phase 145 backlog), so we
follow rather than fork.

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
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_LOG = logging.getLogger(__name__)


@dataclass
class LiveSignalSpec:
    """One curve to display. ``state_idx`` points into the state
    vector that the kernel pushes into the ring buffer; that lookup
    happens once at registration so the per-tick path is a single
    numpy column slice."""

    name: str
    state_idx: int
    color: str = "#4e79a7"
    unit: str = "V"


# Pleasant pyqtgraph defaults. Same palette as the existing ScopeWindow
# so the live view doesn't clash with the post-run static view.
# Default colour cycle — mirrors the ScopeWindow palette so the live
# view doesn't visually clash with the post-run static view.
DEFAULT_PALETTE: tuple[str, ...] = (
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759",
    "#76b7b2", "#edc949", "#af7aa1", "#ff9da7",
)

_BG_COLOR = "#16181c"
_GRID_COLOR = "#2c3038"
_TEXT_COLOR = "#d6d8db"


class LiveScopeWidget(QWidget):
    """Embeddable live-scope widget.

    Parameters
    ----------
    stream
        The :class:`pulsim.stream.NativeLiveStream` (or any object
        exposing ``get_new_samples() -> (t, x) | None``, ``stop()``,
        ``attached: bool``). The widget never assumes the stream is
        attached at construction time — kernel attachment happens
        when ``simulate(live_stream=…)`` first sees it.
    signals
        Curves to draw. Empty list is valid (you can register later
        via :meth:`add_signal`); but the widget is more useful with
        at least one signal so the y-axis auto-ranges to something.
    window_seconds
        Rolling-window width. Older samples are dropped from the
        display only — the underlying ring buffer keeps its own
        capacity-bound history.
    update_hz
        Redraw rate. 60 Hz is the sweet spot for "feels live"
        without burning the GUI thread.
    """

    # Emitted when the user clicks the in-widget Stop button. Connect
    # this in the host window to call ``stream.stop()`` + tear down
    # the worker thread.
    stop_requested = Signal()

    def __init__(
        self,
        stream: Any,
        signals: list[LiveSignalSpec] | None = None,
        *,
        window_seconds: float = 2.0,
        update_hz: float = 60.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._stream = stream
        self._window_seconds = float(window_seconds)
        self._update_interval_ms = max(10, int(1000.0 / float(update_hz)))

        # Preallocated numpy ring buffers per signal — same approach
        # the kernel's LiveScope uses. 300k samples × 8 B × N_signals
        # ≈ a few MB for any realistic GUI scenario.
        self._max_points = 300_000
        self._sig_specs: list[LiveSignalSpec] = []
        self._ring_t: dict[str, np.ndarray] = {}
        self._ring_y: dict[str, np.ndarray] = {}
        self._ring_n: dict[str, int] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}

        self._paused = False
        self._finalised = False
        self._sample_count = 0
        self._dropped = 0

        self._build_ui()
        for spec in signals or []:
            self.add_signal(spec)

        self._timer = QTimer(self)
        self._timer.setInterval(self._update_interval_ms)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # UI scaffolding
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        pg.setConfigOptions(
            antialias=True, background=_BG_COLOR, foreground=_TEXT_COLOR,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Plot — single panel for now. Multi-panel can come later
        # without breaking the public API (we'd swap PlotWidget for
        # GraphicsLayoutWidget and route signals by panel-name).
        self._plot = pg.PlotWidget()
        self._plot.setBackground(_BG_COLOR)
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.getAxis("left").setPen(_GRID_COLOR)
        self._plot.getAxis("bottom").setPen(_GRID_COLOR)
        self._plot.getAxis("left").setTextPen(_TEXT_COLOR)
        self._plot.getAxis("bottom").setTextPen(_TEXT_COLOR)
        self._plot.setLabel("bottom", "t", units="s")
        self._plot.setLabel("left", "value")
        # Auto-downsample so a million ring samples don't try to
        # rasterize a million line segments per redraw.
        self._plot.setDownsampling(auto=True, mode="peak")
        self._plot.setClipToView(True)
        # Sliding-window x-range gets enforced inside _tick so the
        # user sees the latest ``window_seconds`` of activity even
        # when the simulation runs much longer.
        self._plot.addLegend(offset=(8, 8))
        root.addWidget(self._plot, stretch=1)

        # Status row — sample count, dropped frames, FPS-ish.
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

        root.addLayout(status_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_signal(self, spec: LiveSignalSpec) -> None:
        """Register a curve. Safe to call before or after
        :meth:`start`; the curve appears on the next ``_tick``."""
        if spec.name in self._curves:
            _LOG.debug("LiveScopeWidget: signal %r already registered", spec.name)
            return
        self._sig_specs.append(spec)
        self._ring_t[spec.name] = np.empty(self._max_points, dtype=np.float64)
        self._ring_y[spec.name] = np.empty(self._max_points, dtype=np.float64)
        self._ring_n[spec.name] = 0
        pen = pg.mkPen(color=spec.color, width=1.8)
        self._curves[spec.name] = self._plot.plot(
            pen=pen, name=spec.name,
        )

    def start(self) -> None:
        """Begin polling the stream. Idempotent — calling twice has
        no extra effect."""
        if not self._timer.isActive():
            self._timer.start()

    def stop_polling(self) -> None:
        """Stop the redraw timer. Does NOT signal the kernel to stop
        producing samples — use :meth:`request_kernel_stop` for that."""
        self._timer.stop()

    def request_kernel_stop(self) -> None:
        """Ask the kernel to halt the simulation at the next step
        boundary. The underlying ``NativeLiveStream.stop()`` flips an
        atomic flag that the C++ ``run_transient_with_chain`` polls."""
        if self._stream is None:
            return
        stop = getattr(self._stream, "stop", None)
        if callable(stop):
            stop()

    def clear(self) -> None:
        """Drop all sample history and reset the curves."""
        for name in self._ring_n:
            self._ring_n[name] = 0
        for curve in self._curves.values():
            curve.clear()
        self._sample_count = 0
        self._dropped = 0
        self._update_status()

    def finalize(self, t_full: np.ndarray, x_full: np.ndarray) -> None:
        """Replace the streaming buffer with the full-resolution
        simulation result. Called by the host when the run completes
        so the scope shows the entire sweep, not just the last
        ``window_seconds``.

        Parameters
        ----------
        t_full
            1-D array of timestamps (seconds), shape ``(N,)``.
        x_full
            2-D state matrix, shape ``(N, state_dim)``. Columns are
            indexed by ``LiveSignalSpec.state_idx``.
        """
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
        # Reset to full x-range so the user sees the whole sweep.
        self._plot.setXRange(float(t_full[0]), float(t_full[-1]), padding=0.02)
        self._plot.enableAutoRange(axis="y")
        self._finalised = True
        self._update_status(extra=f" — finalised ({t_full.size} pts)")

    # ------------------------------------------------------------------
    # QTimer tick — the hot path
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self._stream is None or self._paused or self._finalised:
            return
        samples = self._stream.get_new_samples()
        if samples is None:
            self._update_status()
            return
        t_new, x_new = samples
        if t_new.size == 0:
            return
        # Append to per-signal ring; trim with a memmove when we'd
        # overflow the preallocated buffer.
        for spec in self._sig_specs:
            if spec.state_idx >= x_new.shape[1]:
                continue
            t_ring = self._ring_t[spec.name]
            y_ring = self._ring_y[spec.name]
            n = self._ring_n[spec.name]
            n_new = t_new.size
            if n + n_new > self._max_points:
                # Slide the oldest half out — keeps ``setData`` cheap
                # while still showing plenty of context.
                keep = self._max_points // 2
                t_ring[:keep] = t_ring[n - keep:n]
                y_ring[:keep] = y_ring[n - keep:n]
                n = keep
            end = n + n_new
            t_ring[n:end] = t_new
            y_ring[n:end] = x_new[:, spec.state_idx]
            self._ring_n[spec.name] = end
        # Single setData per curve — pyqtgraph batches the upload.
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
        self._plot.setXRange(x_min, latest_t, padding=0.02)
        self._sample_count += int(t_new.size)
        # Pull dropped-sample stat if the stream tracks it.
        dropped = getattr(self._stream, "_dropped_samples", None)
        if isinstance(dropped, int):
            self._dropped = dropped
        self._update_status()

    # ------------------------------------------------------------------
    # Helpers
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
        self._status_label.setText(
            f"samples={self._sample_count}{drop_part}{extra}",
        )


__all__ = ["LiveScopeWidget", "LiveSignalSpec"]
