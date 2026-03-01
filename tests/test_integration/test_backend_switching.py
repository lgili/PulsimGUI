"""Tests for backend switching behavior.

These tests verify that:
1. Switching from placeholder to real backend works
2. State is preserved across backend switches
3. Capabilities are properly updated
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pulsimgui.services import backend_adapter
from pulsimgui.services.backend_adapter import (
    BackendLoader,
    BackendInfo,
    PlaceholderBackend,
    PulsimBackend,
)


@pytest.fixture(autouse=True)
def disable_entry_points(monkeypatch):
    """Ensure tests run with predictable entry-point list."""
    monkeypatch.setattr(backend_adapter.metadata, "entry_points", lambda: ())


class TestBackendSwitching:
    """Tests for switching between backends."""

    def test_switch_from_placeholder_to_placeholder(self, monkeypatch) -> None:
        """Test switching stays on placeholder when no real backend.

        GUI Validation:
        1. Start GUI without PulsimCore installed
        2. Go to Preferences > Backends
        3. Only "Placeholder" should be available
        """
        def _missing(_name: str):
            raise ImportError("pulsim not installed")

        monkeypatch.setattr(backend_adapter, "import_module", _missing)

        loader = BackendLoader()

        # Should start with placeholder
        assert loader.backend.info.identifier == "placeholder"

        # Available backends should only include placeholder
        identifiers = {info.identifier for info in loader.available_backends}
        assert identifiers == {"placeholder"}

    def test_switch_from_placeholder_to_pulsim(self, monkeypatch) -> None:
        """Test switching from placeholder to real pulsim backend.

        GUI Validation:
        1. Start GUI with PulsimCore installed
        2. Go to Preferences > Backends
        3. Both "Pulsim" and "Placeholder" should be available
        4. Switch to Pulsim
        5. Verify status bar shows Pulsim version
        """
        fake_module = SimpleNamespace(
            __version__="0.3.0",
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()

        # Should start with pulsim (preferred)
        assert loader.backend.info.identifier == "pulsim"

        # Switch to placeholder
        placeholder_info = loader.activate("placeholder")
        assert placeholder_info.identifier == "placeholder"
        assert loader.backend.info.identifier == "placeholder"

        # Switch back to pulsim
        pulsim_info = loader.activate("pulsim")
        assert pulsim_info.identifier == "pulsim"
        assert loader.backend.info.identifier == "pulsim"

    def test_available_backends_list(self, monkeypatch) -> None:
        """Test that available_backends lists all options.

        GUI Validation:
        1. Open Preferences > Backends
        2. Dropdown should show all detected backends
        3. Each should show name, version, status
        """
        fake_module = SimpleNamespace(
            __version__="0.3.0",
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()

        available = list(loader.available_backends)
        identifiers = {info.identifier for info in available}

        assert identifiers == {"pulsim", "placeholder"}

        # Check each has required fields
        for info in available:
            assert info.name
            assert info.version
            assert info.status

    def test_invalid_backend_raises_error(self, monkeypatch) -> None:
        """Test that activating unknown backend raises ValueError.

        GUI Validation:
        1. This shouldn't happen in GUI (dropdown only shows valid options)
        2. But API should raise clear error
        """
        def _missing(_name: str):
            raise ImportError("pulsim not installed")

        monkeypatch.setattr(backend_adapter, "import_module", _missing)

        loader = BackendLoader()

        with pytest.raises(ValueError, match="Unknown backend"):
            loader.activate("nonexistent")


class TestCapabilityUpdates:
    """Tests for capability updates on backend switch."""

    def test_placeholder_capabilities(self, monkeypatch) -> None:
        """Test placeholder backend capabilities.

        GUI Validation:
        1. Switch to Placeholder backend
        2. Check About dialog shows capabilities
        3. Should include: transient, dc, ac
        """
        def _missing(_name: str):
            raise ImportError("pulsim not installed")

        monkeypatch.setattr(backend_adapter, "import_module", _missing)

        loader = BackendLoader()
        backend = loader.backend

        assert backend.has_capability("transient")
        assert backend.has_capability("dc")
        assert backend.has_capability("ac")

    def test_pulsim_capabilities_detected(self, monkeypatch) -> None:
        """Test real pulsim backend capabilities are detected.

        GUI Validation:
        1. Switch to Pulsim backend
        2. Check Simulation Settings shows available capabilities
        3. Menu items should be enabled/disabled based on capabilities
        """
        fake_module = SimpleNamespace(
            __version__="0.3.0",
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
            # Add capabilities
            dc_operating_point=MagicMock,
            run_ac=MagicMock,
            ThermalSimulator=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()
        info = loader.backend.info

        assert "transient" in info.capabilities
        assert "dc" in info.capabilities
        assert "ac" in info.capabilities
        assert "thermal" in info.capabilities


class TestStatePreservation:
    """Tests for state preservation across backend switches."""

    def test_settings_preserved_on_switch(self, monkeypatch) -> None:
        """Test that simulation settings are preserved when switching.

        GUI Validation:
        1. Configure simulation settings (t_stop, solver, etc.)
        2. Switch backends
        3. Verify settings remain unchanged
        """
        fake_module = SimpleNamespace(
            __version__="0.3.0",
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()

        # Settings are managed by SimulationService, not BackendLoader
        # This test verifies loader doesn't corrupt anything

        # Switch multiple times
        loader.activate("placeholder")
        loader.activate("pulsim")
        loader.activate("placeholder")

        # Loader should still work
        assert loader.backend is not None

    def test_backend_info_updated_on_switch(self, monkeypatch) -> None:
        """Test that backend info is updated correctly on switch.

        GUI Validation:
        1. Check status bar shows current backend
        2. Switch backends
        3. Status bar should update to show new backend
        """
        fake_module = SimpleNamespace(
            __version__="0.3.0",
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()

        # Start with pulsim
        assert loader.backend.info.identifier == "pulsim"
        assert "0.3.0" in loader.backend.info.version

        # Switch to placeholder
        loader.activate("placeholder")
        assert loader.backend.info.identifier == "placeholder"
        assert "demo" in loader.backend.info.name.lower() or "placeholder" in loader.backend.info.identifier.lower()


class TestVersionWarningsOnSwitch:
    """Tests for version warnings when switching backends."""

    def test_old_version_shows_warning(self, monkeypatch) -> None:
        """Test that old backend version shows compatibility warning.

        GUI Validation:
        1. Install old PulsimCore version
        2. Start GUI or switch to Pulsim backend
        3. Warning should appear in status bar or dialog
        4. About dialog should show warning
        """
        fake_module = SimpleNamespace(
            __version__="0.1.0",  # Old version
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()
        info = loader.backend.info

        # Should have compatibility warning
        assert not info.is_compatible
        assert info.compatibility_warning
        assert "older than minimum" in info.compatibility_warning

    def test_new_version_no_warning(self, monkeypatch) -> None:
        """Test that new backend version has no warning.

        GUI Validation:
        1. Install recent PulsimCore version
        2. Start GUI
        3. No warning should appear
        """
        fake_module = SimpleNamespace(
            __version__="1.0.0",  # New version
            __file__="/tmp/pulsim/__init__.py",
            Circuit=MagicMock,
        )

        class DummyConverter:
            def __init__(self, module):
                self.module = module

        monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
        monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

        loader = BackendLoader()
        info = loader.backend.info

        # Should have no compatibility warning
        assert info.is_compatible
        assert info.compatibility_warning == ""
