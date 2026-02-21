"""UI widgets for the thermal viewer."""

from __future__ import annotations

from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSizePolicy,
)

from pulsimgui.services.theme_service import ThemeService, Theme
from pulsimgui.services.thermal_service import ThermalResult, ThermalDeviceResult


class ThermalViewerWidget(QWidget):
    """Tabbed widget offering thermal network, temperature, and loss views."""

    def __init__(
        self,
        theme_service: ThemeService | None = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._result: Optional[ThermalResult] = None
        self._theme_service = theme_service
        self._series_palette = [
            "#4CAF50",
            "#03A9F4",
            "#FFC107",
            "#E91E63",
            "#9C27B0",
            "#FF5722",
        ]

        self._tabs = QTabWidget(self)

        self._network_tree = QTreeWidget()
        self._network_tree.setColumnCount(4)
        self._network_tree.setHeaderLabels(["Device / Stage", "Rth (K/W)", "Cth (J/K)", "Temp (°C)"])
        self._network_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for index in range(1, 4):
            self._network_tree.header().setSectionResizeMode(index, QHeaderView.ResizeToContents)

        self._temperature_plot = pg.PlotWidget()
        self._temperature_plot.showGrid(x=True, y=True, alpha=0.2)
        self._temperature_plot.setLabel("left", "Temperature", units="°C")
        self._temperature_plot.setLabel("bottom", "Time", units="s")

        self._loss_table = QTableWidget(0, 5)
        self._loss_table.setHorizontalHeaderLabels(
            ["Device", "Conduction (W)", "Switching (W)", "Total (W)", "Percent"]
        )
        self._loss_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            self._loss_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self._loss_table.verticalHeader().setVisible(False)
        self._loss_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._loss_plot = pg.PlotWidget()
        self._loss_plot.showGrid(x=True, y=True, alpha=0.15)
        self._loss_plot.setLabel("left", "Loss (W)")
        self._loss_plot.setLabel("bottom", "Device")

        self._loss_caption = QLabel()
        self._loss_caption.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._tabs.addTab(self._network_tree, "Thermal Network")
        temp_tab = QWidget()
        temp_layout = QVBoxLayout(temp_tab)
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_layout.addWidget(self._temperature_plot)
        self._tabs.addTab(temp_tab, "Temperatures")

        loss_tab = QWidget()
        loss_layout = QVBoxLayout(loss_tab)
        loss_layout.setContentsMargins(0, 0, 0, 0)
        loss_layout.addWidget(self._loss_table)
        loss_layout.addWidget(self._loss_plot, stretch=1)
        loss_layout.addWidget(self._loss_caption)
        self._tabs.addTab(loss_tab, "Loss Breakdown")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self.apply_theme)
            self.apply_theme(self._theme_service.current_theme)

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to all thermal viewer surfaces."""
        c = theme.colors
        if self._theme_service is not None:
            self._series_palette = [QColor(*rgb).name() for rgb in self._theme_service.get_trace_palette(theme)]

        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {c.tab_border};
                background-color: {c.background};
            }}
            QTabBar::tab {{
                background-color: {c.tab_background};
                border: 1px solid {c.tab_border};
                color: {c.foreground};
                padding: 6px 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {c.tab_active};
            }}
        """)
        self._network_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {c.panel_background};
                border: 1px solid {c.panel_border};
                color: {c.foreground};
            }}
            QHeaderView::section {{
                background-color: {c.panel_header};
                color: {c.foreground};
                border: none;
                border-bottom: 1px solid {c.panel_border};
                padding: 6px;
                font-weight: 600;
            }}
        """)
        self._loss_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c.panel_background};
                border: 1px solid {c.panel_border};
                gridline-color: {c.divider};
                color: {c.foreground};
            }}
            QHeaderView::section {{
                background-color: {c.panel_header};
                color: {c.foreground};
                border: none;
                border-bottom: 1px solid {c.panel_border};
                padding: 6px;
                font-weight: 600;
            }}
        """)
        self._loss_caption.setStyleSheet(f"color: {c.foreground_muted};")
        self._apply_plot_theme(self._temperature_plot, theme)
        self._apply_plot_theme(self._loss_plot, theme)
        if self._result is not None:
            self._plot_temperatures(self._result)
            self._render_loss_chart(self._result)

    def _apply_plot_theme(self, plot_widget: pg.PlotWidget, theme: Theme) -> None:
        """Apply theme to a pyqtgraph plot surface."""
        c = theme.colors
        plot_widget.setBackground(c.plot_background)
        plot_item = plot_widget.getPlotItem()
        axis_color = c.plot_axis
        text_color = c.plot_text
        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen(axis_color))
            axis.setTickPen(pg.mkPen(axis_color))
            axis.setTextPen(pg.mkPen(text_color))
        grid_alpha = 0.18 if theme.is_dark else 0.12
        plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)
        if plot_item.legend is not None:
            plot_item.legend.setLabelTextColor(text_color)
            plot_item.legend.setBrush(pg.mkBrush(c.plot_legend_background))
            plot_item.legend.setPen(pg.mkPen(c.plot_legend_border))

    def set_result(self, result: Optional[ThermalResult]) -> None:
        """Populate the widget with a new data set."""
        self._result = result
        if not result or not result.devices:
            self._clear_views()
            return

        self._populate_network(result)
        self._plot_temperatures(result)
        self._update_loss_summary(result)

    # ------------------------------------------------------------------
    # Network view helpers
    def _populate_network(self, result: ThermalResult) -> None:
        self._network_tree.clear()
        for device in result.devices:
            top_item = QTreeWidgetItem(
                [
                    device.component_name,
                    "-",
                    "-",
                    f"{device.peak_temperature:.1f}",
                ]
            )
            self._network_tree.addTopLevelItem(top_item)
            for stage in device.stages:
                child = QTreeWidgetItem(
                    [
                        stage.name,
                        f"{stage.resistance:.3f}",
                        f"{stage.capacitance:.3f}",
                        f"{stage.temperature:.1f}",
                    ]
                )
                top_item.addChild(child)
            top_item.setExpanded(True)

        self._network_tree.resizeColumnToContents(0)

    # ------------------------------------------------------------------
    # Temperature plot helpers
    def _plot_temperatures(self, result: ThermalResult) -> None:
        self._temperature_plot.clear()
        plot_item = self._temperature_plot.getPlotItem()
        if plot_item.legend is None:
            legend = self._temperature_plot.addLegend()
        else:
            plot_item.legend.clear()
        palette = self._color_palette()
        for index, device in enumerate(result.devices):
            if not device.temperature_trace:
                continue
            pen = pg.mkPen(palette[index % len(palette)], width=2)
            self._temperature_plot.plot(result.time, device.temperature_trace, pen=pen, name=device.component_name)

    # ------------------------------------------------------------------
    # Loss summary helpers
    def _update_loss_summary(self, result: ThermalResult) -> None:
        self._loss_table.setRowCount(0)
        total_losses = result.total_losses() or 1.0

        for device in result.devices:
            row = self._loss_table.rowCount()
            self._loss_table.insertRow(row)
            percent = (device.total_loss / total_losses) * 100.0
            values = [
                device.component_name,
                f"{device.conduction_loss:.2f}",
                f"{device.switching_loss:.2f}",
                f"{device.total_loss:.2f}",
                f"{percent:.1f}%",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._loss_table.setItem(row, column, item)

        self._render_loss_chart(result)
        self._loss_caption.setText(
            f"Total loss: {result.total_losses():.2f} W    Ambient: {result.ambient_temperature:.1f} °C"
        )

    def _render_loss_chart(self, result: ThermalResult) -> None:
        self._loss_plot.clear()
        palette = self._color_palette()
        x_positions = list(range(len(result.devices)))
        if not x_positions:
            return

        width = 0.35
        conduction_heights = [device.conduction_loss for device in result.devices]
        switching_heights = [device.switching_loss for device in result.devices]

        conduction_bar = pg.BarGraphItem(
            x=[x - width / 2 for x in x_positions],
            height=conduction_heights,
            width=width,
            brush=palette[0],
            pen=pg.mkPen(color=palette[0])
        )
        switching_bar = pg.BarGraphItem(
            x=[x + width / 2 for x in x_positions],
            height=switching_heights,
            width=width,
            brush=palette[1],
            pen=pg.mkPen(color=palette[1])
        )
        self._loss_plot.addItem(conduction_bar)
        self._loss_plot.addItem(switching_bar)

        axis = self._loss_plot.getAxis("bottom")
        axis.setTicks([[ (x, result.devices[x].component_name) for x in x_positions ]])

        legend = self._loss_plot.getPlotItem().legend
        if legend is None:
            legend = self._loss_plot.addLegend()
        legend.clear()
        legend.addItem(conduction_bar, "Conduction")
        legend.addItem(switching_bar, "Switching")

    # ------------------------------------------------------------------
    def _clear_views(self) -> None:
        self._network_tree.clear()
        self._temperature_plot.clear()
        self._loss_table.setRowCount(0)
        self._loss_plot.clear()
        self._loss_caption.setText("No thermal data available.")

    def _color_palette(self) -> list[str]:
        return self._series_palette
