"""Convergence diagnostics dialog for analyzing solver failures."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QLabel,
    QPushButton,
    QFormLayout,
    QTextBrowser,
    QSplitter,
)

from pulsimgui.services.backend_types import ConvergenceInfo, IterationRecord
from pulsimgui.views.widgets import StatusBanner


class ConvergenceDiagnosticsDialog(QDialog):
    """Dialog for displaying convergence diagnostics and suggestions.

    Shows detailed information about solver convergence behavior including:
    - Summary of key metrics
    - Iteration history plot (residual vs iteration)
    - List of problematic variables
    - Suggestions for improving convergence
    """

    def __init__(self, info: ConvergenceInfo, parent=None):
        super().__init__(parent)
        self._info = info

        self.setWindowTitle("Convergence Diagnostics")
        self.setMinimumSize(800, 600)

        # Configure pyqtgraph
        pg.setConfigOptions(antialias=True)

        self._setup_ui()
        self._populate_data()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Status banner
        if self._info.converged:
            status = StatusBanner.success(
                f"Converged in {self._info.iterations} iterations "
                f"(residual: {self._info.final_residual:.2e})"
            )
        else:
            msg = self._info.failure_reason or "Solver did not converge"
            status = StatusBanner.error(msg)
        layout.addWidget(status)

        # Tab widget
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Summary tab
        summary_widget = self._create_summary_tab()
        self._tabs.addTab(summary_widget, "Summary")

        # Iteration history tab
        history_widget = self._create_history_tab()
        self._tabs.addTab(history_widget, "Iteration History")

        # Problematic variables tab
        variables_widget = self._create_variables_tab()
        self._tabs.addTab(variables_widget, "Problematic Variables")

        # Suggestions tab
        suggestions_widget = self._create_suggestions_tab()
        self._tabs.addTab(suggestions_widget, "Suggestions")

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _create_summary_tab(self) -> QWidget:
        """Create the summary tab with key metrics."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Key metrics group
        metrics_group = QGroupBox("Key Metrics")
        metrics_layout = QFormLayout(metrics_group)

        # Convergence status
        status_label = QLabel()
        if self._info.converged:
            status_label.setText("<span style='color: #16a34a; font-weight: 600;'>Converged</span>")
        else:
            status_label.setText("<span style='color: #dc2626; font-weight: 600;'>Did Not Converge</span>")
        metrics_layout.addRow("Status:", status_label)

        # Iterations
        metrics_layout.addRow("Iterations:", QLabel(str(self._info.iterations)))

        # Final residual
        residual_label = QLabel(f"{self._info.final_residual:.6e}")
        metrics_layout.addRow("Final Residual:", residual_label)

        # Strategy used
        metrics_layout.addRow("Strategy:", QLabel(self._info.strategy_used.replace("_", " ").title()))

        # Convergence trend
        trend_label = QLabel()
        trend = self._info.trend
        trend_colors = {
            "converging": "#16a34a",
            "stalling": "#ca8a04",
            "diverging": "#dc2626",
            "unknown": "#6b7280",
        }
        color = trend_colors.get(trend, "#6b7280")
        trend_label.setText(f"<span style='color: {color};'>{trend.title()}</span>")
        metrics_layout.addRow("Trend:", trend_label)

        # Time of failure (for transient)
        if self._info.time_of_failure is not None:
            time_label = QLabel(f"{self._info.time_of_failure:.6e} s")
            metrics_layout.addRow("Failure Time:", time_label)

        layout.addWidget(metrics_group)

        # Failure details group (if not converged)
        if not self._info.converged and self._info.failure_reason:
            details_group = QGroupBox("Failure Details")
            details_layout = QVBoxLayout(details_group)

            details_text = QLabel(self._info.failure_reason)
            details_text.setWordWrap(True)
            details_text.setStyleSheet("""
                QLabel {
                    background-color: #fef2f2;
                    border: 1px solid #fecaca;
                    border-radius: 6px;
                    padding: 12px;
                    color: #991b1b;
                }
            """)
            details_layout.addWidget(details_text)

            layout.addWidget(details_group)

        layout.addStretch()
        return widget

    def _create_history_tab(self) -> QWidget:
        """Create the iteration history tab with residual plot."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        if not self._info.history:
            no_data_label = QLabel("No iteration history available.")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data_label.setStyleSheet("color: #6b7280; font-style: italic;")
            layout.addWidget(no_data_label)
            return widget

        # Create splitter for plot and table
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Residual plot
        plot_widget = QWidget()
        plot_layout = QVBoxLayout(plot_widget)
        plot_layout.setContentsMargins(0, 0, 0, 0)

        self._residual_plot = pg.PlotWidget()
        self._residual_plot.setLabel("left", "Residual Norm")
        self._residual_plot.setLabel("bottom", "Iteration")
        self._residual_plot.setLogMode(x=False, y=True)
        self._residual_plot.showGrid(x=True, y=True, alpha=0.3)
        self._residual_plot.setBackground("w")
        self._residual_plot.getAxis("left").setPen("k")
        self._residual_plot.getAxis("bottom").setPen("k")
        self._residual_plot.getAxis("left").setTextPen("k")
        self._residual_plot.getAxis("bottom").setTextPen("k")
        plot_layout.addWidget(self._residual_plot)

        splitter.addWidget(plot_widget)

        # History table
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)

        self._history_table = self._create_table([
            "Iteration", "Residual", "Voltage Error", "Current Error", "Damping", "Step Norm"
        ])
        table_layout.addWidget(self._history_table)

        splitter.addWidget(table_widget)

        # Set initial sizes (60% plot, 40% table)
        splitter.setSizes([360, 240])

        layout.addWidget(splitter)
        return widget

    def _create_variables_tab(self) -> QWidget:
        """Create the problematic variables tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if not self._info.problematic_variables:
            no_data_label = QLabel("No problematic variables detected.")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data_label.setStyleSheet("color: #6b7280; font-style: italic;")
            layout.addWidget(no_data_label)
            return widget

        # Description
        desc_label = QLabel(
            "Variables that did not meet convergence criteria, sorted by normalized error:"
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Variables table
        self._variables_table = self._create_table([
            "Variable", "Type", "Value", "Change", "Tolerance", "Error Ratio"
        ])
        layout.addWidget(self._variables_table)

        return widget

    def _create_suggestions_tab(self) -> QWidget:
        """Create the suggestions tab with troubleshooting advice."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Generate suggestions
        suggestions = self._generate_suggestions()

        if not suggestions:
            no_suggestions = QLabel("No specific suggestions available.")
            no_suggestions.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_suggestions.setStyleSheet("color: #6b7280; font-style: italic;")
            layout.addWidget(no_suggestions)
            return widget

        # Suggestions browser
        suggestions_browser = QTextBrowser()
        suggestions_browser.setOpenExternalLinks(True)
        suggestions_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 12px;
            }
        """)

        html = self._format_suggestions_html(suggestions)
        suggestions_browser.setHtml(html)

        layout.addWidget(suggestions_browser)
        return widget

    def _create_table(self, headers: list[str]) -> QTableWidget:
        """Create a styled table widget."""
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)

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

    def _populate_data(self) -> None:
        """Populate all data views."""
        self._populate_history()
        self._populate_variables()

    def _populate_history(self) -> None:
        """Populate the iteration history plot and table."""
        if not self._info.history:
            return

        # Extract data
        iterations = [r.iteration for r in self._info.history]
        residuals = [r.residual_norm for r in self._info.history]

        # Plot residual curve
        pen = pg.mkPen(color=(0, 100, 200), width=2)
        self._residual_plot.plot(iterations, residuals, pen=pen, symbol="o", symbolSize=6)

        # Add convergence tolerance line if we have a reasonable estimate
        if self._info.final_residual > 0:
            # Estimate tolerance (typically 1e-9 or similar)
            tol_estimate = 1e-9
            if residuals[-1] > tol_estimate:
                tol_line = pg.InfiniteLine(
                    pos=tol_estimate,
                    angle=0,
                    pen=pg.mkPen(color=(100, 200, 100), style=Qt.PenStyle.DashLine),
                    label="Tolerance",
                    labelOpts={"position": 0.1, "color": (100, 100, 100)},
                )
                self._residual_plot.addItem(tol_line)

        # Populate table
        self._history_table.setRowCount(len(self._info.history))
        for row, record in enumerate(self._info.history):
            self._history_table.setItem(row, 0, QTableWidgetItem(str(record.iteration)))
            self._history_table.setItem(row, 1, QTableWidgetItem(f"{record.residual_norm:.2e}"))
            self._history_table.setItem(row, 2, QTableWidgetItem(f"{record.voltage_error:.2e}"))
            self._history_table.setItem(row, 3, QTableWidgetItem(f"{record.current_error:.2e}"))
            self._history_table.setItem(row, 4, QTableWidgetItem(f"{record.damping_factor:.3f}"))
            self._history_table.setItem(row, 5, QTableWidgetItem(f"{record.step_norm:.2e}"))

    def _populate_variables(self) -> None:
        """Populate the problematic variables table."""
        if not self._info.problematic_variables:
            return

        # Sort by normalized error (worst first)
        sorted_vars = sorted(
            self._info.problematic_variables,
            key=lambda v: v.normalized_error,
            reverse=True,
        )

        self._variables_table.setRowCount(len(sorted_vars))
        for row, var in enumerate(sorted_vars):
            self._variables_table.setItem(row, 0, QTableWidgetItem(var.name))
            var_type = "Voltage" if var.is_voltage else "Current"
            self._variables_table.setItem(row, 1, QTableWidgetItem(var_type))
            self._variables_table.setItem(row, 2, QTableWidgetItem(f"{var.value:.6e}"))
            self._variables_table.setItem(row, 3, QTableWidgetItem(f"{var.change:.6e}"))
            self._variables_table.setItem(row, 4, QTableWidgetItem(f"{var.tolerance:.2e}"))

            # Color error ratio based on severity
            error_item = QTableWidgetItem(f"{var.normalized_error:.2f}x")
            if var.normalized_error > 100:
                error_item.setForeground(Qt.GlobalColor.red)
            elif var.normalized_error > 10:
                error_item.setForeground(Qt.GlobalColor.darkYellow)
            self._variables_table.setItem(row, 5, error_item)

    def _generate_suggestions(self) -> list[dict]:
        """Generate suggestions based on convergence diagnostics.

        Returns:
            List of suggestion dicts with 'title', 'description', and 'action' keys.
        """
        suggestions = []

        # Check if iterations hit max
        if self._info.iterations >= 50 and not self._info.converged:
            suggestions.append({
                "title": "Increase Maximum Iterations",
                "description": (
                    f"The solver ran {self._info.iterations} iterations without converging. "
                    "If the trend was converging, allowing more iterations may help."
                ),
                "action": "Go to Simulation Settings > Solver tab and increase 'Max Newton iterations'.",
            })

        # Check for diverging trend
        if self._info.trend == "diverging":
            suggestions.append({
                "title": "Enable Voltage Limiting",
                "description": (
                    "The solver is diverging, possibly due to large Newton steps. "
                    "Voltage limiting can help by clamping step sizes."
                ),
                "action": "Go to Simulation Settings > Solver tab and enable 'Voltage limiting'.",
            })
            suggestions.append({
                "title": "Try GMIN Stepping",
                "description": (
                    "GMIN stepping adds small conductances to help find an initial operating point. "
                    "This can stabilize circuits with strong nonlinearities."
                ),
                "action": "Go to Simulation Settings > Solver tab and select 'GMIN Stepping' strategy.",
            })

        # Check for stalling
        if self._info.trend == "stalling":
            suggestions.append({
                "title": "Try Source Stepping",
                "description": (
                    "The solver is stalling (residual not decreasing). "
                    "Source stepping ramps up voltage sources gradually, which can help "
                    "find the operating point in high-gain circuits."
                ),
                "action": "Go to Simulation Settings > Solver tab and select 'Source Stepping' strategy.",
            })

        # Check for problematic voltage nodes
        if self._info.problematic_variables:
            voltage_vars = [v for v in self._info.problematic_variables if v.is_voltage]
            if voltage_vars:
                suggestions.append({
                    "title": "Check Floating Nodes",
                    "description": (
                        f"Node(s) {', '.join(v.name for v in voltage_vars[:3])} "
                        "have convergence issues. This may indicate floating (unconnected) nodes."
                    ),
                    "action": "Verify that all nodes have a DC path to ground.",
                })

        # Check for very high changes
        if self._info.history:
            max_step = max(r.step_norm for r in self._info.history)
            if max_step > 100:
                suggestions.append({
                    "title": "Reduce Maximum Voltage Step",
                    "description": (
                        f"Large Newton steps detected (max step norm: {max_step:.1f}). "
                        "Reducing the maximum voltage step can improve stability."
                    ),
                    "action": "Go to Simulation Settings > Solver tab and reduce 'Max voltage step'.",
                })

        # Check for transient failure at specific time
        if self._info.time_of_failure is not None:
            suggestions.append({
                "title": "Use Pseudo-Transient",
                "description": (
                    f"Convergence failed at t={self._info.time_of_failure:.6e}s. "
                    "Pseudo-transient analysis adds time-stepping to help traverse "
                    "difficult operating regions."
                ),
                "action": "Go to Simulation Settings > Solver tab and select 'Pseudo-Transient' strategy.",
            })

        # General suggestion if nothing specific
        if not suggestions:
            suggestions.append({
                "title": "Review Circuit Topology",
                "description": (
                    "No specific convergence issue detected. Consider reviewing the circuit "
                    "for potential modeling issues."
                ),
                "action": (
                    "Check for: (1) Missing DC paths to ground, (2) Unrealistic component values, "
                    "(3) Incorrect device models."
                ),
            })

        return suggestions

    def _format_suggestions_html(self, suggestions: list[dict]) -> str:
        """Format suggestions as HTML for display."""
        html_parts = ["<style>"]
        html_parts.append("""
            .suggestion {
                margin-bottom: 16px;
                padding: 12px;
                background: white;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
            }
            .suggestion-title {
                font-weight: 600;
                color: #1e40af;
                font-size: 14px;
                margin-bottom: 8px;
            }
            .suggestion-desc {
                color: #4b5563;
                margin-bottom: 8px;
                line-height: 1.5;
            }
            .suggestion-action {
                color: #059669;
                font-style: italic;
                background: #ecfdf5;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        html_parts.append("</style>")

        for i, suggestion in enumerate(suggestions, 1):
            html_parts.append(f"""
                <div class="suggestion">
                    <div class="suggestion-title">{i}. {suggestion['title']}</div>
                    <div class="suggestion-desc">{suggestion['description']}</div>
                    <div class="suggestion-action"><strong>Action:</strong> {suggestion['action']}</div>
                </div>
            """)

        return "".join(html_parts)
