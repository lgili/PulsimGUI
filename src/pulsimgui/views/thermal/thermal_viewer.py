"""UI widgets for the thermal viewer."""

from __future__ import annotations

import math

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

# Temperatures above this threshold are treated as a numeric runaway by
# the display: the loss-temperature feedback solver diverged, or
# pulsim's per-step P_cond reconstruction blew up. Either way, showing
# a bare ``"50000.0"`` in a "Temp (°C)" column misleads the user into
# thinking it's a physical reading. ``300 °C`` is a generous ceiling —
# real silicon T_jmax tops out around 200 °C, so anything above 300 °C
# is unambiguously a numeric artifact.
_T_RUNAWAY_CAP_C = 300.0
_RUNAWAY_TEXT = ">300 °C ⚠"
_RUNAWAY_BG = QColor("#7f1d1d")    # deep red — distinct from amber over-limit
_OVERLIMIT_FG = QColor("#ef4444")  # bright red — matches existing convention


def _temp_display(
    value: float | int | None,
    *,
    runaway: bool = False,
    over_limit: bool = False,
) -> tuple[str, QColor | None, QColor | None]:
    """Format a temperature for the thermal scope's tables.

    Returns ``(text, foreground_color, background_color)`` so each cell
    can be styled consistently. ``None`` means "use the table's
    default colour".

      * ``runaway=True`` OR T > _T_RUNAWAY_CAP_C → "RUNAWAY" badge on
        a dark-red row background. Clipping the displayed value (NOT
        the underlying data) prevents an absurd 130,000 °C reading
        from masquerading as a real measurement.
      * ``over_limit=True`` and finite ≤ _T_RUNAWAY_CAP_C → plain
        formatted number in bright red. Lets the table keep showing
        the actual peak temperature when a device crossed its
        ``thermal_t_max_C`` (already-existing behaviour, just split
        out so the runaway path can stack on top of it).
      * Otherwise → standard one-decimal °C.
    """
    try:
        t = float(value) if value is not None else float("nan")
    except (TypeError, ValueError):
        t = float("nan")

    # NaN / non-finite — show "—" so an empty row doesn't look healthy.
    if not math.isfinite(t):
        return ("—", None, None)

    # Runaway path: divergence reported explicitly OR temp is clearly
    # non-physical. Both lead to the same badge so the user doesn't
    # see different decorations for the same underlying condition.
    if runaway or t > _T_RUNAWAY_CAP_C:
        return (_RUNAWAY_TEXT, QColor("#fee2e2"), _RUNAWAY_BG)

    if over_limit:
        return (f"{t:.1f}", _OVERLIMIT_FG, None)

    return (f"{t:.1f}", None, None)


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

        # 12 columns — Peak T comes BEFORE the Limit + Status pair so a
        # user can glance at the row and read "did the peak overshoot
        # the limit?" left-to-right without their eye jumping around.
        # The T_jmax column makes the absolute headroom explicit on
        # every row (was previously buried in the "Limit (°C)" cell and
        # only legible when the user knew to compare against Peak T).
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
                "T_jmax (°C)",
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

        pulsim 1.7 — when an electrothermal record reports
        ``runaway=True`` (ρ(M·K) ≥ 1, no stable equilibrium), the
        whole row's T_j cells get the RUNAWAY badge so the user sees
        a clear visual cue instead of an absurdly-large temperature.
        The dedicated banner above the tabs is still the headline
        warning; the per-row treatment makes the *which device* part
        impossible to miss.

        Empty tab + caption "no heatsink modeled" when neither result
        list has anything (the legacy isolated thermal path owns the
        T_j answer)."""
        self._coupled_table.setRowCount(0)

        # Split the electrothermal results into stable vs runaway.
        # Stable sinks override the corresponding shared_heatsink
        # record (the electrothermal solve includes the tempco
        # correction); runaway sinks get the badge treatment so the
        # bogus T_j (often >10,000 °C) doesn't appear as a plain
        # number a casual reader might trust.
        eth_by_name = {
            str(rec.get("name") or ""): rec
            for rec in (result.electrothermal_results or [])
            if rec.get("converged") is True
        }
        runaway_by_name = {
            str(rec.get("name") or ""): rec
            for rec in (result.electrothermal_results or [])
            if rec.get("runaway") is True
        }

        had_any_sink = False
        for sh_rec in result.shared_heatsink_results or []:
            sink_name = str(sh_rec.get("name") or "")
            had_any_sink = True
            # Pick the better record per sink. Order of preference:
            # converged electrothermal (carries final_powers_W) →
            # runaway electrothermal (still has T_amb / R_sa) →
            # shared_heatsink (T-independent fallback).
            eth_rec = eth_by_name.get(sink_name)
            runaway_rec = runaway_by_name.get(sink_name)
            sink_is_runaway = runaway_rec is not None
            source = eth_rec if eth_rec is not None else (
                runaway_rec if runaway_rec is not None else sh_rec
            )
            T_amb = float(source.get("T_amb_C") or 0.0)
            # A runaway record has no T_sink_C — pulsim returns the
            # ambient + a diagnostic message instead. Fall back to the
            # shared-heatsink record's T_sink (if any) so the user
            # sees the LAST stable estimate next to the RUNAWAY badge.
            T_sink_val = source.get("T_sink_C")
            if T_sink_val is None and sink_is_runaway:
                T_sink_val = sh_rec.get("T_sink_C")
            T_sink = float(T_sink_val or T_amb)
            devices = source.get("devices") or {}
            powers = source.get(
                "final_powers_W",
                source.get("powers_W") or {},
            )
            if sink_is_runaway:
                # The runaway record's ``devices`` is empty (no
                # equilibrium to report); fall back to the
                # shared-heatsink list of devices so the user can
                # still see WHICH devices are on this sink.
                if not devices:
                    devices = sh_rec.get("devices") or {}
                if not powers:
                    powers = sh_rec.get("powers_W") or {}
            if not isinstance(devices, dict):
                continue
            if not devices:
                continue

            # One row per device under this sink.
            first_row_for_sink = True
            for device_name, T_j in devices.items():
                row = self._coupled_table.rowCount()
                self._coupled_table.insertRow(row)
                t_sink_text, _, t_sink_bg = _temp_display(
                    T_sink, runaway=sink_is_runaway,
                )
                t_j_text, t_j_fg, t_j_bg = _temp_display(
                    T_j, runaway=sink_is_runaway,
                )
                cells = [
                    sink_name if first_row_for_sink else "",
                    f"{T_amb:.1f}" if first_row_for_sink else "",
                    t_sink_text if first_row_for_sink else "",
                    str(device_name),
                    t_j_text,
                    f"{float((powers or {}).get(device_name, 0.0) or 0.0):.2f}",
                ]
                for col, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if col >= 1 and col != 3:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter,
                        )
                    # Paint the runaway-band cells. T_sink only on the
                    # first row of the sink (the others are blank);
                    # T_j on every device row.
                    if col == 2 and first_row_for_sink and t_sink_bg is not None:
                        item.setBackground(QBrush(t_sink_bg))
                        item.setForeground(QBrush(QColor("#fee2e2")))
                    elif col == 4 and t_j_bg is not None:
                        item.setBackground(QBrush(t_j_bg))
                        item.setForeground(QBrush(QColor("#fee2e2")))
                    elif col == 4 and t_j_fg is not None:
                        item.setForeground(QBrush(t_j_fg))
                    self._coupled_table.setItem(row, col, item)
                first_row_for_sink = False

        # Mark sinks that ran the electrothermal solve but weren't
        # also in the shared_heatsink list (defensive — descriptor
        # parity is normally enforced by the converter). Uses the
        # same RUNAWAY-aware formatter as the main loop above so a
        # diverged solve here still gets the badge.
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
            first_row_for_sink = True
            for device_name, T_j in devices.items():
                row = self._coupled_table.rowCount()
                self._coupled_table.insertRow(row)
                t_sink_text, _, _ = _temp_display(T_sink)
                t_j_text, t_j_fg, t_j_bg = _temp_display(T_j)
                self._coupled_table.setItem(
                    row, 0, QTableWidgetItem(sink_name if first_row_for_sink else ""),
                )
                self._coupled_table.setItem(
                    row, 1, QTableWidgetItem(f"{T_amb:.1f}" if first_row_for_sink else ""),
                )
                self._coupled_table.setItem(
                    row, 2, QTableWidgetItem(t_sink_text if first_row_for_sink else ""),
                )
                self._coupled_table.setItem(
                    row, 3, QTableWidgetItem(str(device_name)),
                )
                t_j_item = QTableWidgetItem(t_j_text)
                if t_j_bg is not None:
                    t_j_item.setBackground(QBrush(t_j_bg))
                    t_j_item.setForeground(QBrush(QColor("#fee2e2")))
                elif t_j_fg is not None:
                    t_j_item.setForeground(QBrush(t_j_fg))
                self._coupled_table.setItem(row, 4, t_j_item)
                self._coupled_table.setItem(
                    row, 5, QTableWidgetItem(
                        f"{float((powers or {}).get(device_name, 0.0) or 0.0):.2f}",
                    ),
                )
                first_row_for_sink = False

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
            peak_text, peak_fg, peak_bg = _temp_display(
                device.peak_temperature,
                over_limit=device.exceeds_limit,
            )
            is_runaway = peak_text == _RUNAWAY_TEXT
            if device.thermal_limit is not None and not is_runaway:
                temp_text = f"{peak_text} / {float(device.thermal_limit):.1f}"
            else:
                temp_text = peak_text
            top_item = QTreeWidgetItem(
                [
                    device.component_name,
                    "-",
                    "-",
                    temp_text,
                ]
            )
            self._network_tree.addTopLevelItem(top_item)
            if is_runaway:
                for column in range(4):
                    top_item.setForeground(column, QBrush(QColor("#fee2e2")))
                top_item.setBackground(3, QBrush(_RUNAWAY_BG))
            elif device.exceeds_limit:
                for column in range(4):
                    top_item.setForeground(column, QBrush(_OVERLIMIT_FG))
            for stage in device.stages:
                stage_text, stage_fg, stage_bg = _temp_display(
                    stage.temperature,
                    over_limit=device.exceeds_limit and not is_runaway,
                )
                child = QTreeWidgetItem(
                    [
                        stage.name,
                        f"{stage.resistance:.3f}",
                        f"{stage.capacitance:.3f}",
                        stage_text,
                    ]
                )
                top_item.addChild(child)
                if is_runaway:
                    for column in range(4):
                        child.setForeground(column, QBrush(QColor("#fee2e2")))
                    child.setBackground(3, QBrush(_RUNAWAY_BG))
                elif device.exceeds_limit:
                    for column in range(4):
                        child.setForeground(column, QBrush(_OVERLIMIT_FG))
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

        # pulsim 1.7 — flag rows whose displayed peak T is
        # non-physical (>300 °C). The "RUNAWAY" badge supersedes the
        # plain "OVERLIMIT" badge so the user doesn't have to read a
        # confusing number to know "the simulation said this got
        # hotter than the surface of Venus" is not a real reading.
        for device in result.devices:
            row = self._loss_table.rowCount()
            self._loss_table.insertRow(row)
            percent = (device.total_loss / total_losses) * 100.0
            if device.peak_temperature > hottest_temp:
                hottest_temp = device.peak_temperature
                hottest_name = device.component_name
            if device.exceeds_limit:
                over_limit_devices += 1

            peak_text, peak_fg, peak_bg = _temp_display(
                device.peak_temperature,
                over_limit=device.exceeds_limit,
            )
            runaway_row = peak_text == _RUNAWAY_TEXT

            if device.thermal_limit is None:
                status_text = "No limit"
                limit_text = "-"
            elif runaway_row:
                # When the row's peak T tipped over into the runaway
                # band, the conventional "OVERLIMIT" badge undersells
                # the problem — show the louder status so it lines up
                # with the dark-red row background the cell painter
                # applies below.
                status_text = "RUNAWAY"
                limit_text = f"{float(device.thermal_limit):.1f}"
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
                peak_text,
                limit_text,
                status_text,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if runaway_row:
                    # Bright-red text on the dark-red Peak T cell; the
                    # OTHER cells get plain foreground so the row is
                    # still readable.
                    if column == 8:  # Peak T column
                        item.setForeground(QBrush(QColor("#fee2e2")))
                        item.setBackground(QBrush(_RUNAWAY_BG))
                    elif column == 10:  # Status column
                        item.setForeground(QBrush(QColor("#fee2e2")))
                        item.setBackground(QBrush(_RUNAWAY_BG))
                    else:
                        item.setForeground(QBrush(_OVERLIMIT_FG))
                elif device.exceeds_limit:
                    item.setForeground(QBrush(_OVERLIMIT_FG))
                elif column == 10 and status_text == "OK":
                    item.setForeground(QBrush(QColor("#22c55e")))
                self._loss_table.setItem(row, column, item)

        self._render_loss_chart(result)
        # Same RUNAWAY treatment for the caption — "Hottest: Q_boost
        # (130,000 °C)" reads like the user owns hardware that survived
        # a star's surface. Cap the displayed value at the runaway
        # threshold so the caption mirrors the table.
        hottest_text, _, _ = _temp_display(hottest_temp)
        self._loss_caption.setText(
            "Total loss: "
            f"{result.total_losses():.2f} W    Ambient: {result.ambient_temperature:.1f} °C"
            f"    Over limit: {over_limit_devices}"
            f"    Hottest: {hottest_name} ({hottest_text})"
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
