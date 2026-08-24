"""Visual identity tokens for schematic component symbols.

Centralises the values that define the *Pulsim Pro* visual language so
every component renders with a coherent look:

  - Real electrical components (R, L, C, semis) → IEEE/ANSI-style stroked
    symbols with a single body weight (``STROKE_BODY``) and a thinner
    detail weight (``STROKE_DETAIL``).
  - Signal/control blocks (PI, PID, Σ, K, PWM, transforms…) → rounded
    cards with a coloured stripe on the connection side and a centred
    glyph rendered in the block label font.

Per-component ``_draw_symbol`` methods should read pen widths, radii,
and typography from this module instead of hardcoding numbers, so that
the look stays unified as new components are added.
"""

from __future__ import annotations

from PySide6.QtGui import QFont


# ── Strokes ────────────────────────────────────────────────────────────────
# Three weights cover the entire vocabulary:
#   BODY   = main outline of a component or block body
#   DETAIL = secondary internal markings (channels, arrows, sign glyphs)
#   LEAD   = pin lead lines from the body out to the pin terminal
STROKE_BODY = 2.2
STROKE_DETAIL = 1.4
STROKE_LEAD = 1.6

# ── Blocks (signal/control) ────────────────────────────────────────────────
BLOCK_RADIUS = 6.0           # outer body corner radius
BLOCK_STRIPE_WIDTH = 4.0     # accent stripe thickness
BLOCK_STRIPE_INSET = 3.0     # gap between body edge and stripe
BLOCK_STRIPE_RADIUS = 2.0    # stripe corner radius (matches outer rounding)
BLOCK_STRIPE_MARGIN_Y = 4.0  # vertical inset of the stripe inside the body
BLOCK_LABEL_SIZE = 11        # block-body label point size

# ── Pins ───────────────────────────────────────────────────────────────────
PIN_RADIUS = 2.4             # core pin bubble
PIN_RING_EXTRA = 0.4         # outer ring thickness above core
PIN_GLOW_EXTRA = 1.5         # halo radius above core
PIN_GLOW_ALPHA_LIGHT = 58
PIN_GLOW_ALPHA_DARK = 75
PIN_RING_STROKE = 1.5

# ── Selection / hover ──────────────────────────────────────────────────────
SELECTION_RADIUS = 4.0       # corner radius of the selection halo
SELECTION_STROKE = 1.8
SELECTION_HANDLE = 7.0       # side of the 4 corner-handle squares
HOVER_RADIUS = 3.0
HOVER_STROKE = 1.0


def block_label_font(base: QFont) -> QFont:
    """Return a copy of ``base`` styled for the centred glyph of a block.

    Bold, slightly larger than the default UI font so a one- or two-glyph
    label (``Σ``, ``K``, ``PID``) reads at a glance even when the schematic
    is zoomed out.
    """
    font = QFont(base)
    font.setBold(True)
    font.setPointSize(BLOCK_LABEL_SIZE)
    return font


__all__ = [
    "STROKE_BODY",
    "STROKE_DETAIL",
    "STROKE_LEAD",
    "BLOCK_RADIUS",
    "BLOCK_STRIPE_WIDTH",
    "BLOCK_STRIPE_INSET",
    "BLOCK_STRIPE_RADIUS",
    "BLOCK_STRIPE_MARGIN_Y",
    "BLOCK_LABEL_SIZE",
    "PIN_RADIUS",
    "PIN_RING_EXTRA",
    "PIN_GLOW_EXTRA",
    "PIN_GLOW_ALPHA_LIGHT",
    "PIN_GLOW_ALPHA_DARK",
    "PIN_RING_STROKE",
    "SELECTION_RADIUS",
    "SELECTION_STROKE",
    "HOVER_RADIUS",
    "HOVER_STROKE",
    "block_label_font",
]
