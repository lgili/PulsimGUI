#!/usr/bin/env python3
"""Generate application icons for all platforms.

This script creates placeholder icons for PulsimGui.
For production, replace these with professionally designed icons.

Icon requirements:
- macOS: .icns file containing multiple resolutions (16, 32, 64, 128, 256, 512, 1024)
- Windows: .ico file containing multiple resolutions (16, 32, 48, 64, 128, 256)
- Linux: .png file at 256x256 or higher

Usage:
    python scripts/generate_icons.py

To create production icons:
1. Create a 1024x1024 PNG master icon
2. Use tools like:
   - macOS: iconutil or makeicns
   - Windows: imagemagick or online converters
   - Linux: just use the PNG directly
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ICONS_DIR = PROJECT_ROOT / "packaging" / "icons"


def create_placeholder_svg() -> str:
    """Create a simple SVG placeholder icon."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#4A90D9"/>
      <stop offset="100%" style="stop-color:#2E5D8C"/>
    </linearGradient>
  </defs>
  <!-- Background -->
  <rect x="16" y="16" width="224" height="224" rx="32" fill="url(#bg)"/>
  <!-- Circuit symbol - simplified waveform -->
  <path d="M 48 128 L 80 128 L 96 80 L 112 176 L 128 80 L 144 176 L 160 128 L 208 128"
        stroke="white" stroke-width="8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Ground symbol -->
  <path d="M 128 176 L 128 200 M 112 200 L 144 200 M 120 208 L 136 208 M 126 216 L 130 216"
        stroke="white" stroke-width="4" fill="none" stroke-linecap="round"/>
  <!-- Text -->
  <text x="128" y="56" text-anchor="middle" font-family="Arial, sans-serif" font-size="24" font-weight="bold" fill="white">PulsimGui</text>
</svg>'''


def generate_png(svg_path: Path, png_path: Path, size: int) -> bool:
    """Convert SVG to PNG using available tools."""
    # Try different conversion tools
    converters = [
        # Inkscape
        ["inkscape", str(svg_path), "--export-filename", str(png_path),
         f"--export-width={size}", f"--export-height={size}"],
        # ImageMagick
        ["convert", "-background", "none", "-resize", f"{size}x{size}",
         str(svg_path), str(png_path)],
        # rsvg-convert (librsvg)
        ["rsvg-convert", "-w", str(size), "-h", str(size),
         str(svg_path), "-o", str(png_path)],
    ]

    for cmd in converters:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    return False


def generate_icns(png_path: Path, icns_path: Path) -> bool:
    """Generate macOS .icns file from PNG."""
    if sys.platform != "darwin":
        print("  Skipping .icns generation (not on macOS)")
        return False

    iconset_path = png_path.parent / "pulsimgui.iconset"
    iconset_path.mkdir(exist_ok=True)

    # Required sizes for .icns
    sizes = [16, 32, 64, 128, 256, 512, 1024]

    # Create SVG first
    svg_path = png_path.parent / "pulsimgui.svg"
    svg_path.write_text(create_placeholder_svg())

    for size in sizes:
        # Standard resolution
        icon_name = f"icon_{size}x{size}.png"
        if not generate_png(svg_path, iconset_path / icon_name, size):
            print(f"  Warning: Could not generate {size}x{size} icon")

        # Retina resolution (2x)
        if size <= 512:
            retina_name = f"icon_{size}x{size}@2x.png"
            generate_png(svg_path, iconset_path / retina_name, size * 2)

    # Convert iconset to icns
    try:
        subprocess.run([
            "iconutil", "-c", "icns", str(iconset_path), "-o", str(icns_path)
        ], check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  Warning: iconutil not available")
        return False


def generate_ico(png_path: Path, ico_path: Path) -> bool:
    """Generate Windows .ico file from PNG."""
    # Try ImageMagick
    sizes = "16,32,48,64,128,256"
    try:
        subprocess.run([
            "convert", str(png_path),
            "-define", f"icon:auto-resize={sizes}",
            str(ico_path)
        ], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  Warning: ImageMagick not available for .ico generation")
        return False


def main():
    """Generate all platform icons."""
    print("Generating PulsimGui icons...")

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    # Create SVG source
    svg_path = ICONS_DIR / "pulsimgui.svg"
    svg_path.write_text(create_placeholder_svg())
    print(f"  Created: {svg_path}")

    # Generate PNG (base icon)
    png_path = ICONS_DIR / "pulsimgui.png"
    if generate_png(svg_path, png_path, 256):
        print(f"  Created: {png_path}")
    else:
        print("  Warning: Could not generate PNG. Install inkscape, imagemagick, or librsvg.")
        print("  Creating empty placeholder...")
        png_path.touch()

    # Generate macOS .icns
    icns_path = ICONS_DIR / "pulsimgui.icns"
    if generate_icns(png_path, icns_path):
        print(f"  Created: {icns_path}")

    # Generate Windows .ico
    ico_path = ICONS_DIR / "pulsimgui.ico"
    if generate_ico(png_path, ico_path):
        print(f"  Created: {ico_path}")

    print()
    print("Icon generation complete!")
    print()
    print("For production builds, replace these placeholder icons with")
    print("professionally designed icons in the following formats:")
    print(f"  - macOS:   {ICONS_DIR}/pulsimgui.icns")
    print(f"  - Windows: {ICONS_DIR}/pulsimgui.ico")
    print(f"  - Linux:   {ICONS_DIR}/pulsimgui.png")


if __name__ == "__main__":
    main()
