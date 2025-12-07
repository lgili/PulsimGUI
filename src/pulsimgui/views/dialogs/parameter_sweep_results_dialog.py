"""Dialog for viewing parameter sweep results."""

import pyqtgraph as pg
from PySide6.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout, QWidget

from pulsimgui.services.simulation_service import ParameterSweepResult
from pulsimgui.views.waveform import WaveformViewer


class ParameterSweepResultsDialog(QDialog):
    """Displays waveform families and XY plots for sweeps."""

    def __init__(self, result: ParameterSweepResult, parent=None):
        super().__init__(parent)
        self._result = result

        self.setWindowTitle("Parameter Sweep Results")
        self.resize(900, 600)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        summary = QLabel(
            f"Component: {self._result.settings.component_name}\n"
            f"Parameter: {self._result.settings.parameter_name}\n"
            f"Output: {self._result.settings.output_signal}"
        )
        summary.setStyleSheet("font-weight: bold;")
        layout.addWidget(summary)

        tabs = QTabWidget()
        tabs.addTab(self._create_waveform_tab(), "Waveforms")
        tabs.addTab(self._create_xy_tab(), "Output vs Parameter")
        layout.addWidget(tabs)

    def _create_waveform_tab(self) -> QWidget:
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)
        viewer = WaveformViewer()
        viewer.set_result(self._result.to_waveform_result())
        tab_layout.addWidget(viewer)
        return widget

    def _create_xy_tab(self) -> QWidget:
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)

        plot = pg.PlotWidget()
        plot.setLabel("left", self._result.settings.output_signal)
        plot.setLabel("bottom", f"{self._result.settings.parameter_name}")
        plot.showGrid(x=True, y=True, alpha=0.3)

        xs, ys = self._result.xy_dataset()
        if xs and ys:
            plot.plot(xs, ys, pen=pg.mkPen(color=(31, 119, 180), width=2), symbol="o")

        tab_layout.addWidget(plot)
        return widget
