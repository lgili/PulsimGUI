"""Tests for backend protocol compliance."""

from __future__ import annotations

from types import SimpleNamespace
from typing import runtime_checkable

import pytest

from pulsimgui.services.backend_adapter import (
    BackendCallbacks,
    BackendInfo,
    PlaceholderBackend,
    PulsimBackend,
    SimulationBackend,
)
from pulsimgui.services.backend_protocol import BackendCapabilities
from pulsimgui.services.backend_types import (
    ACSettings,
    DCSettings,
    ThermalSettings,
    TransientResult,
    TransientSettings,
)


class TestSimulationBackendProtocol:
    """Tests for SimulationBackend protocol."""

    def test_placeholder_implements_protocol(self):
        """PlaceholderBackend should implement SimulationBackend."""
        backend = PlaceholderBackend()

        # Check required attributes
        assert hasattr(backend, "info")
        assert hasattr(backend, "capabilities")

        # Check required methods
        assert hasattr(backend, "has_capability")
        assert hasattr(backend, "run_transient")
        assert hasattr(backend, "run_dc")
        assert hasattr(backend, "run_ac")
        assert hasattr(backend, "run_thermal")
        assert hasattr(backend, "request_pause")
        assert hasattr(backend, "request_resume")
        assert hasattr(backend, "request_stop")

    def test_placeholder_info_structure(self):
        """PlaceholderBackend info should have required fields."""
        backend = PlaceholderBackend()
        info = backend.info

        assert isinstance(info, BackendInfo)
        assert info.identifier == "placeholder"
        assert info.name is not None
        assert info.version is not None
        assert info.status is not None
        assert isinstance(info.capabilities, set)

    def test_placeholder_capabilities(self):
        """PlaceholderBackend should report all capabilities for demo mode."""
        backend = PlaceholderBackend()

        assert "transient" in backend.capabilities
        assert "dc" in backend.capabilities
        assert "ac" in backend.capabilities
        assert "thermal" in backend.capabilities

    def test_placeholder_has_capability(self):
        """has_capability should return correct values."""
        backend = PlaceholderBackend()

        assert backend.has_capability("transient") is True
        assert backend.has_capability("dc") is True
        assert backend.has_capability("ac") is True
        assert backend.has_capability("thermal") is True
        assert backend.has_capability("nonexistent") is False


class TestPlaceholderBackendDC:
    """Tests for PlaceholderBackend DC analysis."""

    def test_run_dc_returns_result(self):
        """run_dc should return a DCResult."""
        backend = PlaceholderBackend()
        settings = DCSettings()

        result = backend.run_dc({}, settings)

        assert result is not None
        assert result.is_valid
        assert len(result.node_voltages) > 0

    def test_run_dc_has_convergence_info(self):
        """DC result should have convergence info."""
        backend = PlaceholderBackend()
        settings = DCSettings()

        result = backend.run_dc({}, settings)

        assert result.convergence_info is not None
        assert result.convergence_info.converged is True


