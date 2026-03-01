"""Floating windows that host per-component scope viewers."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.waveform import WaveformViewer

from .bindings import ScopeChannelBinding, ScopeSignal


class ScopeWindow(QWidget):
    """Standalone scope window wrapping a :class:`WaveformViewer`."""

    closed = Signal(str, tuple)

    def __init__(
        self,
        component_id: str,
        component_name: str,
        scope_type: ComponentType,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._component_id = component_id
        self._component_name = component_name
        self._scope_type = scope_type
        self._bindings: list[ScopeChannelBinding] = []

        self._viewer = WaveformViewer()
        self._viewer.setMinimumSize(520, 320)

        self._mapping_label = QLabel()
        self._mapping_label.setWordWrap(True)
        self._mapping_label.setObjectName("scopeMappingLabel")

        self._message_label = QLabel("Waiting for simulation results...")
        self._message_label.setWordWrap(True)
        self._message_label.setObjectName("scopeMessageLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._viewer, stretch=1)

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(12, 8, 12, 12)
        info_layout.setSpacing(4)
        info_layout.addWidget(self._mapping_label)
        info_layout.addWidget(self._message_label)
        layout.addWidget(info_container, stretch=0)

        self._refresh_title()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def component_id(self) -> str:
        return self._component_id

    def set_component_name(self, name: str) -> None:
        self._component_name = name
        self._refresh_title()

    def set_bindings(self, bindings: list[ScopeChannelBinding]) -> None:
        self._bindings = bindings
        if not bindings:
            self._mapping_label.setText("No channels assigned.")
            return

        lines = []
        for binding in bindings:
            if binding.signals:
                targets = ", ".join(signal.label or signal.signal_key or "(unlabeled)" for signal in binding.signals)
            else:
                targets = "(unconnected)"
            lines.append(f"{binding.display_name} -> {targets}")
        self._mapping_label.setText("\n".join(lines))

    def apply_simulation_result(self, result: SimulationResult | None) -> None:
        """Filter the supplied result down to the window's bindings."""

        if not result or not result.time:
            self._viewer.set_result(SimulationResult())
            self._message_label.setText("No simulation data available yet.")
            return

        subset = SimulationResult()
        subset.time = list(result.time)
        subset.signals = {}
        subset.statistics = dict(result.statistics)

        found_channels: list[str] = []
        missing_channels: list[str] = []

        for binding in self._bindings:
            if not binding.signals:
                missing_channels.append(binding.display_name)
                continue

            for idx, signal in enumerate(binding.signals):
                label = self._format_signal_label(binding, signal, idx)
                if not signal.signal_key:
                    missing_channels.append(label)
                    continue
                series = result.signals.get(signal.signal_key)
                if series:
                    subset.signals[label] = list(series)
                    found_channels.append(label)
                else:
                    missing_channels.append(label)

        if subset.signals:
            self._viewer.set_result(subset)
        else:
            empty = SimulationResult(time=subset.time, signals={})
            self._viewer.set_result(empty)

        self._message_label.setText(self._format_status(found_channels, missing_channels))

    def apply_geometry_state(self, geometry: list[int] | None) -> None:
        if geometry and len(geometry) == 4:
            self.setGeometry(*geometry)
        else:
            self.resize(640, 420)

    def capture_geometry_state(self) -> tuple[int, int, int, int]:
        rect = self.geometry()
        return rect.x(), rect.y(), rect.width(), rect.height()

    # ------------------------------------------------------------------
    # QWidget overrides
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: D401 - Qt override
        self.closed.emit(self._component_id, self.capture_geometry_state())
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _refresh_title(self) -> None:
        label = "Scope" if self._scope_type == ComponentType.ELECTRICAL_SCOPE else "Thermal Scope"
        self.setWindowTitle(f"{self._component_name or 'Unnamed'} - {label}")

    def _format_status(self, found: list[str], missing: list[str]) -> str:
        parts: list[str] = []
        if found:
            parts.append(f"Signals: {', '.join(found)}")
        if missing:
            parts.append(f"Missing: {', '.join(missing)}")
        if not parts:
            return "Waiting for matching signals..."
        return " ; ".join(parts)

    def _format_signal_label(self, binding: ScopeChannelBinding, signal: ScopeSignal, index: int) -> str:
        if len(binding.signals) == 1:
            return signal.label or binding.display_name
        suffix = signal.label or f"Signal {index + 1}"
        return f"{binding.display_name}/{suffix}"
