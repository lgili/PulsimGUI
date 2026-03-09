#!/usr/bin/env python3
"""Generate a multi-resolution Windows .ico from the packaged PNG icon."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ICON_SIZES = [
    (16, 16),
    (20, 20),
    (24, 24),
    (32, 32),
    (40, 40),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]


def _ico_image_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 6:
        raise RuntimeError(f"Invalid ICO file (too small): {path}")
    reserved, icon_type, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or icon_type != 1 or count <= 0:
        raise RuntimeError(f"Invalid ICO header in {path}")
    return count


def ensure_windows_icon(project_root: Path, *, force: bool = False) -> Path:
    """Create ``packaging/icons/pulsimgui.ico`` from ``pulsimgui.png``."""
    icon_dir = project_root / "packaging" / "icons"
    png_path = icon_dir / "pulsimgui.png"
    ico_path = icon_dir / "pulsimgui.ico"

    if ico_path.exists() and not force:
        print(f"Windows icon already exists: {ico_path}")
        return ico_path

    if not png_path.exists():
        raise FileNotFoundError(f"Missing source icon: {png_path}")

    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(
            "Pillow is required to generate packaging/icons/pulsimgui.ico"
        ) from exc

    icon_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(png_path) as source:
        rgba = source.convert("RGBA")
        rgba.save(ico_path, format="ICO", sizes=ICON_SIZES)

    if not ico_path.exists():
        raise RuntimeError(f"Failed to generate icon: {ico_path}")

    image_count = _ico_image_count(ico_path)
    print(f"Generated Windows icon: {ico_path} ({image_count} size(s))")
    return ico_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Windows .ico icon exists")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Project root path (defaults to repository root)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate .ico even when it already exists",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit status on failure",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    try:
        ensure_windows_icon(project_root, force=bool(args.force))
    except Exception as exc:
        if args.strict:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Warning: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
