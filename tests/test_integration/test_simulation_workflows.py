"""Integration tests for full simulation workflows.

These tests verify end-to-end simulation workflows using example circuits.
Each test corresponds to a GUI validation scenario described in example_circuits.py.
"""

from __future__ import annotations

import math
import pytest

from pulsimgui.services.backend_adapter import PlaceholderBackend, BackendInfo
from pulsimgui.services.backend_types import (
    DCSettings,
    ACSettings,
    TransientSettings,
    ThermalSettings,
)
from pulsimgui.services.thermal_service import ThermalAnalysisService

from .example_circuits import (
    voltage_divider,
    rc_lowpass_filter,
    rc_transient,
    mosfet_switch,
    diode_rectifier,
    rl_circuit,
)


class TestDCAnalysisWorkflow:
    """Integration tests for DC operating point analysis."""

    def test_voltage_divider_dc_analysis(self) -> None:
        """Test DC analysis on voltage divider circuit.

        Expected: V(out) = 5.0V for equal resistors with 10V input.

        GUI Validation:
        1. Load voltage_divider circuit
        2. Run DC Operating Point (F6)
        3. Check V(out) ≈ 5.0V in results dialog
        """
        backend = PlaceholderBackend()
        circuit_data = voltage_divider()
        settings = DCSettings()

        result = backend.run_dc(circuit_data, settings)

        assert result.error_message == ""
        assert result.convergence_info.converged
        # Placeholder returns synthetic data, but structure should be correct
        assert isinstance(result.node_voltages, dict)
        assert isinstance(result.branch_currents, dict)

    def test_diode_rectifier_dc_convergence(self) -> None:
        """Test DC convergence on circuit with diode.

        Diode circuits can be challenging for convergence due to
        the exponential I-V characteristic.

        GUI Validation:
        1. Load diode_rectifier circuit
        2. Run DC Operating Point (F6)
        3. Verify convergence succeeds
        4. Check diode forward voltage ≈ 0.7V
        """
        backend = PlaceholderBackend()
        circuit_data = diode_rectifier()
        settings = DCSettings(strategy="auto", max_iterations=100)

        result = backend.run_dc(circuit_data, settings)

        assert result.error_message == ""
        assert result.convergence_info.converged

    def test_mosfet_switch_dc_analysis(self) -> None:
        """Test DC analysis on MOSFET switch circuit.

        GUI Validation:
        1. Load mosfet_switch circuit
        2. Run DC Operating Point (F6)
        3. Verify MOSFET is ON (Vgs > Vth)
        4. Check drain current flows through load
        """
        backend = PlaceholderBackend()
        circuit_data = mosfet_switch()
        settings = DCSettings()

        result = backend.run_dc(circuit_data, settings)

        assert result.error_message == ""
        assert result.convergence_info.converged

    def test_dc_with_gmin_stepping(self) -> None:
        """Test DC analysis with GMIN stepping strategy.

        GUI Validation:
        1. In Simulation Settings, select GMIN Stepping
        2. Run DC Operating Point
        3. Verify convergence on difficult circuits
        """
        backend = PlaceholderBackend()
        circuit_data = diode_rectifier()
        settings = DCSettings(
            strategy="gmin",
            gmin_initial=1e-3,
            gmin_final=1e-12,
        )

        result = backend.run_dc(circuit_data, settings)

        assert result.error_message == ""


class TestACAnalysisWorkflow:
    """Integration tests for AC frequency analysis."""

    def test_rc_lowpass_frequency_response(self) -> None:
        """Test AC analysis on RC low-pass filter.

        Expected: -3dB at cutoff frequency (1kHz for R=1k, C=159nF)

        GUI Validation:
        1. Load rc_lowpass_filter circuit
        2. Run AC Analysis (F7) from 10Hz to 100kHz
        3. Check Bode plot shows -3dB at ~1kHz
        4. Check phase plot shows -45° at cutoff
        """
        backend = PlaceholderBackend()
        circuit_data = rc_lowpass_filter()
        settings = ACSettings(
            f_start=10.0,
            f_stop=100000.0,
            points_per_decade=10,
        )

        result = backend.run_ac(circuit_data, settings)

        assert result.error_message == ""
        assert result.is_valid
        assert len(result.frequencies) > 0
        assert len(result.magnitude) > 0
        assert len(result.phase) > 0

        # Verify frequency range
        assert min(result.frequencies) <= 100
        assert max(result.frequencies) >= 10000

    def test_ac_single_frequency(self) -> None:
        """Test AC analysis at single frequency point.

        GUI Validation:
        1. Run AC Analysis with very narrow range (e.g., 1kHz to 1kHz)
        2. Verify single data point returned
        """
        backend = PlaceholderBackend()
        circuit_data = rc_lowpass_filter()
        settings = ACSettings(
            f_start=1000.0,
            f_stop=1000.0,
            points_per_decade=1,
        )

        result = backend.run_ac(circuit_data, settings)

        assert result.error_message == ""
        assert result.is_valid

    def test_ac_wide_frequency_range(self) -> None:
        """Test AC analysis over wide frequency range.

        GUI Validation:
        1. Run AC Analysis from 1Hz to 1GHz
        2. Verify data spans entire range
        """
        backend = PlaceholderBackend()
        circuit_data = rc_lowpass_filter()
        settings = ACSettings(
            f_start=1.0,
            f_stop=1e9,
            points_per_decade=5,
        )

        result = backend.run_ac(circuit_data, settings)

        assert result.error_message == ""
        assert result.is_valid


