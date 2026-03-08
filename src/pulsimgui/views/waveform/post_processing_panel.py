"""Post-processing panel for waveform analysis jobs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pulsimgui.services.backend_types import PostProcessingResult
from pulsimgui.views.widgets import StatusBanner


class PostProcessingPanel(QFrame):
    """Sidebar panel for running backend-owned waveform post-processing jobs."""

    run_requested = Signal(object)  # list[dict]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PostProcessingPanel")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Post-Processing")
        title.setObjectName("postProcessingTitle")
        layout.addWidget(title)

        self._status = StatusBanner.info("Select signals and run analysis.")
        layout.addWidget(self._status)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self._job_kind_combo = QComboBox()
        self._job_kind_combo.addItem("Time domain", "time_domain")
        self._job_kind_combo.addItem("Spectral", "spectral")
        self._job_kind_combo.addItem("Power efficiency", "power_efficiency")
        self._job_kind_combo.currentIndexChanged.connect(self._on_job_kind_changed)
        form.addRow("Job type:", self._job_kind_combo)

        self._fundamental_spin = QDoubleSpinBox()
        self._fundamental_spin.setRange(0.0, 1e9)
        self._fundamental_spin.setDecimals(3)
        self._fundamental_spin.setSuffix(" Hz")
        self._fundamental_spin.setToolTip("Optional fundamental frequency for spectral jobs.")
        form.addRow("Fundamental:", self._fundamental_spin)

        layout.addLayout(form)

        self._signals_list = QListWidget()
        self._signals_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._signals_list.setToolTip("Select one or more signals.")
        layout.addWidget(self._signals_list, 1)

        actions = QHBoxLayout()
        self._run_button = QPushButton("Run Analysis")
        self._run_button.clicked.connect(self._on_run_clicked)
        actions.addWidget(self._run_button)

        self._clear_button = QPushButton("Clear")
        self._clear_button.clicked.connect(self._clear_results)
        actions.addWidget(self._clear_button)
        actions.addStretch()
        layout.addLayout(actions)

        self._summary = QLabel("No results yet.")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._results_table = QTableWidget()
        self._results_table.setColumnCount(4)
        self._results_table.setHorizontalHeaderLabels(["Metric", "Value", "Unit", "Source"])
        self._results_table.verticalHeader().setVisible(False)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._results_table, 2)

        self._on_job_kind_changed()
        self.set_available_signals([])

    def _on_job_kind_changed(self) -> None:
        kind = str(self._job_kind_combo.currentData() or "time_domain")
        self._fundamental_spin.setEnabled(kind == "spectral")

    def set_available_signals(self, signal_names: list[str]) -> None:
        """Populate selectable signals from the current waveform result."""
        self._signals_list.clear()
        for name in signal_names:
            self._signals_list.addItem(QListWidgetItem(str(name)))
        has_signals = bool(signal_names)
        self._run_button.setEnabled(has_signals)
        if not has_signals:
            self._status.setStatusType(StatusBanner.WARNING)
            self._status.setText("Run a transient simulation first to enable post-processing.")
        else:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Select signals and run analysis.")

    def set_running(self, running: bool) -> None:
        """Toggle panel busy state while backend analysis is running."""
        self._run_button.setEnabled(not running and self._signals_list.count() > 0)
        if running:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Running post-processing in background...")

    def show_result(self, result: PostProcessingResult) -> None:
        """Render the first job result in a compact table view."""
        self.set_running(False)
        self._clear_results(keep_status=True)

        if not result.jobs:
            self._status.setStatusType(StatusBanner.WARNING)
            self._status.setText("No post-processing jobs returned by backend.")
            self._summary.setText("No job data returned.")
            return

        job = result.jobs[0]
        if not job.success:
            message = job.diagnostic_message or job.diagnostic or "Job failed"
            self._status.setStatusType(StatusBanner.ERROR)
            self._status.setText(message)
        else:
            self._status.setStatusType(StatusBanner.SUCCESS)
            self._status.setText("Post-processing completed.")

        summary_parts: list[str] = [f"Job: {job.job_id or '(unnamed)'}", f"Kind: {job.kind}"]
        if job.sample_count > 0:
            summary_parts.append(f"Samples: {job.sample_count}")
        self._summary.setText(" | ".join(summary_parts))

        rows: list[tuple[str, str, str, str]] = []
        for metric in job.scalar_metrics.values():
            rows.append(
                (
                    metric.name,
                    f"{metric.value:.6g}",
                    metric.unit,
                    metric.source_signal or metric.signal_name,
                )
            )

        if job.thd_pct is not None:
            rows.append(("thd_pct", f"{job.thd_pct:.6g}", "%", "spectral"))
        if job.fundamental_hz is not None:
            rows.append(("fundamental_hz", f"{job.fundamental_hz:.6g}", "Hz", "spectral"))
        if job.average_input_power is not None:
            rows.append(("avg_input_power", f"{job.average_input_power:.6g}", "W", "power"))
        if job.average_output_power is not None:
            rows.append(("avg_output_power", f"{job.average_output_power:.6g}", "W", "power"))
        if job.efficiency is not None:
            rows.append(("efficiency", f"{job.efficiency:.6g}", "", "power"))
        if job.power_factor is not None:
            rows.append(("power_factor", f"{job.power_factor:.6g}", "", "power"))

        for item in job.undefined_metrics:
            rows.append((item.name, "undefined", "", item.reason))

        self._results_table.setRowCount(len(rows))
        for row, (name, value, unit, source) in enumerate(rows):
            self._results_table.setItem(row, 0, QTableWidgetItem(name))
            self._results_table.setItem(row, 1, QTableWidgetItem(value))
            self._results_table.setItem(row, 2, QTableWidgetItem(unit))
            self._results_table.setItem(row, 3, QTableWidgetItem(source))

    def show_error(self, message: str) -> None:
        """Display a top-level post-processing failure."""
        self.set_running(False)
        self._status.setStatusType(StatusBanner.ERROR)
        self._status.setText(message or "Post-processing failed.")

    def _clear_results(self, *, keep_status: bool = False) -> None:
        self._results_table.clearContents()
        self._results_table.setRowCount(0)
        self._summary.setText("No results yet.")
        if not keep_status and self._signals_list.count() > 0:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Select signals and run analysis.")

    def _selected_signals(self) -> list[str]:
        return [item.text() for item in self._signals_list.selectedItems()]

    def _on_run_clicked(self) -> None:
        selected_signals = self._selected_signals()
        kind = str(self._job_kind_combo.currentData() or "time_domain")

        if not selected_signals:
            self._status.setStatusType(StatusBanner.WARNING)
            self._status.setText("Select at least one signal.")
            return

        job: dict[str, Any] = {
            "job_id": f"{kind}_job",
            "kind": kind,
            "signals": selected_signals,
        }

        if kind == "spectral" and self._fundamental_spin.value() > 0.0:
            job["fundamental_hz"] = float(self._fundamental_spin.value())

        if kind == "power_efficiency":
            if len(selected_signals) < 4:
                self._status.setStatusType(StatusBanner.WARNING)
                self._status.setText(
                    "Power efficiency requires 4 signals: Vin, Iin, Vout, Iout."
                )
                return
            job["input_voltage"] = selected_signals[0]
            job["input_current"] = selected_signals[1]
            job["output_voltage"] = selected_signals[2]
            job["output_current"] = selected_signals[3]

        self.set_running(True)
        self.run_requested.emit([job])
