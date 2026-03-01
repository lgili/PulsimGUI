# Building PulsimGui Standalone Installers

This document explains how to build standalone PulsimGui executables that include all dependencies.

## Overview

The build system creates self-contained executables using PyInstaller. The resulting application includes:

- **Frontend**: PySide6 (Qt6), pyqtgraph, numpy, qtawesome
- **Backend**: pulsim simulation engine with native extensions
- All required Qt plugins and resources

Users don't need to install Python or any dependencies - the executable runs standalone.

## Quick Start

```bash
# Install build dependencies
pip install -e ".[build]"

# Build for current platform
python scripts/build.py
```

## Build Output

| Platform | Output | Location |
|----------|--------|----------|
| macOS | .app bundle + .dmg | `dist/PulsimGui.app`, `dist/PulsimGui-*.dmg` |
| Windows | .exe installer | `dist/PulsimGui.exe` |
| Linux | AppImage + binary | `dist/*.AppImage`, `dist/pulsimgui` |

## Platform-Specific Instructions

### macOS

```bash
# Prerequisites
brew install python@3.12

# Build
pip install -e ".[build]"
python scripts/build.py

# Output: dist/PulsimGui.app, dist/PulsimGui-0.5.3-macos.dmg
```

The macOS build creates:
1. `PulsimGui.app` - Standard macOS application bundle
2. `PulsimGui-0.5.3-macos.dmg` - Distributable disk image

### Windows

```powershell
# Prerequisites: Python 3.10+ from python.org

# Build
pip install -e ".[build]"
python scripts/build.py

# Output: dist/PulsimGui.exe
```

For NSIS installer (optional):
1. Install [NSIS](https://nsis.sourceforge.io/)
2. Run the build script - it will automatically create an installer if NSIS is available

### Linux

```bash
# Prerequisites (Ubuntu/Debian)
sudo apt install python3 python3-pip python3-venv fuse libfuse2

# Build
pip install -e ".[build]"
python scripts/build.py

# Output: dist/PulsimGui-0.5.3-x86_64.AppImage, dist/pulsimgui
```

The Linux build creates:
1. `pulsimgui` - Standalone executable
2. `PulsimGui-0.5.3-x86_64.AppImage` - Portable AppImage (recommended for distribution)

## Build Options

```bash
# Clean build artifacts
python scripts/build.py --clean

# Build without creating installer (just the executable)
python scripts/build.py --no-installer

# Specify target platform (for cross-compilation research only)
python scripts/build.py --platform windows
```

## GitHub Actions

Automated releases are configured in `.github/workflows/release.yml`. They trigger on:
- Git tags starting with `v` (e.g., `v0.5.3`)
- Manual workflow dispatch

### Creating a Release

1. Tag the commit:
   ```bash
   git tag v0.5.3
   git push origin v0.5.3
   ```

2. GitHub Actions will automatically:
   - Build for macOS, Windows, and Linux
   - Publish artifacts to GitHub Releases
   - Build and publish `pulsimgui` (`sdist` + `wheel`) to PyPI

3. Verify release assets and package availability:
   - GitHub: `https://github.com/lgili/PulsimGUI/releases`
   - PyPI: `https://pypi.org/project/pulsimgui/`

### PyPI One-Time Setup (Trusted Publishing)

In PyPI project settings (`pulsimgui`), configure a trusted publisher with:

- Owner: `lgili`
- Repository: `PulsimGUI`
- Workflow: `release.yml`
- Environment: *(leave empty, unless you enforce one in GitHub Actions)*

## Customizing Icons

The build uses icons from `packaging/icons/`:

| Platform | File | Requirements |
|----------|------|--------------|
| macOS | `pulsimgui.icns` | Multi-resolution icon set |
| Windows | `pulsimgui.ico` | 16-256px sizes |
| Linux | `pulsimgui.png` | 256x256 or higher |

To generate placeholder icons:
```bash
python scripts/generate_icons.py
```

For production, replace with professionally designed icons.

## Troubleshooting

### PyInstaller Import Errors

If PyInstaller can't find certain modules:

1. Add them to `hiddenimports` in `pulsimgui.spec`
2. Or create a hook file in `hooks/hook-modulename.py`

### Missing pulsim Native Extension

Ensure pulsim is installed before building:
```bash
pip install pulsim>=0.5.3
```

The spec file automatically locates and bundles the native `.so`/`.pyd` extension.

### Large Binary Size

The builds include the full Qt6 framework. To reduce size:

1. Ensure `excludes` in the spec file removes unused modules
2. Enable UPX compression (already enabled for Windows/Linux)
3. Strip debug symbols (enabled for Linux)

### Code Signing (Production)

For production releases:

**macOS:**
```bash
codesign --deep --force --sign "Developer ID Application: Your Name" dist/PulsimGui.app
```

**Windows:**
Use `signtool.exe` with your code signing certificate.

## File Structure

```
PulsimGui/
├── pulsimgui.spec          # PyInstaller spec file
├── scripts/
│   ├── build.py            # Main build script
│   └── generate_icons.py   # Icon generation utility
├── hooks/
│   ├── hook-pulsim.py      # PyInstaller hook for pulsim
│   └── hook-qtawesome.py   # PyInstaller hook for qtawesome
├── packaging/
│   ├── icons/              # Application icons
│   ├── macos/              # macOS-specific files
│   ├── windows/            # Windows NSIS installer
│   └── linux/              # Linux desktop files
└── .github/workflows/
    └── release.yml         # Release + PyPI publish pipeline
```
