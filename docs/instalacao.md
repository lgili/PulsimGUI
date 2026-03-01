# Installation and Run

## Requirements

- Python `>= 3.10`
- `pip`
- Virtual environment recommended (`venv`)

## Option 1: Release (Recommended)

Download your platform package from [Releases](https://github.com/lgili/PulsimGUI/releases/latest).

## Option 2: Install via pip

Package source: [PyPI — pulsimgui](https://pypi.org/project/pulsimgui/).

```bash
python3 -m pip install --upgrade pip
python3 -m pip install pulsimgui
```

Run:

```bash
pulsimgui
```

or:

```bash
python3 -m pulsimgui
```

The package on PyPI is published by the release workflow (`.github/workflows/release.yml`) on each new `v*` tag.

## Option 3: Run from source

```bash
git clone https://github.com/lgili/PulsimGUI.git
cd PulsimGui
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
python3 -m pulsimgui
```

## Validate Active Backend

```bash
python3 -c "import pulsim; print(pulsim.__version__)"
```

Expected project baseline: `0.5.3`.

## Recommended In-App Runtime Settings

Open `Preferences → Simulation → Backend Runtime`:

- `Source`: `PyPI`
- `Target version`: `v0.5.3`
- `Auto-sync backend on startup`: enabled

## Common Issues

### Qt plugin error

```bash
QT_QPA_PLATFORM=cocoa python3 -m pulsimgui
```

For headless Linux:

```bash
QT_QPA_PLATFORM=offscreen python3 -m pulsimgui
```

### Backend unavailable

- Confirm `pulsim` is installed in the same Python environment used by the app.
- Reopen the app and use `Install / Update Backend` in runtime settings.
