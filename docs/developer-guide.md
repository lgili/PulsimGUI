# Developer Guide

Contributing guide for code, tests, and documentation in PulsimGui.

## Project Structure

```text
src/pulsimgui/
  commands/      # undo/redo
  models/        # circuit/project data
  services/      # simulation, backend, persistence
  views/         # Qt interface (windows, panels, viewer)
  presenters/    # UI flow integration
  utils/         # utilities
  resources/     # themes, icons, branding

docs/            # MkDocs Material documentation
examples/        # reference .pulsim projects
tests/           # pytest suite
```

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
```

## Run the App Locally

```bash
python3 -m pulsimgui
```

## Quality and Tests

```bash
ruff check src tests
pytest
```

For headless environments:

```bash
QT_QPA_PLATFORM=offscreen pytest
```

## Local Documentation

```bash
python3 -m pip install -r docs/requirements.txt
mkdocs serve
mkdocs build --strict
```

## Practical Conventions

- Prefer small, traceable PRs.
- Always include regression tests for bug fixes.
- Avoid coupling simulation logic directly into view classes.
- When changing simulation flow, validate examples in `examples/`.

## Docs Pipeline (GitHub Pages)

- Docs build runs on PRs and on `main`.
- Deploy runs automatically on `main`/`workflow_dispatch` via GitHub Pages Actions.
- Entry point: `.github/workflows/docs-pages.yml`.