class TestTransientWorkflow:
    """Integration tests for transient simulation."""

    def test_rc_transient_charging(self) -> None:
        """Test transient simulation of RC charging.

        Time constant tau = 1ms for R=1k, C=1µF

        GUI Validation:
        1. Load rc_transient circuit
        2. Run Transient from 0 to 5ms
        3. Verify exponential charging curve
        4. At t=1ms, V(out) ≈ 3.16V (63.2% of 5V)
        """
        backend = PlaceholderBackend()
        circuit_data = rc_transient()

        from pulsimgui.services.backend_adapter import BackendCallbacks

        progress_values = []
        time_points = []

        callbacks = BackendCallbacks(
            progress=lambda p, _: progress_values.append(p),
            data_point=lambda t, _: time_points.append(t),
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        # Use backend settings format
        from pulsimgui.services.simulation_service import SimulationSettings

        settings = SimulationSettings(t_start=0, t_stop=5e-3, t_step=1e-6)

        result = backend.run_transient(circuit_data, settings, callbacks)

        assert result.error_message == ""
        assert len(result.time) > 0

    def test_rl_transient(self) -> None:
        """Test transient simulation of RL circuit.

        Time constant tau = 100µs for R=100Ω, L=10mH

        GUI Validation:
        1. Load rl_circuit circuit
        2. Run Transient from 0 to 500µs
        3. Verify current rises exponentially
        """
        backend = PlaceholderBackend()
        circuit_data = rl_circuit()

        from pulsimgui.services.backend_adapter import BackendCallbacks
        from pulsimgui.services.simulation_service import SimulationSettings

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        settings = SimulationSettings(t_start=0, t_stop=500e-6, t_step=100e-9)

        result = backend.run_transient(circuit_data, settings, callbacks)

        assert result.error_message == ""

    def test_diode_rectifier_transient(self) -> None:
        """Test transient simulation of half-wave rectifier.

        GUI Validation:
        1. Load diode_rectifier circuit
        2. Run Transient for 2 periods at 60Hz (33ms)
        3. Verify half-wave rectified waveform
        """
        backend = PlaceholderBackend()
        circuit_data = diode_rectifier()

        from pulsimgui.services.backend_adapter import BackendCallbacks
        from pulsimgui.services.simulation_service import SimulationSettings

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )

        # 2 periods at 60Hz = 33.3ms
        settings = SimulationSettings(t_start=0, t_stop=33.3e-3, t_step=10e-6)

        result = backend.run_transient(circuit_data, settings, callbacks)

        assert result.error_message == ""


