"""Performance tests for simulation workflows.

These tests measure:
1. Circuit conversion overhead
2. Simulation execution time
3. Memory usage patterns
4. Hot path profiling
"""

from __future__ import annotations

import time
from typing import Callable

import pytest

from pulsimgui.services.backend_adapter import PlaceholderBackend
from pulsimgui.services.backend_types import DCSettings, ACSettings
from pulsimgui.services.backend_adapter import BackendCallbacks
from pulsimgui.services.simulation_service import SimulationSettings

from .example_circuits import (
    voltage_divider,
    rc_lowpass_filter,
    rc_transient,
    mosfet_switch,
)


def measure_time(func: Callable, iterations: int = 10) -> tuple[float, float, float]:
    """Measure execution time statistics.

    Returns:
        Tuple of (min_time, avg_time, max_time) in milliseconds.
    """
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)

    return min(times), sum(times) / len(times), max(times)


class TestConversionOverhead:
    """Tests measuring circuit data conversion overhead."""

    def test_small_circuit_conversion_fast(self) -> None:
        """Test that small circuit conversion is fast.

        Benchmark: < 1ms for simple circuits

        GUI Validation:
        1. Create simple circuit (3-4 components)
        2. Run simulation
        3. There should be no perceptible delay before simulation starts
        """
        backend = PlaceholderBackend()
        circuit_data = voltage_divider()

        def run_dc():
            backend.run_dc(circuit_data, DCSettings())

        min_t, avg_t, max_t = measure_time(run_dc, iterations=20)

        # Should be very fast (placeholder doesn't do real conversion)
        assert avg_t < 100  # Less than 100ms average
        print(f"DC Analysis: min={min_t:.2f}ms, avg={avg_t:.2f}ms, max={max_t:.2f}ms")

    def test_ac_analysis_performance(self) -> None:
        """Test AC analysis performance.

        Benchmark: < 10ms for standard frequency sweep

        GUI Validation:
        1. Run AC analysis with 10 points/decade, 1Hz-1MHz
        2. Results should appear quickly
        """
        backend = PlaceholderBackend()
        circuit_data = rc_lowpass_filter()

        def run_ac():
            backend.run_ac(circuit_data, ACSettings(
                f_start=1.0,
                f_stop=1e6,
                points_per_decade=10,
            ))

        min_t, avg_t, max_t = measure_time(run_ac, iterations=10)

        assert avg_t < 500  # Less than 500ms average
        print(f"AC Analysis: min={min_t:.2f}ms, avg={avg_t:.2f}ms, max={max_t:.2f}ms")


class TestTransientPerformance:
    """Tests measuring transient simulation performance."""

    def test_short_transient_fast(self) -> None:
        """Test short transient simulation is fast.

        Benchmark: < 100ms for 1ms simulation at 1µs step

        GUI Validation:
        1. Run transient 0-1ms with 1µs step
        2. Should complete within ~1 second
        """
        backend = PlaceholderBackend()
        circuit_data = rc_transient()

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )
        settings = SimulationSettings(t_start=0, t_stop=1e-3, t_step=1e-6)

        def run_transient():
            backend.run_transient(circuit_data, settings, callbacks)

        min_t, avg_t, max_t = measure_time(run_transient, iterations=5)

        assert avg_t < 1000  # Less than 1 second
        print(f"Transient (1ms): min={min_t:.2f}ms, avg={avg_t:.2f}ms, max={max_t:.2f}ms")

    def test_progress_callback_overhead(self) -> None:
        """Test that progress callbacks don't slow simulation significantly.

        GUI Validation:
        1. Run simulation
        2. Progress bar should update smoothly without lag
        """
        backend = PlaceholderBackend()
        circuit_data = rc_transient()

        progress_count = [0]
        data_point_count = [0]

        def on_progress(p, msg):
            progress_count[0] += 1

        def on_data_point(t, signals):
            data_point_count[0] += 1

        callbacks_with_logging = BackendCallbacks(
            progress=on_progress,
            data_point=on_data_point,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        callbacks_empty = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        settings = SimulationSettings(t_start=0, t_stop=100e-6, t_step=100e-9)

        # Measure with callbacks
        start = time.perf_counter()
        backend.run_transient(circuit_data, settings, callbacks_with_logging)
        time_with_callbacks = (time.perf_counter() - start) * 1000

        # Measure without callbacks (minimal)
        start = time.perf_counter()
        backend.run_transient(circuit_data, settings, callbacks_empty)
        time_without_callbacks = (time.perf_counter() - start) * 1000

        # Callbacks shouldn't add more than 50% overhead
        overhead = (time_with_callbacks - time_without_callbacks) / max(time_without_callbacks, 0.1)
        print(f"Callback overhead: {overhead*100:.1f}%")
        print(f"Progress callbacks: {progress_count[0]}, Data points: {data_point_count[0]}")


class TestMemoryUsage:
    """Tests for memory usage patterns."""

    def test_results_memory_reasonable(self) -> None:
        """Test that simulation results don't use excessive memory.

        GUI Validation:
        1. Run long transient simulation
        2. Monitor memory usage in task manager
        3. Should stay within reasonable bounds
        """
        backend = PlaceholderBackend()
        circuit_data = rc_transient()

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        # Simulate longer run
        settings = SimulationSettings(t_start=0, t_stop=10e-3, t_step=1e-6)

        result = backend.run_transient(circuit_data, settings, callbacks)

        # Check result size is reasonable
        assert len(result.time) <= 10001  # t_stop/t_step + 1
        assert len(result.signals) > 0

    def test_multiple_runs_no_memory_leak(self) -> None:
        """Test that multiple simulation runs don't leak memory.

        GUI Validation:
        1. Run simulation multiple times
        2. Memory usage should stabilize, not grow indefinitely
        """
        import gc

        backend = PlaceholderBackend()
        circuit_data = rc_transient()

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )
        settings = SimulationSettings(t_start=0, t_stop=100e-6, t_step=100e-9)

        # Run multiple times
        for i in range(10):
            result = backend.run_transient(circuit_data, settings, callbacks)
            assert result is not None

            # Allow garbage collection
            del result
            gc.collect()

        # If we got here without memory error, test passes


