"""Run Bar — primary simulation-control band shown above the status bar.

Surfaces the four states a power-electronics simulation can be in:

  idle       → Run / Pause / Stop button group, progress hidden.
  running    → progress bar animates, elapsed-time counter ticks,
               realtime factor (t_sim / t_wall) shown.
  completed  → progress at 100 %, "Completed in N.Ns" message.
  failed     → progress freezes at last value, red accent, error
               message shown inline.

The Run Bar binds to the application's ``SimulationService`` so the UI
layer doesn't need to manage simulation state directly — wire the
service's ``state_changed`` / ``progress`` / ``simulation_finished`` /
``error`` signals into the corresponding ``on_*`` slots once at
construction time.
"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
)


class RunBar(QFrame):
    """Floating control band: Run / Pause / Stop + progress + RT factor."""

    # Public signals the host (MainWindow) wires into the simulation service.
    run_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()

    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_COMPLETED = "completed"
    STATE_FAILED = "failed"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RunBar")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self._state = self.STATE_IDLE
        self._start_wall_time: float | None = None
        self._last_sim_time: float = 0.0
        self._last_progress_pct: float = 0.0
        self._t_stop: float = 0.0

        self._setup_ui()
        self._apply_state(self.STATE_IDLE)

        # The realtime-factor readout updates on a short timer so the
        # number stays alive even if the runtime publishes progress
        # rarely (e.g. switching-event-heavy frames between ticks).
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)  # 10 Hz
        self._tick_timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self._run_button = self._make_action_button("▶  Run", "run")
        self._pause_button = self._make_action_button("⏸  Pause", "pause")
        self._stop_button = self._make_action_button("■  Stop", "stop")

        self._run_button.clicked.connect(self.run_requested)
        self._pause_button.clicked.connect(self.pause_requested)
        self._stop_button.clicked.connect(self.stop_requested)

        layout.addWidget(self._run_button)
        layout.addWidget(self._pause_button)
        layout.addWidget(self._stop_button)

        self._progress = QProgressBar()
        self._progress.setObjectName("RunBarProgress")
        self._progress.setRange(0, 1000)  # 0.1% resolution for smooth fills
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Fixed)
        layout.addWidget(self._progress, 1)

        self._time_label = QLabel("0.000 s")
        self._time_label.setObjectName("RunBarTime")
        time_font = QFont()
        time_font.setFamily("Menlo, Consolas, monospace")
        time_font.setPointSize(10)
        self._time_label.setFont(time_font)
        self._time_label.setMinimumWidth(110)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignVCenter
                                      | Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._time_label)

        self._rt_label = QLabel("—")
        self._rt_label.setObjectName("RunBarRT")
        self._rt_label.setFont(time_font)
        self._rt_label.setMinimumWidth(64)
        self._rt_label.setAlignment(Qt.AlignmentFlag.AlignVCenter
                                    | Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._rt_label)

        self._status_label = QLabel("Idle")
        self._status_label.setObjectName("RunBarStatus")
        self._status_label.setMinimumWidth(120)
        layout.addWidget(self._status_label)

    def _make_action_button(self, text: str, name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(f"RunBarBtn_{name}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.setMinimumHeight(28)
        return btn

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def state(self) -> str:
        return self._state

    def set_running(self, t_stop: float | None = None) -> None:
        """Switch to the running state. Should be called when the
        simulation service emits its ``simulation_started`` signal.
        """
        self._t_stop = float(t_stop or 0.0)
        self._start_wall_time = time.perf_counter()
        self._last_sim_time = 0.0
        self._last_progress_pct = 0.0
        self._apply_state(self.STATE_RUNNING)
        self._progress.setValue(0)
        self._tick_timer.start()

    def set_progress(self, percent: float, message: str = "") -> None:
        """Update the progress bar and elapsed-time label.

        ``percent`` is in the range 0..100; ``message`` is passed
        through to the trailing status label so the host can surface
        e.g. ``"Newton (3 iter)"`` or ``"Initial DC OP"``.
        """
        percent = max(0.0, min(100.0, float(percent)))
        self._last_progress_pct = percent
        self._progress.setValue(int(percent * 10))
        if self._t_stop > 0.0:
            self._last_sim_time = (percent / 100.0) * self._t_stop
            self._time_label.setText(self._format_time(self._last_sim_time))
        if message:
            self._status_label.setText(message)

    def set_completed(self) -> None:
        """Switch to the completed state (final ``simulation_finished``)."""
        self._progress.setValue(self._progress.maximum())
        self._apply_state(self.STATE_COMPLETED)
        wall = self._wall_elapsed()
        if wall > 0:
            self._status_label.setText(f"Completed in {self._format_time(wall)}")
        self._tick_timer.stop()

    def set_failed(self, message: str = "") -> None:
        """Switch to the failed state. ``message`` is the failure reason."""
        self._apply_state(self.STATE_FAILED)
        if message:
            self._status_label.setText(f"Failed: {message}")
        else:
            self._status_label.setText("Failed")
        self._tick_timer.stop()

    def reset_to_idle(self) -> None:
        """Clear progress + readouts and return to the idle state."""
        self._progress.setValue(0)
        self._time_label.setText("0.000 s")
        self._rt_label.setText("—")
        self._status_label.setText("Idle")
        self._start_wall_time = None
        self._last_sim_time = 0.0
        self._last_progress_pct = 0.0
        self._t_stop = 0.0
        self._apply_state(self.STATE_IDLE)
        self._tick_timer.stop()

    # ------------------------------------------------------------------
    # Slots / callbacks
    # ------------------------------------------------------------------

    def on_state_changed(self, sim_state) -> None:
        """Slot for ``SimulationService.state_changed``.

        Accepts whatever enum/value the service ships; we only inspect
        the lowercase string form so the import direction stays one-way.
        """
        token = str(getattr(sim_state, "value", sim_state)).lower()
        if "run" in token:
            self.set_running()
        elif "paus" in token:
            self._apply_state(self.STATE_PAUSED)
        elif "idle" in token or "ready" in token:
            self.reset_to_idle()
        elif "stopped" in token or "complete" in token:
            self.set_completed()
        elif "fail" in token or "error" in token:
            self.set_failed()

    def on_progress(self, percent: float, message: str = "") -> None:
        """Slot for ``SimulationService.progress(float, str)``."""
        if self._state == self.STATE_IDLE:
            # The service emits its first progress tick before the
            # state_changed → running transition propagates. Auto-promote
            # so the user sees motion immediately.
            self.set_running()
        self.set_progress(percent, message)

    def on_finished(self, result) -> None:
        """Slot for ``SimulationService.simulation_finished(result)``."""
        if getattr(result, "is_valid", False):
            self.set_completed()
        else:
            self.set_failed(str(getattr(result, "error_message", "")
                                or "convergence failed"))

    def on_error(self, message: str) -> None:
        """Slot for ``SimulationService.error(message)``."""
        self.set_failed(message)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_tick(self) -> None:
        if self._state != self.STATE_RUNNING:
            return
        wall = self._wall_elapsed()
        if wall <= 0:
            self._rt_label.setText("—")
            return
        if self._last_sim_time <= 0:
            self._rt_label.setText("…")
            return
        factor = self._last_sim_time / wall
        # Format defensively: very fast runs can blow past 10×.
        if factor >= 100:
            self._rt_label.setText(f"{factor:.0f}×")
        elif factor >= 10:
            self._rt_label.setText(f"{factor:.1f}×")
        else:
            self._rt_label.setText(f"{factor:.2f}×")

    def _wall_elapsed(self) -> float:
        if self._start_wall_time is None:
            return 0.0
        return time.perf_counter() - self._start_wall_time

    def _apply_state(self, state: str) -> None:
        self._state = state
        # Toggle button enablement so users can't fire conflicting
        # commands at the service.
        is_running = state == self.STATE_RUNNING
        is_paused = state == self.STATE_PAUSED
        self._run_button.setEnabled(not is_running)
        self._pause_button.setEnabled(is_running or is_paused)
        self._stop_button.setEnabled(is_running or is_paused)
        self._progress.setVisible(state != self.STATE_IDLE)
        self._time_label.setVisible(state != self.STATE_IDLE)
        self._rt_label.setVisible(state != self.STATE_IDLE)
        self._refresh_style()

    def _refresh_style(self) -> None:
        accents = {
            self.STATE_IDLE: "rgba(107, 114, 128, 0.45)",
            self.STATE_RUNNING: "rgba(59, 130, 246, 0.90)",
            self.STATE_PAUSED: "rgba(245, 158, 11, 0.85)",
            self.STATE_COMPLETED: "rgba(34, 197, 94, 0.95)",
            self.STATE_FAILED: "rgba(239, 68, 68, 0.95)",
        }
        accent = accents[self._state]
        # The primary-action button picks up a semantic tint while the
        # secondary buttons stay muted. This makes the user's eye land
        # on the right action without forcing them to read three button
        # labels every time the state changes.
        is_idle = self._state == self.STATE_IDLE
        is_running = self._state == self.STATE_RUNNING
        is_paused = self._state == self.STATE_PAUSED
        is_completed = self._state == self.STATE_COMPLETED

        run_bg = "rgba(34, 197, 94, 0.20)" if (is_idle or is_completed) else "transparent"
        run_fg = "#16a34a" if (is_idle or is_completed) else "rgba(120,120,120,0.55)"
        pause_fg = "#1d4ed8" if is_running else "rgba(120,120,120,0.45)"
        stop_fg = "#b91c1c" if (is_running or is_paused) else "rgba(120,120,120,0.45)"

        self.setStyleSheet(
            "#RunBar { background: transparent; }"
            f"#RunBarProgress::chunk {{ background: {accent}; border-radius: 4px; }}"
            "#RunBarProgress { background: rgba(107, 114, 128, 0.18); "
            "border: 0px; border-radius: 4px; }"
            "#RunBarBtn_run, #RunBarBtn_pause, #RunBarBtn_stop {"
            "  padding: 4px 14px; border-radius: 6px; font-weight: 600;"
            "}"
            f"#RunBarBtn_run {{ background: {run_bg}; color: {run_fg}; }}"
            "#RunBarBtn_run:hover:enabled { background: rgba(34, 197, 94, 0.30); }"
            f"#RunBarBtn_pause {{ color: {pause_fg}; }}"
            "#RunBarBtn_pause:hover:enabled { background: rgba(59, 130, 246, 0.18); }"
            f"#RunBarBtn_stop {{ color: {stop_fg}; }}"
            "#RunBarBtn_stop:hover:enabled { background: rgba(220, 38, 38, 0.18); }"
            "#RunBarBtn_run:disabled, #RunBarBtn_pause:disabled, #RunBarBtn_stop:disabled {"
            "  color: rgba(120,120,120,0.35); background: transparent;"
            "}"
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds >= 1.0:
            return f"{seconds:.3f} s"
        if seconds >= 1e-3:
            return f"{seconds * 1e3:.3f} ms"
        if seconds >= 1e-6:
            return f"{seconds * 1e6:.3f} µs"
        return f"{seconds * 1e9:.3f} ns"


# ---------------------------------------------------------------------------
# Convenience wiring
# ---------------------------------------------------------------------------


def wire_run_bar_to_service(
    bar: RunBar,
    service,
    *,
    run_callback: Callable[[], None] | None = None,
    pause_callback: Callable[[], None] | None = None,
    stop_callback: Callable[[], None] | None = None,
) -> None:
    """Connect a :class:`RunBar` to an existing ``SimulationService`` instance.

    The host MainWindow calls this once at startup. It connects the bar's
    request signals to the supplied callbacks (which typically forward to
    the host's own action handlers so the run/pause/stop logic stays
    centralised) and binds the service's lifecycle signals back into the
    bar.
    """
    if run_callback is not None:
        bar.run_requested.connect(run_callback)
    if pause_callback is not None:
        bar.pause_requested.connect(pause_callback)
    if stop_callback is not None:
        bar.stop_requested.connect(stop_callback)

    if hasattr(service, "progress"):
        service.progress.connect(bar.on_progress)
    if hasattr(service, "state_changed"):
        service.state_changed.connect(bar.on_state_changed)
    if hasattr(service, "simulation_finished"):
        service.simulation_finished.connect(bar.on_finished)
    if hasattr(service, "error"):
        service.error.connect(bar.on_error)


__all__ = ["RunBar", "wire_run_bar_to_service"]
