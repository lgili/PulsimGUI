"""DC operating point results dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QDialogButtonBox,
    QHeaderView,
    QGroupBox,
    QLabel,
    QPushButton,
    QFileDialog,
)

from pulsimgui.services.simulation_service import DCResult
from pulsimgui.utils.si_prefix import format_si_value
from pulsimgui.views.widgets import StatusBanner


class DCResultsDialog(QDialog):
    """Dialog for displaying DC operating point results."""

    def __init__(self, result: DCResult, parent=None):
        super().__init__(parent)
        self._result = result

        self.setWindowTitle("DC Operating Point Results")
        self.setMinimumSize(500, 400)

        self._setup_ui()
        self._populate_tables()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Status banner
        if self._result.is_valid:
            status = StatusBanner.success("DC operating point converged successfully.")
        else:
            status = StatusBanner.error(f"Error: {self._result.error_message}")
        layout.addWidget(status)

        # Tab widget
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Node voltages tab
        voltages_widget = QWidget()
        voltages_layout = QVBoxLayout(voltages_widget)
        self._voltages_table = self._create_table(["Node", "Voltage"])
        voltages_layout.addWidget(self._voltages_table)
        self._tabs.addTab(voltages_widget, "Node Voltages")

        # Branch currents tab
        currents_widget = QWidget()
        currents_layout = QVBoxLayout(currents_widget)
        self._currents_table = self._create_table(["Branch", "Current"])
        currents_layout.addWidget(self._currents_table)
        self._tabs.addTab(currents_widget, "Branch Currents")

        # Power dissipation tab
        power_widget = QWidget()
        power_layout = QVBoxLayout(power_widget)
        self._power_table = self._create_table(["Component", "Power"])
        power_layout.addWidget(self._power_table)

        # Total power summary card
        self._total_power_label = QLabel("")
        self._total_power_label.setStyleSheet("""
            QLabel {
                background-color: #f0f9ff;
                border: 1px solid #bae6fd;
                border-radius: 6px;
                padding: 10px 14px;
                color: #0369a1;
                font-weight: 600;
                font-size: 12px;
            }
        """)
        power_layout.addWidget(self._total_power_label)

        self._tabs.addTab(power_widget, "Power Dissipation")

        # Buttons
        button_layout = QHBoxLayout()

        export_btn = QPushButton("Export to CSV...")
        export_btn.clicked.connect(self._export_csv)
        button_layout.addWidget(export_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _create_table(self, headers: list[str]) -> QTableWidget:
        """Create a styled results table."""
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)

        # Apply modern styling
        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                background-color: #ffffff;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid #f3f4f6;
            }
            QTableWidget::item:selected {
                background-color: #dbeafe;
                color: #1e40af;
            }
            QTableWidget::item:alternate {
                background-color: #f9fafb;
            }
            QHeaderView::section {
                background-color: #f9fafb;
                color: #374151;
                font-weight: 600;
                font-size: 11px;
                padding: 10px 12px;
                border: none;
                border-bottom: 2px solid #e5e7eb;
            }
        """)
        return table

    def _populate_tables(self) -> None:
        """Populate all result tables."""
        # Node voltages
        self._voltages_table.setRowCount(len(self._result.node_voltages))
        for row, (node, voltage) in enumerate(sorted(self._result.node_voltages.items())):
            self._voltages_table.setItem(row, 0, QTableWidgetItem(node))
            self._voltages_table.setItem(row, 1, QTableWidgetItem(format_si_value(voltage, "V")))

        # Branch currents
        self._currents_table.setRowCount(len(self._result.branch_currents))
        for row, (branch, current) in enumerate(sorted(self._result.branch_currents.items())):
            self._currents_table.setItem(row, 0, QTableWidgetItem(branch))
            self._currents_table.setItem(row, 1, QTableWidgetItem(format_si_value(current, "A")))

        # Power dissipation
        self._power_table.setRowCount(len(self._result.power_dissipation))
        total_power = 0.0
        for row, (comp, power) in enumerate(sorted(self._result.power_dissipation.items())):
            self._power_table.setItem(row, 0, QTableWidgetItem(comp))
            self._power_table.setItem(row, 1, QTableWidgetItem(format_si_value(power, "W")))
            total_power += power

        self._total_power_label.setText(f"Total Power: {format_si_value(total_power, 'W')}")

    def _export_csv(self) -> None:
        """Export results to CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export DC Results",
            "dc_results.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w") as f:
                # Node voltages
                f.write("Node Voltages\n")
                f.write("Node,Voltage (V)\n")
                for node, voltage in sorted(self._result.node_voltages.items()):
                    f.write(f"{node},{voltage}\n")

                f.write("\nBranch Currents\n")
                f.write("Branch,Current (A)\n")
                for branch, current in sorted(self._result.branch_currents.items()):
                    f.write(f"{branch},{current}\n")

                f.write("\nPower Dissipation\n")
                f.write("Component,Power (W)\n")
                for comp, power in sorted(self._result.power_dissipation.items()):
                    f.write(f"{comp},{power}\n")

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")
