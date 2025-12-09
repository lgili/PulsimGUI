"""Tests for backend discovery and selection logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pulsimgui.services import backend_adapter


@pytest.fixture(autouse=True)
def disable_entry_points(monkeypatch):
    """Ensure tests run with a predictable entry-point list."""
    monkeypatch.setattr(backend_adapter.metadata, "entry_points", lambda: ())


def test_backend_loader_falls_back_to_placeholder(monkeypatch):
    """When Pulsim import fails the loader should expose the demo backend."""

    def _missing(_name: str):
        raise ImportError("pulsim not installed")

    monkeypatch.setattr(backend_adapter, "import_module", _missing)

    loader = backend_adapter.BackendLoader()
    info = loader.backend.info

    assert info.identifier == "placeholder"
    assert info.status == "error"
    assert "pulsim not installed" in info.message


def test_backend_loader_prefers_real_backend_and_allows_switch(monkeypatch):
    """The detected Pulsim backend should activate by default and be switchable."""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        __file__="/tmp/pulsim/__init__.py",
    )

    class DummyConverter:
        def __init__(self, module):
            self.module = module

    monkeypatch.setattr(backend_adapter, "import_module", lambda name: fake_module)
    monkeypatch.setattr(backend_adapter, "CircuitConverter", DummyConverter)

    loader = backend_adapter.BackendLoader()

    active_info = loader.backend.info
    identifiers = {info.identifier for info in loader.available_backends}

    assert active_info.identifier == "pulsim"
    assert identifiers.issuperset({"pulsim", "placeholder"})

    placeholder_info = loader.activate("placeholder")
    assert placeholder_info.identifier == "placeholder"
    assert loader.backend.info.identifier == "placeholder"


def test_backend_loader_rejects_unknown_identifier(monkeypatch):
    """Selecting a non-existent backend should raise an explicit error."""

    def _missing(_name: str):
        raise ImportError("pulsim not installed")

    monkeypatch.setattr(backend_adapter, "import_module", _missing)

    loader = backend_adapter.BackendLoader()

    with pytest.raises(ValueError):
        loader.activate("does-not-exist")
