"""Bode plot dialog for AC analysis results."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QSplitter,
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
)

from pulsimgui.services.simulation_service import ACResult


class BodePlotDialog(QDialog):
    """Dialog for displaying Bode plots from AC analysis."""

    def __init__(self, result: ACResult, parent=None):
        super().__init__(parent)
        self._result = result

        self.setWindowTitle("AC Analysis - Bode Plot")
        self.setMinimumSize(900, 700)

        # Configure pyqtgraph for dark/light theme compatibility
        pg.setConfigOptions(antialias=True)

        self._setup_ui()
        self._populate_plots()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Status label
        if self._result.is_valid:
            status = QLabel(
                f"AC analysis completed: {len(self._result.frequencies)} frequency points"
            )
            status.setStyleSheet("color: green; font-weight: bold;")
        else:
            status = QLabel(f"Error: {self._result.error_message}")
            status.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(status)

        # Tab widget for plots and data
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Bode plot tab
        bode_widget = self._create_bode_tab()
        self._tabs.addTab(bode_widget, "Bode Plot")

        # Data table tab
        data_widget = self._create_data_tab()
        self._tabs.addTab(data_widget, "Data Table")

        # Controls and buttons
        controls_layout = QHBoxLayout()

        # Signal selector
        signal_group = QGroupBox("Signal")
        signal_layout = QHBoxLayout(signal_group)
        self._signal_combo = QComboBox()
        self._signal_combo.addItems(list(self._result.magnitude.keys()))
        self._signal_combo.currentTextChanged.connect(self._on_signal_changed)
        signal_layout.addWidget(self._signal_combo)
        controls_layout.addWidget(signal_group)

        # Display options
        options_group = QGroupBox("Display Options")
        options_layout = QHBoxLayout(options_group)

        self._show_magnitude = QCheckBox("Magnitude")
        self._show_magnitude.setChecked(True)
        self._show_magnitude.toggled.connect(self._update_plot_visibility)
        options_layout.addWidget(self._show_magnitude)

        self._show_phase = QCheckBox("Phase")
        self._show_phase.setChecked(True)
        self._show_phase.toggled.connect(self._update_plot_visibility)
        options_layout.addWidget(self._show_phase)

        self._show_grid = QCheckBox("Grid")
        self._show_grid.setChecked(True)
        self._show_grid.toggled.connect(self._toggle_grid)
        options_layout.addWidget(self._show_grid)

        controls_layout.addWidget(options_group)
        controls_layout.addStretch()

        # Export button
        export_btn = QPushButton("Export to CSV...")
        export_btn.clicked.connect(self._export_csv)
        controls_layout.addWidget(export_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        controls_layout.addWidget(close_btn)

        layout.addLayout(controls_layout)

    def _create_bode_tab(self) -> QWidget:
        """Create the Bode plot tab with magnitude and phase plots."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a splitter for magnitude and phase plots
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Magnitude plot (top)
        self._mag_plot = pg.PlotWidget()
        self._mag_plot.setLabel("left", "Magnitude", units="dB")
        self._mag_plot.setLabel("bottom", "Frequency", units="Hz")
        self._mag_plot.setLogMode(x=True, y=False)
        self._mag_plot.showGrid(x=True, y=True, alpha=0.3)
        self._mag_plot.setBackground("w")
        self._mag_plot.getAxis("left").setPen("k")
        self._mag_plot.getAxis("bottom").setPen("k")
        self._mag_plot.getAxis("left").setTextPen("k")
        self._mag_plot.getAxis("bottom").setTextPen("k")
        splitter.addWidget(self._mag_plot)

        # Phase plot (bottom)
        self._phase_plot = pg.PlotWidget()
        self._phase_plot.setLabel("left", "Phase", units="deg")
        self._phase_plot.setLabel("bottom", "Frequency", units="Hz")
        self._phase_plot.setLogMode(x=True, y=False)
        self._phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self._phase_plot.setBackground("w")
        self._phase_plot.getAxis("left").setPen("k")
        self._phase_plot.getAxis("bottom").setPen("k")
        self._phase_plot.getAxis("left").setTextPen("k")
        self._phase_plot.getAxis("bottom").setTextPen("k")
        splitter.addWidget(self._phase_plot)

        # Link X axes
        self._phase_plot.setXLink(self._mag_plot)

        layout.addWidget(splitter)
        return widget

    def _create_data_tab(self) -> QWidget:
        """Create the data table tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._data_table = QTableWidget()
        self._data_table.setColumnCount(3)
        self._data_table.setHorizontalHeaderLabels(["Frequency (Hz)", "Magnitude (dB)", "Phase (deg)"])
        self._data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._data_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._data_table.setAlternatingRowColors(True)

        layout.addWidget(self._data_table)
        return widget

    def _populate_plots(self) -> None:
        """Populate the Bode plots with data."""
        if not self._result.is_valid:
            return

        # Get first signal
        if self._result.magnitude:
            signal_name = list(self._result.magnitude.keys())[0]
            self._plot_signal(signal_name)

    def _plot_signal(self, signal_name: str) -> None:
        """Plot a specific signal's Bode data."""
        if signal_name not in self._result.magnitude:
            return

        frequencies = np.array(self._result.frequencies)
        magnitude = np.array(self._result.magnitude[signal_name])
        phase = np.array(self._result.phase[signal_name])

        # Clear existing plots
        self._mag_plot.clear()
        self._phase_plot.clear()

        # Plot magnitude
        pen_mag = pg.mkPen(color=(0, 100, 200), width=2)
        self._mag_curve = self._mag_plot.plot(
            frequencies, magnitude, pen=pen_mag, name="Magnitude"
        )

        # Plot phase
        pen_phase = pg.mkPen(color=(200, 100, 0), width=2)
        self._phase_curve = self._phase_plot.plot(
            frequencies, phase, pen=pen_phase, name="Phase"
        )

        # Add markers for key frequencies
        self._add_markers(frequencies, magnitude, phase)

        # Update data table
        self._update_data_table(signal_name)

    def _add_markers(
        self, frequencies: np.ndarray, magnitude: np.ndarray, phase: np.ndarray
    ) -> None:
        """Add markers for -3dB point and other key frequencies."""
        # Find -3dB point (cutoff frequency)
        max_mag = np.max(magnitude)
        cutoff_level = max_mag - 3.0

        # Find where magnitude crosses -3dB
        for i in range(len(magnitude) - 1):
            if magnitude[i] >= cutoff_level > magnitude[i + 1]:
                # Interpolate to find exact frequency
                f_cutoff = frequencies[i]

                # Add vertical line at cutoff
                cutoff_line = pg.InfiniteLine(
                    pos=f_cutoff,
                    angle=90,
                    pen=pg.mkPen(color=(150, 150, 150), style=Qt.PenStyle.DashLine),
                    label=f"fc={f_cutoff:.1f}Hz",
                    labelOpts={"position": 0.9, "color": (100, 100, 100)},
                )
                self._mag_plot.addItem(cutoff_line)

                # Add -3dB horizontal line
                db3_line = pg.InfiniteLine(
                    pos=cutoff_level,
                    angle=0,
                    pen=pg.mkPen(color=(150, 150, 150), style=Qt.PenStyle.DashLine),
                    label=f"-3dB ({cutoff_level:.1f}dB)",
                    labelOpts={"position": 0.1, "color": (100, 100, 100)},
                )
                self._mag_plot.addItem(db3_line)
                break

        # Add 0dB reference line
        if np.min(magnitude) < 0 < np.max(magnitude):
            zero_line = pg.InfiniteLine(
                pos=0,
                angle=0,
                pen=pg.mkPen(color=(200, 200, 200), style=Qt.PenStyle.DotLine),
            )
            self._mag_plot.addItem(zero_line)

        # Add -180° line for phase margin
        if np.min(phase) < -180:
            phase_line = pg.InfiniteLine(
                pos=-180,
                angle=0,
                pen=pg.mkPen(color=(200, 200, 200), style=Qt.PenStyle.DotLine),
            )
            self._phase_plot.addItem(phase_line)

    def _update_data_table(self, signal_name: str) -> None:
        """Update the data table with current signal data."""
        frequencies = self._result.frequencies
        magnitude = self._result.magnitude[signal_name]
        phase = self._result.phase[signal_name]

        self._data_table.setRowCount(len(frequencies))

        for row, (f, m, p) in enumerate(zip(frequencies, magnitude, phase)):
            self._data_table.setItem(row, 0, QTableWidgetItem(f"{f:.2f}"))
            self._data_table.setItem(row, 1, QTableWidgetItem(f"{m:.2f}"))
            self._data_table.setItem(row, 2, QTableWidgetItem(f"{p:.2f}"))

    def _on_signal_changed(self, signal_name: str) -> None:
        """Handle signal selection change."""
        self._plot_signal(signal_name)

    def _update_plot_visibility(self) -> None:
        """Update plot visibility based on checkboxes."""
        self._mag_plot.setVisible(self._show_magnitude.isChecked())
        self._phase_plot.setVisible(self._show_phase.isChecked())

    def _toggle_grid(self, show: bool) -> None:
        """Toggle grid visibility on plots."""
        alpha = 0.3 if show else 0
        self._mag_plot.showGrid(x=show, y=show, alpha=alpha)
        self._phase_plot.showGrid(x=show, y=show, alpha=alpha)

    def _export_csv(self) -> None:
        """Export Bode plot data to CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export AC Analysis Results",
            "ac_results.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w") as f:
                # Header
                f.write("AC Analysis Results\n")
                f.write(f"Frequency Points: {len(self._result.frequencies)}\n\n")

                # Write data for each signal
                for signal_name in self._result.magnitude:
                    f.write(f"Signal: {signal_name}\n")
                    f.write("Frequency (Hz),Magnitude (dB),Phase (deg)\n")

                    frequencies = self._result.frequencies
                    magnitude = self._result.magnitude[signal_name]
                    phase = self._result.phase[signal_name]

                    for freq, mag, ph in zip(frequencies, magnitude, phase):
                        f.write(f"{freq},{mag},{ph}\n")

                    f.write("\n")

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")
