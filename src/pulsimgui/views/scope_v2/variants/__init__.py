"""Scope variants — concrete ``ScopeVariant`` implementations.

Each variant declares the metadata the shell needs (name, badge, glyph,
accent colour, default unit) and the list of capabilities it composes
with. The shell remains variant-agnostic.
"""

from .electrical_scope import ElectricalScopeVariant
from .thermal_scope import ThermalScopeVariant

__all__ = ["ElectricalScopeVariant", "ThermalScopeVariant"]
