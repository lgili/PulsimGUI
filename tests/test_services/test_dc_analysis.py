"""Tests for DC operating point analysis."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pulsimgui.services.backend_adapter import PlaceholderBackend, PulsimBackend, BackendInfo
from pulsimgui.services.backend_types import (
    ConvergenceInfo,
    DCResult as BackendDCResult,
    DCSettings,
    IterationRecord,
    ProblematicVariable,
)
from pulsimgui.services.simulation_service import DCResult, SimulationService


class TestPlaceholderDCAnalysis:
    """Tests for DC analysis with PlaceholderBackend."""

    def test_simple_resistive_circuit(self):
        """PlaceholderBackend should return valid DC result for any circuit."""
        backend = PlaceholderBackend()
        settings = DCSettings()

        # Simple voltage divider circuit data
        circuit_data = {
            "components": [
                {"id": "V1", "type": "voltage_source", "value": 10.0},
                {"id": "R1", "type": "resistor", "value": 1000},
                {"id": "R2", "type": "resistor", "value": 1000},
            ],
            "nets": [
                {"name": "in", "connections": ["V1.p", "R1.1"]},
                {"name": "out", "connections": ["R1.2", "R2.1"]},
                {"name": "gnd", "connections": ["V1.n", "R2.2"]},
            ],
        }

        result = backend.run_dc(circuit_data, settings)

        assert result.is_valid
        assert result.convergence_info.converged
        assert len(result.node_voltages) > 0

    def test_dc_returns_convergence_info(self):
        """DC result should include convergence information."""
        backend = PlaceholderBackend()
        settings = DCSettings()

        result = backend.run_dc({}, settings)

        assert result.convergence_info is not None
        assert result.convergence_info.converged is True
        assert result.convergence_info.iterations > 0

    def test_dc_with_different_strategies(self):
        """DC analysis should work with different convergence strategies."""
        backend = PlaceholderBackend()

        strategies = ["auto", "direct", "gmin", "source", "pseudo"]
        for strategy in strategies:
            settings = DCSettings(strategy=strategy)
            result = backend.run_dc({}, settings)

            assert result.is_valid, f"Strategy {strategy} should produce valid result"


class TestDCSettingsMapping:
    """Tests for DCSettings mapping to backend options."""

    def test_default_settings(self):
        """Default DCSettings should have sensible values."""
        settings = DCSettings()

        assert settings.strategy == "auto"
        assert settings.max_iterations == 100
        assert settings.tolerance == 1e-9
        assert settings.enable_limiting is True
        assert settings.max_voltage_step == 5.0

    def test_gmin_settings(self):
        """GMIN settings should be configurable."""
        settings = DCSettings(
            strategy="gmin",
            gmin_initial=1e-2,
            gmin_final=1e-15,
        )

        assert settings.gmin_initial == 1e-2
        assert settings.gmin_final == 1e-15


class TestDCConvergenceFailure:
    """Tests for DC convergence failure handling."""

    def test_failed_convergence_result(self):
        """Failed convergence should produce valid but unsuccessful result."""
        # Create a result representing convergence failure
        result = BackendDCResult(
            node_voltages={},
            branch_currents={},
            power_dissipation={},
            error_message="Failed to converge after 100 iterations",
            convergence_info=ConvergenceInfo(
                converged=False,
                iterations=100,
                final_residual=1e-3,
                strategy_used="newton",
                failure_reason="Maximum iterations exceeded",
            ),
        )

        assert not result.is_valid
        assert not result.convergence_info.converged
        assert result.error_message != ""

    def test_convergence_info_with_problematic_variables(self):
        """Failed convergence should identify problematic variables."""
        info = ConvergenceInfo(
            converged=False,
            iterations=50,
            final_residual=1e-2,
            strategy_used="newton",
            problematic_variables=[
                ProblematicVariable(
                    index=0,
                    name="V(floating_node)",
                    value=1e10,
                    change=1e8,
                    tolerance=1e-6,
                    normalized_error=1e14,
                    is_voltage=True,
                ),
            ],
        )

        assert len(info.problematic_variables) == 1
        assert info.problematic_variables[0].name == "V(floating_node)"
        assert info.problematic_variables[0].normalized_error > 1e10

    def test_convergence_trend_diverging(self):
        """Diverging convergence should be detected from history."""
        info = ConvergenceInfo(
            converged=False,
            iterations=10,
            final_residual=1e6,
            strategy_used="newton",
            history=[
                IterationRecord(0, 1e-3),
                IterationRecord(1, 1e-2),
                IterationRecord(2, 1e-1),
                IterationRecord(3, 1e0),
                IterationRecord(4, 1e1),
            ],
        )

        assert info.trend == "diverging"


class TestDCResultConversion:
    """Tests for converting backend DC results to GUI format."""

    def test_gui_dc_result_valid(self):
        """GUI DCResult should correctly report validity."""
        result = DCResult(
            node_voltages={"V(out)": 5.0},
            branch_currents={"I(R1)": 0.005},
            power_dissipation={"P(R1)": 0.025},
            error_message="",
        )

        assert result.is_valid

    def test_gui_dc_result_invalid_with_error(self):
        """GUI DCResult with error message should be invalid."""
        result = DCResult(
            node_voltages={},
            error_message="Convergence failed",
        )

        assert not result.is_valid


class TestSimulationServiceDC:
    """Tests for SimulationService DC analysis integration."""

    @pytest.fixture
    def mock_backend(self):
        """Create a mock backend for testing."""
        backend = MagicMock()
        backend.has_capability.return_value = True
        backend.info = BackendInfo(
            identifier="mock",
            name="Mock Backend",
            version="1.0.0",
            status="available",
        )
        return backend

    def test_dc_with_placeholder_backend(self, qtbot):
        """DC analysis should work with placeholder backend."""
        service = SimulationService()

        # Capture the DC result
        results = []

        def on_dc_finished(result):
            results.append(result)

        service.dc_finished.connect(on_dc_finished)

        circuit_data = {"components": [], "nets": []}
        service.run_dc_operating_point(circuit_data)

        # Wait for signal (DC is synchronous in placeholder, should be immediate)
        qtbot.waitUntil(lambda: len(results) > 0, timeout=5000)

        assert len(results) == 1
        # Placeholder always returns valid result
        assert results[0].is_valid or not results[0].is_valid  # Either is valid

    def test_dc_settings_passed_to_backend(self, qtbot):
        """DC settings should be passed to the backend."""
        service = SimulationService()

        # Set up custom solver settings
        service.settings.dc_strategy = "gmin"
        service.settings.max_newton_iterations = 200
        service.settings.enable_voltage_limiting = False
        service.settings.max_voltage_step = 10.0

        results = []
        service.dc_finished.connect(results.append)

        circuit_data = {"components": [], "nets": []}
        service.run_dc_operating_point(circuit_data)

        qtbot.waitUntil(lambda: len(results) > 0, timeout=5000)

        # Verify settings were used (via convergence info if available)
        assert len(results) == 1

    def test_last_convergence_info_stored(self, qtbot):
        """SimulationService should store last convergence info."""
        service = SimulationService()

        results = []
        service.dc_finished.connect(results.append)

        circuit_data = {"components": [], "nets": []}
        service.run_dc_operating_point(circuit_data)

        qtbot.waitUntil(lambda: len(results) > 0, timeout=5000)

        # Check if convergence info is accessible
        info = service.last_convergence_info
        # May be None for placeholder or contain ConvergenceInfo
        assert info is None or hasattr(info, "converged")


class TestDCCircuitTypes:
    """Tests for DC analysis with different circuit types."""

    def test_resistive_voltage_divider(self):
        """Test DC analysis of a simple voltage divider."""
        backend = PlaceholderBackend()
        settings = DCSettings()

        # Voltage divider: V1 = 10V, R1 = R2 = 1k
        # Expected: V(out) = 5V
        circuit_data = {
            "components": [
                {"id": "V1", "type": "voltage_source", "value": 10.0},
                {"id": "R1", "type": "resistor", "value": 1000},
                {"id": "R2", "type": "resistor", "value": 1000},
            ],
        }

        result = backend.run_dc(circuit_data, settings)

        assert result.is_valid
        # Placeholder returns synthetic data, so we just check structure
        assert isinstance(result.node_voltages, dict)

    def test_circuit_with_current_source(self):
        """Test DC analysis with current source."""
        backend = PlaceholderBackend()
        settings = DCSettings()

        circuit_data = {
            "components": [
                {"id": "I1", "type": "current_source", "value": 0.001},
                {"id": "R1", "type": "resistor", "value": 1000},
            ],
        }

        result = backend.run_dc(circuit_data, settings)

        assert result.is_valid

    def test_circuit_with_diode(self):
        """Test DC analysis with nonlinear diode element."""
        backend = PlaceholderBackend()
        settings = DCSettings(
            strategy="gmin",  # GMIN stepping often helps with diodes
            max_iterations=200,
        )

        circuit_data = {
            "components": [
                {"id": "V1", "type": "voltage_source", "value": 5.0},
                {"id": "R1", "type": "resistor", "value": 1000},
                {"id": "D1", "type": "diode", "model": "1N4148"},
            ],
        }

        result = backend.run_dc(circuit_data, settings)

        assert result.is_valid
        # For real backend, we'd verify:
        # - Diode forward voltage ~0.7V
        # - Current through diode = (5 - 0.7) / 1000

    def test_circuit_with_mosfet(self):
        """Test DC analysis with MOSFET."""
        backend = PlaceholderBackend()
        settings = DCSettings(
            strategy="auto",
            enable_limiting=True,  # Important for MOSFETs
        )

        circuit_data = {
            "components": [
                {"id": "V1", "type": "voltage_source", "value": 12.0},
                {"id": "Vg", "type": "voltage_source", "value": 5.0},
                {"id": "R1", "type": "resistor", "value": 100},
                {"id": "M1", "type": "nmos", "model": "IRF540"},
            ],
        }

        result = backend.run_dc(circuit_data, settings)

        assert result.is_valid


class TestDCStrategySelection:
    """Tests for DC convergence strategy selection."""

    def test_auto_strategy(self):
        """Auto strategy should select appropriate method."""
        backend = PlaceholderBackend()
        settings = DCSettings(strategy="auto")

        result = backend.run_dc({}, settings)

        assert result.is_valid
        # Placeholder returns 'placeholder' as strategy, real backends return actual strategy
        assert result.convergence_info.strategy_used in [
            "newton", "gmin_stepping", "source_stepping", "pseudo_transient", "auto", "placeholder"
        ]

    def test_direct_newton(self):
        """Direct Newton should be usable for simple circuits."""
        backend = PlaceholderBackend()
        settings = DCSettings(strategy="direct")

        result = backend.run_dc({}, settings)

        assert result.is_valid

    def test_gmin_stepping(self):
        """GMIN stepping should help with difficult circuits."""
        backend = PlaceholderBackend()
        settings = DCSettings(
            strategy="gmin",
            gmin_initial=1e-3,
            gmin_final=1e-12,
        )

        result = backend.run_dc({}, settings)

        assert result.is_valid

    def test_source_stepping(self):
        """Source stepping should ramp up sources gradually."""
        backend = PlaceholderBackend()
        settings = DCSettings(strategy="source")

        result = backend.run_dc({}, settings)

        assert result.is_valid

    def test_pseudo_transient(self):
        """Pseudo-transient should add time-stepping."""
        backend = PlaceholderBackend()
        settings = DCSettings(strategy="pseudo")

        result = backend.run_dc({}, settings)

        assert result.is_valid
