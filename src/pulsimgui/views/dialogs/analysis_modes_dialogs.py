"""Sub-wave B analysis-mode dialogs (wave-4).

Three minimal-viable dialogs:

* :class:`FraDialog` — closed-loop frequency response analysis.
* :class:`PeriodicSteadyStateDialog` — shooting-based periodic
  steady-state.
* :class:`HarmonicBalanceDialog` — harmonic balance.

All three share the same pattern: collect a settings dataclass,
call the corresponding :class:`SimulationService` method, then show
a text summary via QMessageBox. Rich result viewers (Bode overlay
for FRA, single-period waveform inset for PSS, spectrum bar chart
for HB) are queued as a sub-wave B follow-up — the dialogs ship now
so users can drive the analyses from the menu without dropping into
the Python API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.backend_types import (
    FraResult,
    FraSettings,
    HarmonicBalanceResult,
    HarmonicBalanceSettings,
    PeriodicSteadyStateResult,
    PeriodicSteadyStateSettings,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pulsimgui.models.project import Project
    from pulsimgui.services.simulation_service import SimulationService


# =============================================================================
# Base class — common Run / Cancel button row + capability gate.
# =============================================================================
class _BaseAnalysisDialog(QDialog):
    """Shared scaffolding for the three sub-wave B dialogs."""

    capability_name: str = ""
    capability_label: str = ""

    def __init__(
        self,
        simulation_service: "SimulationService",
        project: "Project",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._simulation_service = simulation_service
        self._project = project
        self._last_result: Any | None = None
        self.setMinimumWidth(440)

    def _make_buttons(self, outer: QVBoxLayout) -> QPushButton:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        run_btn = QPushButton("Run")
        run_btn.setDefault(True)
        run_btn.clicked.connect(self._on_run_clicked)
        buttons.addButton(run_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        return run_btn

    def _check_capability(self) -> bool:
        if not self._simulation_service.has_capability(self.capability_name):
            QMessageBox.warning(
                self,
                f"{self.capability_label} unavailable",
                f"The active simulation backend does not support {self.capability_label}. "
                "Upgrade Pulsim to 0.9.0 or newer.",
            )
            return False
        return True

    # Each subclass overrides _on_run_clicked.
    def _on_run_clicked(self) -> None:  # pragma: no cover - virtual
        raise NotImplementedError

    @property
    def last_result(self) -> Any | None:
        return self._last_result


# =============================================================================
# 2.1 — FRA
# =============================================================================
class FraDialog(_BaseAnalysisDialog):
    """Closed-loop Frequency Response Analysis dialog."""

    capability_name = "fra"
    capability_label = "FRA"

    def __init__(
        self,
        simulation_service: "SimulationService",
        project: "Project",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(simulation_service, project, parent=parent)
        self.setWindowTitle("Frequency Response Analysis (FRA)")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        heading = QLabel(
            "Inject a small perturbation across a frequency sweep and record the "
            "magnitude / phase response at the requested measurement nodes."
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._f_start = QDoubleSpinBox()
        self._f_start.setDecimals(6)
        self._f_start.setRange(1e-9, 1e12)
        self._f_start.setSuffix(" Hz")
        self._f_start.setValue(1.0)
        form.addRow("Start frequency:", self._f_start)

        self._f_stop = QDoubleSpinBox()
        self._f_stop.setDecimals(6)
        self._f_stop.setRange(1e-9, 1e12)
        self._f_stop.setSuffix(" Hz")
        self._f_stop.setValue(1e6)
        form.addRow("Stop frequency:", self._f_stop)

        self._points_per_decade = QSpinBox()
        self._points_per_decade.setRange(1, 1000)
        self._points_per_decade.setValue(10)
        form.addRow("Points/decade:", self._points_per_decade)

        self._scale_combo = QComboBox()
        self._scale_combo.addItem("Decade (log)", "decade")
        self._scale_combo.addItem("Linear", "linear")
        form.addRow("Sweep scale:", self._scale_combo)

        self._perturbation_amp = QDoubleSpinBox()
        self._perturbation_amp.setDecimals(6)
        self._perturbation_amp.setRange(1e-9, 1e3)
        self._perturbation_amp.setValue(0.01)
        form.addRow("Perturbation amplitude:", self._perturbation_amp)

        self._perturbation_source = QLineEdit()
        self._perturbation_source.setPlaceholderText("e.g. Vin")
        form.addRow("Perturbation source:", self._perturbation_source)

        self._measurement_nodes = QLineEdit()
        self._measurement_nodes.setPlaceholderText("Vout, Vfb  (comma-separated)")
        form.addRow("Measurement nodes:", self._measurement_nodes)

        outer.addLayout(form)
        self._make_buttons(outer)

    def _build_settings(self) -> FraSettings:
        nodes = tuple(
            n.strip()
            for n in self._measurement_nodes.text().split(",")
            if n.strip()
        )
        return FraSettings(
            f_start=float(self._f_start.value()),
            f_stop=float(self._f_stop.value()),
            points_per_decade=int(self._points_per_decade.value()),
            scale=str(self._scale_combo.currentData() or "decade"),
            perturbation_amplitude=float(self._perturbation_amp.value()),
            perturbation_source=self._perturbation_source.text().strip(),
            measurement_nodes=nodes,
        )

    def _on_run_clicked(self) -> None:
        if not self._check_capability():
            return
        settings = self._build_settings()
        try:
            result: FraResult = self._simulation_service.run_fra(self._project, settings)
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "FRA failed", str(exc))
            return
        self._last_result = result
        if not result.success:
            QMessageBox.warning(self, "FRA failed", result.failure_reason or "Unknown error")
            return
        msg = (
            f"Swept {len(result.frequencies)} frequencies in "
            f"{result.wall_seconds:.3g} s.\n"
            f"Transient steps: {result.total_transient_steps}\n\n"
            f"First sample:  {result.entries[0].frequency:.3g} Hz, "
            f"{result.entries[0].magnitude_db:.2f} dB, "
            f"{result.entries[0].phase_deg:.1f}°\n"
            if result.entries
            else "No entries returned.\n"
        )
        msg += "Rich Bode-overlay viewer is queued for a follow-up release."
        QMessageBox.information(self, "FRA complete", msg)
        self.accept()


# =============================================================================
# 2.2 — Periodic Steady-State
# =============================================================================
class PeriodicSteadyStateDialog(_BaseAnalysisDialog):
    capability_name = "periodic_steady_state"
    capability_label = "Periodic Steady-State"

    def __init__(
        self,
        simulation_service: "SimulationService",
        project: "Project",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(simulation_service, project, parent=parent)
        self.setWindowTitle("Periodic Steady-State (Shooting)")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        heading = QLabel(
            "Find the periodic orbit of a switching converter without waiting for "
            "transient soak. Provide the fundamental period (e.g. 1 / fsw)."
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._period = QDoubleSpinBox()
        self._period.setDecimals(9)
        self._period.setRange(1e-12, 1.0)
        self._period.setSuffix(" s")
        self._period.setValue(1e-5)
        form.addRow("Period:", self._period)

        self._max_iter = QSpinBox()
        self._max_iter.setRange(1, 5000)
        self._max_iter.setValue(50)
        form.addRow("Max iterations:", self._max_iter)

        self._tolerance = QDoubleSpinBox()
        self._tolerance.setDecimals(12)
        self._tolerance.setRange(1e-15, 1.0)
        self._tolerance.setValue(1e-6)
        form.addRow("Newton tolerance:", self._tolerance)

        self._relaxation = QDoubleSpinBox()
        self._relaxation.setDecimals(3)
        self._relaxation.setRange(0.0, 2.0)
        self._relaxation.setSingleStep(0.05)
        self._relaxation.setValue(1.0)
        form.addRow("Relaxation:", self._relaxation)

        self._store_transient = QCheckBox("Store last transient cycle")
        self._store_transient.setChecked(True)
        form.addRow(self._store_transient)

        outer.addLayout(form)
        self._make_buttons(outer)

    def _build_settings(self) -> PeriodicSteadyStateSettings:
        return PeriodicSteadyStateSettings(
            period=float(self._period.value()),
            max_iterations=int(self._max_iter.value()),
            tolerance=float(self._tolerance.value()),
            relaxation=float(self._relaxation.value()),
            store_last_transient=bool(self._store_transient.isChecked()),
        )

    def _on_run_clicked(self) -> None:
        if not self._check_capability():
            return
        settings = self._build_settings()
        try:
            result: PeriodicSteadyStateResult = (
                self._simulation_service.run_periodic_steady_state(self._project, settings)
            )
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Periodic steady-state failed", str(exc))
            return
        self._last_result = result
        if not result.success:
            QMessageBox.warning(
                self,
                "Periodic steady-state did not converge",
                result.message
                or "Increase max iterations, relax the tolerance, or check the period.",
            )
            return
        msg = (
            f"Converged in {result.iterations} iterations.\n"
            f"Final residual: {result.residual_norm:.3e}\n"
            f"Diagnostic: {result.diagnostic or '—'}"
        )
        QMessageBox.information(self, "Periodic steady-state complete", msg)
        self.accept()


# =============================================================================
# 2.3 — Harmonic Balance
# =============================================================================
class HarmonicBalanceDialog(_BaseAnalysisDialog):
    capability_name = "harmonic_balance"
    capability_label = "Harmonic Balance"

    def __init__(
        self,
        simulation_service: "SimulationService",
        project: "Project",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(simulation_service, project, parent=parent)
        self.setWindowTitle("Harmonic Balance")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        heading = QLabel(
            "Solve directly in the frequency domain via harmonic balance. Best for "
            "circuits driven by a single periodic source."
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._period = QDoubleSpinBox()
        self._period.setDecimals(9)
        self._period.setRange(1e-12, 1.0)
        self._period.setSuffix(" s")
        self._period.setValue(1e-5)
        form.addRow("Period:", self._period)

        self._num_samples = QSpinBox()
        self._num_samples.setRange(4, 4096)
        self._num_samples.setValue(64)
        form.addRow("Samples / period:", self._num_samples)

        self._max_iter = QSpinBox()
        self._max_iter.setRange(1, 5000)
        self._max_iter.setValue(50)
        form.addRow("Max iterations:", self._max_iter)

        self._tolerance = QDoubleSpinBox()
        self._tolerance.setDecimals(12)
        self._tolerance.setRange(1e-15, 1.0)
        self._tolerance.setValue(1e-6)
        form.addRow("Balancing tolerance:", self._tolerance)

        self._relaxation = QDoubleSpinBox()
        self._relaxation.setDecimals(3)
        self._relaxation.setRange(0.0, 2.0)
        self._relaxation.setSingleStep(0.05)
        self._relaxation.setValue(1.0)
        form.addRow("Relaxation:", self._relaxation)

        self._init_from_transient = QCheckBox("Initialise from transient warm-up")
        self._init_from_transient.setChecked(True)
        form.addRow(self._init_from_transient)

        outer.addLayout(form)
        self._make_buttons(outer)

    def _build_settings(self) -> HarmonicBalanceSettings:
        return HarmonicBalanceSettings(
            period=float(self._period.value()),
            num_samples=int(self._num_samples.value()),
            max_iterations=int(self._max_iter.value()),
            tolerance=float(self._tolerance.value()),
            relaxation=float(self._relaxation.value()),
            initialize_from_transient=bool(self._init_from_transient.isChecked()),
        )

    def _on_run_clicked(self) -> None:
        if not self._check_capability():
            return
        settings = self._build_settings()
        try:
            result: HarmonicBalanceResult = self._simulation_service.run_harmonic_balance(
                self._project, settings
            )
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Harmonic balance failed", str(exc))
            return
        self._last_result = result
        if not result.success:
            QMessageBox.warning(
                self,
                "Harmonic balance did not converge",
                result.message or "Increase iterations or check the period guess.",
            )
            return
        msg = (
            f"Converged in {result.iterations} iterations.\n"
            f"Final residual: {result.residual_norm:.3e}\n"
            f"Samples in solution: {result.sample_count}\n"
            f"Diagnostic: {result.diagnostic or '—'}"
        )
        QMessageBox.information(self, "Harmonic balance complete", msg)
        self.accept()
