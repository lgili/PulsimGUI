"""Waveform viewer widget for displaying simulation results."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer, QMimeData
from PySide6.QtGui import QDrag, QColor, QPalette
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QLabel,
    QCheckBox,
    QGroupBox,
    QSplitter,
    QFrame,
    QGridLayout,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
)

from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.services.theme_service import ThemeService, Theme


# Maximum points to display before decimation kicks in
# Higher = better resolution but slower updates
MAX_DISPLAY_POINTS = 10000
TRACE_PERFORMANCE_THRESHOLD = 5000


# Color palette for traces (distinguishable colors)
TRACE_COLORS = [
    (31, 119, 180),   # Blue
    (255, 127, 14),   # Orange
    (44, 160, 44),    # Green
    (214, 39, 40),    # Red
    (148, 103, 189),  # Purple
    (140, 86, 75),    # Brown
    (227, 119, 194),  # Pink
    (127, 127, 127),  # Gray
    (188, 189, 34),   # Olive
    (23, 190, 207),   # Cyan
]

# Cursor colors
CURSOR_COLORS = [
    (255, 0, 0),     # Red for cursor 1
    (0, 0, 255),     # Blue for cursor 2
]


class DraggableCursor(pg.InfiniteLine):
    """A draggable vertical cursor line."""

    cursor_moved = Signal(float)

    def __init__(self, pos, color, label="", **kwargs):
        pen = pg.mkPen(color=color, width=2, style=Qt.PenStyle.DashLine)
        super().__init__(pos=pos, angle=90, pen=pen, movable=True, **kwargs)
        self._label = label
        self._color = color

        # Add label
        self._text = pg.TextItem(text=label, color=color, anchor=(0.5, 1))
        self._text.setPos(pos, 0)

        self.sigPositionChanged.connect(self._on_position_changed)

    def _on_position_changed(self) -> None:
        """Handle position change."""
        pos = self.value()
        self._text.setPos(pos, 0)
        self.cursor_moved.emit(pos)

    def set_label_y(self, y: float) -> None:
        """Set the Y position of the label."""
        self._text.setPos(self.value(), y)

    def get_text_item(self) -> pg.TextItem:
        """Get the text item for adding to plot."""
        return self._text

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Update cursor line/text colors for active theme changes."""
        self._color = color
        self.setPen(pg.mkPen(color=color, width=2, style=Qt.PenStyle.DashLine))
        self._text.setColor(color)


