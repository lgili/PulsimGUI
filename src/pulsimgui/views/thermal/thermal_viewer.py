"""UI widgets for the thermal viewer."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.theme_service import Theme, ThemeService
from pulsimgui.services.thermal_service import ThermalResult
from pulsimgui.views.widgets.status_widgets import StatusBanner


class ThermalViewerWidget(QWidget):
    """Tabbed widget offering thermal network, temperature, and loss views."""

    def __init__(
        self,
        theme_service: ThemeService | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._result: ThermalResult | None = None
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

        self._loss_table = QTableWidget(0, 11)
        self._loss_table.setHorizontalHeaderLabels(
            [
                "Device",
                "Conduction (W)",
                "Sw On (W)",
                "Sw Off (W)",
                "Rev Rec (W)",
                "Switching (W)",
                "Total (W)",
                "Share",
                "Peak T (°C)",
                "Limit (°C)",
                "Status",
            ]
        )
        self._loss_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 11):
            self._loss_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self._loss_table.verticalHeader().setVisible(False)
        self._loss_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._loss_plot = pg.PlotWidget()
        self._loss_plot.showGrid(x=True, y=True, alpha=0.15)
        self._loss_plot.setLabel("left", "Loss (W)")
        self._loss_plot.setLabel("bottom", "Device")

        self._loss_caption = QLabel()
        self._loss_caption.setAlignment(Qt.AlignmentFlag.AlignRight)

        # pulsim 1.7 — Coupled-Solve tab. Shows the SharedHeatsink +
        # electrothermal steady-state results from result.statistics so
        # the user can see the *coupled* answer (Σ Pᵢ · R_sa)
        # alongside the per-device-isolated legacy temperatures.
        self._coupled_table = QTableWidget(0, 6)
        self._coupled_table.setHorizontalHeaderLabels([
            "Heatsink", "T_amb (°C)", "T_sink (°C)",
            "Device", "T_j (°C)", "Power (W)",
        ])
        self._coupled_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents,
        )
        for column in range(1, 6):
            self._coupled_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents,
            )
        self._coupled_table.verticalHeader().setVisible(False)
        self._coupled_table.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding,
        )
        self._coupled_caption = QLabel()
        self._coupled_caption.setWordWrap(True)
        self._coupled_caption.setStyleSheet("color: #888; font-size: 11px;")

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

        coupled_tab = QWidget()
        coupled_layout = QVBoxLayout(coupled_tab)
        coupled_layout.setContentsMargins(0, 0, 0, 0)
        coupled_layout.addWidget(self._coupled_table, stretch=1)
        coupled_layout.addWidget(self._coupled_caption)
        self._coupled_tab_index = self._tabs.addTab(
            coupled_tab, "Coupled Solve",
        )

        # pulsim 1.7 — runaway warning banner. Hidden until set_result
        # picks up an electrothermal record with runaway=True. Placed
        # ABOVE the tabs so it's impossible to miss — the user can be
        # on any tab and still see the warning.
        self._runaway_banner = StatusBanner.warning(
            "Thermal runaway predicted — review Coupled Solve tab.",
            parent=self,
        )
        self._runaway_banner.hide()

        # pulsim 1.7 — T_j limit-trip banner. Separate from runaway so
        # both can show at once. T_max trips are an existing-device
        # safety report; runaway is a "this design will never reach
        # equilibrium" sizing answer.
        self._limit_banner = StatusBanner.warning(
            "Junction-temperature limit exceeded — review Loss Breakdown tab.",
            parent=self,
        )
        self._limit_banner.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._runaway_banner)
        layout.addWidget(self._limit_banner)
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

    def set_result(self, result: ThermalResult | None) -> None:
        """Populate the widget with a new data set."""
        self._result = result
        if not result or not result.devices:
            self._clear_views()
            return

        self._populate_network(result)
        self._plot_temperatures(result)
        self._update_loss_summary(result)
        self._update_coupled_solve(result)
        self._update_warning_banners(result)

    def _update_warning_banners(self, result: ThermalResult) -> None:
        """Show / hide the runaway + T_j limit-trip banners based on
        what landed in ``result.statistics``.

        Both banners can show simultaneously — they answer different
        questions ("did the design ever reach equilibrium?" vs "did
        any device exceed its rated T_max during the run?")."""
        # Runaway: any sink whose electrothermal solve diverged.
        runaway_sinks = [
            rec for rec in (result.electrothermal_results or [])
            if rec.get("runaway") is True
        ]
        if runaway_sinks:
            names = ", ".join(
                str(rec.get("name") or "unnamed") for rec in runaway_sinks
            )
            gains = ", ".join(
                f"ρ={float(rec.get('feedback_gain') or 0.0):.2f}"
                for rec in runaway_sinks
            )
            self._runaway_banner.setText(
                f"Thermal runaway predicted on heatsink(s): {names}.  "
                f"Feedback gain {gains} (≥1 means no stable T_j). "
                f"Review the Coupled Solve tab and consider a bigger "
                f"heatsink, lower R_jc, or derating."
            )
            self._runaway_banner.show()
        else:
            self._runaway_banner.hide()

        # Limit trip: any device whose T_max threshold was crossed.
        trips = [
            rec for rec in (result.thermal_limit_trips or [])
            if rec.get("tripped") is True
        ]
        if trips:
            names = ", ".join(
                f"{rec.get('device_name', '?')} "
                f"({float(rec.get('peak_temperature_C') or 0.0):.0f}°C "
                f">{float(rec.get('T_limit_C') or 0.0):.0f}°C)"
                for rec in trips
            )
            self._limit_banner.setText(
                f"Junction-temperature limit exceeded — {names}.  "
                f"Review the Loss Breakdown tab."
            )
            self._limit_banner.show()
        else:
            self._limit_banner.hide()

    def _update_coupled_solve(self, result: ThermalResult) -> None:
        """Fill the Coupled Solve tab with the SharedHeatsink and (if
        present) electrothermal steady-state breakdowns. Prefers the
        electrothermal record when available — its converged powers
        include the temperature-dependent loss correction; the
        shared_heatsink record uses the reference loss directly.

        Empty tab + caption "no heatsink modeled" when neither result
        list has anything (the legacy isolated thermal path owns the
        T_j answer)."""
        self._coupled_table.setRowCount(0)

        # If electrothermal solved cleanly for any sink, prefer that
        # record (it carries final_powers_W and ρ); fall back to the
        # T-independent shared_heatsink answer per sink that didn't.
        eth_by_name = {
            str(rec.get("name") or ""): rec
            for rec in (result.electrothermal_results or [])
            if rec.get("converged") is True
        }

        had_any_sink = False
        for sh_rec in result.shared_heatsink_results or []:
            sink_name = str(sh_rec.get("name") or "")
            had_any_sink = True
            # Pick the better record per sink.
            eth_rec = eth_by_name.get(sink_name)
            source = eth_rec if eth_rec is not None else sh_rec
            T_amb = float(source.get("T_amb_C") or 0.0)
            T_sink = float(source.get("T_sink_C") or T_amb)
            devices = source.get("devices") or {}
            powers = source.get(
                "final_powers_W",
                source.get("powers_W") or {},
            )
            if not isinstance(devices, dict):
                continue
            if not devices:
                continue

            # One row per device under this sink.
            for device_name, T_j in devices.items():
                row = self._coupled_table.rowCount()
                self._coupled_table.insertRow(row)
                cells = [
                    sink_name if row == 0 else "",  # sink name only on first row
                    f"{T_amb:.1f}" if row == 0 else "",
                    f"{T_sink:.1f}" if row == 0 else "",
                    str(device_name),
                    f"{float(T_j):.1f}",
                    f"{float((powers or {}).get(device_name, 0.0) or 0.0):.2f}",
                ]
                for col, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if col >= 1 and col != 3:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter,
                        )
                    self._coupled_table.setItem(row, col, item)

        # Mark sinks that ran the electrothermal solve but weren't
        # also in the shared_heatsink list (defensive — descriptor
        # parity is normally enforced by the converter).
        for sink_name, eth_rec in eth_by_name.items():
            if any(
                str(rec.get("name") or "") == sink_name
                for rec in result.shared_heatsink_results or []
            ):
                continue
            had_any_sink = True
            devices = eth_rec.get("devices") or {}
            if not isinstance(devices, dict):
                continue
            T_amb = float(eth_rec.get("T_amb_C") or 0.0)
            T_sink = float(eth_rec.get("T_sink_C") or T_amb)
            powers = eth_rec.get("final_powers_W") or {}
            for device_name, T_j in devices.items():
                row = self._coupled_table.rowCount()
                self._coupled_table.insertRow(row)
                self._coupled_table.setItem(
                    row, 0, QTableWidgetItem(sink_name if row == 0 else ""),
                )
                self._coupled_table.setItem(
                    row, 1, QTableWidgetItem(f"{T_amb:.1f}" if row == 0 else ""),
                )
                self._coupled_table.setItem(
                    row, 2, QTableWidgetItem(f"{T_sink:.1f}" if row == 0 else ""),
                )
                self._coupled_table.setItem(
                    row, 3, QTableWidgetItem(str(device_name)),
                )
                self._coupled_table.setItem(
                    row, 4, QTableWidgetItem(f"{float(T_j):.1f}"),
                )
                self._coupled_table.setItem(
                    row, 5, QTableWidgetItem(
                        f"{float((powers or {}).get(device_name, 0.0) or 0.0):.2f}",
                    ),
                )

        if not had_any_sink:
            self._coupled_caption.setText(
                "No HEATSINK component on the schematic — junction "
                "temperatures shown on the other tabs come from the "
                "per-device-isolated thermal pipeline (legacy path)."
            )
            self._tabs.setTabEnabled(self._coupled_tab_index, False)
        else:
            using_eth = bool(eth_by_name)
            self._coupled_caption.setText(
                "Coupled shared-heatsink steady state. "
                + (
                    "Powers reflect temperature-dependent loss "
                    "(electrothermal solve)."
                    if using_eth
                    else "Powers are reference (T-independent) losses; "
                    "set loss_a_cond_per_C / loss_a_sw_per_C on the "
                    "devices to enable the self-consistent solve."
                )
            )
            self._tabs.setTabEnabled(self._coupled_tab_index, True)

    # ------------------------------------------------------------------
    # Network view helpers
    def _populate_network(self, result: ThermalResult) -> None:
        self._network_tree.clear()
        for device in result.devices:
            temp_text = f"{device.peak_temperature:.1f}"
            if device.thermal_limit is not None:
                temp_text = f"{temp_text} / {float(device.thermal_limit):.1f}"
            top_item = QTreeWidgetItem(
                [
                    device.component_name,
                    "-",
                    "-",
                    temp_text,
                ]
            )
            self._network_tree.addTopLevelItem(top_item)
            if device.exceeds_limit:
                for column in range(4):
                    top_item.setForeground(column, QBrush(QColor("#ef4444")))
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
                if device.exceeds_limit:
                    for column in range(4):
                        child.setForeground(column, QBrush(QColor("#ef4444")))
            top_item.setExpanded(True)

        self._network_tree.resizeColumnToContents(0)

    # ------------------------------------------------------------------
    # Temperature plot helpers
    def _plot_temperatures(self, result: ThermalResult) -> None:
        self._temperature_plot.clear()
        plot_item = self._temperature_plot.getPlotItem()
        if plot_item.legend is None:
            self._temperature_plot.addLegend()
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
        over_limit_devices = 0
        hottest_name = "-"
        hottest_temp = float("-inf")

        for device in result.devices:
            row = self._loss_table.rowCount()
            self._loss_table.insertRow(row)
            percent = (device.total_loss / total_losses) * 100.0
            if device.peak_temperature > hottest_temp:
                hottest_temp = device.peak_temperature
                hottest_name = device.component_name
            if device.exceeds_limit:
                over_limit_devices += 1

            if device.thermal_limit is None:
                status_text = "No limit"
                limit_text = "-"
            elif device.exceeds_limit:
                status_text = "OVERLIMIT"
                limit_text = f"{float(device.thermal_limit):.1f}"
            else:
                status_text = "OK"
                limit_text = f"{float(device.thermal_limit):.1f}"

            values = [
                device.component_name,
                f"{device.conduction_loss:.2f}",
                f"{device.switching_loss_on:.2f}",
                f"{device.switching_loss_off:.2f}",
                f"{device.reverse_recovery_loss:.2f}",
                f"{device.switching_loss:.2f}",
                f"{device.total_loss:.2f}",
                f"{percent:.1f}%",
                f"{device.peak_temperature:.1f}",
                limit_text,
                status_text,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if device.exceeds_limit:
                    item.setForeground(QBrush(QColor("#ef4444")))
                elif column == 10 and status_text == "OK":
                    item.setForeground(QBrush(QColor("#22c55e")))
                self._loss_table.setItem(row, column, item)

        self._render_loss_chart(result)
        self._loss_caption.setText(
            "Total loss: "
            f"{result.total_losses():.2f} W    Ambient: {result.ambient_temperature:.1f} °C"
            f"    Over limit: {over_limit_devices}"
            f"    Hottest: {hottest_name} ({hottest_temp:.1f} °C)"
        )

    def _render_loss_chart(self, result: ThermalResult) -> None:
        self._loss_plot.clear()
        palette = self._color_palette()
        x_positions = list(range(len(result.devices)))
        if not x_positions:
            return

        width = 0.17
        conduction_heights = [device.conduction_loss for device in result.devices]
        switching_on_heights = [device.switching_loss_on for device in result.devices]
        switching_off_heights = [device.switching_loss_off for device in result.devices]
        reverse_recovery_heights = [device.reverse_recovery_loss for device in result.devices]

        conduction_bar = pg.BarGraphItem(
            x=[x - (width * 1.5) for x in x_positions],
            height=conduction_heights,
            width=width,
            brush=palette[0],
            pen=pg.mkPen(color=palette[0])
        )
        switching_on_bar = pg.BarGraphItem(
            x=[x - (width * 0.5) for x in x_positions],
            height=switching_on_heights,
            width=width,
            brush=palette[1],
            pen=pg.mkPen(color=palette[1])
        )
        switching_off_bar = pg.BarGraphItem(
            x=[x + (width * 0.5) for x in x_positions],
            height=switching_off_heights,
            width=width,
            brush=palette[2],
            pen=pg.mkPen(color=palette[2])
        )
        reverse_recovery_bar = pg.BarGraphItem(
            x=[x + (width * 1.5) for x in x_positions],
            height=reverse_recovery_heights,
            width=width,
            brush=palette[3],
            pen=pg.mkPen(color=palette[3])
        )
        self._loss_plot.addItem(conduction_bar)
        self._loss_plot.addItem(switching_on_bar)
        self._loss_plot.addItem(switching_off_bar)
        self._loss_plot.addItem(reverse_recovery_bar)

        axis = self._loss_plot.getAxis("bottom")
        axis.setTicks([[ (x, result.devices[x].component_name) for x in x_positions ]])

        legend = self._loss_plot.getPlotItem().legend
        if legend is None:
            legend = self._loss_plot.addLegend()
        legend.clear()
        legend.addItem(conduction_bar, "Conduction")
        legend.addItem(switching_on_bar, "Sw On")
        legend.addItem(switching_off_bar, "Sw Off")
        legend.addItem(reverse_recovery_bar, "Rev Rec")

    # ------------------------------------------------------------------
    def _clear_views(self) -> None:
        self._network_tree.clear()
        self._temperature_plot.clear()
        self._loss_table.setRowCount(0)
        self._loss_plot.clear()
        self._loss_caption.setText("No thermal data available.")
        # pulsim 1.7 — reset coupled-solve view + hide banners so a
        # cleared widget doesn't show stale runaway warnings.
        self._coupled_table.setRowCount(0)
        self._coupled_caption.setText("")
        self._tabs.setTabEnabled(self._coupled_tab_index, False)
        self._runaway_banner.hide()
        self._limit_banner.hide()

    def _color_palette(self) -> list[str]:
        return self._series_palette
