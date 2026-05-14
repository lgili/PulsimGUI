"""File ▸ Export ▸ FMU 2.0... dialog.

Collects the inputs needed by :py:meth:`SimulationService.export_fmu`
(model name, output path, integration step, optional output node list)
and shows the export summary on success.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.backend_types import FmuExportResult, FmuExportSettings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pulsimgui.models.project import Project
    from pulsimgui.services.simulation_service import SimulationService


_DEFAULT_DT = 1e-4


class FmuExportDialog(QDialog):
    """Modal dialog that drives FMU 2.0 co-simulation export.

    Use :meth:`run` (preferred over ``exec()``) to launch and have the
    last successful :class:`FmuExportResult` returned. The dialog
    performs no work on the main thread other than calling the synchronous
    backend export — heavy projects may briefly block the UI; future
    revisions can move it onto a worker.
    """

    def __init__(
        self,
        simulation_service: "SimulationService",
        project: "Project",
        *,
        available_node_names: Iterable[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export FMU 2.0…")
        self.setMinimumWidth(520)
        self._simulation_service = simulation_service
        self._project = project
        self._available_nodes = sorted(set(available_node_names or ()))
        self._last_result: FmuExportResult | None = None

        self._build_ui()
        self._refresh_can_export()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        heading = QLabel(
            "Export the current circuit as a FMI 2.0 co-simulation .fmu archive. "
            "The bundle can be consumed by MATLAB/Simulink, OpenModelica, and any "
            "FMU-aware HIL runner."
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        default_name = self._derive_default_model_name()
        self._name_edit = QLineEdit(default_name)
        self._name_edit.setPlaceholderText("e.g. buck_converter")
        self._name_edit.textChanged.connect(self._refresh_can_export)
        form.addRow("Model name:", self._name_edit)

        self._dt_spin = QDoubleSpinBox()
        self._dt_spin.setDecimals(9)
        self._dt_spin.setRange(1e-9, 1.0)
        self._dt_spin.setSingleStep(1e-5)
        self._dt_spin.setSuffix(" s")
        self._dt_spin.setValue(_DEFAULT_DT)
        form.addRow("Integration step:", self._dt_spin)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("/absolute/path/to/output.fmu")
        self._path_edit.textChanged.connect(self._refresh_can_export)
        path_row.addWidget(self._path_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)
        form.addRow("Output file:", path_row)

        outer.addLayout(form)

        # Optional output-node selector
        self._expose_nodes_check = QCheckBox("Expose circuit nodes as FMU outputs")
        self._expose_nodes_check.toggled.connect(self._on_expose_toggled)
        outer.addWidget(self._expose_nodes_check)

        self._outputs_list = QListWidget()
        self._outputs_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        for node in self._available_nodes:
            item = QListWidgetItem(node)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._outputs_list.addItem(item)
        self._outputs_list.setVisible(False)
        self._outputs_list.setMaximumHeight(160)
        outer.addWidget(self._outputs_list)

        # Dialog buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self._export_btn = QPushButton("Export FMU")
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
    def _derive_default_model_name(self) -> str:
        """Best-effort default for the model-name field."""
        for attr in ("name", "circuit_name", "title"):
            value = getattr(self._project, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip().replace(" ", "_")
        circuit = getattr(self._project, "get_active_circuit", None)
        if callable(circuit):
            try:
                obj = circuit()
                if obj is not None:
                    name = getattr(obj, "name", None)
                    if isinstance(name, str) and name.strip():
                        return name.strip().replace(" ", "_")
            except Exception:
                pass
        return "pulsim_model"

    def _on_browse(self) -> None:
        suggested = self._path_edit.text().strip() or f"{self._name_edit.text()}.fmu"
        chosen, _filter = QFileDialog.getSaveFileName(
            self,
            "Save FMU archive",
            suggested,
            "FMU archives (*.fmu);;All files (*)",
        )
        if chosen:
            if not chosen.lower().endswith(".fmu"):
                chosen = f"{chosen}.fmu"
            self._path_edit.setText(chosen)

    def _on_expose_toggled(self, checked: bool) -> None:
        self._outputs_list.setVisible(checked and bool(self._available_nodes))
        if checked and not self._available_nodes:
            QMessageBox.information(
                self,
                "No nodes available",
                "The active project does not currently expose any named nodes. "
                "Run a simulation first to populate the node list, or skip this "
                "option to export the FMU with default outputs.",
            )
            self._expose_nodes_check.setChecked(False)

    def _refresh_can_export(self) -> None:
        ok = bool(self._name_edit.text().strip()) and bool(self._path_edit.text().strip())
        self._export_btn.setEnabled(ok)

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------
    def _selected_outputs(self) -> tuple[str, ...]:
        if not self._expose_nodes_check.isChecked():
            return ()
        result: list[str] = []
        for row in range(self._outputs_list.count()):
            item = self._outputs_list.item(row)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return tuple(result)

    def _build_settings(self) -> FmuExportSettings:
        out_path = self._path_edit.text().strip()
        if not out_path.lower().endswith(".fmu"):
            out_path = f"{out_path}.fmu"
        return FmuExportSettings(
            out_path=str(Path(out_path).expanduser()),
            dt=float(self._dt_spin.value()),
            model_name=self._name_edit.text().strip(),
            outputs=self._selected_outputs(),
        )

    def _on_export_clicked(self) -> None:
        settings = self._build_settings()

        if not self._simulation_service.has_capability("fmu_export"):
            QMessageBox.critical(
                self,
                "FMU export unavailable",
                "The active simulation backend does not support FMU export. "
                "Upgrade Pulsim to 0.8.0 or newer, or install the official "
                "runtime via ``pip install pulsim``.",
            )
            return

        self._export_btn.setEnabled(False)
        try:
            result = self._simulation_service.export_fmu(self._project, settings)
        except NotImplementedError as exc:
            QMessageBox.critical(self, "FMU export unavailable", str(exc))
            self._export_btn.setEnabled(True)
            return
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "FMU export failed", str(exc))
            self._export_btn.setEnabled(True)
            return

        self._last_result = result
        msg = (
            f"FMU written to:\n{result.path}\n\n"
            f"Model identifier: {result.model_identifier or '—'}\n"
            f"Inputs: {len(result.inputs)}    Outputs: {len(result.outputs)}    "
            f"States: {result.state_size}"
        )
        QMessageBox.information(self, "FMU export complete", msg)
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> FmuExportResult | None:
        """Show the dialog modally and return the export summary, if any."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._last_result
        return None

    @property
    def last_result(self) -> FmuExportResult | None:
        return self._last_result
