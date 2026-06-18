"""Structural design tokens — the theme-independent half of the design system.

Colours live in :class:`pulsimgui.services.theme_service.ThemeColors` and flip
between light/dark. Everything in THIS file is constant across themes: the
spacing rhythm, corner radii, the type scale, motion timing, and elevation.
These values are lifted from the ``termico`` app's design language (an 8 px
grid, Tailwind-style ``xl/lg/md/sm`` radii, a tight type scale) so the two
apps feel consistent.

Usage::

    from pulsimgui.views.design import Space, Radius, FontSize

    layout.setContentsMargins(*Space.inset_card())     # 16,16,16,16
    layout.setSpacing(Space.MD)                         # 12
    frame.setStyleSheet(f"border-radius: {Radius.LG}px;")

All values are integer PIXELS (Qt's QSS unit), so they drop straight into
stylesheets and ``setContentsMargins`` / ``setSpacing`` without conversion.
"""

from __future__ import annotations

from typing import Final


class Space:
    """Spacing scale on an 8 px grid (with a 4 px half-step).

    Pick the smallest step that reads as "separate". The named helpers
    (``inset_*``) give the conventional paddings so screens don't re-invent
    "how much padding does a card get".
    """

    NONE: Final = 0
    XS: Final = 4     # hairline gap, icon↔label
    SM: Final = 8     # tight group spacing
    MD: Final = 12    # default control spacing
    LG: Final = 16    # card inset, section gap
    XL: Final = 24    # page gutter, major section gap
    XXL: Final = 32   # page top/bottom padding
    XXXL: Final = 48  # hero / empty-state breathing room

    @staticmethod
    def inset_card() -> tuple[int, int, int, int]:
        """``(l, t, r, b)`` content margins for a Card body."""
        return (Space.LG, Space.LG, Space.LG, Space.LG)

    @staticmethod
    def inset_page() -> tuple[int, int, int, int]:
        """Content margins for a top-level page/panel."""
        return (Space.XL, Space.XXL, Space.XL, Space.XXL)

    @staticmethod
    def inset_compact() -> tuple[int, int, int, int]:
        """Content margins for a dense list row / toolbar."""
        return (Space.MD, Space.SM, Space.MD, Space.SM)


class Radius:
    """Corner radii. ``XL`` cards / ``LG`` controls / ``MD`` small /
    ``PILL`` badges — the termico convention."""

    NONE: Final = 0
    SM: Final = 6     # chips, small inputs
    MD: Final = 8     # buttons, inputs, list rows
    LG: Final = 10    # panels, group boxes
    XL: Final = 14    # cards, dialogs
    PILL: Final = 999  # badges, segmented controls


class FontSize:
    """Type scale in pixels. A tight, restrained ladder — most UI text is
    ``BODY`` (13); reach for the bigger steps deliberately."""

    CAPTION: Final = 11   # timestamps, hint text, axis labels
    SMALL: Final = 12     # secondary metadata
    BODY: Final = 13      # default body / control text
    LABEL: Final = 14     # form labels, list primary text (often MEDIUM weight)
    SUBTITLE: Final = 15  # card titles, sub-section headers
    TITLE: Final = 18     # section / panel titles
    HEADING: Final = 22   # page titles
    DISPLAY: Final = 28   # KPI numbers, hero figures


class FontWeight:
    """Font weights. Reserve ``SEMIBOLD``/``BOLD`` for hierarchy, not
    emphasis-by-default."""

    REGULAR: Final = 400
    MEDIUM: Final = 500
    SEMIBOLD: Final = 600
    BOLD: Final = 700


class Motion:
    """Animation durations in milliseconds. 60–200 ms is the perceptual sweet
    spot for UI motion — long enough to read as motion, short enough to feel
    instant. Pair with an ease-out curve for entrances."""

    INSTANT: Final = 60   # micro-feedback (press, hover tint)
    FAST: Final = 120     # the default: panel slide, fade, tab switch
    BASE: Final = 200     # larger transitions, drawer open
    SLOW: Final = 320     # deliberate / first-run reveals only


class Elevation:
    """Drop-shadow parameters for ``QGraphicsDropShadowEffect``. Shadows are
    soft and low — depth, not drama. Each tuple is
    ``(blur_radius, y_offset, alpha)``; the colour is the theme's shadow
    token applied with ``alpha``."""

    FLAT: Final = (0, 0, 0)
    RAISED: Final = (16, 2, 28)    # cards
    OVERLAY: Final = (32, 8, 48)   # popovers, menus, dialogs
    DRAGGING: Final = (40, 6, 64)  # an item being dragged
