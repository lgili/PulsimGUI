"""Dialog that displays the thermal viewer widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QDialogButtonBox,
)

from pulsimgui.services.thermal_service import ThermalResult
from pulsimgui.views.thermal import ThermalViewerWidget


class ThermalViewerDialog(QDialog):
    """Modal dialog that hosts the thermal viewer."""

    def __init__(self, result: ThermalResult | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thermal Viewer")
        self.resize(900, 600)

        # Header with title and synthetic badge
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel("Thermal Analysis Results")
        self._title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(self._title_label)

        self._synthetic_badge = QLabel("(Synthetic Data)")
        self._synthetic_badge.setStyleSheet(
            "color: #FFA500; font-weight: bold; padding: 2px 8px; "
            "border: 1px solid #FFA500; border-radius: 4px;"
        )
        self._synthetic_badge.setVisible(False)
        header_layout.addWidget(self._synthetic_badge)

        header_layout.addStretch()

        self._viewer = ThermalViewerWidget(self)
        self._update_display(result)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).setDefault(True)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addWidget(self._viewer)
        layout.addWidget(buttons)

    def _update_display(self, result: ThermalResult | None) -> None:
        """Update the viewer and synthetic badge visibility."""
        self._viewer.set_result(result)
        if result is not None:
            self._synthetic_badge.setVisible(result.is_synthetic)
            if result.is_synthetic:
                self.setWindowTitle("Thermal Viewer (Synthetic)")
            else:
                self.setWindowTitle("Thermal Viewer")
        else:
            self._synthetic_badge.setVisible(False)
            self.setWindowTitle("Thermal Viewer")

    def set_result(self, result: ThermalResult | None) -> None:
        """Update the dialog with new data."""
        self._update_display(result)