class TestThermalWorkflow:
    """Integration tests for thermal simulation."""

    def test_mosfet_thermal_analysis(self) -> None:
        """Test thermal analysis on MOSFET switch.

        GUI Validation:
        1. Load mosfet_switch circuit
        2. Run Transient simulation (PWM switching)
        3. Open Thermal Viewer
        4. Verify junction temperature shows rise from losses
        5. Check thermal badge shows "Real Data" or "(Synthetic Data)"
        """
        # ThermalAnalysisService generates synthetic data without backend
        service = ThermalAnalysisService()

        from pulsimgui.models.circuit import Circuit
        from pulsimgui.models.component import Component, ComponentType

        # Create a circuit with MOSFET for thermal analysis
        circuit = Circuit(name="MOSFET Thermal Test")
        mosfet = Component(type=ComponentType.MOSFET_N, name="M1")
        circuit.add_component(mosfet)

        # Build thermal result (synthetic)
        thermal_result = service.build_result(circuit, None)

        assert thermal_result is not None
        assert thermal_result.is_synthetic  # No backend, so synthetic
        assert len(thermal_result.devices) == 1
        assert thermal_result.devices[0].component_name == "M1"

    def test_thermal_with_backend(self) -> None:
        """Test thermal analysis with mock backend.

        GUI Validation:
        1. Ensure PulsimCore is installed
        2. Run Transient + Thermal
        3. Check Thermal Viewer shows real data (no synthetic badge)
        """
        from unittest.mock import MagicMock
        from pulsimgui.services.backend_types import (
            ThermalResult as BackendThermalResult,
            ThermalDeviceResult as BackendThermalDeviceResult,
            FosterStage,
            LossBreakdown,
        )

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            time=[0.0, 0.5, 1.0],
            devices=[
                BackendThermalDeviceResult(
                    name="M1",
                    junction_temperature=[25.0, 75.0, 100.0],
                    peak_temperature=100.0,
                    steady_state_temperature=95.0,
                    losses=LossBreakdown(conduction=10.0, switching_on=2.0, switching_off=1.5),
                    foster_stages=[
                        FosterStage(resistance=0.5, capacitance=0.01),
                    ],
                ),
            ],
            ambient_temperature=25.0,
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)

        from pulsimgui.models.circuit import Circuit
        from pulsimgui.models.component import Component, ComponentType

        circuit = Circuit(name="test")
        mosfet = Component(type=ComponentType.MOSFET_N, name="M1")
        circuit.add_component(mosfet)

        thermal_result = service.build_result(
            circuit, None, circuit_data=mosfet_switch()
        )

        assert thermal_result is not None
        assert not thermal_result.is_synthetic  # Real data from backend


class TestCombinedWorkflow:
    """Integration tests combining multiple analysis types."""

    def test_dc_then_ac_workflow(self) -> None:
        """Test running DC then AC on same circuit.

        GUI Validation:
        1. Load rc_lowpass_filter
        2. Run DC Operating Point - verify bias point
        3. Run AC Analysis - verify frequency response
        """
        backend = PlaceholderBackend()
        circuit_data = rc_lowpass_filter()

        # DC analysis first
        dc_result = backend.run_dc(circuit_data, DCSettings())
        assert dc_result.error_message == ""

        # Then AC analysis
        ac_result = backend.run_ac(circuit_data, ACSettings())
        assert ac_result.error_message == ""
        assert ac_result.is_valid

    def test_dc_then_transient_workflow(self) -> None:
        """Test running DC then Transient on same circuit.

        GUI Validation:
        1. Load rc_transient
        2. Run DC Operating Point - verify initial conditions
        3. Run Transient - verify dynamic behavior
        """
        backend = PlaceholderBackend()
        circuit_data = rc_transient()

        # DC analysis first
        dc_result = backend.run_dc(circuit_data, DCSettings())
        assert dc_result.error_message == ""

        # Then transient
        from pulsimgui.services.backend_adapter import BackendCallbacks
        from pulsimgui.services.simulation_service import SimulationSettings

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )
        settings = SimulationSettings(t_start=0, t_stop=1e-3, t_step=1e-6)

        transient_result = backend.run_transient(circuit_data, settings, callbacks)
        assert transient_result.error_message == ""

    def test_full_power_electronics_workflow(self) -> None:
        """Test complete power electronics analysis workflow.

        GUI Validation:
        1. Load mosfet_switch
        2. Run DC - verify operating point
        3. Run Transient - verify switching behavior
        4. Open Thermal Viewer - verify thermal data
        """
        backend = PlaceholderBackend()
        circuit_data = mosfet_switch()

        # DC analysis
        dc_result = backend.run_dc(circuit_data, DCSettings())
        assert dc_result.error_message == ""

        # Transient analysis
        from pulsimgui.services.backend_adapter import BackendCallbacks
        from pulsimgui.services.simulation_service import SimulationSettings

        callbacks = BackendCallbacks(
            progress=lambda p, _: None,
            data_point=lambda t, _: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        )
        settings = SimulationSettings(t_start=0, t_stop=100e-6, t_step=100e-9)

        transient_result = backend.run_transient(circuit_data, settings, callbacks)
        assert transient_result.error_message == ""

        # Thermal analysis (synthetic without real backend)
        from pulsimgui.models.circuit import Circuit
        from pulsimgui.models.component import Component, ComponentType

        circuit = Circuit(name="test")
        mosfet = Component(type=ComponentType.MOSFET_N, name="M1")
        circuit.add_component(mosfet)

        thermal_service = ThermalAnalysisService()
        thermal_result = thermal_service.build_result(circuit, None)
        assert thermal_result is not None
