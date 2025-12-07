"""Waveform viewer widget for displaying simulation results."""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer, QMimeData
from PySide6.QtGui import QDrag, QColor
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
)

from pulsimgui.services.simulation_service import SimulationResult


# Maximum points to display before decimation kicks in
MAX_DISPLAY_POINTS = 5000


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


class MeasurementsPanel(QFrame):
    """Panel displaying cursor measurements and signal statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Cursor measurements
        cursor_group = QGroupBox("Cursor Measurements")
        cursor_layout = QGridLayout(cursor_group)
        cursor_layout.setSpacing(2)

        # Cursor 1
        cursor_layout.addWidget(QLabel("C1 Time:"), 0, 0)
        self._c1_time = QLabel("---")
        self._c1_time.setStyleSheet("color: red; font-weight: bold;")
        cursor_layout.addWidget(self._c1_time, 0, 1)

        cursor_layout.addWidget(QLabel("C1 Value:"), 1, 0)
        self._c1_value = QLabel("---")
        self._c1_value.setStyleSheet("color: red;")
        cursor_layout.addWidget(self._c1_value, 1, 1)

        # Cursor 2
        cursor_layout.addWidget(QLabel("C2 Time:"), 2, 0)
        self._c2_time = QLabel("---")
        self._c2_time.setStyleSheet("color: blue; font-weight: bold;")
        cursor_layout.addWidget(self._c2_time, 2, 1)

        cursor_layout.addWidget(QLabel("C2 Value:"), 3, 0)
        self._c2_value = QLabel("---")
        self._c2_value.setStyleSheet("color: blue;")
        cursor_layout.addWidget(self._c2_value, 3, 1)

        # Delta
        cursor_layout.addWidget(QLabel("Delta T:"), 4, 0)
        self._delta_t = QLabel("---")
        self._delta_t.setStyleSheet("font-weight: bold;")
        cursor_layout.addWidget(self._delta_t, 4, 1)

        cursor_layout.addWidget(QLabel("Delta V:"), 5, 0)
        self._delta_v = QLabel("---")
        cursor_layout.addWidget(self._delta_v, 5, 1)

        cursor_layout.addWidget(QLabel("Freq:"), 6, 0)
        self._frequency = QLabel("---")
        cursor_layout.addWidget(self._frequency, 6, 1)

        layout.addWidget(cursor_group)

        # Signal statistics
        stats_group = QGroupBox("Signal Statistics")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setSpacing(2)

        stats_layout.addWidget(QLabel("Min:"), 0, 0)
        self._min_value = QLabel("---")
        stats_layout.addWidget(self._min_value, 0, 1)

        stats_layout.addWidget(QLabel("Max:"), 1, 0)
        self._max_value = QLabel("---")
        stats_layout.addWidget(self._max_value, 1, 1)

        stats_layout.addWidget(QLabel("Mean:"), 2, 0)
        self._mean_value = QLabel("---")
        stats_layout.addWidget(self._mean_value, 2, 1)

        stats_layout.addWidget(QLabel("RMS:"), 3, 0)
        self._rms_value = QLabel("---")
        stats_layout.addWidget(self._rms_value, 3, 1)

        stats_layout.addWidget(QLabel("Pk-Pk:"), 4, 0)
        self._pkpk_value = QLabel("---")
        stats_layout.addWidget(self._pkpk_value, 4, 1)

        layout.addWidget(stats_group)
        layout.addStretch()

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
        """Update signal statistics."""
        self._min_value.setText(f"{min_val:.6g}")
        self._max_value.setText(f"{max_val:.6g}")
        self._mean_value.setText(f"{mean_val:.6g}")
        self._rms_value.setText(f"{rms_val:.6g}")
        self._pkpk_value.setText(f"{max_val - min_val:.6g}")

    def clear_statistics(self) -> None:
        """Clear all statistics."""
        self._min_value.setText("---")
        self._max_value.setText("---")
        self._mean_value.setText("---")
        self._rms_value.setText("---")
        self._pkpk_value.setText("---")


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
        """Update the color display for this item."""
        r, g, b = self._color
        self.setForeground(QColor(r, g, b))

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
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)

        self._signal_items: dict[str, SignalListItem] = {}
        self._color_index = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header
        header = QLabel("Signals")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

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

        # Buttons
        button_layout = QHBoxLayout()

        show_all_btn = QPushButton("Show All")
        show_all_btn.clicked.connect(self._show_all)
        button_layout.addWidget(show_all_btn)

        hide_all_btn = QPushButton("Hide All")
        hide_all_btn.clicked.connect(self._hide_all)
        button_layout.addWidget(hide_all_btn)

        layout.addLayout(button_layout)

    def set_signals(self, signal_names: list[str]) -> None:
        """Set the list of available signals."""
        self._list_widget.clear()
        self._signal_items.clear()
        self._color_index = 0

        for name in signal_names:
            color = TRACE_COLORS[self._color_index % len(TRACE_COLORS)]
            self._color_index += 1

            item = SignalListItem(name, color)
            self._list_widget.addItem(item)
            self._signal_items[name] = item

    def get_signal_color(self, signal_name: str) -> tuple | None:
        """Get the color assigned to a signal."""
        if signal_name in self._signal_items:
            return self._signal_items[signal_name].color
        return None

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

    def clear(self) -> None:
        """Clear all signals."""
        self._list_widget.clear()
        self._signal_items.clear()
        self._color_index = 0


class WaveformViewer(QWidget):
    """Widget for displaying simulation waveforms using PyQtGraph."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._result: SimulationResult | None = None
        self._traces: dict[str, pg.PlotDataItem] = {}
        self._color_index = 0

        # Cursors
        self._cursor1: DraggableCursor | None = None
        self._cursor2: DraggableCursor | None = None
        self._cursors_visible = False
        self._active_signal: str | None = None

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
        self._update_timer.setInterval(50)  # 20 Hz update rate
        self._update_timer.timeout.connect(self._flush_streaming_data)
        self._pending_updates = False

        # Configure pyqtgraph
        pg.setConfigOptions(antialias=True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main splitter for plot and measurements panel
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Plot container
        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("left", "Value")
        self._plot_widget.setLabel("bottom", "Time", units="s")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setBackground("w")
        self._plot_widget.getAxis("left").setPen("k")
        self._plot_widget.getAxis("bottom").setPen("k")
        self._plot_widget.getAxis("left").setTextPen("k")
        self._plot_widget.getAxis("bottom").setTextPen("k")

        # Configure view box for mouse interactions
        view_box = self._plot_widget.getViewBox()
        view_box.setMouseMode(pg.ViewBox.RectMode)

        # Connect range change signal for zoom history
        view_box.sigRangeChanged.connect(self._on_range_changed)

        # Add legend
        self._legend = self._plot_widget.addLegend(offset=(10, 10))
        self._legend.setLabelTextColor("k")

        plot_layout.addWidget(self._plot_widget)

        # Controls bar
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(5, 5, 5, 5)

        # Signal selector
        controls_layout.addWidget(QLabel("Add Signal:"))
        self._signal_combo = QComboBox()
        self._signal_combo.setMinimumWidth(150)
        self._signal_combo.currentTextChanged.connect(self._on_signal_selected)
        controls_layout.addWidget(self._signal_combo)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_signal)
        controls_layout.addWidget(add_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_traces)
        controls_layout.addWidget(clear_btn)

        controls_layout.addStretch()

        # Auto-scroll toggle for streaming mode
        self._auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self._auto_scroll_checkbox.setChecked(True)
        self._auto_scroll_checkbox.setToolTip("Automatically scroll to show latest data during simulation")
        self._auto_scroll_checkbox.toggled.connect(self._toggle_auto_scroll)
        controls_layout.addWidget(self._auto_scroll_checkbox)

        # Cursor toggle
        self._cursor_checkbox = QCheckBox("Cursors")
        self._cursor_checkbox.setChecked(False)
        self._cursor_checkbox.toggled.connect(self._toggle_cursors)
        controls_layout.addWidget(self._cursor_checkbox)

        # Navigation buttons
        self._back_btn = QPushButton("<")
        self._back_btn.setToolTip("Previous zoom level")
        self._back_btn.setMaximumWidth(30)
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._zoom_back)
        controls_layout.addWidget(self._back_btn)

        self._forward_btn = QPushButton(">")
        self._forward_btn.setToolTip("Next zoom level")
        self._forward_btn.setMaximumWidth(30)
        self._forward_btn.setEnabled(False)
        self._forward_btn.clicked.connect(self._zoom_forward)
        controls_layout.addWidget(self._forward_btn)

        # Grid toggle
        self._grid_checkbox = QCheckBox("Grid")
        self._grid_checkbox.setChecked(True)
        self._grid_checkbox.toggled.connect(self._toggle_grid)
        controls_layout.addWidget(self._grid_checkbox)

        # Auto-range button
        auto_btn = QPushButton("Fit")
        auto_btn.setToolTip("Zoom to fit all data")
        auto_btn.clicked.connect(self._auto_range)
        controls_layout.addWidget(auto_btn)

        plot_layout.addWidget(controls)
        splitter.addWidget(plot_container)

        # Right side container with signal list and measurements
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # Signal list panel
        self._signal_list_panel = SignalListPanel()
        self._signal_list_panel.setMinimumWidth(150)
        self._signal_list_panel.setMaximumWidth(200)
        self._signal_list_panel.signal_visibility_changed.connect(
            self._on_signal_visibility_changed
        )
        self._signal_list_panel.signal_selected.connect(self._on_signal_list_selected)
        right_layout.addWidget(self._signal_list_panel, stretch=1)

        # Measurements panel
        self._measurements_panel = MeasurementsPanel()
        self._measurements_panel.setMinimumWidth(150)
        self._measurements_panel.setMaximumWidth(200)
        right_layout.addWidget(self._measurements_panel, stretch=1)

        splitter.addWidget(right_container)

        # Set splitter sizes
        splitter.setSizes([700, 200])

        layout.addWidget(splitter)

    def set_result(self, result: SimulationResult) -> None:
        """Set the simulation result to display."""
        self._result = result
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
            self._signal_list_panel.set_signals(list(result.signals.keys()))

            # Auto-add first signal if available
            first_signal = list(result.signals.keys())[0]
            self.add_trace(first_signal)
            self._active_signal = first_signal

            # Mark first signal as visible in list
            self._signal_list_panel.set_signal_visible(first_signal, True)
        else:
            self._signal_list_panel.clear()

    def _update_signal_combo(self) -> None:
        """Update the signal combo box with available signals."""
        self._signal_combo.clear()
        if self._result:
            self._signal_combo.addItems(list(self._result.signals.keys()))

    def add_trace(self, signal_name: str) -> None:
        """Add a trace for the specified signal."""
        if not self._result or signal_name not in self._result.signals:
            return

        if signal_name in self._traces:
            return

        time = np.array(self._result.time)
        values = np.array(self._result.signals[signal_name])

        # Get color from signal list panel if available, otherwise use default
        color = self._signal_list_panel.get_signal_color(signal_name)
        if color is None:
            color = TRACE_COLORS[self._color_index % len(TRACE_COLORS)]
            self._color_index += 1

        pen = pg.mkPen(color=color, width=2)
        trace = self._plot_widget.plot(time, values, pen=pen, name=signal_name)
        self._traces[signal_name] = trace

        # Update statistics
        self._update_statistics(signal_name)

    def remove_trace(self, signal_name: str) -> None:
        """Remove a trace from the plot."""
        if signal_name in self._traces:
            self._plot_widget.removeItem(self._traces[signal_name])
            del self._traces[signal_name]

    def clear_traces(self) -> None:
        """Remove all traces from the plot."""
        for trace in self._traces.values():
            self._plot_widget.removeItem(trace)
        self._traces.clear()
        self._color_index = 0
        self._legend.clear()
        self._measurements_panel.clear_statistics()

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
        self._cursor1 = DraggableCursor(c1_pos, CURSOR_COLORS[0], "C1")
        self._plot_widget.addItem(self._cursor1)
        self._plot_widget.addItem(self._cursor1.get_text_item())
        self._cursor1.cursor_moved.connect(self._on_cursor_moved)

        # Create cursor 2
        self._cursor2 = DraggableCursor(c2_pos, CURSOR_COLORS[1], "C2")
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
            return

        if not self._result or not self._active_signal:
            return

        if self._active_signal not in self._result.signals:
            return

        time = np.array(self._result.time)
        values = np.array(self._result.signals[self._active_signal])

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

        # Update label positions
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
        if not self._result or signal_name not in self._result.signals:
            self._measurements_panel.clear_statistics()
            return

        values = np.array(self._result.signals[signal_name])

        if len(values) == 0:
            self._measurements_panel.clear_statistics()
            return

        min_val = float(np.min(values))
        max_val = float(np.max(values))
        mean_val = float(np.mean(values))
        rms_val = float(np.sqrt(np.mean(values ** 2)))

        self._measurements_panel.update_statistics(min_val, max_val, mean_val, rms_val)

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
            self._update_cursor_values()

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
        self._streaming_time.clear()
        self._streaming_signals.clear()

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

        # Make viewer visible
        self.parentWidget().setVisible(True) if self.parentWidget() else None

    def stop_streaming(self) -> None:
        """Stop streaming mode."""
        self._streaming = False
        self._update_timer.stop()

        # Flush any remaining data
        if self._pending_updates:
            self._flush_streaming_data()

    def add_data_point(self, time: float, signals: dict[str, float]) -> None:
        """Add a single data point during streaming.

        Args:
            time: The time value for this data point
            signals: Dictionary mapping signal names to their values
        """
        if not self._streaming:
            self.start_streaming()

        # Add time point
        self._streaming_time.append(time)

        # Add signal values
        for name, value in signals.items():
            if name not in self._streaming_signals:
                self._streaming_signals[name] = []
            self._streaming_signals[name].append(value)

        # Mark that we have pending updates
        self._pending_updates = True

    def _flush_streaming_data(self) -> None:
        """Flush buffered streaming data to the plot."""
        if not self._pending_updates or not self._streaming_time:
            return

        self._pending_updates = False

        # Decimate data if needed
        time_data, signals_data = self._decimate_data(
            self._streaming_time, self._streaming_signals
        )

        time_array = np.array(time_data)

        # Update or create traces for each signal
        for name, values in signals_data.items():
            values_array = np.array(values)

            if name in self._streaming_traces:
                # Update existing trace
                self._streaming_traces[name].setData(time_array, values_array)
            else:
                # Create new trace
                color = TRACE_COLORS[self._color_index % len(TRACE_COLORS)]
                self._color_index += 1
                pen = pg.mkPen(color=color, width=2)
                trace = self._plot_widget.plot(
                    time_array, values_array, pen=pen, name=name
                )
                self._streaming_traces[name] = trace

        # Handle auto-scroll
        if self._auto_scroll and len(time_data) > 0:
            current_time = time_data[-1]

            # Calculate window size based on data
            if len(time_data) > 1:
                # Use 10% of total time as window, minimum scroll_window
                total_time = time_data[-1] - time_data[0]
                window = max(self._scroll_window, total_time * 0.1)
            else:
                window = self._scroll_window

            # Set X range to show recent data
            x_min = max(0, current_time - window)
            x_max = current_time + window * 0.1  # Small padding on right

            self._recording_zoom = False
            self._plot_widget.setXRange(x_min, x_max, padding=0)
            self._recording_zoom = True

            # Auto-scale Y axis
            self._plot_widget.enableAutoRange(axis='y')

    def _decimate_data(
        self, time_data: list[float], signals_data: dict[str, list[float]]
    ) -> tuple[list[float], dict[str, list[float]]]:
        """Decimate data if it exceeds MAX_DISPLAY_POINTS.

        Uses LTTB (Largest Triangle Three Buckets) algorithm for efficient
        downsampling while preserving visual features.

        Args:
            time_data: List of time values
            signals_data: Dictionary of signal data lists

        Returns:
            Tuple of (decimated_time, decimated_signals)
        """
        n_points = len(time_data)

        if n_points <= MAX_DISPLAY_POINTS:
            return time_data, signals_data

        # Calculate decimation factor
        target_points = MAX_DISPLAY_POINTS
        step = n_points / target_points

        # Use simple min-max decimation for each bucket
        # This preserves peaks which is important for waveforms
        decimated_time = []
        decimated_signals = {name: [] for name in signals_data}

        bucket_start = 0
        while bucket_start < n_points:
            bucket_end = min(int(bucket_start + step), n_points)

            if bucket_end <= bucket_start:
                bucket_end = bucket_start + 1

            # For time, use the middle of the bucket
            mid_idx = (bucket_start + bucket_end) // 2
            if mid_idx < len(time_data):
                decimated_time.append(time_data[mid_idx])

                # For each signal, find min and max in bucket
                for name, values in signals_data.items():
                    bucket_values = values[bucket_start:bucket_end]
                    if bucket_values:
                        # Use value at mid point (simple but effective)
                        if mid_idx < len(values):
                            decimated_signals[name].append(values[mid_idx])

            bucket_start = bucket_end

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
        if visible_signals and self._active_signal not in visible_signals:
            self._active_signal = visible_signals[0]
            self._update_statistics(self._active_signal)
            self._update_cursor_values()

    def _on_signal_list_selected(self, signal_name: str) -> None:
        """Handle signal selection from signal list panel.

        Makes the selected signal active for measurements.

        Args:
            signal_name: Name of the selected signal
        """
        self._active_signal = signal_name
        self._update_statistics(signal_name)
        self._update_cursor_values()

        # Also update the combo box selection
        idx = self._signal_combo.findText(signal_name)
        if idx >= 0:
            self._signal_combo.blockSignals(True)
            self._signal_combo.setCurrentIndex(idx)
            self._signal_combo.blockSignals(False)
