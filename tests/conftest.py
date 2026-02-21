"""Pytest configuration and fixtures."""

import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class SimpleQtBot:
    """Simple Qt bot for signal waiting without full pytest-qt dependency."""

    def __init__(self, app: QApplication):
        self._app = app

    def waitUntil(self, callback, timeout: int = 5000) -> None:
        """Wait until callback returns True or timeout is reached."""
        deadline = time.time() + timeout / 1000.0
        while time.time() < deadline:
            QCoreApplication.processEvents()
            if callback():
                return
            time.sleep(0.01)
        raise TimeoutError(f"Condition not met within {timeout}ms")

    def addWidget(self, widget) -> None:
        """Track a widget (no-op for basic implementation)."""
        pass


@pytest.fixture
def qtbot(qapp):
    """Provide a simple Qt bot for signal waiting."""
    return SimpleQtBot(qapp)


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
