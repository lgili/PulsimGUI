#!/usr/bin/env python3
"""Build script for creating PulsimGui standalone distributions.

This script creates self-contained executables that include:
- All Python dependencies (PySide6, numpy, pyqtgraph, qtawesome)
- The pulsim simulation backend with native extensions
- All required Qt plugins and resources

No additional installation is required on the target machine.
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
PACKAGING_DIR = PROJECT_ROOT / "packaging"
HOOKS_DIR = PROJECT_ROOT / "hooks"


def get_version() -> str:
    """Get version from pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject) as f:
        for line in f:
            if line.startswith("version"):
                return line.split("=")[1].strip().strip('"')
    return "0.1.0"


def clean() -> None:
    """Clean build artifacts."""
    print("Cleaning build artifacts...")
    for path in [DIST_DIR, BUILD_DIR]:
        if path.exists():
            shutil.rmtree(path)
            print(f"  Removed {path}")


def install_dependencies() -> None:
    """Install build dependencies and ensure all runtime deps are available."""
    print("Installing build dependencies...")

    # Build tools
    build_deps = [
        "pyinstaller>=6.0",
    ]

    # Platform-specific build tools
    if sys.platform == "darwin":
        build_deps.append("dmgbuild>=1.6.0")

    subprocess.run([
        sys.executable, "-m", "pip", "install", *build_deps
    ], check=True)

    # Ensure all runtime dependencies are installed
    print("Verifying runtime dependencies...")
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "PySide6>=6.5.0",
        "pyqtgraph>=0.13.0",
        "numpy>=1.24.0",
        "qtawesome>=1.3.0",
        "pulsim>=0.1.11",
    ], check=True)


def build_pyinstaller() -> Path:
    """Build with PyInstaller."""
    print("Building with PyInstaller...")

    # Install the package first
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)
    ], check=True)

    # Run PyInstaller
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(PROJECT_ROOT / "pulsimgui.spec"),
    ], cwd=PROJECT_ROOT, check=True)

    # Return path to built application
    system = platform.system()
    if system == "Darwin":
        return DIST_DIR / "PulsimGui.app"
    elif system == "Windows":
        return DIST_DIR / "PulsimGui.exe"
    else:
        return DIST_DIR / "pulsimgui"


def build_macos_dmg(app_path: Path) -> Path:
    """Create macOS DMG installer."""
    print("Creating macOS DMG...")

    version = get_version()
    dmg_path = DIST_DIR / f"PulsimGui-{version}-macos.dmg"

    # Use dmgbuild if available, otherwise use hdiutil
    try:
        import dmgbuild
        settings = PACKAGING_DIR / "macos" / "dmg_settings.json"
        dmgbuild.build_dmg(
            str(dmg_path),
            "PulsimGui",
            settings=str(settings) if settings.exists() else None,
        )
    except ImportError:
        # Fallback to hdiutil
        subprocess.run([
            "hdiutil", "create",
            "-volname", "PulsimGui",
            "-srcfolder", str(app_path),
            "-ov",
            "-format", "UDZO",
            str(dmg_path),
        ], check=True)

    print(f"Created: {dmg_path}")
    return dmg_path


def build_windows_installer(exe_path: Path) -> Path:
    """Create Windows NSIS installer."""
    print("Creating Windows installer...")

    nsis_script = PACKAGING_DIR / "windows" / "installer.nsi"
    if not nsis_script.exists():
        print("  NSIS script not found, skipping installer creation")
        return exe_path

    # Check if NSIS is available
    nsis_cmd = shutil.which("makensis")
    if not nsis_cmd:
        print("  NSIS not found, skipping installer creation")
        print("  Install NSIS from https://nsis.sourceforge.io/")
        return exe_path

    subprocess.run([nsis_cmd, str(nsis_script)], check=True)

    version = get_version()
    installer_path = PACKAGING_DIR / "windows" / f"PulsimGui-{version}-setup.exe"
    if installer_path.exists():
        final_path = DIST_DIR / installer_path.name
        shutil.move(str(installer_path), str(final_path))
        print(f"Created: {final_path}")
        return final_path

    return exe_path


def build_linux_appimage(exe_path: Path) -> Path:
    """Create Linux AppImage."""
    print("Creating Linux AppImage...")

    version = get_version()
    appimage_name = f"PulsimGui-{version}-x86_64.AppImage"
    appdir = BUILD_DIR / "PulsimGui.AppDir"

    # Create AppDir structure
    appdir.mkdir(parents=True, exist_ok=True)
    (appdir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (appdir / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
    (appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True, exist_ok=True)

    # Copy executable
    shutil.copy2(exe_path, appdir / "usr" / "bin" / "pulsimgui")

    # Copy desktop file
    desktop_src = PACKAGING_DIR / "linux" / "pulsimgui.desktop"
    if desktop_src.exists():
        shutil.copy2(desktop_src, appdir / "usr" / "share" / "applications" / "pulsimgui.desktop")
        shutil.copy2(desktop_src, appdir / "pulsimgui.desktop")

    # Copy icon
    icon_src = PACKAGING_DIR / "icons" / "pulsimgui.png"
    if icon_src.exists():
        shutil.copy2(icon_src, appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "pulsimgui.png")
        shutil.copy2(icon_src, appdir / "pulsimgui.png")

    # Create AppRun
    apprun = appdir / "AppRun"
    apprun.write_text('''#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/pulsimgui" "$@"
''')
    apprun.chmod(0o755)

    # Download and run appimagetool
    appimagetool = BUILD_DIR / "appimagetool"
    if not appimagetool.exists():
        print("  Downloading appimagetool...")
        subprocess.run([
            "wget", "-q",
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage",
            "-O", str(appimagetool),
        ], check=True)
        appimagetool.chmod(0o755)

    # Create AppImage
    env = {"ARCH": "x86_64"}
    subprocess.run([
        str(appimagetool), str(appdir), str(DIST_DIR / appimage_name)
    ], env={**subprocess.os.environ, **env}, check=True)

    appimage_path = DIST_DIR / appimage_name
    print(f"Created: {appimage_path}")
    return appimage_path


def main():
    parser = argparse.ArgumentParser(description="Build PulsimGui distributions")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument("--no-installer", action="store_true", help="Skip installer creation")
    parser.add_argument("--platform", choices=["windows", "macos", "linux", "auto"],
                       default="auto", help="Target platform")
    args = parser.parse_args()

    if args.clean:
        clean()
        return

    # Determine platform
    if args.platform == "auto":
        system = platform.system()
        if system == "Darwin":
            target = "macos"
        elif system == "Windows":
            target = "windows"
        else:
            target = "linux"
    else:
        target = args.platform

    print(f"Building for: {target}")
    print(f"Version: {get_version()}")
    print()

    # Install dependencies
    install_dependencies()

    # Build with PyInstaller
    app_path = build_pyinstaller()
    print(f"Built: {app_path}")

    # Create platform-specific installer
    if not args.no_installer:
        if target == "macos":
            build_macos_dmg(app_path)
        elif target == "windows":
            build_windows_installer(app_path)
        elif target == "linux":
            build_linux_appimage(app_path)

    print()
    print("Build complete!")
    print(f"Output directory: {DIST_DIR}")


if __name__ == "__main__":
    main()
