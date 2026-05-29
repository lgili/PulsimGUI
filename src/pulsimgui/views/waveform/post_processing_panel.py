"""Post-processing panel for waveform analysis jobs."""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.backend_types import PostProcessingResult
from pulsimgui.services.theme_service import LIGHT_THEME, Theme
from pulsimgui.views.widgets import StatusBanner


class PostProcessingPanel(QFrame):
    """Sidebar panel for running backend-owned waveform post-processing jobs."""

    run_requested = Signal(object)  # list[dict]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PostProcessingPanel")
        self._capability_enabled = True
        self._theme: Theme = LIGHT_THEME
        self._setup_ui()
        self.apply_theme(self._theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Analysis & Measurements")
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

        self._window_mode_combo = QComboBox()
        self._window_mode_combo.addItem("Time", "time")
        self._window_mode_combo.addItem("Index", "index")
        self._window_mode_combo.addItem("Cycle", "cycle")
        self._window_mode_combo.currentIndexChanged.connect(self._on_window_mode_changed)
        form.addRow("Window mode:", self._window_mode_combo)
        layout.addLayout(form)

        self._window_stack = QStackedWidget()
        self._window_stack.addWidget(self._build_time_window_page())
        self._window_stack.addWidget(self._build_index_window_page())
        self._window_stack.addWidget(self._build_cycle_window_page())
        layout.addWidget(self._window_stack)

        self._signals_list = QListWidget()
        self._signals_list.setToolTip("Check one or more signals.")
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

        self._results_stack = QStackedWidget()
        self._results_stack.addWidget(self._build_time_result_page())
        self._results_stack.addWidget(self._build_spectral_result_page())
        self._results_stack.addWidget(self._build_power_result_page())
        self._results_stack.setVisible(False)
        layout.addWidget(self._results_stack, 2)

        self._on_job_kind_changed()
        self._on_window_mode_changed()
        self.set_available_signals([])

    def _build_time_window_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        self._time_start_spin = QDoubleSpinBox()
        self._time_start_spin.setRange(0.0, 1e12)
        self._time_start_spin.setDecimals(9)
        self._time_start_spin.setSuffix(" s")
        form.addRow("Start:", self._time_start_spin)
        self._time_stop_spin = QDoubleSpinBox()
        self._time_stop_spin.setRange(0.0, 1e12)
        self._time_stop_spin.setDecimals(9)
        self._time_stop_spin.setSuffix(" s")
        form.addRow("Stop:", self._time_stop_spin)
        return page

    def _build_index_window_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        self._index_start_spin = QSpinBox()
        self._index_start_spin.setRange(0, 10_000_000)
        form.addRow("Start:", self._index_start_spin)
        self._index_stop_spin = QSpinBox()
        self._index_stop_spin.setRange(0, 10_000_000)
        form.addRow("Stop:", self._index_stop_spin)
        return page

    def _build_cycle_window_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        self._cycle_start_spin = QSpinBox()
        self._cycle_start_spin.setRange(0, 1_000_000)
        form.addRow("Start cycle:", self._cycle_start_spin)
        self._cycle_stop_spin = QSpinBox()
        self._cycle_stop_spin.setRange(0, 1_000_000)
        form.addRow("Stop cycle:", self._cycle_stop_spin)
        return page

    def _build_time_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._time_results_table = QTableWidget()
        self._time_results_table.setColumnCount(4)
        self._time_results_table.setHorizontalHeaderLabels(["Metric", "Value", "Unit", "Signal"])
        self._time_results_table.verticalHeader().setVisible(False)
        self._time_results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._time_results_table.setSortingEnabled(True)
        layout.addWidget(self._time_results_table)
        return page

    def _build_spectral_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._spectral_summary_label = QLabel("THD: -- | Fundamental: --")
        layout.addWidget(self._spectral_summary_label)

        self._spectral_plot = pg.PlotWidget()
        self._spectral_plot.setObjectName("postProcessingSpectralPlot")
        self._spectral_plot.setLabel("left", "Amplitude")
        self._spectral_plot.setLabel("bottom", "Frequency", units="Hz")
        self._spectral_plot.showGrid(x=True, y=True, alpha=0.25)
        layout.addWidget(self._spectral_plot, 1)
        return page

    def apply_theme(self, theme: Theme) -> None:
        """Apply the active application theme to the analysis panel."""
        self._theme = theme
        c = theme.colors
        self._status.apply_theme(theme)

        self.setStyleSheet(f"""
            QFrame#PostProcessingPanel {{
                background-color: {c.panel_background};
                border: 1px solid {c.panel_border};
                border-radius: 10px;
            }}
            QLabel#postProcessingTitle {{
                color: {c.foreground};
                font-size: 12px;
                font-weight: 700;
            }}
            QFrame#PostProcessingPanel QLabel {{
                color: {c.foreground};
            }}
            QFrame#PostProcessingPanel QComboBox,
            QFrame#PostProcessingPanel QDoubleSpinBox,
            QFrame#PostProcessingPanel QSpinBox,
            QFrame#PostProcessingPanel QPushButton {{
                background-color: {c.input_background};
                color: {c.foreground};
                border: 1px solid {c.input_border};
                border-radius: 7px;
                padding: 4px 8px;
                min-height: 24px;
            }}
            QFrame#PostProcessingPanel QComboBox:hover,
            QFrame#PostProcessingPanel QDoubleSpinBox:hover,
            QFrame#PostProcessingPanel QSpinBox:hover,
            QFrame#PostProcessingPanel QPushButton:hover {{
                border-color: {c.input_focus_border};
            }}
            QFrame#PostProcessingPanel QListWidget,
            QFrame#PostProcessingPanel QTableWidget {{
                background-color: {c.background};
                alternate-background-color: {c.panel_background};
                color: {c.foreground};
                border: 1px solid {c.panel_border};
                border-radius: 8px;
                gridline-color: {c.divider};
            }}
            QFrame#PostProcessingPanel QListWidget::item:selected,
            QFrame#PostProcessingPanel QTableWidget::item:selected {{
                background-color: {c.tree_item_selected};
                color: {c.foreground};
            }}
            QFrame#PostProcessingPanel QListWidget::item:hover,
            QFrame#PostProcessingPanel QTableWidget::item:hover {{
                background-color: {c.tree_item_hover};
            }}
            QFrame#PostProcessingPanel QHeaderView::section {{
                background-color: {c.panel_header};
                color: {c.foreground_muted};
                border: none;
                border-right: 1px solid {c.divider};
                border-bottom: 1px solid {c.divider};
                padding: 4px 6px;
                font-weight: 600;
            }}
            QFrame#PostProcessingPanel QComboBox QAbstractItemView {{
                background-color: {c.menu_background};
                color: {c.foreground};
                border: 1px solid {c.panel_border};
                selection-background-color: {c.menu_hover};
                selection-color: {c.foreground};
            }}
        """)

        plot_bg = c.plot_background
        self._spectral_plot.setBackground(plot_bg)
        self._spectral_plot.showGrid(x=True, y=True, alpha=0.18 if theme.is_dark else 0.28)
        plot_item = self._spectral_plot.getPlotItem()
        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen(c.plot_axis))
            axis.setTickPen(pg.mkPen(c.plot_axis))
            axis.setTextPen(pg.mkPen(c.plot_text))

    def _build_power_result_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self._power_pin_label = QLabel("--")
        self._power_pout_label = QLabel("--")
        self._power_eff_label = QLabel("--")
        self._power_pf_label = QLabel("--")
        form.addRow("P_in (W):", self._power_pin_label)
        form.addRow("P_out (W):", self._power_pout_label)
        form.addRow("Efficiency (%):", self._power_eff_label)
        form.addRow("Power factor:", self._power_pf_label)
        return page

    def _on_job_kind_changed(self) -> None:
        kind = str(self._job_kind_combo.currentData() or "time_domain")
        self._fundamental_spin.setEnabled(kind == "spectral")

    def _on_window_mode_changed(self) -> None:
        mode = str(self._window_mode_combo.currentData() or "time")
        page_index = {"time": 0, "index": 1, "cycle": 2}.get(mode, 0)
        self._window_stack.setCurrentIndex(page_index)

    def set_capability_enabled(self, enabled: bool, reason: str = "") -> None:
        """Enable/disable post-processing interactions by backend capability."""
        self._capability_enabled = bool(enabled)
        interactive_widgets: list[QWidget] = [
            self._job_kind_combo,
            self._fundamental_spin,
            self._window_mode_combo,
            self._window_stack,
            self._signals_list,
            self._run_button,
        ]
        for widget in interactive_widgets:
            widget.setEnabled(self._capability_enabled)
            widget.setToolTip("" if self._capability_enabled else reason)

        if not self._capability_enabled:
            self._status.setStatusType(StatusBanner.WARNING)
            self._status.setText(reason or "Post-processing backend capability unavailable.")
        elif self._signals_list.count() == 0:
            self._status.setStatusType(StatusBanner.WARNING)
            self._status.setText("Run a transient simulation first to enable post-processing.")
        else:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Select signals and run analysis.")

    def set_available_signals(self, signal_names: list[str]) -> None:
        """Populate selectable signals from the current waveform result."""
        self._signals_list.clear()
        for name in signal_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._signals_list.addItem(item)
        has_signals = bool(signal_names)
        self._run_button.setEnabled(self._capability_enabled and has_signals)
        if not has_signals:
            self._status.setStatusType(StatusBanner.WARNING)
            self._status.setText("Run a transient simulation first to enable post-processing.")
        elif self._capability_enabled:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Select signals and run analysis.")

    def set_running(self, running: bool) -> None:
        """Toggle panel busy state while backend analysis is running."""
        self._run_button.setEnabled(
            self._capability_enabled and not running and self._signals_list.count() > 0
        )
        if running:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Running post-processing in background...")

    def show_result(self, result: PostProcessingResult) -> None:
        """Backward-compatible wrapper for rendering results."""
        self._on_result(result)

    def _on_result(self, result: PostProcessingResult) -> None:
        """Render the first job result in the matching results page."""
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
            self._results_stack.setVisible(False)
            return

        summary_parts: list[str] = [f"Job: {job.job_id or '(unnamed)'}", f"Kind: {job.kind}"]
        if job.sample_count > 0:
            summary_parts.append(f"Samples: {job.sample_count}")
        self._summary.setText(" | ".join(summary_parts))
        self._status.setStatusType(StatusBanner.SUCCESS)
        self._status.setText("Post-processing completed.")

        kind = str(job.kind or "").strip().lower()
        if kind == "spectral":
            self._render_spectral_result(job)
            self._results_stack.setCurrentIndex(1)
        elif kind == "power_efficiency":
            self._render_power_result(job)
            self._results_stack.setCurrentIndex(2)
        else:
            self._render_time_result(job)
            self._results_stack.setCurrentIndex(0)
        self._results_stack.setVisible(True)

    def show_error(self, message: str) -> None:
        """Display a top-level post-processing failure."""
        self._on_error(message)

    def _on_error(self, message: str) -> None:
        self.set_running(False)
        self._results_stack.setVisible(False)
        self._status.setStatusType(StatusBanner.ERROR)
        self._status.setText(message or "Post-processing failed.")

    def _render_time_result(self, job: Any) -> None:
        rows: list[tuple[str, str, str, str]] = []
        for metric in sorted(job.scalar_metrics.values(), key=lambda item: item.name.lower()):
            rows.append(
                (
                    metric.name,
                    f"{metric.value:.6g}",
                    metric.unit,
                    metric.source_signal or metric.signal_name,
                )
            )
        for item in job.undefined_metrics:
            rows.append((item.name, "undefined", "", item.reason))

        self._time_results_table.setSortingEnabled(False)
        self._time_results_table.setRowCount(len(rows))
        for row, (name, value, unit, source) in enumerate(rows):
            self._time_results_table.setItem(row, 0, QTableWidgetItem(name))
            self._time_results_table.setItem(row, 1, QTableWidgetItem(value))
            self._time_results_table.setItem(row, 2, QTableWidgetItem(unit))
            self._time_results_table.setItem(row, 3, QTableWidgetItem(source))
        self._time_results_table.setSortingEnabled(True)

    def _render_spectral_result(self, job: Any) -> None:
        thd_text = f"{job.thd_pct:.6g}%" if job.thd_pct is not None else "--"
        fund_text = f"{job.fundamental_hz:.6g} Hz" if job.fundamental_hz is not None else "--"
        self._spectral_summary_label.setText(f"THD: {thd_text} | Fundamental: {fund_text}")

        self._spectral_plot.clear()
        if job.harmonics:
            x_h = [entry.frequency_hz for entry in job.harmonics]
            y_h = [entry.amplitude for entry in job.harmonics]
            if x_h:
                if len(x_h) > 1:
                    width = max(min(x_h[index] - x_h[index - 1] for index in range(1, len(x_h))) * 0.5, 1e-9)
                else:
                    width = max(x_h[0] * 0.1, 1.0)
                bars = pg.BarGraphItem(x=x_h, height=y_h, width=width, brush=(80, 140, 220, 190))
                self._spectral_plot.addItem(bars)

        if job.spectrum_bins:
            x_b = [entry.frequency_hz for entry in job.spectrum_bins]
            y_b = [entry.amplitude for entry in job.spectrum_bins]
            self._spectral_plot.plot(
                x_b,
                y_b,
                pen=None,
                symbol="o",
                symbolSize=5,
                symbolBrush=(220, 120, 80, 210),
                symbolPen=None,
            )

    def _render_power_result(self, job: Any) -> None:
        self._power_pin_label.setText(
            f"{job.average_input_power:.6g}" if job.average_input_power is not None else "--"
        )
        self._power_pout_label.setText(
            f"{job.average_output_power:.6g}" if job.average_output_power is not None else "--"
        )
        if job.efficiency is not None:
            self._power_eff_label.setText(f"{job.efficiency * 100.0:.3f}")
        else:
            self._power_eff_label.setText("--")
        self._power_pf_label.setText(
            f"{job.power_factor:.6g}" if job.power_factor is not None else "--"
        )

    def _clear_results(self, *, keep_status: bool = False) -> None:
        self._time_results_table.clearContents()
        self._time_results_table.setRowCount(0)
        self._spectral_plot.clear()
        self._spectral_summary_label.setText("THD: -- | Fundamental: --")
        self._power_pin_label.setText("--")
        self._power_pout_label.setText("--")
        self._power_eff_label.setText("--")
        self._power_pf_label.setText("--")
        self._summary.setText("No results yet.")
        self._results_stack.setVisible(False)
        if not keep_status and self._signals_list.count() > 0 and self._capability_enabled:
            self._status.setStatusType(StatusBanner.INFO)
            self._status.setText("Select signals and run analysis.")

    def _selected_signals(self) -> list[str]:
        selected: list[str] = []
        for index in range(self._signals_list.count()):
            item = self._signals_list.item(index)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    def _window_payload(self) -> dict[str, Any]:
        mode = str(self._window_mode_combo.currentData() or "time")
        payload: dict[str, Any] = {"window_mode": mode}
        if mode == "time":
            start = float(self._time_start_spin.value())
            stop = float(self._time_stop_spin.value())
            if stop > start:
                payload["window_t_start"] = start
                payload["window_t_stop"] = stop
        elif mode == "index":
            start = int(self._index_start_spin.value())
            stop = int(self._index_stop_spin.value())
            if stop > start:
                payload["window_index_start"] = start
                payload["window_index_stop"] = stop
        else:
            start = int(self._cycle_start_spin.value())
            stop = int(self._cycle_stop_spin.value())
            if stop > start:
                payload["window_cycle_start"] = start
                payload["window_cycle_stop"] = stop
        return payload

    def _on_run_clicked(self) -> None:
        if not self._capability_enabled:
            return

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
        job.update(self._window_payload())

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
