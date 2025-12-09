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
    """Create a modern, minimalist SVG icon for PulsimGui."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Modern gradient background -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#1a1a2e"/>
      <stop offset="50%" style="stop-color:#16213e"/>
      <stop offset="100%" style="stop-color:#0f3460"/>
    </linearGradient>
    <!-- Accent gradient for the pulse -->
    <linearGradient id="pulseGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#00d9ff"/>
      <stop offset="50%" style="stop-color:#00ff88"/>
      <stop offset="100%" style="stop-color:#00d9ff"/>
    </linearGradient>
    <!-- Glow effect -->
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <!-- Subtle inner shadow -->
    <filter id="innerShadow" x="-50%" y="-50%" width="200%" height="200%">
      <feOffset dx="0" dy="2"/>
      <feGaussianBlur stdDeviation="3" result="offset-blur"/>
      <feComposite operator="out" in="SourceGraphic" in2="offset-blur" result="inverse"/>
      <feFlood flood-color="#000" flood-opacity="0.2" result="color"/>
      <feComposite operator="in" in="color" in2="inverse" result="shadow"/>
      <feComposite operator="over" in="shadow" in2="SourceGraphic"/>
    </filter>
  </defs>

  <!-- Background with rounded corners (iOS/macOS style) -->
  <rect x="8" y="8" width="240" height="240" rx="48" fill="url(#bgGrad)" filter="url(#innerShadow)"/>

  <!-- Subtle grid pattern -->
  <g opacity="0.1" stroke="#ffffff" stroke-width="0.5">
    <line x1="48" y1="8" x2="48" y2="248"/>
    <line x1="88" y1="8" x2="88" y2="248"/>
    <line x1="128" y1="8" x2="128" y2="248"/>
    <line x1="168" y1="8" x2="168" y2="248"/>
    <line x1="208" y1="8" x2="208" y2="248"/>
    <line x1="8" y1="88" x2="248" y2="88"/>
    <line x1="8" y1="128" x2="248" y2="128"/>
    <line x1="8" y1="168" x2="248" y2="168"/>
  </g>

  <!-- PWM Pulse waveform - signature of power electronics -->
  <g filter="url(#glow)">
    <!-- Main pulse signal -->
    <path d="M 40 148
             L 40 148 L 56 148 L 56 108 L 88 108 L 88 148
             L 104 148 L 104 108 L 136 108 L 136 148
             L 152 148 L 152 108 L 184 108 L 184 148
             L 200 148 L 200 108 L 216 108 L 216 148"
          stroke="url(#pulseGrad)" stroke-width="5" fill="none"
          stroke-linecap="round" stroke-linejoin="round"/>
  </g>

  <!-- Circuit nodes/connection points -->
  <circle cx="40" cy="148" r="6" fill="#00d9ff" filter="url(#glow)"/>
  <circle cx="216" cy="148" r="6" fill="#00ff88" filter="url(#glow)"/>

  <!-- Stylized "P" lettermark hint with circuit aesthetic -->
  <g opacity="0.15">
    <circle cx="128" cy="128" r="70" stroke="#ffffff" stroke-width="2" fill="none"/>
  </g>

  <!-- Small accent dots representing data/simulation points -->
  <g fill="#00d9ff" opacity="0.6">
    <circle cx="56" cy="108" r="3"/>
    <circle cx="104" cy="108" r="3"/>
    <circle cx="152" cy="108" r="3"/>
    <circle cx="200" cy="108" r="3"/>
  </g>

  <!-- PULSIM text - modern, clean typography -->
  <text x="128" y="198"
        text-anchor="middle"
        font-family="SF Pro Display, -apple-system, Helvetica Neue, Arial, sans-serif"
        font-size="32"
        font-weight="600"
        letter-spacing="6"
        fill="#ffffff"
        opacity="0.95">PULSIM</text>
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