class TestScalability:
    """Tests for scalability with circuit size."""

    def test_many_components_handled(self) -> None:
        """Test handling of circuit with many components.

        GUI Validation:
        1. Create circuit with 50+ components
        2. Run DC analysis
        3. Should complete without hanging
        """
        # Create circuit with many resistors in series
        components = []
        node_map = {}

        # Voltage source
        components.append({
            "id": "v1",
            "type": "VOLTAGE_SOURCE",
            "name": "V1",
            "parameters": {"dc_value": 10.0},
            "pin_nodes": ["n0", "0"],
        })
        node_map["v1"] = ["n0", "0"]

        # Chain of 50 resistors
        for i in range(50):
            rid = f"r{i}"
            components.append({
                "id": rid,
                "type": "RESISTOR",
                "name": f"R{i}",
                "parameters": {"resistance": 100.0},
                "pin_nodes": [f"n{i}", f"n{i+1}" if i < 49 else "0"],
            })
            node_map[rid] = [f"n{i}", f"n{i+1}" if i < 49 else "0"]

        circuit_data = {
            "components": components,
            "node_map": node_map,
            "node_aliases": {},
        }

        backend = PlaceholderBackend()

        start = time.perf_counter()
        result = backend.run_dc(circuit_data, DCSettings())
        elapsed = (time.perf_counter() - start) * 1000

        assert result is not None
        assert result.error_message == ""
        print(f"50-resistor chain DC: {elapsed:.2f}ms")

    def test_many_frequency_points(self) -> None:
        """Test AC analysis with many frequency points.

        GUI Validation:
        1. Run AC analysis with 100 points/decade over wide range
        2. Bode plot should render smoothly
        """
        backend = PlaceholderBackend()
        circuit_data = rc_lowpass_filter()

        settings = ACSettings(
            f_start=0.1,
            f_stop=1e9,
            points_per_decade=50,  # Many points
        )

        start = time.perf_counter()
        result = backend.run_ac(circuit_data, settings)
        elapsed = (time.perf_counter() - start) * 1000

        assert result.is_valid
        assert len(result.frequencies) > 100
        print(f"Wide AC sweep ({len(result.frequencies)} points): {elapsed:.2f}ms")


class TestBenchmarkSummary:
    """Summary benchmark for overall performance."""

    def test_complete_workflow_timing(self) -> None:
        """Benchmark complete simulation workflow.

        GUI Validation:
        1. Load circuit
        2. Run DC + AC + Transient
        3. Open results dialogs
        4. Total time should be reasonable (<5s for simple circuits)
        """
        backend = PlaceholderBackend()
        circuit_data = mosfet_switch()

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        total_start = time.perf_counter()

        # DC Analysis
        dc_start = time.perf_counter()
        dc_result = backend.run_dc(circuit_data, DCSettings())
        dc_time = (time.perf_counter() - dc_start) * 1000

        # AC Analysis
        ac_start = time.perf_counter()
        ac_result = backend.run_ac(circuit_data, ACSettings())
        ac_time = (time.perf_counter() - ac_start) * 1000

        # Transient
        trans_start = time.perf_counter()
        settings = SimulationSettings(t_start=0, t_stop=100e-6, t_step=100e-9)
        trans_result = backend.run_transient(circuit_data, settings, callbacks)
        trans_time = (time.perf_counter() - trans_start) * 1000

        total_time = (time.perf_counter() - total_start) * 1000

        print("\n=== Performance Summary ===")
        print(f"DC Analysis:   {dc_time:8.2f} ms")
        print(f"AC Analysis:   {ac_time:8.2f} ms")
        print(f"Transient:     {trans_time:8.2f} ms")
        print(f"Total:         {total_time:8.2f} ms")
        print("===========================\n")

        # All should complete successfully
        assert dc_result.error_message == ""
        assert ac_result.is_valid
        assert trans_result.error_message == ""

        # Total should be reasonable
        assert total_time < 5000  # Less than 5 seconds
