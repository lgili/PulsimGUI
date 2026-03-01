"""Tests for MainWindow template project creation flow."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
import pulsimgui.views.main_window as main_window_module
from pulsimgui.views.main_window import MainWindow


def test_on_new_from_template_uses_project_circuits_mapping(monkeypatch, qapp) -> None:
    """Template flow should populate Project.circuits with the generated circuit."""

    template_circuit = Circuit(name="Template Circuit")

    class _TemplateDialogStub:
        def __init__(self, parent=None) -> None:
            self._selected_template_id = "buck_converter"

        def exec(self) -> bool:
            return True

        def get_selected_template_id(self) -> str:
            return self._selected_template_id

    monkeypatch.setattr(main_window_module, "TemplateDialog", _TemplateDialogStub)
    monkeypatch.setattr(
        main_window_module.TemplateService,
        "create_circuit_from_template",
        staticmethod(lambda _template_id: template_circuit),
    )

    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_check_save", lambda: True)
        window._on_new_from_template()

        assert window._project.circuits["main"] is template_circuit
        assert window._project.active_circuit == "main"
        assert window._project.name == "Template Circuit"
        assert window._project.is_dirty
    finally:
        window.close()
