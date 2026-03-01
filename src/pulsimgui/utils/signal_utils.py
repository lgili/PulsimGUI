"""Helpers for formatting and sanitizing signal identifiers."""

from __future__ import annotations

import re

__all__ = ["sanitize_signal_label", "format_signal_key"]

_SIGNAL_PATTERN = re.compile(r"[^0-9A-Za-z_\-.:/]+")


def sanitize_signal_label(label: str | None) -> str:
    """Return a filesystem-safe label for use in signal identifiers."""
    if not label:
        return "signal"
    cleaned = _SIGNAL_PATTERN.sub("_", label.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "signal"


def format_signal_key(prefix: str, label: str | None) -> str:
    """Format a canonical signal key like ``V(out)`` or ``T(node)``."""
    sanitized = sanitize_signal_label(label)
    return f"{prefix}({sanitized})"
