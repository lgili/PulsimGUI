"""Bundled-font registration + the app's canonical type stacks.

This module is the SINGLE source of truth for typography families in
PulsimGUI. Before it existed, font selection was scattered and
self-contradictory:

* ``__main__.py`` registered the bundled DejaVu Sans and set it as the
  application font — but the global QSS in ``theme_service`` then forced
  ``"SF Pro Text", "Segoe UI", "Noto Sans"`` onto every ``QWidget``,
  overriding it. Which family actually rendered depended on the
  platform, so screenshots from macOS / Windows / Linux never matched.
* Monospace call sites hand-rolled their own stacks — and five of them
  called ``QFont.setFamily("Menlo, Consolas, monospace")``, which is a
  bug: ``setFamily`` takes ONE family name, not a CSS list, so Qt
  searched for a family literally named "Menlo, Consolas, monospace",
  found nothing, and silently fell back to whatever the platform picked.

The fix is the classic engineering-tool pairing bundled with the app so
every platform renders identically:

* **IBM Plex Sans** — UI text (menus, labels, buttons, panels).
* **IBM Plex Mono** — numeric readouts (coordinates, cursor values,
  measurements, net names, the status bar) where column alignment and
  the instrument look matter.

Both are OFL-licensed (see ``resources/fonts/LICENSE_IBM_PLEX``) and we
ship Regular / Medium / SemiBold weights of each. DejaVu Sans stays
bundled as the glyph-coverage fallback (Ω, µ, θ, λ and friends are
covered by Plex, but DejaVu has the widest net).

Usage:

* App startup (``__main__``): :func:`register_bundled_fonts` once,
  then :func:`preferred_ui_font` for ``QApplication.setFont``.
* QSS builders (``theme_service`` and any view that writes an inline
  stylesheet): interpolate :data:`UI_STACK` / :data:`MONO_STACK`.
* Widget code that needs a ``QFont``: :func:`ui_font` /
  :func:`mono_font`, or ``font.setFamilies(MONO_FAMILIES)`` when
  tweaking an existing font. Never call ``setFamily`` with a
  comma-separated string.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

# ---------------------------------------------------------------------------
# Families and stacks
# ---------------------------------------------------------------------------

#: Primary UI family (bundled).
UI_FAMILY = "IBM Plex Sans"

#: Primary monospace family (bundled).
MONO_FAMILY = "IBM Plex Mono"

#: Ordered fallback chains for ``QFont.setFamilies`` — first present wins.
UI_FAMILIES: list[str] = [
    UI_FAMILY,
    "DejaVu Sans",
    "Noto Sans",
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
]
MONO_FAMILIES: list[str] = [
    MONO_FAMILY,
    "Menlo",
    "Consolas",
    "DejaVu Sans Mono",
    "Courier New",
]

#: QSS ``font-family`` value for UI text. Interpolate into stylesheets.
UI_STACK = '"IBM Plex Sans", "DejaVu Sans", "Noto Sans", "Segoe UI", sans-serif'

#: QSS ``font-family`` value for numeric / code text.
MONO_STACK = '"IBM Plex Mono", "Menlo", "Consolas", "DejaVu Sans Mono", monospace'


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_registered: bool = False
_loaded_families: set[str] = set()


def _fonts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "fonts"


def register_bundled_fonts() -> set[str]:
    """Register every bundled ``.ttf`` with Qt's font database.

    Idempotent — safe to call from multiple entry points (app startup,
    tests, the splash painter). Returns the set of family names that
    were successfully loaded. A missing or corrupt file is skipped
    silently: the fallback chains above keep the UI usable, matching
    the previous DejaVu-only behaviour.
    """
    global _registered
    if _registered:
        return set(_loaded_families)

    fonts = _fonts_dir()
    if fonts.is_dir():
        for ttf in sorted(fonts.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(ttf))
            if font_id < 0:
                continue
            for family in QFontDatabase.applicationFontFamilies(font_id):
                _loaded_families.add(family)

    _registered = True
    return set(_loaded_families)


def loaded_families() -> set[str]:
    """Families successfully registered so far (empty before startup)."""
    return set(_loaded_families)


# ---------------------------------------------------------------------------
# Font factories
# ---------------------------------------------------------------------------

def _make(families: list[str], pixel_size: int | None,
          weight: QFont.Weight) -> QFont:
    font = QFont()
    font.setFamilies(families)
    if pixel_size is not None and pixel_size > 0:
        font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def ui_font(pixel_size: int | None = None,
            weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """A ``QFont`` on the UI stack. ``pixel_size`` maps 1:1 onto the
    ``FontSize`` tokens (px); ``None`` keeps the inherited size."""
    return _make(UI_FAMILIES, pixel_size, weight)


def mono_font(pixel_size: int | None = None,
              weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """A ``QFont`` on the monospace stack — numeric readouts, coords,
    cursor values, net names."""
    return _make(MONO_FAMILIES, pixel_size, weight)


def preferred_ui_font(base_font: QFont) -> QFont:
    """The application-wide default font, derived from ``base_font``.

    Keeps the platform's size metrics (unless unset, where it pins a
    sane default) and swaps the family chain to the bundled UI stack.
    Called once from ``__main__`` for ``QApplication.setFont``.
    """
    register_bundled_fonts()
    font = QFont(base_font)
    font.setFamilies(UI_FAMILIES)
    if font.pointSizeF() <= 0:
        font.setPointSize(10)
    return font
