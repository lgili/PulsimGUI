"""Pytest configuration and fixtures."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def circuit():
    """Create a test circuit."""
    from pulsimgui.models.circuit import Circuit

    return Circuit(name="test_circuit")


@pytest.fixture
def project():
    """Create a test project."""
    from pulsimgui.models.project import Project

    return Project(name="test_project")


@pytest.fixture
def command_stack(qapp):
    """Create a command stack for testing."""
    from pulsimgui.commands.base import CommandStack

    return CommandStack()
