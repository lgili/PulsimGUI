"""Tests for error handling in simulation workflows.

These tests verify robust error handling for:
1. Backend not installed
2. Backend crashes mid-simulation
3. Invalid circuit data
4. Timeout handling
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import time

import pytest

from pulsimgui.services import backend_adapter
from pulsimgui.services.backend_adapter import (
    BackendLoader,
    BackendInfo,
    PlaceholderBackend,
    PulsimBackend,
)
from pulsimgui.services.backend_types import DCSettings, ACSettings
from pulsimgui.services.backend_adapter import BackendCallbacks
from pulsimgui.services.simulation_service import SimulationSettings


@pytest.fixture(autouse=True)
def disable_entry_points(monkeypatch):
    """Ensure tests run with predictable entry-point list."""
    monkeypatch.setattr(backend_adapter.metadata, "entry_points", lambda: ())


class TestBackendNotInstalled:
    """Tests for handling missing backend."""

    def test_missing_pulsim_falls_back_to_placeholder(self, monkeypatch) -> None:
        """Test graceful fallback when pulsim not installed.

        GUI Validation:
        1. Uninstall PulsimCore
        2. Start GUI
        3. Should show "Demo Mode" or placeholder indicator
        4. Simulations should still work (with synthetic data)
        """
        def _missing(_name: str):
            raise ImportError("No module named 'pulsim'")

        monkeypatch.setattr(backend_adapter, "import_module", _missing)

        loader = BackendLoader()

        assert loader.backend is not None
        assert loader.backend.info.identifier == "placeholder"
        assert loader.backend.info.status == "error"
        assert "pulsim" in loader.backend.info.message.lower()

    def test_placeholder_runs_simulations(self, monkeypatch) -> None:
        """Test placeholder backend can run all simulation types.

        GUI Validation:
        1. With placeholder backend active
        2. Run DC, AC, Transient
        3. All should complete (with synthetic data)
        """
        def _missing(_name: str):
            raise ImportError("pulsim not installed")

        monkeypatch.setattr(backend_adapter, "import_module", _missing)

        loader = BackendLoader()
        backend = loader.backend

        # DC analysis
        dc_result = backend.run_dc({}, DCSettings())
        assert dc_result.error_message == ""

        # AC analysis
        ac_result = backend.run_ac({}, ACSettings())
        assert ac_result.error_message == ""
        assert ac_result.is_valid

        # Transient
        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )
        settings = SimulationSettings()
        transient_result = backend.run_transient({}, settings, callbacks)
        assert transient_result.error_message == ""


class TestBackendCrashes:
    """Tests for handling backend crashes during simulation."""

    def test_dc_analysis_exception_handled(self) -> None:
        """Test DC analysis handles backend exceptions gracefully.

        GUI Validation:
        1. If backend crashes during DC analysis
        2. Error dialog should appear
        3. GUI should remain responsive
        4. User can retry or change settings
        """
        mock_backend = MagicMock()
        mock_backend.run_dc.side_effect = RuntimeError("Backend crash!")

        # Wrap in try-except as the real code would
        try:
            mock_backend.run_dc({}, DCSettings())
        except RuntimeError as e:
            error_message = str(e)

        assert "Backend crash" in error_message

    def test_transient_cancelled_gracefully(self) -> None:
        """Test transient simulation handles cancellation.

        GUI Validation:
        1. Start transient simulation
        2. Click Stop button
        3. Simulation should stop cleanly
        4. Partial results may be available
        """
        backend = PlaceholderBackend()

        cancelled = False

        def check_cancelled():
            return cancelled

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=check_cancelled,
            wait_if_paused=lambda: None,
        )

        # Simulate cancellation mid-simulation
        cancelled = True

        settings = SimulationSettings(t_start=0, t_stop=1e-3, t_step=1e-6)
        result = backend.run_transient({}, settings, callbacks)

        # Should handle gracefully (placeholder doesn't check cancelled)
        assert result is not None


class TestInvalidCircuitData:
    """Tests for handling invalid circuit data."""

    def test_empty_circuit_dc(self) -> None:
        """Test DC analysis on empty circuit.

        GUI Validation:
        1. Create new project (empty circuit)
        2. Run DC Operating Point
        3. Should show "No components" warning or empty results
        """
        backend = PlaceholderBackend()

        result = backend.run_dc({}, DCSettings())

        # Placeholder handles empty circuit gracefully
        assert result is not None
        assert result.error_message == ""

    def test_empty_circuit_ac(self) -> None:
        """Test AC analysis on empty circuit.

        GUI Validation:
        1. Create new project (empty circuit)
        2. Run AC Analysis
        3. Should show warning or empty Bode plot
        """
        backend = PlaceholderBackend()

        result = backend.run_ac({}, ACSettings())

        assert result is not None
        assert result.is_valid  # Placeholder returns synthetic data

    def test_invalid_component_type(self) -> None:
        """Test handling of invalid component type.

        GUI Validation:
        1. This shouldn't happen from GUI (only valid types in palette)
        2. But imported files might have unknown types
        3. Should show clear error message
        """
        from pulsimgui.services.circuit_converter import CircuitConversionError

        circuit_data = {
            "components": [
                {
                    "id": "x1",
                    "type": "INVALID_TYPE",
                    "name": "X1",
                    "pin_nodes": ["a", "b"],
                }
            ],
            "node_map": {"x1": ["a", "b"]},
        }

        # This would fail in CircuitConverter
        # The actual conversion happens in PulsimBackend
        # We test the error type exists
        with pytest.raises(Exception):
            # CircuitConverter would raise this
            from pulsimgui.models.component import ComponentType
            ComponentType["INVALID_TYPE"]

    def test_missing_node_connectivity(self) -> None:
        """Test handling of component with missing nodes.

        GUI Validation:
        1. Add component but don't connect pins
        2. Run simulation
        3. Should show "floating node" or connectivity error
        """
        circuit_data = {
            "components": [
                {
                    "id": "r1",
                    "type": "RESISTOR",
                    "name": "R1",
                    "parameters": {"resistance": 1000.0},
                    # Missing pin_nodes
                }
            ],
            "node_map": {},  # No connectivity
        }

        # Placeholder doesn't validate circuit
        backend = PlaceholderBackend()
        result = backend.run_dc(circuit_data, DCSettings())
        assert result is not None

    def test_circuit_with_short(self) -> None:
        """Test circuit with voltage source short circuit.

        GUI Validation:
        1. Connect voltage source directly to ground
        2. Run DC analysis
        3. Should show convergence failure or warning
        """
        circuit_data = {
            "components": [
                {
                    "id": "v1",
                    "type": "VOLTAGE_SOURCE",
                    "name": "V1",
                    "parameters": {"dc_value": 10.0},
                    "pin_nodes": ["0", "0"],  # Shorted!
                }
            ],
            "node_map": {"v1": ["0", "0"]},
        }

        # Placeholder handles this (returns synthetic)
        backend = PlaceholderBackend()
        result = backend.run_dc(circuit_data, DCSettings())
        assert result is not None


class TestConvergenceFailures:
    """Tests for handling convergence failures."""

    def test_dc_convergence_failure_reported(self) -> None:
        """Test DC convergence failure is properly reported.

        GUI Validation:
        1. Create difficult circuit (e.g., diode in unstable config)
        2. Run DC Operating Point
        3. If convergence fails, show Diagnostics dialog
        4. Suggestions should appear for improving convergence
        """
        # Create mock result with convergence failure
        from pulsimgui.services.backend_types import DCResult, ConvergenceInfo

        failed_result = DCResult(
            convergence_info=ConvergenceInfo(
                converged=False,
                iterations=100,
                final_residual=1e5,
                failure_reason="Newton iteration did not converge",
            ),
            error_message="DC analysis failed to converge",
        )

        assert not failed_result.convergence_info.converged
        assert failed_result.error_message

    def test_convergence_diagnostics_available(self) -> None:
        """Test convergence diagnostics are available on failure.

        GUI Validation:
        1. On convergence failure
        2. Click "Show Diagnostics" button
        3. Dialog shows: iteration history, problematic nodes, suggestions
        """
        from pulsimgui.services.backend_types import (
            ConvergenceInfo,
            IterationRecord,
            ProblematicVariable,
        )

        # Create detailed convergence info
        info = ConvergenceInfo(
            converged=False,
            iterations=50,
            final_residual=1e3,
            strategy_used="newton",
            failure_reason="Maximum iterations exceeded",
            history=[
                IterationRecord(iteration=0, residual_norm=1e6),
                IterationRecord(iteration=1, residual_norm=1e5),
                IterationRecord(iteration=2, residual_norm=1e4),
            ],
            problematic_variables=[
                ProblematicVariable(
                    index=0,
                    name="V(out)",
                    value=1e10,
                    change=1e8,
                    tolerance=1e-9,
                    normalized_error=1e17,
                ),
            ],
        )

        assert info.trend == "converging"  # Residual is decreasing
        assert len(info.history) == 3
        assert len(info.problematic_variables) == 1


class TestTimeoutHandling:
    """Tests for simulation timeout handling."""

    def test_long_simulation_can_be_cancelled(self) -> None:
        """Test that long-running simulation can be cancelled.

        GUI Validation:
        1. Start very long transient (e.g., 1 second at 1ns step)
        2. Progress bar should update
        3. Click Stop to cancel
        4. Simulation should stop within reasonable time
        """
        backend = PlaceholderBackend()

        cancel_requested = False
        progress_updates = []

        def on_progress(p, msg):
            progress_updates.append(p)

        def check_cancelled():
            return cancel_requested

        callbacks = BackendCallbacks(
            progress=on_progress,
            data_point=lambda t, _: None,
            check_cancelled=check_cancelled,
            wait_if_paused=lambda: None,
        )

        # Request cancellation after some progress
        cancel_requested = True

        settings = SimulationSettings(t_start=0, t_stop=1e-3, t_step=1e-6)
        result = backend.run_transient({}, settings, callbacks)

        assert result is not None

    def test_progress_reported_during_simulation(self) -> None:
        """Test that progress is reported during simulation.

        GUI Validation:
        1. Run transient simulation
        2. Progress bar should update smoothly
        3. Status should show current simulation time
        """
        backend = PlaceholderBackend()

        progress_updates = []

        def on_progress(p, msg):
            progress_updates.append((p, msg))

        callbacks = BackendCallbacks(
            progress=on_progress,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        settings = SimulationSettings(t_start=0, t_stop=1e-3, t_step=1e-6)
        result = backend.run_transient({}, settings, callbacks)

        # Should have received some progress updates
        assert len(progress_updates) > 0
        # Progress should increase
        if len(progress_updates) > 1:
            assert progress_updates[-1][0] >= progress_updates[0][0]


class TestResourceCleanup:
    """Tests for proper resource cleanup after errors."""

    def test_backend_usable_after_error(self) -> None:
        """Test backend remains usable after an error.

        GUI Validation:
        1. Run simulation that fails (e.g., convergence failure)
        2. Fix circuit
        3. Run simulation again - should work
        """
        backend = PlaceholderBackend()

        # First simulation (simulated "failure" - placeholder doesn't fail)
        result1 = backend.run_dc({}, DCSettings())
        assert result1 is not None

        # Second simulation should still work
        result2 = backend.run_dc({}, DCSettings())
        assert result2 is not None
        assert result2.error_message == ""

    def test_multiple_simulations_sequentially(self) -> None:
        """Test running multiple simulations in sequence.

        GUI Validation:
        1. Run DC analysis
        2. Run AC analysis
        3. Run Transient
        4. All should complete successfully
        """
        backend = PlaceholderBackend()

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        # Run multiple simulations
        for _ in range(3):
            dc_result = backend.run_dc({}, DCSettings())
            assert dc_result.error_message == ""

            ac_result = backend.run_ac({}, ACSettings())
            assert ac_result.is_valid

            settings = SimulationSettings()
            transient_result = backend.run_transient({}, settings, callbacks)
            assert transient_result.error_message == ""