class MeasurementsPanel(QFrame):
    """Panel displaying cursor measurements and signal statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MeasurementsPanelRoot")
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self._value_style_base = "font-weight: 600; font-size: 11px; font-family: monospace;"
        self._theme: Theme | None = None
        self._muted_labels: list[QLabel] = []
        self._accent_labels: dict[QLabel, str] = {}
        self._separator: QFrame | None = None
        self._cursor_palette: tuple[str, str] | None = None
        self._latest_per_signal: dict[str, dict[str, float | None]] = {}
        self._setup_ui()
        self._apply_styles()

    @staticmethod
    def _compact_header(name: str, max_len: int = 12) -> str:
        if len(name) <= max_len:
            return name
        return f"{name[:max_len - 1]}…"

    @staticmethod
    def _to_hex(color: tuple[int, int, int]) -> str:
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

    def _apply_styles(
        self,
        theme: Theme | None = None,
        cursor_colors: tuple[str, str] | None = None,
    ) -> None:
        """Apply modern styling."""
        if theme is None:
            self.setStyleSheet("""
            QFrame#MeasurementsPanelRoot {
                background-color: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 10px;
                color: #374151;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 7px;
                background-color: #ffffff;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                gridline-color: #e5e7eb;
                color: #111827;
                font-size: 10px;
            }
            QHeaderView::section {
                background-color: #f3f4f6;
                color: #374151;
                border: none;
                border-right: 1px solid #e5e7eb;
                border-bottom: 1px solid #e5e7eb;
                padding: 4px 6px;
                font-size: 10px;
                font-weight: 600;
            }
            """)
            muted_color = "#6b7280"
            accent_colors = {
                "cursor_1": "#dc2626",
                "cursor_2": "#2563eb",
                "delta": "#059669",
                "frequency": "#7c3aed",
                "stat_min": "#0891b2",
                "stat_max": "#dc2626",
                "stat_mean": "#374151",
                "stat_rms": "#7c3aed",
                "stat_pkpk": "#059669",
            }
            separator_color = "#e5e7eb"
        else:
            c = theme.colors
            self.setStyleSheet(f"""
                QFrame#MeasurementsPanelRoot {{
                    background-color: {c.panel_background};
                    border: 1px solid {c.panel_border};
                    border-radius: 10px;
                }}
                QGroupBox {{
                    font-weight: 600;
                    font-size: 10px;
                    color: {c.foreground};
                    border: 1px solid {c.panel_border};
                    border-radius: 8px;
                    margin-top: 12px;
                    padding-top: 10px;
                    background-color: {c.background};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 7px;
                    background-color: {c.background};
                }}
                QTableWidget {{
                    background-color: {c.background};
                    alternate-background-color: {c.panel_background};
                    border: 1px solid {c.panel_border};
                    border-radius: 8px;
                    gridline-color: {c.divider};
                    color: {c.foreground};
                    font-size: 10px;
                }}
                QHeaderView::section {{
                    background-color: {c.panel_background};
                    color: {c.foreground};
                    border: none;
                    border-right: 1px solid {c.divider};
                    border-bottom: 1px solid {c.divider};
                    padding: 4px 6px;
                    font-size: 10px;
                    font-weight: 600;
                }}
                QTableCornerButton::section {{
                    background-color: {c.panel_background};
                    border: none;
                    border-right: 1px solid {c.divider};
                    border-bottom: 1px solid {c.divider};
                }}
            """)
            muted_color = c.foreground_muted
            cursor_1 = cursor_colors[0] if cursor_colors is not None else c.error
            cursor_2 = cursor_colors[1] if cursor_colors is not None else c.primary
            accent_colors = {
                "cursor_1": cursor_1,
                "cursor_2": cursor_2,
                "delta": c.success,
                "frequency": c.info,
                "stat_min": c.info,
                "stat_max": c.error,
                "stat_mean": c.foreground,
                "stat_rms": c.primary,
                "stat_pkpk": c.success,
            }
            separator_color = c.divider

        for label in self._muted_labels:
            label.setStyleSheet(f"color: {muted_color}; font-size: 10px;")

        for label, accent_role in self._accent_labels.items():
            accent = accent_colors.get(accent_role, accent_colors["stat_mean"])
            label.setStyleSheet(f"{self._value_style_base} color: {accent};")

        if self._separator is not None:
            self._separator.setStyleSheet(f"background-color: {separator_color};")

        if hasattr(self, "_multi_table"):
            self._multi_table.viewport().update()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Cursor Measurements (C1 / C2 two-column layout) ──────────────────
        cursor_group = QGroupBox("Cursor Measurements")
        cursor_layout = QGridLayout(cursor_group)
        cursor_layout.setContentsMargins(8, 14, 8, 8)
        cursor_layout.setSpacing(4)
        cursor_layout.setColumnStretch(1, 1)
        cursor_layout.setColumnStretch(2, 1)

        # Column headers
        _empty = QLabel("")
        cursor_layout.addWidget(_empty, 0, 0)
        self._c1_header = QLabel("● C1")
        self._c1_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._accent_labels[self._c1_header] = "cursor_1"
        cursor_layout.addWidget(self._c1_header, 0, 1)
        self._c2_header = QLabel("● C2")
        self._c2_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._accent_labels[self._c2_header] = "cursor_2"
        cursor_layout.addWidget(self._c2_header, 0, 2)

        # Separator under header
        sep_h = QFrame()
        sep_h.setFrameShape(QFrame.Shape.HLine)
        sep_h.setFixedHeight(1)
        self._separator = sep_h
        cursor_layout.addWidget(sep_h, 1, 0, 1, 3)

        # Time row
        lbl_time = QLabel("Time")
        self._muted_labels.append(lbl_time)
        cursor_layout.addWidget(lbl_time, 2, 0)
        self._c1_time = QLabel("---")
        self._c1_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._c1_time] = "cursor_1"
        cursor_layout.addWidget(self._c1_time, 2, 1)
        self._c2_time = QLabel("---")
        self._c2_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._c2_time] = "cursor_2"
        cursor_layout.addWidget(self._c2_time, 2, 2)

        # Value row
        lbl_val = QLabel("Value")
        self._muted_labels.append(lbl_val)
        cursor_layout.addWidget(lbl_val, 3, 0)
        self._c1_value = QLabel("---")
        self._c1_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._c1_value] = "cursor_1"
        cursor_layout.addWidget(self._c1_value, 3, 1)
        self._c2_value = QLabel("---")
        self._c2_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._c2_value] = "cursor_2"
        cursor_layout.addWidget(self._c2_value, 3, 2)

        # Separator before delta
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: transparent; border: none;")
        cursor_layout.addWidget(sep2, 4, 0, 1, 3)

        # Delta row
        lbl_dt = QLabel("Δ Time")
        self._muted_labels.append(lbl_dt)
        cursor_layout.addWidget(lbl_dt, 5, 0)
        self._delta_t = QLabel("---")
        self._delta_t.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._delta_t] = "delta"
        cursor_layout.addWidget(self._delta_t, 5, 1, 1, 2)

        lbl_dv = QLabel("Δ Value")
        self._muted_labels.append(lbl_dv)
        cursor_layout.addWidget(lbl_dv, 6, 0)
        self._delta_v = QLabel("---")
        self._delta_v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._delta_v] = "delta"
        cursor_layout.addWidget(self._delta_v, 6, 1, 1, 2)

        lbl_freq = QLabel("Freq")
        self._muted_labels.append(lbl_freq)
        cursor_layout.addWidget(lbl_freq, 7, 0)
        self._frequency = QLabel("---")
        self._frequency.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._accent_labels[self._frequency] = "frequency"
        cursor_layout.addWidget(self._frequency, 7, 1, 1, 2)

        layout.addWidget(cursor_group)

        # ── Measurements table (channels as columns, metrics as rows) ─────────
        table_group = QGroupBox("Measurements")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(6, 14, 6, 6)
        table_layout.setSpacing(4)

        self._measurement_rows: list[tuple[str, str]] = [
            ("c1", "C1"),
            ("c2", "C2"),
            ("dv", "dV"),
            ("min", "Min"),
            ("max", "Max"),
            ("mean", "Mean"),
            ("rms", "RMS"),
            ("pkpk", "Pk-Pk"),
        ]
        self._multi_table = QTableWidget(len(self._measurement_rows), 0)
        self._multi_table.setVerticalHeaderLabels([label for _, label in self._measurement_rows])
        self._multi_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._multi_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._multi_table.setAlternatingRowColors(True)
        self._multi_table.setWordWrap(False)
        self._multi_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._multi_table.horizontalHeader().setMinimumSectionSize(56)
        self._multi_table.horizontalHeader().setDefaultSectionSize(74)
        self._multi_table.horizontalHeader().setStretchLastSection(False)
        self._multi_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._multi_table.verticalHeader().setDefaultSectionSize(19)
        self._multi_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._multi_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._multi_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._multi_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._multi_table.setMinimumHeight(170)
        self._multi_table.setMaximumHeight(220)
        table_layout.addWidget(self._multi_table)

        layout.addWidget(table_group, stretch=0)
        layout.addStretch(1)

    def _refresh_measurements_table(self) -> None:
        signal_names = list(self._latest_per_signal.keys())
        visible_rows = self._measurement_rows

        self._multi_table.setColumnCount(len(signal_names))
        compact_names = [self._compact_header(name) for name in signal_names]
        self._multi_table.setHorizontalHeaderLabels(compact_names)
        self._multi_table.setRowCount(len(visible_rows))
        self._multi_table.setVerticalHeaderLabels([label for _, label in visible_rows])

        for col, signal_name in enumerate(signal_names):
            header_item = self._multi_table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setToolTip(signal_name)

        for row, (metric_key, _metric_label) in enumerate(visible_rows):
            for col, signal_name in enumerate(signal_names):
                values = self._latest_per_signal.get(signal_name, {})
                item = QTableWidgetItem(self._fmt(values.get(metric_key)))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if self._theme is not None:
                    item.setForeground(QColor(self._theme.colors.foreground))
                self._multi_table.setItem(row, col, item)

    def update_cursor1(self, time: float, value: float | None) -> None:
        """Update cursor 1 display."""
        self._c1_time.setText(f"{time:.6g} s")
        if value is not None:
            self._c1_value.setText(f"{value:.6g}")
        else:
            self._c1_value.setText("---")

    def update_cursor2(self, time: float, value: float | None) -> None:
        """Update cursor 2 display."""
        self._c2_time.setText(f"{time:.6g} s")
        if value is not None:
            self._c2_value.setText(f"{value:.6g}")
        else:
            self._c2_value.setText("---")

    def update_delta(
        self, dt: float, dv: float | None, c1_val: float | None, c2_val: float | None
    ) -> None:
        """Update delta measurements."""
        self._delta_t.setText(f"{dt:.6g} s")

        if dv is not None:
            self._delta_v.setText(f"{dv:.6g}")
        else:
            self._delta_v.setText("---")

        if abs(dt) > 1e-15:
            freq = 1.0 / abs(dt)
            self._frequency.setText(f"{freq:.6g} Hz")
        else:
            self._frequency.setText("---")

    def update_statistics(
        self,
        min_val: float,
        max_val: float,
        mean_val: float,
        rms_val: float,
    ) -> None:
        """Legacy API kept for compatibility; stats now shown in Measurements table."""
        _ = (min_val, max_val, mean_val, rms_val)

    def clear_statistics(self) -> None:
        """Legacy API kept for compatibility; stats now shown in Measurements table."""
        return

    def clear_cursor_measurements(self) -> None:
        """Clear cursor readouts."""
        self._c1_time.setText("---")
        self._c1_value.setText("---")
        self._c2_time.setText("---")
        self._c2_value.setText("---")
        self._delta_t.setText("---")
        self._delta_v.setText("---")
        self._frequency.setText("---")

    @staticmethod
    def _fmt(value: float | None) -> str:
        if value is None:
            return "---"
        return f"{value:.6g}"

    def set_multi_signal_measurements(
        self,
        per_signal: dict[str, dict[str, float | None]],
    ) -> None:
        """Populate measurements table (metrics in rows, channels in columns)."""
        self._latest_per_signal = dict(per_signal)
        self._refresh_measurements_table()

    def apply_theme(self, theme: Theme, cursor_palette: list[tuple[int, int, int]] | None = None) -> None:
        """Apply theme colors to measurement surfaces and readouts."""
        self._theme = theme
        cursor_colors = None
        if cursor_palette is not None and len(cursor_palette) >= 2:
            cursor_colors = (
                self._to_hex(cursor_palette[0]),
                self._to_hex(cursor_palette[1]),
            )
        self._cursor_palette = cursor_colors
        self._apply_styles(theme, cursor_colors=cursor_colors)


class SignalListItem(QListWidgetItem):
    """Custom list item for signals with visibility checkbox."""

    def __init__(self, signal_name: str, color: tuple, parent=None):
        super().__init__(parent)
        self._signal_name = signal_name
        self._color = color
        self._visible = False

        self.setText(signal_name)
        self.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        self.setCheckState(Qt.CheckState.Unchecked)

        # Set color indicator
        self._update_color_display()

    def _update_color_display(self) -> None:
        """Update the color display for this item with a colored dot prefix."""
        r, g, b = self._color
        self.setForeground(QColor(r, g, b))
        # Prefix signal name with a colored bullet
        self.setText(f"●  {self._signal_name}")

    @property
    def signal_name(self) -> str:
        """Get the signal name."""
        return self._signal_name

    @property
    def color(self) -> tuple:
        """Get the signal color."""
        return self._color

    @color.setter
    def color(self, value: tuple) -> None:
        """Set the signal color."""
        self._color = value
        self._update_color_display()

    @property
    def is_visible(self) -> bool:
        """Check if signal is visible on plot."""
        return self.checkState() == Qt.CheckState.Checked

    def set_visible(self, visible: bool) -> None:
        """Set visibility state."""
        self.setCheckState(
            Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        )


class SignalListPanel(QFrame):
    """Panel showing list of available signals with visibility toggles."""

    # Signals
    signal_visibility_changed = Signal(str, bool)  # signal_name, visible
    signal_selected = Signal(str)  # signal_name
    signal_double_clicked = Signal(str)  # signal_name (for adding to plot)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SignalListPanelRoot")
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)

        self._signal_items: dict[str, SignalListItem] = {}
        self._color_index = 0
        self._trace_palette = TRACE_COLORS.copy()
        self._compact_min_rows = 2
        self._compact_max_rows = 7
        self._root_layout: QVBoxLayout | None = None
        self._header_row: QWidget | None = None
        self._theme: Theme | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        from PySide6.QtWidgets import QLineEdit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        self._root_layout = layout

        # Header row: title only
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        self._header_label = QLabel("Signals")
        self._header_label.setStyleSheet("font-weight: 600;")
        header_layout.addWidget(self._header_label, stretch=1)
        self._header_row = header_row
        layout.addWidget(header_row)

        # Filter/search box
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter signals…")
        self._filter_edit.setObjectName("signalFilterEdit")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter_edit)

        # Signal list
        self._list_widget = QListWidget()
        self._list_widget.setDragEnabled(True)
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_widget.itemChanged.connect(self._on_item_changed)
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget)
        layout.addStretch(1)

        self._update_compact_height()

    def _row_height_hint(self) -> int:
        if self._list_widget.count() > 0:
            row_hint = self._list_widget.sizeHintForRow(0)
            if row_hint > 0:
                return row_hint
        return max(20, self.fontMetrics().height() + 8)

    def _update_compact_height(self) -> None:
        if self._root_layout is None or self._header_row is None:
            return

        row_height = self._row_height_hint()
        item_count = self._list_widget.count()
        visible_rows = min(max(item_count, self._compact_min_rows), self._compact_max_rows)

        list_height = (self._list_widget.frameWidth() * 2) + (visible_rows * row_height) + 4
        self._list_widget.setMinimumHeight(list_height)
        self._list_widget.setMaximumHeight(list_height)

        margins = self._root_layout.contentsMargins()
        spacing = self._root_layout.spacing()
        header_h = self._header_row.sizeHint().height()
        filter_h = self._filter_edit.sizeHint().height() if hasattr(self, "_filter_edit") else 0
        total_height = (
            margins.top()
            + margins.bottom()
            + header_h
            + spacing
            + filter_h
            + spacing
            + list_height
            + spacing
        )

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(total_height)

    def set_signals(self, signal_names: list[str]) -> None:
        """Set the list of available signals (flat, no categories)."""
        self._list_widget.clear()
        self._signal_items.clear()
        self._color_index = 0

        flt = self._filter_edit.text().strip().lower() if hasattr(self, "_filter_edit") else ""
        for name in signal_names:
            color = self._trace_palette[self._color_index % len(self._trace_palette)]
            self._color_index += 1

            item = SignalListItem(name, color)
            self._list_widget.addItem(item)
            self._signal_items[name] = item
            if flt and flt not in name.lower():
                item.setHidden(True)

        self._update_compact_height()

    def set_signals_with_categories(
        self,
        signal_names: list[str],
        categories: dict[str, str],
    ) -> None:
        """Set signals grouped under ELECTRICAL / CONTROL / THERMAL headers."""
        self._list_widget.clear()
        self._signal_items.clear()
        self._color_index = 0

        # Group signals preserving insertion order
        groups: dict[str, list[str]] = {"ELECTRICAL": [], "CONTROL": [], "THERMAL": []}
        for name in signal_names:
            cat = categories.get(name, "CONTROL")
            groups.setdefault(cat, []).append(name)

        flt = self._filter_edit.text().strip().lower() if hasattr(self, "_filter_edit") else ""

        for cat_name, names in groups.items():
            if not names:
                continue

            # Category header item
            header = QListWidgetItem(cat_name)
            header.setFlags(Qt.ItemFlag.NoItemFlags)  # non-interactive
            header.setData(Qt.ItemDataRole.UserRole, "__category_header__")
            self._list_widget.addItem(header)
            self._apply_category_header_style(header)

            for name in names:
                color = self._trace_palette[self._color_index % len(self._trace_palette)]
                self._color_index += 1
                item = SignalListItem(name, color)
                self._list_widget.addItem(item)
                self._signal_items[name] = item
                if flt and flt not in name.lower():
                    item.setHidden(True)

        self._update_compact_height()

    def _apply_category_header_style(self, header: QListWidgetItem) -> None:
        """Style a category header list item."""
        font = header.font()
        font.setPointSize(max(font.pointSize() - 1, 7))
        font.setBold(True)
        header.setFont(font)
        if self._theme is not None:
            header.setForeground(QColor(self._theme.colors.foreground_muted))
        else:
            header.setForeground(QColor("#6b7280"))



    def set_trace_palette(self, palette: list[tuple[int, int, int]]) -> None:
        """Update signal color palette and refresh existing list colors."""
        self._trace_palette = palette[:] if palette else TRACE_COLORS.copy()
        for index, item in enumerate(self._signal_items.values()):
            item.color = self._trace_palette[index % len(self._trace_palette)]

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme to the signal list panel surfaces."""
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(f"""
            QFrame#SignalListPanelRoot {{
                background-color: {c.panel_background};
                border: 1px solid {c.panel_border};
                border-radius: 10px;
            }}
            QListWidget {{
                background-color: {c.background};
                border: 1px solid {c.panel_border};
                border-radius: 8px;
                color: {c.foreground};
            }}
            QListWidget::item {{
                padding: 4px 6px;
                border-radius: 6px;
                margin: 1px 3px;
            }}
            QListWidget::item:selected {{
                background-color: {c.tree_item_selected};
                color: {c.foreground};
            }}
            QListWidget::item:hover {{
                background-color: {c.tree_item_hover};
            }}
            QLineEdit#signalFilterEdit {{
                background-color: {c.input_background};
                color: {c.foreground};
                border: 1px solid {c.input_border};
                border-radius: 7px;
                padding: 4px 8px;
                font-size: 10px;
            }}
            QLineEdit#signalFilterEdit:hover {{
                border-color: {c.input_focus_border};
            }}
        """)
        self._header_label.setStyleSheet(f"font-weight: 600; color: {c.foreground};")
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == "__category_header__":
                self._apply_category_header_style(item)
        self._update_compact_height()

    def get_signal_color(self, signal_name: str) -> tuple | None:
        """Get the color assigned to a signal."""
        if signal_name in self._signal_items:
            return self._signal_items[signal_name].color
        return None

    def set_signal_color(self, signal_name: str, color: tuple[int, int, int]) -> None:
        """Override display color for a specific signal."""
        if signal_name in self._signal_items:
            self._signal_items[signal_name].color = color

    def set_signal_visible(self, signal_name: str, visible: bool) -> None:
        """Set visibility state for a signal."""
        if signal_name in self._signal_items:
            # Block signals to prevent recursive updates
            self._list_widget.blockSignals(True)
            self._signal_items[signal_name].set_visible(visible)
            self._list_widget.blockSignals(False)

    def get_visible_signals(self) -> list[str]:
        """Get list of visible signal names."""
        return [
            name
            for name, item in self._signal_items.items()
            if item.is_visible
        ]

    def _on_item_changed(self, item: SignalListItem) -> None:
        """Handle item checkbox state change."""
        if isinstance(item, SignalListItem):
            self.signal_visibility_changed.emit(
                item.signal_name, item.is_visible
            )

    def _on_item_clicked(self, item: SignalListItem) -> None:
        """Handle item click (selection)."""
        if isinstance(item, SignalListItem):
            self.signal_selected.emit(item.signal_name)

    def _on_item_double_clicked(self, item: SignalListItem) -> None:
        """Handle item double-click (add to plot)."""
        if isinstance(item, SignalListItem):
            # Toggle visibility on double-click
            item.set_visible(not item.is_visible)
            self.signal_visibility_changed.emit(
                item.signal_name, item.is_visible
            )

    def _show_all(self) -> None:
        """Show all signals."""
        for name, item in self._signal_items.items():
            if not item.is_visible:
                item.set_visible(True)
                self.signal_visibility_changed.emit(name, True)

    def _hide_all(self) -> None:
        """Hide all signals."""
        for name, item in self._signal_items.items():
            if item.is_visible:
                item.set_visible(False)
                self.signal_visibility_changed.emit(name, False)

    def _on_filter_changed(self, text: str) -> None:
        """Filter list items by name."""
        flt = text.strip().lower()
        for name, item in self._signal_items.items():
            item.setHidden(bool(flt) and flt not in name.lower())

    def clear(self) -> None:
        """Clear all signals."""
        self._list_widget.clear()
        self._signal_items.clear()
        self._color_index = 0
        self._update_compact_height()