class TestPlaceholderBackendAC:
    """Tests for PlaceholderBackend AC analysis."""

    def test_run_ac_returns_result(self):
        """run_ac should return an ACResult."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=100000)

        result = backend.run_ac({}, settings)

        assert result is not None
        assert result.is_valid
        assert len(result.frequencies) > 0

    def test_run_ac_frequency_range(self):
        """AC result frequencies should span requested range."""
        backend = PlaceholderBackend()
        settings = ACSettings(f_start=100, f_stop=10000, points_per_decade=5)

        result = backend.run_ac({}, settings)

        assert min(result.frequencies) >= 100
        assert max(result.frequencies) <= 10000


class TestPlaceholderBackendThermal:
    """Tests for PlaceholderBackend thermal simulation."""

    def test_run_thermal_returns_result(self):
        """run_thermal should return a ThermalResult."""
        backend = PlaceholderBackend()
        electrical_result = TransientResult(
            time=[i * 1e-6 for i in range(100)],
            signals={"V(out)": [1.0] * 100},
        )
        settings = ThermalSettings()

        result = backend.run_thermal({}, electrical_result, settings)

        assert result is not None
        assert result.is_synthetic is True
        assert len(result.devices) > 0

    def test_run_thermal_has_foster_stages(self):
        """Thermal devices should have Foster network data."""
        backend = PlaceholderBackend()
        electrical_result = TransientResult(time=[0, 1e-3])
        settings = ThermalSettings()

        result = backend.run_thermal({}, electrical_result, settings)

        for device in result.devices:
            assert len(device.foster_stages) > 0

    def test_run_thermal_has_loss_breakdown(self):
        """Thermal devices should have loss breakdown."""
        backend = PlaceholderBackend()
        electrical_result = TransientResult(time=[0, 1e-3])
        settings = ThermalSettings()

        result = backend.run_thermal({}, electrical_result, settings)

        for device in result.devices:
            assert device.losses is not None
            assert device.losses.total > 0


class TestPulsimBackendProtocol:
    """Tests for PulsimBackend protocol compliance (mocked)."""

    @pytest.fixture
    def mock_pulsim_module(self):
        """Create a mock pulsim module."""
        module = SimpleNamespace(
            __version__="0.3.0",
            __file__="/tmp/pulsim/__init__.py",
            v1=SimpleNamespace(
                DCConvergenceSolver=object,
                NewtonOptions=lambda: SimpleNamespace(),
            ),
            ThermalSimulator=object,
            Simulator=lambda c, o: SimpleNamespace(
                run_transient_with_progress=lambda **kw: SimpleNamespace(
                    time=[0],
                    to_dict=lambda: {"time": [0], "signals": {}},
                    final_status=0,
                ),
            ),
            SimulationOptions=lambda: SimpleNamespace(),
            SimulationController=lambda: SimpleNamespace(
                request_pause=lambda: None,
                request_resume=lambda: None,
                request_stop=lambda: None,
            ),
            SolverStatus=lambda x: SimpleNamespace(name="Success"),
        )
        # Set up SolverStatus.Success
        module.SolverStatus.Success = 0
        return module

    @pytest.fixture
    def mock_converter(self, monkeypatch):
        """Mock CircuitConverter."""
        from pulsimgui.services import backend_adapter

        class MockConverter:
            def __init__(self, module):
                pass

            def build(self, data):
                return SimpleNamespace(node_names=lambda: ["out", "in"])

        monkeypatch.setattr(backend_adapter, "CircuitConverter", MockConverter)

    def test_pulsim_backend_capabilities_detection(self, mock_pulsim_module, mock_converter):
        """PulsimBackend should detect capabilities from module."""
        info = BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="0.3.0",
            status="available",
        )
        backend = PulsimBackend(mock_pulsim_module, info)

        # Should detect DC capability from v1.DCConvergenceSolver
        assert "dc" in backend.capabilities

        # Should detect thermal capability from ThermalSimulator
        assert "thermal" in backend.capabilities

        # Transient is always available
        assert "transient" in backend.capabilities

    def test_pulsim_backend_has_capability(self, mock_pulsim_module, mock_converter):
        """has_capability should work correctly."""
        info = BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="0.3.0",
            status="available",
        )
        backend = PulsimBackend(mock_pulsim_module, info)

        assert backend.has_capability("transient") is True
        assert backend.has_capability("dc") is True
        assert backend.has_capability("nonexistent") is False

    def test_pulsim_backend_capabilities_cached(self, mock_pulsim_module, mock_converter):
        """Capabilities should be cached after first access."""
        info = BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="0.3.0",
            status="available",
        )
        backend = PulsimBackend(mock_pulsim_module, info)

        caps1 = backend.capabilities
        caps2 = backend.capabilities

        # Should be same object (cached)
        assert caps1 is caps2


class TestBackendCapabilitiesProtocol:
    """Tests for BackendCapabilities protocol."""

    def test_protocol_is_runtime_checkable(self):
        """BackendCapabilities should be runtime checkable."""
        assert hasattr(BackendCapabilities, "__protocol_attrs__") or hasattr(
            BackendCapabilities, "_is_runtime_protocol"
        )

    def test_placeholder_satisfies_protocol_methods(self):
        """PlaceholderBackend should have all protocol methods."""
        backend = PlaceholderBackend()

        # All methods from BackendCapabilities
        assert callable(getattr(backend, "run_transient", None))
        assert callable(getattr(backend, "run_dc", None))
        assert callable(getattr(backend, "run_ac", None))
        assert callable(getattr(backend, "run_thermal", None))
        assert callable(getattr(backend, "has_capability", None))
        assert callable(getattr(backend, "request_pause", None))
        assert callable(getattr(backend, "request_resume", None))
        assert callable(getattr(backend, "request_stop", None))
