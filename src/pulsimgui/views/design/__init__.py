"""Design system for PulsimGUI's Qt UI.

This package is the *single source of truth* for the look-and-feel of every
screen built after the v1.x "modernization in place" pass. It exists to kill
the historical problem of styling being scattered across 139 inline
``setStyleSheet`` calls and 367 raw hex literals in ``views/`` — the same
problem a Tailwind + component-library workflow solves on the web.

Two layers:

* :mod:`pulsimgui.views.design.tokens` — the STRUCTURAL scale (spacing on an
  8 px grid, corner radii, the type scale, motion durations, elevation).
  These are theme-independent: they don't change between light and dark.
  The COLOR tokens already live in
  :class:`pulsimgui.services.theme_service.ThemeColors`; this package never
  re-defines a colour, it only consumes ``theme.colors.*``.

* :mod:`pulsimgui.views.design.components` — a small set of reusable styled
  ``QWidget`` primitives (Card, KpiTile, PageHeader, SectionHeader,
  StatusBadge, PrimaryButton, SecondaryButton, SegmentedControl). Every one
  is driven by ``ThemeColors`` + tokens, re-themes itself on
  ``ThemeService.theme_changed``, and contains the ONLY ``setStyleSheet``
  calls a screen needs — screens compose these instead of hand-styling.

The visual language (slate surfaces, 3-level foreground, ``xl`` card radii,
the title→muted-subtitle type rhythm) is lifted from the user's ``termico``
app's DESIGN_NOTES so the two apps feel like siblings.
"""

from __future__ import annotations

from pulsimgui.views.design.components import (
    Card,
    KpiTile,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    SectionHeader,
    SegmentedControl,
    StatusBadge,
)
from pulsimgui.views.design.tokens import (
    Elevation,
    FontSize,
    FontWeight,
    Motion,
    Radius,
    Space,
)

__all__ = [
    # tokens
    "Space",
    "Radius",
    "FontSize",
    "FontWeight",
    "Motion",
    "Elevation",
    # components
    "Card",
    "KpiTile",
    "PageHeader",
    "SectionHeader",
    "StatusBadge",
    "PrimaryButton",
    "SecondaryButton",
    "SegmentedControl",
]