class WaveformViewer(QWidget):
    """Widget for displaying simulation waveforms using PyQtGraph."""

    def __init__(self, theme_service: ThemeService | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("WaveformViewerRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._theme_service = theme_service
        self._theme: Theme | None = None
        self._result: SimulationResult | None = None
        self._traces: dict[str, pg.PlotDataItem] = {}
        self._color_index = 0
        self._trace_palette = TRACE_COLORS.copy()
        self._cursor_palette = CURSOR_COLORS.copy()
        self._trace_styles: dict[str, dict[str, object]] = {}
        self._default_trace_width = 1.0
        self._time_array: np.ndarray | None = None
        self._signal_arrays: dict[str, np.ndarray] = {}
        self._signal_statistics: dict[str, dict[str, float]] = {}

        # Cursors
        self._cursor1: DraggableCursor | None = None
        self._cursor2: DraggableCursor | None = None
        self._cursors_visible = False
        self._active_signal: str | None = None
        self._manual_signal_add_enabled = True
        self._auto_show_all_signals = False

        # Zoom history for back/forward navigation
        self._zoom_history: list[tuple] = []
        self._zoom_history_index = -1
        self._recording_zoom = True

        # Streaming data buffers
        self._streaming = False
        self._streaming_time: list[float] = []
        self._streaming_signals: dict[str, list[float]] = {}
        self._streaming_traces: dict[str, pg.PlotDataItem] = {}
        self._auto_scroll = True
        self._scroll_window = 0.001  # Default 1ms window

        # Update timer for batching streaming updates
        self._update_timer = QTimer()
        self._update_timer.setInterval(16)  # 60 Hz update rate for smooth animation
        self._update_timer.timeout.connect(self._flush_streaming_data)
        self._pending_updates = False
        self._last_displayed_index = 0  # Track how much data we've shown

        # Stats overlay text item (top-right corner of plot)
        self._stats_overlay: pg.TextItem | None = None
        # Hover line and tooltip for mouse-over inspection
        self._hover_vline: pg.InfiniteLine | None = None
        self._hover_tooltip: pg.TextItem | None = None

        # Configure pyqtgraph
        pg.setConfigOptions(antialias=False)

        self._setup_ui()
        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self.apply_theme)
            self.apply_theme(self._theme_service.current_theme)

    def _setup_ui(self) -> None:
        """Set up the widget UI — 3-column layout: signal list | plot | measurements."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Main 3-column splitter ────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── LEFT: Signal list panel ───────────────────────────────────────────
        self._signal_list_panel = SignalListPanel()
        self._signal_list_panel.setMinimumWidth(165)
        self._signal_list_panel.setMaximumWidth(300)
        self._signal_list_panel.signal_visibility_changed.connect(
            self._on_signal_visibility_changed
        )
        self._signal_list_panel.signal_selected.connect(self._on_signal_list_selected)
        splitter.addWidget(self._signal_list_panel)

        # ── CENTER: Plot container ────────────────────────────────────────────
        plot_container = QWidget()
        plot_container.setObjectName("waveformPlotCard")
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(10, 10, 10, 10)
        plot_layout.setSpacing(10)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("left", "Value")
        self._plot_widget.setLabel("bottom", "Time", units="s")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setBackground("w")

        view_box = self._plot_widget.getViewBox()
        view_box.setMouseMode(pg.ViewBox.RectMode)
        view_box.sigRangeChanged.connect(self._on_range_changed)
        view_box.sigRangeChanged.connect(self._reanchor_stats_overlay)

        # Stats overlay (top-right of plot)
        self._stats_overlay = pg.TextItem(
            text="",
            anchor=(1, 0),
            color="#374151",
            fill=pg.mkBrush(255, 255, 255, 200),
        )
        self._stats_overlay.setFont(pg.QtGui.QFont("Courier New", 10))
        self._stats_overlay.setZValue(100)
        self._plot_widget.addItem(self._stats_overlay)
        self._stats_overlay.setVisible(False)

        # Hover vertical line + tooltip
        self._hover_vline = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(color="#6b7280", width=1, style=Qt.PenStyle.DashLine),
        )
        self._hover_vline.setZValue(90)
        self._hover_vline.setVisible(False)
        self._plot_widget.addItem(self._hover_vline)

        self._hover_tooltip = pg.TextItem(
            text="",
            anchor=(0, 1),
            fill=pg.mkBrush(30, 30, 30, 215),
        )
        self._hover_tooltip.setFont(pg.QtGui.QFont("Courier New", 9))
        self._hover_tooltip.setZValue(101)
        self._hover_tooltip.setVisible(False)
        self._plot_widget.addItem(self._hover_tooltip)

        # Connect mouse move to hover handler
        self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Legend
        self._legend = self._plot_widget.addLegend(offset=(12, 10))
        self._legend.setLabelTextColor("#111827")

        plot_layout.addWidget(self._plot_widget)

        # ── Controls bar ─────────────────────────────────────────────────────
        controls = QWidget()
        controls.setObjectName("waveformControlsBar")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(10, 8, 10, 8)
        controls_layout.setSpacing(8)

        self._add_signal_label = QLabel("Signal:")
        controls_layout.addWidget(self._add_signal_label)
        self._signal_combo = QComboBox()
        self._signal_combo.setMinimumWidth(160)
        self._signal_combo.currentTextChanged.connect(self._on_signal_selected)
        controls_layout.addWidget(self._signal_combo)

        self._add_signal_btn = QPushButton("Add")
        self._add_signal_btn.clicked.connect(self._on_add_signal)
        controls_layout.addWidget(self._add_signal_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self.clear_traces)
        controls_layout.addWidget(self._clear_btn)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedWidth(1)
        controls_layout.addWidget(sep1)

        self._back_btn = QPushButton("\u25c0")
        self._back_btn.setToolTip("Previous zoom")
        self._back_btn.setMaximumWidth(30)
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._zoom_back)
        controls_layout.addWidget(self._back_btn)

        self._forward_btn = QPushButton("\u25b6")
        self._forward_btn.setToolTip("Next zoom")
        self._forward_btn.setMaximumWidth(30)
        self._forward_btn.setEnabled(False)
        self._forward_btn.clicked.connect(self._zoom_forward)
        controls_layout.addWidget(self._forward_btn)

        auto_btn = QPushButton("Fit")
        auto_btn.setToolTip("Zoom to fit all")
        auto_btn.clicked.connect(self._auto_range)
        controls_layout.addWidget(auto_btn)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFixedWidth(1)
        controls_layout.addWidget(sep2)

        self._grid_checkbox = QCheckBox("Grid")
        self._grid_checkbox.setChecked(True)
        self._grid_checkbox.toggled.connect(self._toggle_grid)
        controls_layout.addWidget(self._grid_checkbox)

        self._cursor_checkbox = QCheckBox("Cursors")
        self._cursor_checkbox.setChecked(False)
        self._cursor_checkbox.toggled.connect(self._toggle_cursors)
        controls_layout.addWidget(self._cursor_checkbox)

        self._auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self._auto_scroll_checkbox.setChecked(True)
        self._auto_scroll_checkbox.setToolTip("Auto-scroll during simulation")
        self._auto_scroll_checkbox.toggled.connect(self._toggle_auto_scroll)
        controls_layout.addWidget(self._auto_scroll_checkbox)

        controls_layout.addStretch()

        plot_layout.addWidget(controls)
        splitter.addWidget(plot_container)

        # ── RIGHT: Measurements panel ─────────────────────────────────────────
        self._measurements_panel = MeasurementsPanel()
        self._measurements_panel.setMinimumWidth(240)
        self._measurements_panel.setMaximumWidth(460)
        splitter.addWidget(self._measurements_panel)

        splitter.setStretchFactor(0, 0)   # signal list: fixed
        splitter.setStretchFactor(1, 1)   # plot: expands
        splitter.setStretchFactor(2, 0)   # measurements: fixed
        splitter.setSizes([200, 700, 280])

        layout.addWidget(splitter)
        self._update_manual_signal_add_controls()

    def set_manual_signal_add_enabled(self, enabled: bool) -> None:
        """Enable/disable manual signal add controls."""
        self._manual_signal_add_enabled = bool(enabled)
        self._update_manual_signal_add_controls()

    def set_auto_show_all_signals(self, enabled: bool) -> None:
        """Control whether all available signals are auto-plotted on new results."""
        self._auto_show_all_signals = bool(enabled)

    def set_default_trace_width(self, width: float) -> None:
        """Set default line width used when no per-signal style is provided."""
        self._default_trace_width = max(0.5, float(width))
        self._reapply_trace_pens()

    def set_trace_styles(self, styles: dict[str, dict[str, object]]) -> None:
        """Set per-signal style overrides for color and line width."""
        normalized: dict[str, dict[str, object]] = {}
        for signal_name, raw in styles.items():
            if not isinstance(raw, dict):
                continue
            style: dict[str, object] = {}
            color_raw = raw.get("color")
            if (
                isinstance(color_raw, tuple)
                and len(color_raw) == 3
                and all(isinstance(channel, (int, float)) for channel in color_raw)
            ):
                style["color"] = tuple(int(channel) for channel in color_raw)
            width_raw = raw.get("width")
            if isinstance(width_raw, (int, float)):
                style["width"] = max(0.5, float(width_raw))
            if style:
                normalized[signal_name] = style

        self._trace_styles = normalized
        self._refresh_signal_list_colors()
        self._reapply_trace_pens()

    def _refresh_signal_list_colors(self) -> None:
        self._signal_list_panel.set_trace_palette(self._trace_palette)
        for signal_name, style in self._trace_styles.items():
            color = style.get("color")
            if isinstance(color, tuple) and len(color) == 3:
                self._signal_list_panel.set_signal_color(signal_name, color)

    def _on_mouse_moved(self, scene_pos) -> None:
        """Handle mouse movement over the plot — update hover line and tooltip."""
        if self._hover_vline is None or self._hover_tooltip is None:
            return
        vb = self._plot_widget.getViewBox()
        if not vb.sceneBoundingRect().contains(scene_pos):
            self._hover_vline.setVisible(False)
            self._hover_tooltip.setVisible(False)
            return

        mouse_point = vb.mapSceneToView(scene_pos)
        t = mouse_point.x()

        self._hover_vline.setPos(t)
        self._hover_vline.setVisible(True)

        # Build tooltip text
        if self._time_array is not None and len(self._time_array) > 0:
            lines = [f"Time: {self._fmt_time(t)}"]
            for name, values in self._signal_arrays.items():
                if name not in self._traces:
                    continue
                val = self._interpolate_value(self._time_array, values, t)
                if val is not None:
                    color = self._signal_list_panel.get_signal_color(name)
                    lines.append(f"{name}: {val:.6g}")
            self._hover_tooltip.setText("\n".join(lines))

            # Position tooltip near the top of the view near the cursor
            x_range, y_range = vb.viewRange()
            y_top = y_range[1] - (y_range[1] - y_range[0]) * 0.03
            x_pos = t
            # Keep tooltip from going off right edge
            if (t - x_range[0]) / max(x_range[1] - x_range[0], 1e-12) > 0.65:
                self._hover_tooltip.setAnchor((1, 1))
            else:
                self._hover_tooltip.setAnchor((0, 1))
            self._hover_tooltip.setPos(x_pos, y_top)
            self._hover_tooltip.setVisible(True)
        else:
            self._hover_tooltip.setVisible(False)

    @staticmethod
    def _fmt_time(t: float) -> str:
        """Format time value with appropriate unit."""
        abs_t = abs(t)
        if abs_t >= 1.0:
            return f"{t:.4f} s"
        if abs_t >= 1e-3:
            return f"{t * 1e3:.4f} ms"
        if abs_t >= 1e-6:
            return f"{t * 1e6:.4f} \u03bcs"
        return f"{t * 1e9:.4f} ns"

    def _update_stats_overlay(self, signal_name: str | None, stats: dict | None) -> None:
        """Update the floating stats text item in the top-right of the plot."""
        if self._stats_overlay is None:
            return
        if stats is None or signal_name is None:
            self._stats_overlay.setVisible(False)
            return

        fmt = "{:.6g}"
        lines = [
            f"{signal_name}",
            f"RMS:   {fmt.format(stats.get('rms', 0))}",
            f"Peak:  {fmt.format(stats.get('max', 0))}",
            f"Avg:   {fmt.format(stats.get('mean', 0))}",
            f"Min:   {fmt.format(stats.get('min', 0))}",
            f"Max:   {fmt.format(stats.get('max', 0))}",
        ]
        self._stats_overlay.setText("\n".join(lines))
        self._stats_overlay.setVisible(True)
        self._reanchor_stats_overlay()

    def _reanchor_stats_overlay(self) -> None:
        """Position stats overlay in the top-right corner of the current view."""
        if self._stats_overlay is None or not self._stats_overlay.isVisible():
            return
        vb = self._plot_widget.getViewBox()
        x_range, y_range = vb.viewRange()
        # Anchor to top-right, with a small margin
        margin_x = (x_range[1] - x_range[0]) * 0.01
        margin_y = (y_range[1] - y_range[0]) * 0.02
        self._stats_overlay.setPos(x_range[1] - margin_x, y_range[1] - margin_y)

    @staticmethod
    def _extract_pen_color(trace: pg.PlotDataItem) -> tuple[int, int, int] | None:
        pen = trace.opts.get("pen")
        if pen is None:
            return None
        qcolor = pen.color()
        return qcolor.red(), qcolor.green(), qcolor.blue()

    def _resolve_trace_pen(
        self,
        signal_name: str,
        fallback_color: tuple[int, int, int],
    ):
        style = self._trace_styles.get(signal_name, {})
        color = style.get("color")
        if not (isinstance(color, tuple) and len(color) == 3):
            color = fallback_color
        width_raw = style.get("width")
        if isinstance(width_raw, (int, float)):
            width = max(0.5, float(width_raw))
        else:
            width = self._default_trace_width
        return pg.mkPen(color=color, width=width)

    def _reapply_trace_pens(self) -> None:
        for signal_name, trace in self._traces.items():
            color = self._signal_list_panel.get_signal_color(signal_name)
            fallback_color = color or self._extract_pen_color(trace) or self._trace_palette[0]
            trace.setPen(self._resolve_trace_pen(signal_name, fallback_color))

        for signal_name, trace in self._streaming_traces.items():
            fallback_color = self._extract_pen_color(trace) or self._trace_palette[0]
            trace.setPen(self._resolve_trace_pen(signal_name, fallback_color))

    @staticmethod
    def _configure_trace_performance(trace: pg.PlotDataItem, point_count: int) -> None:
        """Enable rendering options that keep interaction responsive on dense traces."""
        if point_count < TRACE_PERFORMANCE_THRESHOLD:
            return
        trace.setClipToView(True)
        trace.setDownsampling(auto=True, method="peak")

    def _rebuild_result_caches(self) -> None:
        """Cache numeric arrays and per-signal statistics for fast cursor/UI updates."""
        self._time_array = None
        self._signal_arrays = {}
        self._signal_statistics = {}

        if not self._result or not self._result.time:
            return

        time = np.asarray(self._result.time, dtype=float)
        if len(time) == 0:
            return
        self._time_array = time

        for signal_name, values_raw in self._result.signals.items():
            values = np.asarray(values_raw, dtype=float)
            if len(values) != len(time) or len(values) == 0:
                continue
            self._signal_arrays[signal_name] = values
            min_val = float(np.min(values))
            max_val = float(np.max(values))
            mean_val = float(np.mean(values))
            rms_val = float(np.sqrt(np.mean(values ** 2)))
            self._signal_statistics[signal_name] = {
                "min": min_val,
                "max": max_val,
                "mean": mean_val,
                "rms": rms_val,
                "pkpk": max_val - min_val,
            }

    def cursor_state(self) -> tuple[bool, float | None, float | None]:
        """Return cursor enabled flag and current positions."""
        enabled = bool(self._cursor_checkbox.isChecked())
        c1 = float(self._cursor1.value()) if self._cursor1 is not None else None
        c2 = float(self._cursor2.value()) if self._cursor2 is not None else None
        return enabled, c1, c2

    def set_cursor_state(
        self,
        enabled: bool,
        c1: float | None = None,
        c2: float | None = None,
    ) -> None:
        """Set cursor enabled flag and optionally sync cursor positions."""
        enabled = bool(enabled)
        if self._cursor_checkbox.isChecked() != enabled:
            self._cursor_checkbox.setChecked(enabled)

        if not enabled or self._cursor1 is None or self._cursor2 is None:
            return

        if c1 is not None and c2 is not None:
            self._set_cursor_positions(c1, c2)

    def _update_manual_signal_add_controls(self) -> None:
        show = self._manual_signal_add_enabled
        self._add_signal_label.setVisible(show)
        self._signal_combo.setVisible(show)
        self._add_signal_btn.setVisible(show)

    def _set_cursor_positions(self, c1: float, c2: float) -> None:
        if self._cursor1 is None or self._cursor2 is None:
            return

        c1_clamped = self._clamp_cursor_time(c1)
        c2_clamped = self._clamp_cursor_time(c2)

        self._cursor1.blockSignals(True)
        self._cursor2.blockSignals(True)
        try:
            self._cursor1.setValue(c1_clamped)
            self._cursor2.setValue(c2_clamped)
        finally:
            self._cursor1.blockSignals(False)
            self._cursor2.blockSignals(False)
        self._update_cursor_values()

    def _clamp_cursor_time(self, value: float) -> float:
        if not self._result or not self._result.time:
            return float(value)
        t_min = float(min(self._result.time))
        t_max = float(max(self._result.time))
        return float(min(max(value, t_min), t_max))

    @staticmethod
    def _rgb_to_hex(color: tuple[int, int, int]) -> str:
        """Convert RGB tuple to hex string."""
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to plot surfaces and side panels."""
        self._theme = theme
        c = theme.colors
        is_dark = theme.is_dark
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(c.background))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        if self._theme_service is not None:
            self._trace_palette = self._theme_service.get_trace_palette(theme)
            self._cursor_palette = self._theme_service.get_cursor_palette(theme)

        plot_bg = QColor(c.plot_background)
        if not is_dark:
            plot_bg = plot_bg.darker(104)
        self._plot_widget.setBackground(plot_bg)
        self._plot_widget.showGrid(x=self._grid_checkbox.isChecked(), y=self._grid_checkbox.isChecked(), alpha=0.18 if is_dark else 0.28)
        plot_item = self._plot_widget.getPlotItem()
        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen(c.plot_axis))
            axis.setTickPen(pg.mkPen(c.plot_axis))
            axis.setTextPen(pg.mkPen(c.plot_text))
        self._legend.setLabelTextColor(c.plot_text)
        legend_bg = QColor(c.plot_legend_background)
        legend_bg.setAlpha(210 if is_dark else 235)
        self._legend.setBrush(pg.mkBrush(legend_bg))
        self._legend.setPen(pg.mkPen(c.plot_legend_border))

        self._refresh_signal_list_colors()
        self._signal_list_panel.apply_theme(theme)
        self._measurements_panel.apply_theme(theme, cursor_palette=self._cursor_palette)

        self.setStyleSheet(f"""
            QWidget#WaveformViewerRoot {{
                background-color: {c.background};
            }}
            QWidget#waveformPlotCard {{
                background-color: {c.background};
                border: 1px solid {c.panel_border};
                border-radius: 12px;
            }}
            QFrame {{
                color: {c.foreground};
            }}
            QWidget#waveformControlsBar {{
                background-color: {c.background_alt};
                border: 1px solid {c.panel_border};
                border-radius: 10px;
            }}
            QWidget#waveformControlsBar QLabel {{
                color: {c.foreground_muted};
                font-size: 10px;
                font-weight: 600;
            }}
            QWidget#waveformControlsBar QComboBox,
            QWidget#waveformControlsBar QPushButton {{
                background-color: {c.input_background};
                color: {c.foreground};
                border: 1px solid {c.input_border};
                border-radius: 7px;
                padding: 3px 8px;
                min-height: 24px;
                max-height: 26px;
            }}
            QWidget#waveformControlsBar QPushButton:hover,
            QWidget#waveformControlsBar QComboBox:hover {{
                border-color: {c.input_focus_border};
            }}
            QWidget#waveformControlsBar QPushButton:pressed {{
                background-color: {c.primary};
                color: {c.primary_foreground};
                border-color: {c.primary};
            }}
            QWidget#waveformControlsBar QCheckBox {{
                color: {c.foreground};
                spacing: 4px;
                margin: 0;
                padding: 0;
                font-size: 11px;
            }}
        """)

        self._reapply_trace_pens()

        if self._cursor1 is not None:
            self._cursor1.set_color(self._cursor_palette[0])
        if self._cursor2 is not None:
            self._cursor2.set_color(self._cursor_palette[1])

        # Update stats overlay colors for the new theme
        if self._stats_overlay is not None:
            is_dark = getattr(theme, "is_dark", False)
            if is_dark:
                self._stats_overlay.setColor(c.plot_text)
                self._stats_overlay.fill = pg.mkBrush(30, 30, 30, 210)
            else:
                self._stats_overlay.setColor(c.plot_axis)
                self._stats_overlay.fill = pg.mkBrush(255, 255, 255, 210)
            self._stats_overlay.update()

        # Update hover tooltip colors for the new theme
        if self._hover_tooltip is not None:
            is_dark = getattr(theme, "is_dark", False)
            if is_dark:
                self._hover_tooltip.setColor("#e5e7eb")
                self._hover_tooltip.fill = pg.mkBrush(24, 24, 24, 220)
            else:
                self._hover_tooltip.setColor("#1f2937")
                self._hover_tooltip.fill = pg.mkBrush(255, 255, 255, 220)
            self._hover_tooltip.update()
        if self._hover_vline is not None:
            self._hover_vline.setPen(pg.mkPen(color=c.plot_axis, width=1, style=Qt.PenStyle.DashLine))

    def set_result(self, result: SimulationResult) -> None:
        """Set the simulation result to display."""
        self._result = result
        self._rebuild_result_caches()
        self._update_signal_combo()

        # Clear existing traces and zoom history
        self.clear_traces()
        self._zoom_history.clear()
        self._zoom_history_index = -1
        self._update_navigation_buttons()

        # Remove cursors
        self._remove_cursors()

        # Update signal list panel
        if result.signals:
            signal_names = list(result.signals.keys())
            self._signal_list_panel.set_signals(signal_names)
            self._refresh_signal_list_colors()
            first_signal = signal_names[0]
            self._active_signal = first_signal

            if self._auto_show_all_signals:
                for signal_name in signal_names:
                    self.add_trace(signal_name)
                    self._signal_list_panel.set_signal_visible(signal_name, True)
            else:
                # Auto-add first signal if available
                self.add_trace(first_signal)
                self._signal_list_panel.set_signal_visible(first_signal, True)

            # Auto-range to fit new data (ensures time axis updates)
            self._auto_range()
        else:
            self._signal_list_panel.clear()
            self._active_signal = None
        self._refresh_measurements_table()

    def _update_signal_combo(self) -> None:
        """Update the signal combo box with available signals."""
        self._signal_combo.clear()
        if self._result:
            self._signal_combo.addItems(list(self._result.signals.keys()))

    def _measurement_signal_names(self) -> list[str]:
        return list(self._signal_arrays.keys())

    def _build_per_signal_measurements(
        self,
        t1: float | None = None,
        t2: float | None = None,
    ) -> dict[str, dict[str, float | None]]:
        if self._time_array is None or not self._signal_arrays:
            return {}

        measurements: dict[str, dict[str, float | None]] = {}
        time = self._time_array
        for signal_name, values in self._signal_arrays.items():
            stats = self._signal_statistics.get(signal_name)
            if stats is None:
                continue

            c1_val = self._interpolate_value(time, values, t1) if t1 is not None else None
            c2_val = self._interpolate_value(time, values, t2) if t2 is not None else None
            dv = c2_val - c1_val if c1_val is not None and c2_val is not None else None
            measurements[signal_name] = {
                "c1": c1_val,
                "c2": c2_val,
                "dv": dv,
                "min": stats["min"],
                "max": stats["max"],
                "mean": stats["mean"],
                "rms": stats["rms"],
                "pkpk": stats["pkpk"],
            }
        return measurements

    def _refresh_measurements_table(
        self,
        t1: float | None = None,
        t2: float | None = None,
    ) -> None:
        self._measurements_panel.set_multi_signal_measurements(
            self._build_per_signal_measurements(t1, t2)
        )

    def add_trace(self, signal_name: str) -> None:
        """Add a trace for the specified signal."""
        if not self._result or signal_name not in self._result.signals:
            return

        if signal_name in self._traces:
            return

        raw_time = self._time_array if self._time_array is not None else np.asarray(self._result.time, dtype=float)
        raw_values = self._signal_arrays.get(signal_name)
        if raw_values is None:
            raw_values = np.asarray(self._result.signals[signal_name], dtype=float)
        time = raw_time
        values = raw_values

        # Decimate if too many points to prevent GUI freeze
        if len(time) > MAX_DISPLAY_POINTS:
            time, values = self._decimate_for_display(time, values)

        # Get color from signal list panel if available, otherwise use default
        color = self._signal_list_panel.get_signal_color(signal_name)
        if color is None:
            color = self._trace_palette[self._color_index % len(self._trace_palette)]
            self._color_index += 1

        pen = self._resolve_trace_pen(signal_name, color)
        trace = self._plot_widget.plot(
            time, values, pen=pen, name=signal_name,
            skipFiniteCheck=True,  # Skip NaN/Inf check (faster)
        )
        self._configure_trace_performance(trace, len(raw_time))
        self._traces[signal_name] = trace

        # Update statistics
        self._update_statistics(signal_name)
        if self._cursor1 is not None and self._cursor2 is not None:
            self._refresh_measurements_table(self._cursor1.value(), self._cursor2.value())
        else:
            self._refresh_measurements_table()

    def _decimate_for_display(
        self, time: np.ndarray, values: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Decimate data for efficient display using min-max bucketing.

        Preserves peaks and visual features while reducing point count.
        """
        n_points = len(time)
        if n_points <= MAX_DISPLAY_POINTS:
            return time, values

        # Calculate bucket size
        n_buckets = MAX_DISPLAY_POINTS // 2  # Each bucket contributes 2 points (min, max)
        bucket_size = n_points // n_buckets

        decimated_time = []
        decimated_values = []

        for i in range(n_buckets):
            start = i * bucket_size
            end = min(start + bucket_size, n_points)
            bucket_values = values[start:end]

            if len(bucket_values) > 0:
                min_idx = start + np.argmin(bucket_values)
                max_idx = start + np.argmax(bucket_values)

                # Add min and max in time order
                if min_idx <= max_idx:
                    decimated_time.extend([time[min_idx], time[max_idx]])
                    decimated_values.extend([values[min_idx], values[max_idx]])
                else:
                    decimated_time.extend([time[max_idx], time[min_idx]])
                    decimated_values.extend([values[max_idx], values[min_idx]])

        return np.array(decimated_time), np.array(decimated_values)

    def remove_trace(self, signal_name: str) -> None:
        """Remove a trace from the plot."""
        if signal_name in self._traces:
            self._plot_widget.removeItem(self._traces[signal_name])
            del self._traces[signal_name]
            if self._active_signal == signal_name:
                self._active_signal = next(iter(self._traces), None)
            if self._cursor1 is not None and self._cursor2 is not None:
                self._refresh_measurements_table(self._cursor1.value(), self._cursor2.value())
            else:
                self._refresh_measurements_table()

    def clear_traces(self) -> None:
        """Remove all traces from the plot."""
        for trace in self._traces.values():
            self._plot_widget.removeItem(trace)
        self._traces.clear()
        self._color_index = 0
        self._legend.clear()
        self._measurements_panel.clear_statistics()
        self._measurements_panel.clear_cursor_measurements()
        self._measurements_panel.set_multi_signal_measurements({})
        if self._stats_overlay is not None:
            self._stats_overlay.setVisible(False)

        # Sync with signal list panel - uncheck all signals
        for signal_name in list(self._signal_list_panel.get_visible_signals()):
            self._signal_list_panel.set_signal_visible(signal_name, False)

    def _on_add_signal(self) -> None:
        """Handle add signal button click."""
        signal_name = self._signal_combo.currentText()
        if signal_name:
            self.add_trace(signal_name)
            # Sync with signal list panel
            self._signal_list_panel.set_signal_visible(signal_name, True)

    def _on_signal_selected(self, signal_name: str) -> None:
        """Handle signal selection change."""
        if signal_name:
            self._active_signal = signal_name
            self._update_statistics(signal_name)
            self._update_cursor_values()
            if self._cursor1 is None or self._cursor2 is None:
                self._refresh_measurements_table()

    def _toggle_grid(self, show: bool) -> None:
        """Toggle grid visibility."""
        alpha = 0.3 if show else 0
        self._plot_widget.showGrid(x=show, y=show, alpha=alpha)

    def _toggle_cursors(self, show: bool) -> None:
        """Toggle cursor visibility."""
        self._cursors_visible = show
        if show:
            self._create_cursors()
        else:
            self._remove_cursors()
            self._measurements_panel.clear_cursor_measurements()
            self._refresh_measurements_table()

    def _create_cursors(self) -> None:
        """Create the two measurement cursors."""
        if not self._result or not self._result.time:
            return

        # Get time range
        time = self._result.time
        t_min, t_max = min(time), max(time)
        t_range = t_max - t_min

        # Position cursors at 1/3 and 2/3 of the range
        c1_pos = t_min + t_range * 0.33
        c2_pos = t_min + t_range * 0.67

        # Create cursor 1
        self._cursor1 = DraggableCursor(c1_pos, self._cursor_palette[0], "C1")
        self._plot_widget.addItem(self._cursor1)
        self._plot_widget.addItem(self._cursor1.get_text_item())
        self._cursor1.cursor_moved.connect(self._on_cursor_moved)

        # Create cursor 2
        self._cursor2 = DraggableCursor(c2_pos, self._cursor_palette[1], "C2")
        self._plot_widget.addItem(self._cursor2)
        self._plot_widget.addItem(self._cursor2.get_text_item())
        self._cursor2.cursor_moved.connect(self._on_cursor_moved)

        # Update values
        self._update_cursor_values()

    def _remove_cursors(self) -> None:
        """Remove the cursors from the plot."""
        if self._cursor1:
            self._plot_widget.removeItem(self._cursor1)
            self._plot_widget.removeItem(self._cursor1.get_text_item())
            self._cursor1 = None

        if self._cursor2:
            self._plot_widget.removeItem(self._cursor2)
            self._plot_widget.removeItem(self._cursor2.get_text_item())
            self._cursor2 = None

    def _on_cursor_moved(self, pos: float) -> None:
        """Handle cursor movement."""
        self._update_cursor_values()

    def _update_cursor_values(self) -> None:
        """Update cursor value displays."""
        if not self._cursor1 or not self._cursor2:
            self._refresh_measurements_table()
            return

        if not self._result or not self._active_signal:
            self._measurements_panel.clear_cursor_measurements()
            self._refresh_measurements_table()
            return

        if self._active_signal not in self._result.signals:
            self._measurements_panel.clear_cursor_measurements()
            self._refresh_measurements_table()
            return

        if self._time_array is None:
            self._measurements_panel.clear_cursor_measurements()
            self._refresh_measurements_table()
            return
        values = self._signal_arrays.get(self._active_signal)
        if values is None:
            self._measurements_panel.clear_cursor_measurements()
            self._refresh_measurements_table()
            return
        time = self._time_array

        # Get cursor positions
        t1 = self._cursor1.value()
        t2 = self._cursor2.value()

        # Interpolate values at cursor positions
        v1 = self._interpolate_value(time, values, t1)
        v2 = self._interpolate_value(time, values, t2)

        # Update display
        self._measurements_panel.update_cursor1(t1, v1)
        self._measurements_panel.update_cursor2(t2, v2)

        # Calculate delta
        dt = t2 - t1
        dv = v2 - v1 if v1 is not None and v2 is not None else None
        self._measurements_panel.update_delta(dt, dv, v1, v2)
        self._refresh_measurements_table(t1, t2)

        self._update_cursor_label_positions()

    def _update_cursor_label_positions(self) -> None:
        """Update only cursor label Y placement without recomputing measurements."""
        if self._cursor1 is None and self._cursor2 is None:
            return
        view_range = self._plot_widget.getViewBox().viewRange()
        y_top = view_range[1][1]
        if self._cursor1:
            self._cursor1.set_label_y(y_top)
        if self._cursor2:
            self._cursor2.set_label_y(y_top)

    def _interpolate_value(
        self, time: np.ndarray, values: np.ndarray, t: float
    ) -> float | None:
        """Interpolate signal value at time t."""
        if len(time) == 0:
            return None

        if t < time[0] or t > time[-1]:
            return None

        # Find index
        idx = np.searchsorted(time, t)

        if idx == 0:
            return float(values[0])
        if idx >= len(time):
            return float(values[-1])

        # Linear interpolation
        t0, t1 = time[idx - 1], time[idx]
        v0, v1 = values[idx - 1], values[idx]

        if t1 == t0:
            return float(v0)

        frac = (t - t0) / (t1 - t0)
        return float(v0 + frac * (v1 - v0))

    def _update_statistics(self, signal_name: str) -> None:
        """Update statistics for the specified signal."""
        stats = self._signal_statistics.get(signal_name)
        if stats is None:
            self._measurements_panel.clear_statistics()
            self._update_stats_overlay(None, None)
            return

        self._measurements_panel.update_statistics(
            stats["min"],
            stats["max"],
            stats["mean"],
            stats["rms"],
        )
        self._update_stats_overlay(signal_name, stats)

    def _auto_range(self) -> None:
        """Auto-range the plot to fit all data."""
        self._plot_widget.autoRange()

    def _on_range_changed(self) -> None:
        """Handle view range change - record for zoom history."""
        if not self._recording_zoom:
            return

        view_box = self._plot_widget.getViewBox()
        x_range, y_range = view_box.viewRange()
        current_range = (tuple(x_range), tuple(y_range))

        if self._zoom_history and self._zoom_history_index >= 0:
            if self._zoom_history[self._zoom_history_index] == current_range:
                return

        if self._zoom_history_index < len(self._zoom_history) - 1:
            self._zoom_history = self._zoom_history[:self._zoom_history_index + 1]

        self._zoom_history.append(current_range)
        self._zoom_history_index = len(self._zoom_history) - 1

        max_history = 50
        if len(self._zoom_history) > max_history:
            self._zoom_history = self._zoom_history[-max_history:]
            self._zoom_history_index = len(self._zoom_history) - 1

        self._update_navigation_buttons()

        # Update cursor label positions
        if self._cursors_visible:
            self._update_cursor_label_positions()

    def _update_navigation_buttons(self) -> None:
        """Update enabled state of back/forward buttons."""
        self._back_btn.setEnabled(self._zoom_history_index > 0)
        self._forward_btn.setEnabled(
            self._zoom_history_index < len(self._zoom_history) - 1
        )

    def _zoom_back(self) -> None:
        """Go to previous zoom level."""
        if self._zoom_history_index > 0:
            self._zoom_history_index -= 1
            self._apply_zoom_from_history()

    def _zoom_forward(self) -> None:
        """Go to next zoom level."""
        if self._zoom_history_index < len(self._zoom_history) - 1:
            self._zoom_history_index += 1
            self._apply_zoom_from_history()

    def _apply_zoom_from_history(self) -> None:
        """Apply the current zoom level from history."""
        if 0 <= self._zoom_history_index < len(self._zoom_history):
            x_range, y_range = self._zoom_history[self._zoom_history_index]

            self._recording_zoom = False
            self._plot_widget.setXRange(x_range[0], x_range[1], padding=0)
            self._plot_widget.setYRange(y_range[0], y_range[1], padding=0)
            self._recording_zoom = True

            self._update_navigation_buttons()

    def _toggle_auto_scroll(self, checked: bool) -> None:
        """Toggle auto-scroll mode."""
        self._auto_scroll = checked

    # -------------------------------------------------------------------------
    # Streaming Data Methods
    # -------------------------------------------------------------------------

    def start_streaming(self) -> None:
        """Start streaming mode - prepares viewer for real-time data."""
        self._streaming = True
        self._streaming_time = []
        self._streaming_signals = {}
        self._last_displayed_index = 0
        self._y_range_set = False  # Reset Y auto-range flag

        # Clear existing streaming traces
        for trace in self._streaming_traces.values():
            self._plot_widget.removeItem(trace)
        self._streaming_traces.clear()

        # Reset color index for streaming traces
        self._color_index = 0

        # Clear zoom history
        self._zoom_history.clear()
        self._zoom_history_index = -1
        self._update_navigation_buttons()

        # Remove cursors during streaming
        self._remove_cursors()
        self._cursor_checkbox.setChecked(False)

        # Start update timer
        self._update_timer.start()
        self._pending_updates = False

    def stop_streaming(self) -> None:
        """Stop streaming mode."""
        self._streaming = False
        self._update_timer.stop()

        # Flush any remaining data
        if self._pending_updates:
            self._flush_streaming_data()

    def add_data_point(self, time: float, signals: dict[str, float]) -> None:
        """Add data point(s) during streaming.

        Supports multiple modes:
        1. Animated display: _animate + _time_array + _signal_arrays (smoothest)
        2. Incremental chunks: _chunk_time + _chunk_signals
        3. Full data replacement: _full_data with _time/_signals
        4. Single point: individual time + signal values

        Args:
            time: The time value for this data point
            signals: Dictionary with data in one of the supported formats
        """
        if not self._streaming:
            self.start_streaming()

        # Mode 0: Animated display (simulation complete, animate progressively)
        if "_animate" in signals:
            self._start_animated_display(
                signals.get("_time_array"),
                signals.get("_signal_arrays", {}),
                signals.get("_total_points", 0),
            )
            return

        # Mode 1: Chunk data (can be replace or append)
        if "_chunk_time" in signals:
            chunk_time = signals["_chunk_time"]
            chunk_signals = signals.get("_chunk_signals", {})
            replace_mode = signals.get("_replace", False)

            if replace_mode:
                # Replace all data (for animated playback)
                self._streaming_time = list(chunk_time)
                self._streaming_signals = {
                    name: list(values) for name, values in chunk_signals.items()
                }
            else:
                # Append mode (incremental streaming)
                if not isinstance(self._streaming_time, list):
                    self._streaming_time = []
                if not self._streaming_signals:
                    self._streaming_signals = {}

                self._streaming_time.extend(chunk_time)
                for name, values in chunk_signals.items():
                    if name not in self._streaming_signals:
                        self._streaming_signals[name] = []
                    self._streaming_signals[name].extend(values)

            self._pending_updates = True
            return

        # Mode 2: Complete signal (simulation finished)
        if "_complete" in signals:
            # Just mark for final update
            self._pending_updates = True
            return

        # Mode 3: Full data replacement (numpy arrays)
        if "_full_data" in signals:
            full_data = signals["_full_data"]
            if "_time_np" in full_data:
                self._streaming_time = list(full_data["_time_np"])
                self._streaming_signals = {
                    k: list(v) for k, v in full_data.get("_signals_np", {}).items()
                }
            elif "_time" in full_data:
                self._streaming_time = full_data.get("_time", [])
                self._streaming_signals = full_data.get("_signals", {})
            self._pending_updates = True
            return

        # Mode 4: Legacy single point
        if not isinstance(self._streaming_time, list):
            self._streaming_time = []

        self._streaming_time.append(time)
        for name, value in signals.items():
            if not name.startswith("_"):
                if name not in self._streaming_signals:
                    self._streaming_signals[name] = []
                self._streaming_signals[name].append(value)

        self._pending_updates = True

    def _start_animated_display(
        self,
        time_array: np.ndarray | None,
        signal_arrays: dict[str, np.ndarray],
        total_points: int,
    ) -> None:
        """Start animated display of complete simulation data.

        Uses QTimer for smooth 60 FPS animation without blocking the UI.

        Args:
            time_array: Complete time data as numpy array
            signal_arrays: Complete signal data as numpy arrays
            total_points: Total number of data points
        """
        if time_array is None or len(time_array) == 0:
            return

        # Store the complete data for animation
        self._anim_time = time_array
        self._anim_signals = signal_arrays
        self._anim_total_points = total_points
        self._anim_current_index = 0

        # Calculate animation parameters (~4 second animation at 60 FPS)
        animation_duration = 4.0  # seconds (slower, more satisfying animation)
        fps = 60
        total_frames = int(animation_duration * fps)
        self._anim_points_per_frame = max(1, total_points // total_frames)
        self._anim_frame_count = 0

        # Create traces for each signal (if not already present)
        for name in signal_arrays.keys():
            if name not in self._streaming_traces:
                color = self._trace_palette[self._color_index % len(self._trace_palette)]
                self._color_index += 1
                pen = self._resolve_trace_pen(name, color)
                # Start with empty data
                trace = self._plot_widget.plot(
                    [], [], pen=pen, name=name,
                    skipFiniteCheck=True,
                )
                self._configure_trace_performance(trace, total_points)
                self._streaming_traces[name] = trace

        # Set up animation timer (separate from regular update timer)
        if not hasattr(self, '_anim_timer'):
            self._anim_timer = QTimer()
            self._anim_timer.timeout.connect(self._animate_frame)

        self._anim_timer.start(16)  # 60 FPS

    def _animate_frame(self) -> None:
        """Render one frame of the animation."""
        if not hasattr(self, '_anim_time') or self._anim_time is None:
            if hasattr(self, '_anim_timer'):
                self._anim_timer.stop()
            return

        # Calculate how much data to show this frame
        self._anim_current_index = min(
            self._anim_current_index + self._anim_points_per_frame,
            self._anim_total_points
        )

        # Get current slice of data
        end_idx = self._anim_current_index
        time_slice = self._anim_time[:end_idx]

        # Update each trace with current data slice
        for name, full_values in self._anim_signals.items():
            if name in self._streaming_traces:
                values_slice = full_values[:end_idx]
                self._streaming_traces[name].setData(time_slice, values_slice)

        # Update X range to show waveform growing
        if len(time_slice) > 0:
            t_start = float(time_slice[0])
            t_current = float(time_slice[-1])
            t_range = t_current - t_start
            if t_range > 0:
                t_end = t_current + t_range * 0.1
                self._recording_zoom = False
                self._plot_widget.setXRange(t_start, t_end, padding=0)
                self._recording_zoom = True

        # Auto-range Y only on first frame
        if self._anim_frame_count == 0:
            self._plot_widget.enableAutoRange(axis='y')

        self._anim_frame_count += 1

        # Check if animation is complete
        if self._anim_current_index >= self._anim_total_points:
            self._anim_timer.stop()
            # Store final data for result display
            self._streaming_time = self._anim_time.tolist()
            self._streaming_signals = {
                name: values.tolist() for name, values in self._anim_signals.items()
            }
            # Clean up animation data
            self._anim_time = None
            self._anim_signals = None

    def _flush_streaming_data(self) -> None:
        """Flush buffered streaming data to the plot.

        Optimized for high-performance real-time display.
        PyQtGraph handles downsampling automatically with autoDownsample=True.
        """
        if not self._pending_updates:
            return

        time_data = self._streaming_time
        if not time_data or len(time_data) == 0:
            return

        self._pending_updates = False

        # Convert to numpy array once (much faster for pyqtgraph)
        time_array = np.asarray(time_data, dtype=np.float64)

        # Update or create traces for each signal
        for name, values in self._streaming_signals.items():
            values_array = np.asarray(values, dtype=np.float64)

            if name in self._streaming_traces:
                # Fast update - just set new data
                self._streaming_traces[name].setData(time_array, values_array)
            else:
                # Create new trace (only happens once per signal)
                color = self._trace_palette[self._color_index % len(self._trace_palette)]
                self._color_index += 1
                pen = self._resolve_trace_pen(name, color)
                trace = self._plot_widget.plot(
                    time_array, values_array, pen=pen, name=name,
                    skipFiniteCheck=True,
                )
                self._configure_trace_performance(trace, len(time_array))
                self._streaming_traces[name] = trace

        # Set view to show waveform growing from start
        if len(time_array) > 0:
            t_start = float(time_array[0])
            t_current = float(time_array[-1])
            t_range = t_current - t_start

            if t_range > 0:
                t_end = t_current + t_range * 0.1
                self._recording_zoom = False
                self._plot_widget.setXRange(t_start, t_end, padding=0)
                self._recording_zoom = True

            # Only auto-range Y on first update (expensive operation)
            if not hasattr(self, '_y_range_set') or not self._y_range_set:
                self._plot_widget.enableAutoRange(axis='y')
                self._y_range_set = True

    def _decimate_data(
        self, time_data: list[float], signals_data: dict[str, list[float]]
    ) -> tuple[list[float], dict[str, list[float]]]:
        """Decimate data if it exceeds MAX_DISPLAY_POINTS.

        Uses min-max bucketing to preserve peaks and visual features,
        which is critical for accurate waveform display.

        Args:
            time_data: List of time values
            signals_data: Dictionary of signal data lists

        Returns:
            Tuple of (decimated_time, decimated_signals)
        """
        n_points = len(time_data)

        if n_points <= MAX_DISPLAY_POINTS:
            return time_data, signals_data

        # Use min-max decimation: each bucket produces 2 points (min and max)
        # This preserves peaks which is essential for waveforms
        n_buckets = MAX_DISPLAY_POINTS // 2
        bucket_size = max(1, n_points // n_buckets)

        decimated_time: list[float] = []
        decimated_signals: dict[str, list[float]] = {name: [] for name in signals_data}

        for i in range(n_buckets):
            start = i * bucket_size
            end = min(start + bucket_size, n_points)

            if start >= n_points:
                break

            # Get bucket slice
            bucket_time = time_data[start:end]
            if not bucket_time:
                continue

            # For the first signal, find min/max indices to determine order
            first_signal = next(iter(signals_data.values()), None)
            if first_signal:
                bucket_vals = first_signal[start:end]
                if bucket_vals:
                    local_min_idx = min(range(len(bucket_vals)), key=lambda x: bucket_vals[x])
                    local_max_idx = max(range(len(bucket_vals)), key=lambda x: bucket_vals[x])

                    # Add points in time order
                    if local_min_idx <= local_max_idx:
                        idx1, idx2 = local_min_idx, local_max_idx
                    else:
                        idx1, idx2 = local_max_idx, local_min_idx

                    # Add time points
                    decimated_time.append(bucket_time[idx1])
                    if idx1 != idx2:
                        decimated_time.append(bucket_time[idx2])

                    # Add all signal values at these indices
                    for name, values in signals_data.items():
                        bucket_vals = values[start:end]
                        if len(bucket_vals) > idx1:
                            decimated_signals[name].append(bucket_vals[idx1])
                        if idx1 != idx2 and len(bucket_vals) > idx2:
                            decimated_signals[name].append(bucket_vals[idx2])

        return decimated_time, decimated_signals

    def _decimate_data_numpy(
        self, time_data: np.ndarray, signals_data: dict[str, np.ndarray]
    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Decimate numpy array data using efficient vectorized operations.

        Uses LTTB-like min-max bucketing optimized for numpy arrays.
        Much faster than the list-based version for large datasets.

        Args:
            time_data: Numpy array of time values
            signals_data: Dictionary of signal numpy arrays

        Returns:
            Tuple of (decimated_time, decimated_signals)
        """
        n_points = len(time_data)

        if n_points <= MAX_DISPLAY_POINTS:
            return time_data, signals_data

        # Use min-max decimation with numpy vectorized operations
        n_buckets = MAX_DISPLAY_POINTS // 2
        bucket_size = n_points // n_buckets

        # Get the first signal for determining min/max indices
        first_signal_name = next(iter(signals_data.keys()), None)
        if first_signal_name is None:
            return time_data, signals_data

        first_signal = signals_data[first_signal_name]
        if not isinstance(first_signal, np.ndarray):
            first_signal = np.array(first_signal)

        # Pre-allocate output arrays (2 points per bucket)
        max_output_size = n_buckets * 2
        decimated_time = np.zeros(max_output_size)
        decimated_signals = {name: np.zeros(max_output_size) for name in signals_data}

        output_idx = 0

        for i in range(n_buckets):
            start = i * bucket_size
            end = min(start + bucket_size, n_points)

            if start >= n_points:
                break

            # Get bucket slice
            bucket_signal = first_signal[start:end]
            if len(bucket_signal) == 0:
                continue

            # Find min and max indices within bucket
            local_min_idx = np.argmin(bucket_signal)
            local_max_idx = np.argmax(bucket_signal)

            # Add points in time order
            if local_min_idx <= local_max_idx:
                idx1, idx2 = local_min_idx, local_max_idx
            else:
                idx1, idx2 = local_max_idx, local_min_idx

            # Add time points
            decimated_time[output_idx] = time_data[start + idx1]
            for name, values in signals_data.items():
                if isinstance(values, np.ndarray):
                    decimated_signals[name][output_idx] = values[start + idx1]
                else:
                    decimated_signals[name][output_idx] = values[start + idx1]
            output_idx += 1

            # Add second point if different
            if idx1 != idx2:
                decimated_time[output_idx] = time_data[start + idx2]
                for name, values in signals_data.items():
                    if isinstance(values, np.ndarray):
                        decimated_signals[name][output_idx] = values[start + idx2]
                    else:
                        decimated_signals[name][output_idx] = values[start + idx2]
                output_idx += 1

        # Trim to actual size
        decimated_time = decimated_time[:output_idx]
        decimated_signals = {name: arr[:output_idx] for name, arr in decimated_signals.items()}

        return decimated_time, decimated_signals

    def finalize_streaming(self, result: SimulationResult) -> None:
        """Finalize streaming and switch to full result display.

        Called when simulation completes to show the full result set.

        Args:
            result: The complete simulation result
        """
        self.stop_streaming()

        # Clear streaming traces
        for trace in self._streaming_traces.values():
            self._plot_widget.removeItem(trace)
        self._streaming_traces.clear()

        # Set the complete result
        self.set_result(result)

    # -------------------------------------------------------------------------
    # Signal List Panel Handlers
    # -------------------------------------------------------------------------

    def _on_signal_visibility_changed(self, signal_name: str, visible: bool) -> None:
        """Handle signal visibility toggle from signal list panel.

        Args:
            signal_name: Name of the signal being toggled
            visible: True to show the signal, False to hide it
        """
        if visible:
            # Add trace if not already present
            if signal_name not in self._traces:
                self.add_trace(signal_name)
        else:
            # Remove trace if present
            self.remove_trace(signal_name)

        # Update active signal if the toggled signal is now the only visible one
        visible_signals = self._signal_list_panel.get_visible_signals()
        if not visible_signals:
            self._active_signal = None
            self._measurements_panel.clear_statistics()
            if self._cursor1 is not None and self._cursor2 is not None:
                self._refresh_measurements_table(self._cursor1.value(), self._cursor2.value())
            else:
                self._refresh_measurements_table()
        elif self._active_signal not in visible_signals:
            self._active_signal = visible_signals[0]
            self._update_statistics(self._active_signal)
            self._update_cursor_values()
        else:
            if self._cursor1 is not None and self._cursor2 is not None:
                self._refresh_measurements_table(self._cursor1.value(), self._cursor2.value())
            else:
                self._refresh_measurements_table()

    def _on_signal_list_selected(self, signal_name: str) -> None:
        """Handle signal selection from signal list panel.

        Makes the selected signal active for measurements.

        Args:
            signal_name: Name of the selected signal
        """
        self._active_signal = signal_name
        self._update_statistics(signal_name)
        self._update_cursor_values()
        if self._cursor1 is None or self._cursor2 is None:
            self._refresh_measurements_table()

        # Also update the combo box selection
        idx = self._signal_combo.findText(signal_name)
        if idx >= 0:
            self._signal_combo.blockSignals(True)
            self._signal_combo.setCurrentIndex(idx)
            self._signal_combo.blockSignals(False)
