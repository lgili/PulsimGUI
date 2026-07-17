"""Styling ratchet — the guardrail that keeps the modernization from rotting.

The historical problem: styling scattered as raw hex across ``views/`` (367
literals at the start of the design-system pass). The fix is the
:mod:`pulsimgui.views.design` component layer. To stop the codebase drifting
back, this test enforces two rules:

1. **The design package is the clean reference** — ``views/design/`` must
   contain ZERO raw hex colour literals. Every colour there comes from a
   ``ThemeColors`` token. If this fails, someone hardcoded a colour in the
   one place that must stay pure.

2. **The rest of ``views/`` may only get cleaner** — the total count of raw
   hex literals across ``views/`` (excluding ``design/``) must not exceed a
   frozen ceiling. New inline colours are rejected; migrating a screen to the
   component layer lowers the count, and you then LOWER ``HEX_CEILING`` to
   lock in the win. The ceiling only ever ratchets DOWN.

This is the QSS-linter equivalent of a "no new ``# type: ignore``" rule: it
grandfathers existing debt and bans new debt, so the design system wins by
attrition instead of a risky big-bang restyle.
"""
from __future__ import annotations

import re
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "pulsimgui" / "views"
DESIGN = VIEWS / "design"

# Matches valid CSS hex colours: #rgb, #rgba, #rrggbb, #rrggbbaa
# (longest-first so the engine doesn't stop at a 3-char prefix of a 6).
_HEX = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b"
)

# Ratchet ceiling — the count of raw hex literals in views/ (excluding
# design/). It must only EVER decrease: every time a screen migrates to the
# design components, re-run
#   grep -rEn '#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}\b' src/pulsimgui/views --include='*.py' | grep -v /design/ | wc -l
# and set this to the new (lower) number to lock the improvement in.
# History: 383 (start) → 365 (thermal_viewer.py migrated to KpiTile + theme
# tokens, -18) → 285 (chrome sweep fase 1: scope_v2/shell.py -30,
# widgets/status_widgets.py -35, properties/properties_panel.py -15).
HEX_CEILING = 285


def _count_hex(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    return len(_HEX.findall(text))


def _iter_view_files(exclude_design: bool) -> list[Path]:
    files = []
    for p in VIEWS.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if exclude_design and DESIGN in p.parents:
            continue
        files.append(p)
    return files


# branding.py is the one sanctioned home for raw hex in the package: it
# holds FIXED brand-identity colours (logo green, mark white) that do not
# follow the UI theme — like a bundled app-icon. Everything else must use
# ThemeColors tokens.
_DESIGN_HEX_EXEMPT = {"branding.py"}


def test_design_package_has_zero_raw_hex() -> None:
    """The component layer is the clean reference — no hardcoded colours,
    except the one documented brand-identity file."""
    offenders = {
        str(p.relative_to(VIEWS.parent.parent.parent)): _count_hex(p)
        for p in DESIGN.rglob("*.py")
        if "__pycache__" not in p.parts
        and p.name not in _DESIGN_HEX_EXEMPT
        and _count_hex(p) > 0
    }
    assert not offenders, (
        "views/design/ must use ThemeColors tokens, never raw hex "
        "(the only exception is the documented branding.py). "
        f"Hardcoded colours found: {offenders}"
    )


def test_views_raw_hex_does_not_exceed_ceiling() -> None:
    """Inline hex in views/ may only ratchet down, never up."""
    total = sum(_count_hex(p) for p in _iter_view_files(exclude_design=True))
    assert total <= HEX_CEILING, (
        f"Raw hex literals in views/ rose to {total} (ceiling {HEX_CEILING}). "
        "New inline colours are banned — compose pulsimgui.views.design "
        "components, or route the colour through a ThemeColors token."
    )


def test_ceiling_is_tight_so_migrations_get_recorded() -> None:
    """Keep the ceiling honest: if the real count dropped well below the
    ceiling (a screen migrated but HEX_CEILING wasn't lowered), nudge the
    dev to ratchet it down so backsliding is caught. A 30-literal slack is
    allowed so this doesn't fail on every single migration mid-PR."""
    total = sum(_count_hex(p) for p in _iter_view_files(exclude_design=True))
    assert HEX_CEILING - total <= 30, (
        f"views/ now has only {total} raw-hex literals but HEX_CEILING is "
        f"{HEX_CEILING}. Lower HEX_CEILING to {total} to lock in the cleanup."
    )
