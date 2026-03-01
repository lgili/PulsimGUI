# Contributing to PulsimGui

Thank you for your interest in contributing to PulsimGui! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)

---

## Code of Conduct

This project follows a standard code of conduct. Please be respectful and constructive in all interactions.

---

## Getting Started

### Finding Issues to Work On

- Look for issues labeled `good first issue` for beginner-friendly tasks
- Check `help wanted` labels for issues where we need community help
- Feel free to ask questions on any issue before starting work

### Reporting Bugs

1. Search existing issues to avoid duplicates
2. Use the bug report template
3. Include:
   - PulsimGui version
   - Operating system
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots if applicable

### Suggesting Features

1. Search existing issues and discussions
2. Use the feature request template
3. Explain the use case and benefits
4. Be open to discussion and alternative approaches

---

## Development Setup

### Prerequisites

- Python 3.10 or later
- Git

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/lgili/PulsimGui.git
cd PulsimGui

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Run the application
pulsimgui

# Run tests
pytest

# Run linting
ruff check src/ tests/
```

---

## Making Changes

### Branch Naming

Create a branch from `main` with a descriptive name:

- `feature/add-transformer-component`
- `fix/wire-routing-bug`
- `docs/update-user-manual`
- `refactor/simplify-command-stack`

### Commit Messages

Follow conventional commit format:

```
type(scope): short description

Longer description if needed.

Fixes #123
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(components): add IGBT component symbol
fix(wires): correct junction detection at T-intersections
docs(readme): update installation instructions
test(models): add serialization tests for Circuit
```

### Keep Commits Focused

- Each commit should represent one logical change
- Avoid mixing unrelated changes
- Squash work-in-progress commits before PR

---

## Pull Request Process

### Before Submitting

1. **Update from main**: `git fetch origin && git rebase origin/main`
2. **Run tests**: `pytest`
3. **Run linting**: `ruff check src/ tests/`
4. **Format code**: `black src/ tests/`
5. **Update documentation** if needed

### Creating the PR

1. Push your branch: `git push origin your-branch-name`
2. Open a PR on GitHub
3. Fill out the PR template completely
4. Link related issues

### PR Review

- Respond to review comments promptly
- Make requested changes in new commits (for easier review)
- Squash commits when approved and ready to merge

### After Merge

- Delete your branch
- Update local main: `git checkout main && git pull`

---

## Coding Standards

### Python Style

- **Formatter**: Black with 100 character line length
- **Linter**: Ruff
- **Python version**: 3.10+ (use modern syntax)

### Type Hints

Required for all public functions and methods:

```python
def calculate_power(voltage: float, current: float) -> float:
    """Calculate power from voltage and current."""
    return voltage * current
```

### Docstrings

Use Google style docstrings:

```python
def add_component(self, component: Component, position: tuple[float, float]) -> str:
    """Add a component to the circuit.

    Args:
        component: The component to add.
        position: The (x, y) position in scene coordinates.

    Returns:
        The ID of the added component.

    Raises:
        ValueError: If a component with the same ID already exists.
    """
```

### Import Organization

Imports should be organized in this order:

1. Standard library
2. Third-party packages
3. Local imports

```python
import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWidget
import numpy as np

from pulsimgui.models import Component
from pulsimgui.views import MainWindow
```

### Naming Conventions

- **Classes**: PascalCase (`ComponentItem`, `SimulationService`)
- **Functions/Methods**: snake_case (`get_component`, `run_simulation`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_GRID_SIZE`, `MAX_ZOOM`)
- **Private members**: Leading underscore (`_internal_state`, `_update_display`)

---

## Testing Guidelines

### Test File Organization

```
tests/
├── conftest.py           # Shared fixtures
├── test_models/
│   ├── test_component.py
│   ├── test_circuit.py
│   └── test_project.py
├── test_commands/
│   └── test_command_stack.py
├── test_views/
│   └── test_main_window.py
└── test_services/
    └── test_simulation.py
```

### Writing Tests

```python
import pytest
from pulsimgui.models import Component, ComponentType

class TestComponent:
    """Tests for Component model."""

    def test_create_with_defaults(self):
        """Component should initialize with provided values."""
        component = Component(
            id="test-123",
            type=ComponentType.RESISTOR,
            name="R1",
            position=(100, 200),
        )
        assert component.id == "test-123"
        assert component.type == ComponentType.RESISTOR

    def test_serialization_roundtrip(self):
        """Component should serialize and deserialize correctly."""
        original = Component(...)
        data = original.to_dict()
        restored = Component.from_dict(data)
        assert original == restored
```

### Using Fixtures

```python
# conftest.py
import pytest
from pulsimgui.models import Circuit, Component, ComponentType

@pytest.fixture
def sample_circuit():
    """Create a circuit with basic components."""
    circuit = Circuit(name="Test Circuit")
    circuit.add_component(Component(
        id="r1",
        type=ComponentType.RESISTOR,
        name="R1",
        position=(0, 0),
    ))
    return circuit
```

### GUI Testing

```python
from pytestqt.qtbot import QtBot

def test_component_selection(qtbot: QtBot, main_window):
    """Selecting a component should update properties panel."""
    # Add component
    main_window.scene.add_component(...)

    # Simulate click
    qtbot.mouseClick(main_window.scene_view, Qt.LeftButton, pos=QPoint(100, 100))

    # Verify
    assert main_window.properties_panel.current_component is not None
```

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_models/test_component.py

# Run tests matching pattern
pytest -k "serialization"

# Run with coverage
pytest --cov=src/pulsimgui --cov-report=html
```

---

## Documentation

### Code Documentation

- All public classes, methods, and functions need docstrings
- Complex algorithms should have inline comments
- Update docstrings when changing function behavior

### User Documentation

Located in `docs/`:

- `user-manual.md` - End-user documentation
- `tutorials.md` - Tutorial outlines
- `developer-guide.md` - Developer documentation

### Updating Documentation

- Update relevant docs when adding features
- Keep examples up to date
- Use clear, concise language
- Include screenshots where helpful

---

## Project Structure

When adding new features, follow the existing structure:

```
src/pulsimgui/
├── models/           # Data classes (no Qt dependencies)
├── views/            # Qt widgets and UI components
│   ├── schematic/    # Schematic editor components
│   ├── panels/       # Dockable panels
│   └── dialogs/      # Modal dialogs
├── commands/         # Undo/redo command classes
├── services/         # Business logic services
└── resources/        # Static resources (icons, themes)
```

### Guidelines

- **Models**: Pure Python, no Qt dependencies, serializable
- **Views**: Qt widgets, delegate logic to services/commands
- **Commands**: Encapsulate state changes, support undo/redo
- **Services**: Stateless business logic, can use workers for async

---

## Questions?

- Open a GitHub Discussion for general questions
- Create an issue for bugs or feature requests
- Tag maintainers if you need help with a PR

Thank you for contributing to PulsimGui!
