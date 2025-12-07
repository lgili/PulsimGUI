"""Dialog that displays the thermal viewer widget."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

from pulsimgui.services.thermal_service import ThermalResult
from pulsimgui.views.thermal import ThermalViewerWidget


class ThermalViewerDialog(QDialog):
    """Modal dialog that hosts the thermal viewer."""

    def __init__(self, result: ThermalResult | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thermal Viewer")
        self.resize(900, 600)

        self._viewer = ThermalViewerWidget(self)
        self._viewer.set_result(result)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).setDefault(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._viewer)
        layout.addWidget(buttons)

    def set_result(self, result: ThermalResult | None) -> None:
        """Update the dialog with new data."""
        self._viewer.set_result(result)
