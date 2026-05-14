"""File ▸ Export ▸ C99 controller… dialog (wave-4 sub-A 1.2).

Collects the inputs needed by :py:meth:`SimulationService.export_c99`
(output directory, fixed-step dt, optional operating-point time) and
shows the codegen summary on success.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.backend_types import C99CodegenResult, C99CodegenSettings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pulsimgui.models.project import Project
    from pulsimgui.services.simulation_service import SimulationService


_DEFAULT_DT = 1e-4
# Only ``c99`` ships today; ARM Cortex-M7 / Zynq targets are deferred per
# pulsim.codegen.generate's docstring. The combobox keeps the option open
# so future runtime versions just need to extend this list.
_TARGETS: tuple[str, ...] = ("c99",)


class C99ExportDialog(QDialog):
    """Modal dialog that drives C99 real-time controller export."""

    def __init__(
        self,
        simulation_service: "SimulationService",
        project: "Project",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export C99 controller…")
        self.setMinimumWidth(540)
        self._simulation_service = simulation_service
        self._project = project
        self._last_result: C99CodegenResult | None = None

        self._build_ui()
        self._refresh_can_export()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        heading = QLabel(
            "Generate deployable C99 controller code from the active circuit. "
            "The runtime emits a discrete-time state-space model plus driver "
            "stubs you can drop into your firmware build."
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        out_row = QHBoxLayout()
        self._out_dir_edit = QLineEdit()
        self._out_dir_edit.setPlaceholderText("/absolute/path/to/output_directory")
        self._out_dir_edit.textChanged.connect(self._refresh_can_export)
        out_row.addWidget(self._out_dir_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        out_row.addWidget(browse_btn)
        form.addRow("Output directory:", out_row)

        self._dt_spin = QDoubleSpinBox()
        self._dt_spin.setDecimals(9)
        self._dt_spin.setRange(1e-9, 1.0)
        self._dt_spin.setSingleStep(1e-5)
        self._dt_spin.setSuffix(" s")
        self._dt_spin.setValue(_DEFAULT_DT)
        form.addRow("Discretization step:", self._dt_spin)

        self._t_op_spin = QDoubleSpinBox()
        self._t_op_spin.setDecimals(6)
        self._t_op_spin.setRange(0.0, 1e9)
        self._t_op_spin.setSingleStep(1e-3)
        self._t_op_spin.setSuffix(" s")
        self._t_op_spin.setValue(0.0)
        self._t_op_spin.setToolTip(
            "Time at which to linearize the operating point. "
            "Leave at 0 to use the auto-computed DC operating point."
        )
        form.addRow("Operating-point time:", self._t_op_spin)

        self._target_combo = QComboBox()
        for target in _TARGETS:
            self._target_combo.addItem(target)
        form.addRow("Target:", self._target_combo)

        outer.addLayout(form)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self._export_btn = QPushButton("Generate code")
        self._export_btn.setDefault(True)
        self._export_btn.clicked.connect(self._on_export_clicked)
        self._buttons.addButton(
            self._export_btn, QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose output directory",
            self._out_dir_edit.text().strip() or str(Path.home()),
        )
        if chosen:
            self._out_dir_edit.setText(chosen)

    def _refresh_can_export(self) -> None:
        ok = bool(self._out_dir_edit.text().strip())
        self._export_btn.setEnabled(ok)

    def _build_settings(self) -> C99CodegenSettings:
        return C99CodegenSettings(
            out_dir=str(Path(self._out_dir_edit.text().strip()).expanduser()),
            dt=float(self._dt_spin.value()),
            target=self._target_combo.currentText() or "c99",
            t_op=float(self._t_op_spin.value()),
        )

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------
    def _on_export_clicked(self) -> None:
        if not self._simulation_service.has_capability("c99_codegen"):
            QMessageBox.critical(
                self,
                "C99 codegen unavailable",
                "The active simulation backend does not support C99 codegen. "
                "Upgrade Pulsim to 0.8.0 or newer.",
            )
            return

        settings = self._build_settings()
        self._export_btn.setEnabled(False)
        try:
            result = self._simulation_service.export_c99(self._project, settings)
        except NotImplementedError as exc:
            QMessageBox.critical(self, "C99 codegen unavailable", str(exc))
            self._export_btn.setEnabled(True)
            return
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "C99 codegen failed", str(exc))
            self._export_btn.setEnabled(True)
            return

        self._last_result = result
        rom_kb = result.rom_estimate_bytes / 1024.0
        ram_kb = result.ram_estimate_bytes / 1024.0
        files_summary = (
            ", ".join(result.files_written[:3])
            + (" + …" if len(result.files_written) > 3 else "")
        )
        msg = (
            f"Code written to:\n{result.out_dir}\n\n"
            f"Target: {result.target}\n"
            f"States: {result.state_size}    Inputs: {result.input_size}    "
            f"Outputs: {result.output_size}\n"
            f"Stability radius: {result.stability_radius:.4g}\n"
            f"ROM estimate: {rom_kb:.1f} KB    "
            f"RAM estimate: {ram_kb:.1f} KB\n"
            f"Files: {files_summary or '—'}"
        )
        QMessageBox.information(self, "C99 codegen complete", msg)
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> C99CodegenResult | None:
        """Show the dialog modally and return the codegen summary, if any."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._last_result
        return None

    @property
    def last_result(self) -> C99CodegenResult | None:
        return self._last_result
