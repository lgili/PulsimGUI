"""Thermal-scope variant — temperatures in °C, orange-tinted chrome."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThermalScopeVariant:
    """Metadata + default capabilities for a thermal scope window."""

    name: str = "Thermal Scope"
    type_label: str = "thermal"
    type_glyph: str = "🌡"
    accent_color: str = "#f59e0b"  # orange — thermal domain colour
    default_unit: str = "°C"
