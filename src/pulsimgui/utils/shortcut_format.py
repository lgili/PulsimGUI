"""Platform-aware shortcut rendering.

This module normalises the keyboard-shortcut strings shown in the
component palette, menu items, and tooltips so they match the active
platform's modifier-glyph conventions:

- On macOS:  ``Ctrl+M`` → ``⌃M``,  ``Shift+M`` → ``⇧M``,
  ``Cmd+M`` → ``⌘M``,  ``Alt+M`` → ``⌥M``.
- On Linux / Windows:  modifiers stay as their literal text form,
  joined with a ``+`` separator.

The function accepts either a raw string (``"Ctrl+Shift+M"``,
``"Cmd+K"``) or a ``QKeySequence`` instance, and returns the display
string the UI should render.
"""

from __future__ import annotations

import sys

try:  # pragma: no cover - tests may not have Qt available
    from PySide6.QtGui import QKeySequence
except Exception:  # pragma: no cover
    QKeySequence = None  # type: ignore[assignment]


_MAC = sys.platform == "darwin"


# Glyphs that replace literal modifier names on macOS.
_MAC_GLYPHS = {
    "ctrl": "⌃",       # ⌃
    "control": "⌃",
    "shift": "⇧",      # ⇧
    "cmd": "⌘",        # ⌘
    "command": "⌘",
    "meta": "⌘",       # Qt's "Meta" maps to ⌘ on macOS
    "alt": "⌥",        # ⌥
    "option": "⌥",
    "opt": "⌥",
}

# Modifier order on macOS matches the standard Apple HIG ordering:
# Control, Option, Shift, Command. Modifiers are emitted in this order
# regardless of input order so users see a consistent prefix.
_MAC_ORDER = [
    "⌃",  # Control
    "⌥",  # Option
    "⇧",  # Shift
    "⌘",  # Command
]


def _normalize_token(token: str) -> str:
    return token.strip().lower().replace("_", "").replace("-", "")


def shortcut_format(value: object) -> str:
    """Return the display string for a keyboard shortcut.

    Parameters
    ----------
    value : str or QKeySequence
        Either a plain string like ``"Ctrl+M"`` or a Qt ``QKeySequence``.

    Returns
    -------
    str
        The display string to render in the UI for the current platform.
        Empty input returns an empty string (callers can skip rendering
        the shortcut hint entirely).
    """
    if value in (None, ""):
        return ""

    # Accept a QKeySequence by lifting it to its native portable string
    # form, which already uses ``+`` as the separator.
    if QKeySequence is not None and isinstance(value, QKeySequence):
        try:
            text = value.toString(QKeySequence.SequenceFormat.PortableText)
        except AttributeError:
            text = value.toString()
    else:
        text = str(value)

    text = text.strip()
    if not text:
        return ""

    tokens = [tok for tok in text.split("+") if tok]
    if not tokens:
        return ""

    if not _MAC:
        # Linux / Windows: keep the canonical "Ctrl+Shift+M" form but
        # normalise the modifier capitalisation so we don't render a
        # mixture of "ctrl" and "Ctrl".
        canonicalised: list[str] = []
        for tok in tokens:
            key = _normalize_token(tok)
            if key in {"ctrl", "control"}:
                canonicalised.append("Ctrl")
            elif key == "shift":
                canonicalised.append("Shift")
            elif key in {"alt", "option", "opt"}:
                canonicalised.append("Alt")
            elif key in {"cmd", "command", "meta"}:
                canonicalised.append("Meta")
            else:
                # Non-modifier — preserve original casing.
                canonicalised.append(tok)
        return "+".join(canonicalised)

    # macOS: replace modifier names with their glyphs, then sort the
    # glyphs into HIG order, then join with the key (no separator).
    glyphs: list[str] = []
    key_tokens: list[str] = []
    for tok in tokens:
        key = _normalize_token(tok)
        glyph = _MAC_GLYPHS.get(key)
        if glyph is not None:
            if glyph not in glyphs:
                glyphs.append(glyph)
        else:
            key_tokens.append(tok)

    glyphs.sort(key=lambda g: _MAC_ORDER.index(g) if g in _MAC_ORDER else 99)
    return "".join(glyphs) + "".join(key_tokens)


__all__ = ["shortcut_format"]
