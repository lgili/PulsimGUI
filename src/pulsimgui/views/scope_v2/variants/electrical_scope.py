"""Electrical-scope variant — voltages / currents in volts / amperes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ElectricalScopeVariant:
    """Metadata + default capabilities for an electrical scope window."""

    name: str = "Scope"
    type_label: str = "electrical"
    type_glyph: str = "⚡"
    accent_color: str = "#5b8def"  # blue — same family as primary
    default_unit: str = "V"
