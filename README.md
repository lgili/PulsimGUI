<div align="center">

<img src="docs/imgs/dashboard_dark.png" alt="PulsimGui — Dark Theme" width="100%" />

# PulsimGui

**Professional GUI for power electronics simulation with Pulsim.**

[![Release](https://img.shields.io/github/v/release/lgili/PulsimGUI?label=latest&color=brightgreen)](https://github.com/lgili/PulsimGUI/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/pulsimgui?label=PyPI&color=orange)](https://pypi.org/project/pulsimgui/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-0ea5e9)](https://lgili.github.io/PulsimGUI/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

[**Download latest release**](https://github.com/lgili/PulsimGUI/releases/latest) · [**Install from PyPI**](https://pypi.org/project/pulsimgui/) · [**Documentation**](https://lgili.github.io/PulsimGUI/) · [**Report a bug**](https://github.com/lgili/PulsimGUI/issues)

</div>

---

**PulsimGui** is a cross-platform desktop interface for [Pulsim](https://github.com/lgili/PulsimCore), focused on modeling and validating power converter topologies.

## Key Features

- Schematic editor with drag-and-drop workflow.
- Component library focused on power electronics.
- Transient simulation with advanced solver controls.
- Integrated waveform viewer with signal measurements.
- Ready-to-run examples (`RC`, `buck`, `boost`, and more).

## Official Documentation

Full documentation is available at:

- [https://lgili.github.io/PulsimGUI/](https://lgili.github.io/PulsimGUI/)

Main content includes:

- Installation and execution
- GUI guides and workflow
- Simulation and backend configuration
- Practical tutorials
- Technical reference for contributors

## Installation

### 1. Release (Recommended)

Use installers from [Releases](https://github.com/lgili/PulsimGUI/releases/latest).

### 2. Install via pip

```bash
python3 -m pip install --upgrade pip
python3 -m pip install pulsimgui
```

Run:

```bash
pulsimgui
```

The `pulsimgui` package is published to PyPI by the release pipeline (`.github/workflows/release.yml`) whenever a new tag `v*` is released.

### 3. Development setup (source code)

```bash
git clone https://github.com/lgili/PulsimGUI.git
cd PulsimGui
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
python3 -m pulsimgui
```

## Recommended Backend

For reproducible behavior, use **`pulsim v0.5.2`**.

Quick check:

```bash
python3 -c "import pulsim; print(pulsim.__version__)"
```

In the app: `Preferences → Simulation → Backend Runtime`.

## Development

### Tests

```bash
pytest
```

### Lint

```bash
ruff check src tests
```

### Local docs build

```bash
python3 -m pip install -r docs/requirements.txt
mkdocs build --strict
mkdocs serve
```

## GitHub Pages (Docs)

Documentation is published through:

- `.github/workflows/docs-pages.yml`

Automatic deploy runs on `main` and `workflow_dispatch`.

> Repository setting required: **Settings → Pages → Source: GitHub Actions**.

## Contributing

- Open issues for bug reports and feature requests.
- For PRs, include context, validation steps, and evidence (logs/screenshots).
- Update docs whenever a user workflow or feature changes.

## License

MIT — see [LICENSE](LICENSE).
