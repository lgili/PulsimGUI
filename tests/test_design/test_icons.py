"""Icon-set audit — keeps the bundled SVG family coherent and complete.

Redesign slice 2 made the bundled SVG dict the primary icon source
(one Lucide-convention family instead of two mixed icon fonts). These
tests are the ratchet that keeps it that way:

1. Every glyph body renders as VALID SVG through QSvgRenderer — an
   authoring typo can't ship a blank icon.
2. Every icon name referenced from ``views/`` (string literals in
   ``get_icon`` / ``get_themed_icon`` / ``icon()`` calls, and the
   scope shell's ``_ICON_MAP`` values) resolves in the bundled set —
   no silent fallback to ``help-circle`` or a mismatched font glyph.
3. The legacy qtawesome alias map may only SHRINK: aliases exist for
   migration, and every name it covers must already have a bundled
   glyph so the app renders identically without qtawesome installed.
4. Recoloring reaches every visible element — no glyph hardcodes a
   stroke color the theme can't override.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pulsimgui.resources.icons import ICON_MAP, IconService
from pulsimgui.resources.icons.icons import ICONS, svg_for

VIEWS_DIR = Path(__file__).resolve().parents[2] / "src" / "pulsimgui" / "views"

# Direct string-literal icon references: get_icon("name"...),
# get_themed_icon("name"...), icon("name"...).
_CALL_RE = re.compile(
    r"(?:get_icon|get_themed_icon|\bicon)\(\s*\"([a-z0-9-]+)\""
)
# The scope shell's local alias map: values are IconService names.
_SHELL_MAP_RE = re.compile(r"\"[a-z0-9-]+\":\s*\"([a-z0-9-]+)\"")


def _referenced_names() -> set[str]:
    names: set[str] = set()
    for py in VIEWS_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        names.update(_CALL_RE.findall(text))
        if py.name == "shell.py" and "_ICON_MAP" in text:
            start = text.index("_ICON_MAP")
            block = text[start : text.index("}", start)]
            names.update(_SHELL_MAP_RE.findall(block))
    return names


def test_every_glyph_renders_valid_svg(qapp):
    from PySide6.QtSvg import QSvgRenderer

    bad: list[str] = []
    for name in ICONS:
        svg = svg_for(name, color="#dfe3e9")
        assert svg is not None
        if not QSvgRenderer(svg.encode("utf-8")).isValid():
            bad.append(name)
    assert not bad, f"glyph bodies fail to parse: {bad}"


def test_every_referenced_name_is_in_the_bundled_set():
    referenced = _referenced_names()
    assert referenced, "harvest found nothing — regex drifted from call sites"
    missing = sorted(n for n in referenced if n not in ICONS)
    assert not missing, (
        f"icon names referenced in views/ but absent from the bundled "
        f"SVG set (would fall back silently): {missing}"
    )


def test_legacy_alias_map_fully_covered_by_bundled_set():
    uncovered = sorted(n for n in ICON_MAP if n not in ICONS)
    assert not uncovered, (
        f"legacy qtawesome aliases without a bundled glyph — the app "
        f"would render these differently without qtawesome: {uncovered}"
    )


def test_no_hardcoded_stroke_colors_in_bodies():
    offenders = []
    for name, body in ICONS.items():
        # stroke="none" is the only allowed literal (filled shapes);
        # everything else must inherit the template stroke or use
        # fill="currentColor" (recolored at render time). The
        # measurements-filled tick marks use a translucent black that
        # reads on any fill — the one deliberate exception.
        for m in re.finditer(r'stroke="([^"]+)"', body):
            value = m.group(1)
            if value == "none":
                continue
            if name == "measurements-filled":
                continue
            offenders.append((name, value))
    assert not offenders, f"hardcoded stroke colors defeat theming: {offenders}"


def test_icon_service_returns_populated_icons(qapp):
    for name in ("play", "wire", "probe-voltage", "fft-chart", "auto-layout"):
        qicon = IconService.get_icon(name, color="#4d9fff")
        assert not qicon.isNull(), f"{name}: null QIcon"
        assert qicon.availableSizes(), f"{name}: no rendered sizes"


def test_unknown_name_falls_back_to_help_circle(qapp):
    qicon = IconService.get_icon("definitely-not-an-icon", color="#9aa0a8")
    assert not qicon.isNull()


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
