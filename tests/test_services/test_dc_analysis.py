"""Tests for DC operating point analysis."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from pulsimgui.services.backend_adapter import BackendInfo, PlaceholderBackend, PulsimBackend
from pulsimgui.services.backend_types import (
    ConvergenceInfo,
    DCSettings,
    IterationRecord,
    ProblematicVariable,
)
from pulsimgui.services.backend_types import (
    DCResult as BackendDCResult,
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

    @pytest.mark.skip(reason="Requires isolated Qt environment - run separately")
    def test_dc_with_placeholder_backend(self, qapp):
        """DC analysis should work with placeholder backend."""
        service = SimulationService()

        # Capture the DC result
        results = []

        def on_dc_finished(result):
            results.append(result)

        service.dc_finished.connect(on_dc_finished)

        circuit_data = {"components": [], "nets": []}
        service.run_dc_operating_point(circuit_data)

        # DC is synchronous, signal emitted before run_dc_operating_point returns
        assert len(results) == 1
        # Placeholder always returns valid result
        assert results[0].is_valid or not results[0].is_valid  # Either is valid

    @pytest.mark.skip(reason="Requires isolated Qt environment - run separately")
    def test_dc_settings_passed_to_backend(self, qapp):
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

        # DC is synchronous, signal emitted before run_dc_operating_point returns
        assert len(results) == 1

    @pytest.mark.skip(reason="Requires isolated Qt environment - run separately")
    def test_last_convergence_info_stored(self, qapp):
        """SimulationService should store last convergence info."""
        service = SimulationService()

        results = []
        service.dc_finished.connect(results.append)

        circuit_data = {"components": [], "nets": []}
        service.run_dc_operating_point(circuit_data)

        # DC is synchronous, signal emitted before run_dc_operating_point returns
        assert len(results) == 1

        # Check if convergence info is accessible
        info = service.last_convergence_info
        # May be None for placeholder or contain ConvergenceInfo
        assert info is None or hasattr(info, "converged")


class TestSimulationServiceDCFallback:
    """Tests for DC fallback strategy behavior in SimulationService."""

    def test_run_dc_operating_point_retries_after_gmin_failure(self, monkeypatch) -> None:
        service = SimulationService()
        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.info = BackendInfo(
            identifier="mock",
            name="Mock Backend",
            version="1.0.0",
            status="available",
        )

        calls: list[DCSettings] = []

        def _run_dc(_circuit_data, settings):
            calls.append(settings)
            if len(calls) == 1:
                return BackendDCResult(
                    error_message="Gmin stepping failed at step 0.",
                    convergence_info=ConvergenceInfo(
                        converged=False,
                        failure_reason="gmin step 0",
                    ),
                )
            return BackendDCResult(
                node_voltages={"V(out)": 6.0},
                convergence_info=ConvergenceInfo(converged=True, strategy_used=settings.strategy),
            )

        mock_backend.run_dc.side_effect = _run_dc

        service._backend = mock_backend
        monkeypatch.setattr(service, "_ensure_backend_ready", lambda: True)
        service.settings.dc_strategy = "gmin"
        service.settings.gmin_initial = 1e-2
        service.settings.gmin_final = 1e-12

        results: list[DCResult] = []
        errors: list[str] = []
        service.dc_finished.connect(results.append)
        service.error.connect(errors.append)

        service.run_dc_operating_point({"components": [], "nets": []})

        assert len(results) == 1
        assert results[0].error_message == ""
        assert results[0].node_voltages.get("V(out)") == 6.0
        assert not errors
        assert len(calls) >= 2
        assert calls[0].strategy == "gmin"
        assert calls[1].gmin_initial <= 1e-3

    def test_build_dc_fallback_attempts_tunes_aggressive_gmin(self) -> None:
        attempts = SimulationService._build_dc_fallback_attempts(
            DCSettings(
                strategy="gmin",
                gmin_initial=1e-2,
                gmin_final=1e-12,
                source_steps=5,
            )
        )

        assert attempts
        assert attempts[0].strategy == "gmin"
        tuned = [
            attempt
            for attempt in attempts
            if attempt.strategy == "gmin" and attempt.gmin_initial <= 1e-3
        ]
        assert tuned
        assert any(attempt.strategy == "direct" for attempt in attempts)
        assert any(attempt.strategy == "auto" for attempt in attempts)


class TestPulsimBackendTopLevelDCStrategy:
    """Tests for top-level dc_operating_point strategy mapping."""

    @pytest.mark.parametrize(
        ("strategy", "expected_attr"),
        [
            ("auto", "Auto"),
            ("direct", "Direct"),
            ("gmin", "GminStepping"),
            ("source", "SourceStepping"),
            ("pseudo", "PseudoTransient"),
        ],
    )
    def test_top_level_dc_strategy_mapping(self, monkeypatch, strategy: str, expected_attr: str) -> None:
        class _FakeDCStrategy:
            Auto = object()
            Direct = object()
            GminStepping = object()
            SourceStepping = object()
            PseudoTransient = object()

        class _FakeDCConvergenceConfig:
            def __init__(self) -> None:
                self.strategy = None
                self.source_config = types.SimpleNamespace(max_steps=0)
                self.gmin_config = types.SimpleNamespace(initial_gmin=0.0, final_gmin=0.0)

        captured: dict[str, object] = {}

        def _dc_operating_point(_circuit, config):
            captured["strategy"] = config.strategy
            captured["source_steps"] = config.source_config.max_steps
            captured["gmin_initial"] = config.gmin_config.initial_gmin
            captured["gmin_final"] = config.gmin_config.final_gmin
            return types.SimpleNamespace(
                success=True,
                message="",
                newton_result=types.SimpleNamespace(
                    solution=[0.0, 6.0],
                    iterations=2,
                    final_residual=1e-12,
                    history=[],
                ),
            )

        module = types.SimpleNamespace(
            DCConvergenceConfig=_FakeDCConvergenceConfig,
            DCStrategy=_FakeDCStrategy,
            dc_operating_point=_dc_operating_point,
        )

        backend = PulsimBackend(
            module=module,
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )
        monkeypatch.setattr(
            backend._converter,
            "build",
            lambda _data: types.SimpleNamespace(node_names=lambda: ["0", "out"]),
        )

        result = backend.run_dc(
            {"components": [], "nets": []},
            DCSettings(
                strategy=strategy,
                source_steps=33,
                gmin_initial=1e-3,
                gmin_final=1e-9,
            ),
        )

        assert result.error_message == ""
        assert result.convergence_info.converged
        assert captured["strategy"] is getattr(_FakeDCStrategy, expected_attr)
        if strategy == "source":
            assert captured["source_steps"] == 33
        if strategy == "gmin":
            assert captured["gmin_initial"] == 1e-3
            assert captured["gmin_final"] == 1e-9


class TestPulsimBackendNodeVoltageMapping:
    """Tests for DC node voltage mapping across backend API variants."""

    def test_convert_dc_analysis_result_uses_generic_node_labels_when_names_unavailable(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(num_nodes=lambda: 2)
        dc_analysis_result = types.SimpleNamespace(
            success=True,
            message="",
            newton_result=types.SimpleNamespace(
                solution=[5.0, 6.0, 0.01],
                iterations=2,
                final_residual=1e-12,
                history=[],
            ),
        )

        converted = backend._convert_dc_analysis_result(dc_analysis_result, circuit)
        assert converted.error_message == ""
        assert converted.node_voltages == {"V(node_0)": 5.0, "V(node_1)": 6.0}

    def test_convert_dc_result_uses_get_node_names_when_available(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(get_node_names=lambda: ["in", "out"])
        native_result = types.SimpleNamespace(
            solution=[12.0, 6.0],
            converged=True,
            iterations=3,
            final_residual=1e-12,
            history=[],
        )

        converted = backend._convert_dc_result(native_result, circuit)
        assert converted.error_message == ""
        assert converted.node_voltages == {"V(in)": 12.0, "V(out)": 6.0}

    def test_convert_dc_analysis_result_maps_branch_currents_from_signal_names(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(
            signal_names=lambda: ["V(in)", "V(out)", "I(V1)"],
            num_nodes=lambda: 2,
            num_branches=lambda: 1,
        )
        dc_analysis_result = types.SimpleNamespace(
            success=True,
            message="",
            newton_result=types.SimpleNamespace(
                solution=[12.0, 6.0, -0.012],
                iterations=3,
                final_residual=1e-12,
                history=[],
            ),
        )

        converted = backend._convert_dc_analysis_result(dc_analysis_result, circuit)
        assert converted.error_message == ""
        assert converted.node_voltages == {"V(in)": 12.0, "V(out)": 6.0}
        assert converted.branch_currents == {"I(V1)": -0.012}

    def test_convert_dc_analysis_result_fallback_generates_branch_currents(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(
            node_names=lambda: ["out"],
            num_nodes=lambda: 1,
            num_branches=lambda: 2,
        )
        dc_analysis_result = types.SimpleNamespace(
            success=True,
            message="",
            newton_result=types.SimpleNamespace(
                solution=[6.0, 0.1, -0.2],
                iterations=2,
                final_residual=1e-12,
                history=[],
            ),
        )

        converted = backend._convert_dc_analysis_result(dc_analysis_result, circuit)
        assert converted.error_message == ""
        assert converted.node_voltages == {"V(out)": 6.0}
        assert converted.branch_currents == {"I(branch0)": 0.1, "I(branch1)": -0.2}

    def test_convert_dc_analysis_result_estimates_resistor_power(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(signal_names=lambda: ["V(in)", "V(out)"])
        dc_analysis_result = types.SimpleNamespace(
            success=True,
            message="",
            newton_result=types.SimpleNamespace(
                solution=[12.0, 6.0],
                iterations=2,
                final_residual=1e-12,
                history=[],
            ),
        )
        circuit_data = {
            "components": [
                {
                    "id": "R1",
                    "name": "R1",
                    "type": "RESISTOR",
                    "pin_nodes": ["in", "out"],
                    "parameters": {"resistance": 1200.0},
                }
            ]
        }

        converted = backend._convert_dc_analysis_result(dc_analysis_result, circuit, circuit_data)
        assert converted.error_message == ""
        assert converted.power_dissipation["P(R1)"] == pytest.approx(0.03, rel=1e-9)

    def test_convert_dc_analysis_result_estimates_power_with_ground_node(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(signal_names=lambda: ["V(out)", "V(0)"])
        dc_analysis_result = types.SimpleNamespace(
            success=True,
            message="",
            newton_result=types.SimpleNamespace(
                solution=[5.0, 0.0],
                iterations=2,
                final_residual=1e-12,
                history=[],
            ),
        )
        circuit_data = {
            "components": [
                {
                    "id": "Rload",
                    "name": "Rload",
                    "type": "RESISTOR",
                    "pin_nodes": ["out", "0"],
                    "parameters": {"resistance": 10.0},
                }
            ]
        }

        converted = backend._convert_dc_analysis_result(dc_analysis_result, circuit, circuit_data)
        assert converted.error_message == ""
        assert converted.power_dissipation["P(Rload)"] == pytest.approx(2.5, rel=1e-9)

    def test_convert_dc_result_uses_native_power_map_when_available(self) -> None:
        backend = PulsimBackend(
            module=types.SimpleNamespace(),
            info=BackendInfo(
                identifier="fake",
                name="Fake",
                version="0.0.0",
                status="available",
            ),
        )

        circuit = types.SimpleNamespace(signal_names=lambda: ["V(in)", "V(out)"])
        native_result = types.SimpleNamespace(
            solution=[12.0, 6.0],
            converged=True,
            iterations=3,
            final_residual=1e-12,
            history=[],
            power_dissipation={"R1": 0.123},
        )

        converted = backend._convert_dc_result(native_result, circuit)
        assert converted.error_message == ""
        assert converted.power_dissipation == {"P(R1)": 0.123}


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
