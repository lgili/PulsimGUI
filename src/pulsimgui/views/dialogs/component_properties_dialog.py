"""Modal dialog for editing component properties with explicit apply/cancel."""

from copy import deepcopy

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from pulsimgui.models.component import Component
from pulsimgui.services.theme_service import ThemeService
from pulsimgui.views.properties import PropertiesPanel


class ComponentPropertiesDialog(QDialog):
    """Edit component properties in a modal flow with OK/Cancel."""

    def __init__(
        self,
        component: Component,
        theme_service: ThemeService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._target_component = component
        self._editable_component = deepcopy(component)
        self._theme_service = theme_service

        self.setModal(True)
        self.setWindowTitle(f"Component Properties - {component.name}")
        self.resize(450, 530)
        self.setMinimumSize(420, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self._panel = PropertiesPanel(theme_service=theme_service, parent=self)
        self._panel.set_show_position_controls(False)
        self._panel.set_compact_mode(True)
        self._panel.set_component(self._editable_component)
        layout.addWidget(self._panel, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def edited_component(self) -> Component:
        """Return edited component snapshot."""
        return self._editable_component
