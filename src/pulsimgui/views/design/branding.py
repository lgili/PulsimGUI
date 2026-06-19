"""Fixed brand-identity colours — the ONE place in ``views/design`` that may
hold raw hex.

These are *app-identity* colours, not theme tokens: the Pulsim logo green
and the mark white read the same in light and dark, exactly like a bundled
app-icon PNG would. Putting them through ``ThemeColors`` would be wrong —
the brand doesn't recolour with the UI theme. The styling ratchet
(``tests/test_design/test_styling_ratchet.py``) exempts this file for that
reason; every OTHER file in the package must use theme tokens.

The green gradient matches the handoff's menu-bar logo chip
(``#3fb950 → #1f7a33``).
"""

from __future__ import annotations


class Brand:
    """Immutable brand-identity colours (hex)."""

    GREEN_TOP = "#3fb950"     # logo chip gradient — top
    GREEN_BOTTOM = "#1f7a33"  # logo chip gradient — bottom
    MARK = "#ffffff"          # the white pulse glyph on the chip
