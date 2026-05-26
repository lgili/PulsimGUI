"""Default trace palette used when a spec doesn't pin its own colour."""

from __future__ import annotations

from .plot_canvas import DEFAULT_PALETTE


def next_palette_color(index: int) -> str:
    """Return the next default trace colour, cycling through the palette."""
    return DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]


__all__ = ["next_palette_color"]
