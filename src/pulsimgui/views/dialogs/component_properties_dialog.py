"""Modal dialog for editing component properties with explicit apply/cancel."""

from copy import deepcopy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.theme_service import ThemeService
from pulsimgui.views.dialogs.component_parameter_help_dialog import ComponentParameterHelpDialog
from pulsimgui.views.properties import PropertiesPanel


class ComponentPropertiesDialog(QDialog):
    """Edit component properties in a modal flow with OK/Cancel."""

    net_label_pair_requested = Signal(str, str)

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
        self._pair_navigation_request: tuple[str, str] | None = None

        self.setModal(True)
        self.setWindowTitle(f"Component Properties - {component.name}")
        if component.type == ComponentType.C_BLOCK:
            self.resize(900, 700)
            self.setMinimumSize(840, 620)
        else:
            self.resize(450, 600)
            self.setMinimumSize(420, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self._panel = PropertiesPanel(theme_service=theme_service, parent=self)
        self._panel.set_show_position_controls(False)
        self._panel.set_compact_mode(True)
        self._panel.net_label_pair_requested.connect(self._on_net_label_pair_requested)
        self._panel.set_component(self._editable_component)
        layout.addWidget(self._panel, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._help_button = buttons.addButton("Help", QDialogButtonBox.ButtonRole.HelpRole)
        self._help_button.clicked.connect(self._on_open_help)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def edited_component(self) -> Component:
        """Return edited component snapshot."""
        return self._editable_component

    @property
    def pair_navigation_request(self) -> tuple[str, str] | None:
        """Return requested net-label pair navigation payload, if any."""
        return self._pair_navigation_request

    def _on_open_help(self) -> None:
        """Open contextual parameter help for the current component type."""
        dialog = ComponentParameterHelpDialog(self._editable_component, self)
        dialog.exec()

    def _on_net_label_pair_requested(self, component_id: str, net_label: str) -> None:
        """Close modal editor and request pair navigation in schematic view."""
        self._pair_navigation_request = (component_id, net_label)
        self.net_label_pair_requested.emit(component_id, net_label)
        self.accept()
