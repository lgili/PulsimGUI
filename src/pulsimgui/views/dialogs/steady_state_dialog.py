"""Steady-state check dialog — per-cycle residual table + verdict.

Post-processes the latest transient result: the user supplies the fundamental
frequency (pre-filled when the caller can infer it), the service slices the
run into cycles and reports whether the waveforms converged to a periodic
steady state — the question every multilevel/thermal run ends with.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pulsimgui.services.steady_state import analyze_steady_state


class SteadyStateDialog(QDialog):
    """Run the periodic steady-state check on a finished transient."""

    def __init__(self, times, signals: dict, parent=None,
                 *, default_frequency: float = 50.0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Steady-State Check")
        self.resize(560, 460)
        self._times = np.asarray(times, dtype=float)
        self._signals = dict(signals)
        self.last_report = None

        root = QVBoxLayout(self)

        form = QFormLayout()
        self._freq = QDoubleSpinBox()
        self._freq.setRange(1e-3, 1e9)
        self._freq.setDecimals(3)
        self._freq.setSuffix(" Hz")
        self._freq.setValue(max(default_frequency, 1e-3))
        form.addRow("Fundamental frequency", self._freq)

        self._tol = QDoubleSpinBox()
        self._tol.setRange(0.001, 100.0)
        self._tol.setDecimals(3)
        self._tol.setSuffix(" %")
        self._tol.setValue(1.0)
        form.addRow("Tolerance (cycle-to-cycle RMS)", self._tol)
        root.addLayout(form)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Check")
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._verdict = QLabel("—")
        self._verdict.setWordWrap(True)
        root.addWidget(self._verdict)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Cycle k vs k−1", "Residual %"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    # ── run ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        period = 1.0 / float(self._freq.value())
        report = analyze_steady_state(
            self._times, self._signals, period,
            tol_pct=float(self._tol.value()),
        )
        self.last_report = report

        self._table.setRowCount(len(report.residuals_pct))
        for k, r in enumerate(report.residuals_pct):
            self._table.setItem(k, 0, QTableWidgetItem(f"{k + 2} vs {k + 1}"))
            self._table.setItem(k, 1, QTableWidgetItem(f"{r:.4g}"))
        self._table.scrollToBottom()

        if report.n_cycles < 2:
            self._verdict.setText(
                "Not enough data: the run covers fewer than 2 fundamental "
                "periods. Increase t_stop or check the frequency.")
            return
        if report.converged:
            self._verdict.setText(
                f"✅ Steady state reached at cycle {report.converged_cycle} of "
                f"{report.n_cycles} (final residual "
                f"{report.final_residual_pct:.3g} % ≤ {report.tol_pct:g} %). "
                "The last cycle is representative — measure/export it.")
        else:
            self._verdict.setText(
                f"⚠️ NOT converged after {report.n_cycles} cycles: final "
                f"residual {report.final_residual_pct:.3g} % > "
                f"{report.tol_pct:g} % (worst signal: "
                f"{report.worst_signal or '—'}). The circuit is still "
                "drifting — run longer, or look for an uncontrolled state "
                "(e.g. capacitor energy) in that signal.")
