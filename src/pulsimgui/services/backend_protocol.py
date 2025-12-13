"""Backend capabilities protocol defining the interface all backends must implement."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo
    from pulsimgui.services.backend_types import (
        ACResult,
        ACSettings,
        DCResult,
        DCSettings,
        ThermalResult,
        ThermalSettings,
        TransientResult,
        TransientSettings,
    )


@runtime_checkable
class BackendCapabilities(Protocol):
    """Protocol defining the full backend interface.

    All simulation backends must implement this protocol to be usable by PulsimGui.
    The protocol supports feature detection via `has_capability()` to enable
    graceful degradation when certain features are unavailable.

    Capabilities:
        - "transient": Time-domain simulation
        - "dc": DC operating point analysis
        - "ac": Frequency-domain (AC) analysis
        - "thermal": Thermal simulation with loss calculation
    """

    @property
    def info(self) -> "BackendInfo":
        """Return metadata about this backend."""
        ...

    @property
    def capabilities(self) -> set[str]:
        """Return set of supported capability names.

        Standard capability names:
            - "transient": Time-domain simulation
            - "dc": DC operating point analysis
            - "ac": Frequency-domain analysis
            - "thermal": Thermal simulation
        """
        ...

    def has_capability(self, name: str) -> bool:
        """Check if a specific capability is supported.

        Args:
            name: The capability name to check (e.g., "dc", "ac", "thermal")

        Returns:
            True if the capability is supported, False otherwise.
        """
        ...

    def run_transient(
        self,
        circuit_data: dict,
        settings: "TransientSettings",
        callbacks: "BackendCallbacks",
    ) -> "TransientResult":
        """Run time-domain transient simulation.

        Args:
            circuit_data: Dictionary representation of the circuit.
            settings: Transient simulation settings.
            callbacks: Callbacks for progress reporting and control.

        Returns:
            TransientResult with time-domain waveforms.
        """
        ...

    def run_dc(
        self,
        circuit_data: dict,
        settings: "DCSettings",
    ) -> "DCResult":
        """Run DC operating point analysis.

        Args:
            circuit_data: Dictionary representation of the circuit.
            settings: DC analysis settings including strategy and tolerances.

        Returns:
            DCResult with node voltages and branch currents.

        Raises:
            NotImplementedError: If DC analysis is not supported.
        """
        ...

    def run_ac(
        self,
        circuit_data: dict,
        settings: "ACSettings",
    ) -> "ACResult":
        """Run AC frequency-domain analysis.

        Args:
            circuit_data: Dictionary representation of the circuit.
            settings: AC analysis settings including frequency range.

        Returns:
            ACResult with magnitude and phase data.

        Raises:
            NotImplementedError: If AC analysis is not supported.
        """
        ...

    def run_thermal(
        self,
        circuit_data: dict,
        electrical_result: "TransientResult",
        settings: "ThermalSettings",
    ) -> "ThermalResult":
        """Run thermal simulation based on electrical results.

        Args:
            circuit_data: Dictionary representation of the circuit.
            electrical_result: Results from a prior transient simulation.
            settings: Thermal simulation settings.

        Returns:
            ThermalResult with temperature traces and loss breakdown.

        Raises:
            NotImplementedError: If thermal simulation is not supported.
        """
        ...

    def request_pause(self, run_id: int | None = None) -> None:
        """Request to pause a running simulation.

        Args:
            run_id: Optional identifier for the specific simulation run.
        """
        ...

    def request_resume(self, run_id: int | None = None) -> None:
        """Request to resume a paused simulation.

        Args:
            run_id: Optional identifier for the specific simulation run.
        """
        ...

    def request_stop(self, run_id: int | None = None) -> None:
        """Request to stop a running simulation.

        Args:
            run_id: Optional identifier for the specific simulation run.
        """
        ...


__all__ = ["BackendCapabilities"]
