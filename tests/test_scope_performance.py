#!/usr/bin/env python3
"""
Standalone test to benchmark and optimize the waveform viewer performance.

This test generates a large waveform and streams it to the viewer to simulate
real-time display, isolating scope performance from simulation performance.

Run with:
    python tests/test_scope_performance.py          # GUI mode
    python tests/test_scope_performance.py --bench  # Benchmark mode (no GUI)
"""

import sys
import os
import time
import numpy as np
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Check for benchmark mode (no GUI needed)
BENCHMARK_MODE = "--bench" in sys.argv

if BENCHMARK_MODE:
    # Use offscreen platform for benchmarking without display
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Fix Qt plugin path before importing any Qt modules
import PySide6
_pyside6_dir = Path(PySide6.__path__[0])
_qt_plugins = _pyside6_dir / "Qt" / "plugins"
if _qt_plugins.exists():
    os.environ["QT_PLUGIN_PATH"] = str(_qt_plugins)

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QHBoxLayout
from PySide6.QtCore import QTimer, QCoreApplication
import pyqtgraph as pg

# Ensure library paths include PySide6 plugins
QCoreApplication.addLibraryPath(str(_qt_plugins))


# Generate test waveform data
def generate_test_waveform(duration: float = 0.01, sample_rate: float = 1e6) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Generate a complex test waveform with multiple signals.

    Args:
        duration: Duration in seconds (default 10ms)
        sample_rate: Samples per second (default 1MHz = 1M points per second)

    Returns:
        Tuple of (time_array, signals_dict)
    """
    n_points = int(duration * sample_rate)
    print(f"Generating {n_points:,} data points...")

    t = np.linspace(0, duration, n_points, dtype=np.float64)

    # Generate multiple signals
    signals = {}

    # Signal 1: PWM-like waveform (square wave with varying duty cycle)
    freq1 = 10000  # 10kHz
    signals["V(pwm)"] = np.where(np.sin(2 * np.pi * freq1 * t) > 0, 12.0, 0.0)

    # Signal 2: Filtered version (exponential decay)
    tau = 1e-5  # 10us time constant
    signals["V(filtered)"] = 6.0 + 5.0 * np.sin(2 * np.pi * freq1 * t) * np.exp(-t / (10 * tau))

    # Signal 3: High frequency ripple
    freq2 = 100000  # 100kHz
    signals["V(ripple)"] = 0.5 * np.sin(2 * np.pi * freq2 * t)

    # Signal 4: Slow ramp
    signals["V(ramp)"] = 10.0 * t / duration

    print(f"Generated {len(signals)} signals with {n_points:,} points each")
    print(f"Total data size: {n_points * len(signals) * 8 / 1024 / 1024:.1f} MB")

    return t, signals


class PerformanceTestWindow(QMainWindow):
    """Window to test waveform viewer performance."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scope Performance Test")
        self.resize(1200, 800)

        # Generate test data
        self.time_data, self.signals_data = generate_test_waveform(
            duration=0.01,  # 10ms
            sample_rate=1e6  # 1MHz = 10,000 points
        )
        self.total_points = len(self.time_data)

        # Setup UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Controls
        controls = QHBoxLayout()

        self.btn_stream = QPushButton("Start Streaming (60 FPS)")
        self.btn_stream.clicked.connect(self.start_streaming)
        controls.addWidget(self.btn_stream)

        self.btn_instant = QPushButton("Show All Instant")
        self.btn_instant.clicked.connect(self.show_all_instant)
        controls.addWidget(self.btn_instant)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_plot)
        controls.addWidget(self.btn_clear)

        self.status_label = QLabel("Ready")
        controls.addWidget(self.status_label)

        layout.addLayout(controls)

        # Plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('k')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.setLabel('left', 'Voltage', units='V')
        layout.addWidget(self.plot_widget)

        # Traces dict
        self.traces: dict[str, pg.PlotDataItem] = {}

        # Streaming state
        self.streaming = False
        self.stream_index = 0
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self._stream_update)

        # Colors
        self.colors = [
            (31, 119, 180),   # Blue
            (255, 127, 14),   # Orange
            (44, 160, 44),    # Green
            (214, 39, 40),    # Red
        ]

        # Performance metrics
        self.frame_times: list[float] = []

    def clear_plot(self):
        """Clear all traces."""
        self.plot_widget.clear()
        self.traces.clear()
        self.stream_index = 0
        self.streaming = False
        self.stream_timer.stop()
        self.status_label.setText("Cleared")

    def show_all_instant(self):
        """Show all data instantly (test maximum performance)."""
        self.clear_plot()

        start_time = time.perf_counter()

        for i, (name, values) in enumerate(self.signals_data.items()):
            color = self.colors[i % len(self.colors)]
            pen = pg.mkPen(color=color, width=1)
            trace = self.plot_widget.plot(
                self.time_data, values, pen=pen, name=name,
                skipFiniteCheck=True,
            )
            self.traces[name] = trace

        elapsed = time.perf_counter() - start_time
        self.status_label.setText(f"Rendered {self.total_points:,} points x {len(self.signals_data)} signals in {elapsed*1000:.1f}ms")

    def start_streaming(self):
        """Start streaming simulation at 60 FPS."""
        self.clear_plot()
        self.streaming = True
        self.stream_index = 0
        self.frame_times = []

        # Calculate points per frame for ~2 second animation
        animation_duration = 2.0  # seconds
        fps = 60
        total_frames = int(animation_duration * fps)
        self.points_per_frame = max(1, self.total_points // total_frames)

        self.status_label.setText(f"Streaming... {self.points_per_frame} points/frame")
        self.stream_timer.start(16)  # ~60 FPS
        self.last_frame_time = time.perf_counter()

    def _stream_update(self):
        """Update streaming display (called by timer)."""
        if not self.streaming:
            return

        frame_start = time.perf_counter()

        # Calculate end index for this frame
        self.stream_index += self.points_per_frame
        if self.stream_index >= self.total_points:
            self.stream_index = self.total_points
            self.streaming = False
            self.stream_timer.stop()

        # Get data slice
        t_slice = self.time_data[:self.stream_index]

        # Update or create traces
        for i, (name, values) in enumerate(self.signals_data.items()):
            v_slice = values[:self.stream_index]

            if name in self.traces:
                # Update existing trace
                self.traces[name].setData(t_slice, v_slice)
            else:
                # Create new trace
                color = self.colors[i % len(self.colors)]
                pen = pg.mkPen(color=color, width=1)
                trace = self.plot_widget.plot(
                    t_slice, v_slice, pen=pen, name=name,
                    skipFiniteCheck=True,
                )
                self.traces[name] = trace

        # Update view range
        if len(t_slice) > 0:
            t_end = t_slice[-1] + (t_slice[-1] - t_slice[0]) * 0.1
            self.plot_widget.setXRange(t_slice[0], t_end, padding=0)

        # Track frame time
        frame_time = time.perf_counter() - frame_start
        self.frame_times.append(frame_time)

        # Update status
        progress = self.stream_index / self.total_points * 100
        avg_frame_time = np.mean(self.frame_times) * 1000 if self.frame_times else 0
        fps = 1000 / avg_frame_time if avg_frame_time > 0 else 0

        self.status_label.setText(
            f"Streaming: {progress:.0f}% | {self.stream_index:,} points | "
            f"Frame: {frame_time*1000:.1f}ms | Avg FPS: {fps:.0f}"
        )

        if not self.streaming:
            # Finished - show final stats
            total_time = sum(self.frame_times)
            avg_fps = len(self.frame_times) / total_time if total_time > 0 else 0
            self.status_label.setText(
                f"Done! {self.total_points:,} points | "
                f"{len(self.frame_times)} frames in {total_time:.2f}s | "
                f"Avg FPS: {avg_fps:.0f}"
            )


def run_benchmark():
    """Run automated benchmark without requiring user interaction."""
    print("\n" + "="*60)
    print("SCOPE PERFORMANCE BENCHMARK")
    print("="*60)

    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=False)

    # Generate test data
    print("\n--- Generating Test Data ---")
    time_data, signals_data = generate_test_waveform(
        duration=0.01,  # 10ms
        sample_rate=1e6  # 1MHz = 10,000 points
    )
    total_points = len(time_data)

    # Create plot widget
    plot_widget = pg.PlotWidget()
    plot_widget.setBackground('k')
    plot_widget.showGrid(x=True, y=True, alpha=0.3)

    colors = [
        (31, 119, 180),   # Blue
        (255, 127, 14),   # Orange
        (44, 160, 44),    # Green
        (214, 39, 40),    # Red
    ]

    # Test 1: Instant rendering (all data at once)
    print("\n--- Test 1: Instant Rendering ---")
    plot_widget.clear()
    start = time.perf_counter()
    for i, (name, values) in enumerate(signals_data.items()):
        pen = pg.mkPen(color=colors[i % len(colors)], width=1)
        plot_widget.plot(time_data, values, pen=pen, name=name, skipFiniteCheck=True)
    instant_time = time.perf_counter() - start
    print(f"Rendered {total_points:,} points x {len(signals_data)} signals in {instant_time*1000:.2f}ms")

    # Test 2: Streaming simulation (incremental updates)
    print("\n--- Test 2: Streaming Simulation (60 FPS target) ---")
    plot_widget.clear()
    traces: dict = {}

    animation_duration = 2.0  # seconds
    fps = 60
    total_frames = int(animation_duration * fps)
    points_per_frame = max(1, total_points // total_frames)

    print(f"Target: {fps} FPS, {total_frames} frames, {points_per_frame} points/frame")

    frame_times = []
    stream_index = 0

    while stream_index < total_points:
        frame_start = time.perf_counter()

        stream_index = min(stream_index + points_per_frame, total_points)
        t_slice = time_data[:stream_index]

        for i, (name, values) in enumerate(signals_data.items()):
            v_slice = values[:stream_index]
            if name in traces:
                traces[name].setData(t_slice, v_slice)
            else:
                pen = pg.mkPen(color=colors[i % len(colors)], width=1)
                traces[name] = plot_widget.plot(t_slice, v_slice, pen=pen, name=name, skipFiniteCheck=True)

        # Process events (simulate real Qt event loop)
        app.processEvents()

        frame_time = time.perf_counter() - frame_start
        frame_times.append(frame_time)

    avg_frame_time = np.mean(frame_times) * 1000
    max_frame_time = np.max(frame_times) * 1000
    min_frame_time = np.min(frame_times) * 1000
    achieved_fps = 1000 / avg_frame_time if avg_frame_time > 0 else 0

    print(f"Completed {len(frame_times)} frames")
    print(f"Frame time: avg={avg_frame_time:.2f}ms, min={min_frame_time:.2f}ms, max={max_frame_time:.2f}ms")
    print(f"Achieved FPS: {achieved_fps:.0f} (target: {fps})")

    # Test 3: Large dataset test
    print("\n--- Test 3: Large Dataset (100k points) ---")
    time_large, signals_large = generate_test_waveform(
        duration=0.1,  # 100ms
        sample_rate=1e6  # 1MHz = 100,000 points
    )

    plot_widget.clear()
    start = time.perf_counter()
    for i, (name, values) in enumerate(signals_large.items()):
        pen = pg.mkPen(color=colors[i % len(colors)], width=1)
        plot_widget.plot(time_large, values, pen=pen, name=name, skipFiniteCheck=True)
    large_time = time.perf_counter() - start
    print(f"Rendered {len(time_large):,} points x {len(signals_large)} signals in {large_time*1000:.2f}ms")

    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    print(f"Instant render (10k points):  {instant_time*1000:.2f}ms")
    print(f"Streaming (60 FPS target):    {achieved_fps:.0f} FPS achieved")
    print(f"Large render (100k points):   {large_time*1000:.2f}ms")
    print()

    if achieved_fps >= 55:
        print("✓ Performance is GOOD (>55 FPS)")
    elif achieved_fps >= 30:
        print("⚠ Performance is ACCEPTABLE (30-55 FPS)")
    else:
        print("✗ Performance needs optimization (<30 FPS)")

    return 0


def main():
    if BENCHMARK_MODE:
        sys.exit(run_benchmark())

    app = QApplication(sys.argv)

    # Set dark theme for pyqtgraph
    pg.setConfigOptions(antialias=False)  # Disable antialiasing for speed

    window = PerformanceTestWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
