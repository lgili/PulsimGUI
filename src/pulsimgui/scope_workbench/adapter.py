"""Host adapter contract for standalone scope workbench integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class ScopeSignalDescriptor:
    """Metadata for one available signal in the host signal catalog."""

    signal_key: str
    label: str
    unit: str = ""
    domain: str = ""


@dataclass(slots=True)
class ScopeSampleBatch:
    """Batch of scope samples pushed by host applications."""

    time: list[float]
    signals: dict[str, list[float]]


class ScopeHostAdapter(Protocol):
    """Contract that host apps implement to feed standalone scope workbench."""

    def list_signals(self, workspace_id: str) -> list[ScopeSignalDescriptor]:
        """Return signal catalog for the workspace."""

    def get_scope_samples(
        self,
        workspace_id: str,
        scope_id: str,
        signal_keys: list[str],
    ) -> ScopeSampleBatch:
        """Return current timeseries samples for a scope request."""

    def save_workspace_state(self, workspace_id: str, state: dict[str, object]) -> None:
        """Persist serialized workspace state in the host application."""

    def load_workspace_state(self, workspace_id: str) -> dict[str, object] | None:
        """Load previously persisted workspace state if available."""
