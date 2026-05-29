"""Regression tests for the "Create empty subcircuit" flow.

When the user runs Edit → Create Subcircuit with no selection,
MainWindow must:
  1. Open the dialog with selected_count=0 (different wording —
     "add components inside after it's placed")
  2. On accept, build an empty SubcircuitDefinition, register it
     with the project + HierarchyService, and drop an empty
     SubcircuitInstance on the canvas at the viewport center
  3. Auto-descend into the new (empty) body so the user can start
     populating it immediately

These tests pin all three steps without needing to actually drive
the QDialog UI — we monkey-patch ``CreateSubcircuitDialog`` to skip
the modal and return scripted values.
"""
from __future__ import annotations

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.subcircuit import (
    SubcircuitInstance,
    create_empty_subcircuit_definition,
)
from pulsimgui.views.main_window import MainWindow


class _StubDialog:
    """Drop-in replacement for CreateSubcircuitDialog that never
    actually shows. The test injects this via monkeypatch so we can
    drive the accept/reject path deterministically."""

    def __init__(
        self,
        selected_count: int,
        boundary_nets,
        parent=None,
        *,
        accept: bool = True,
        name: str = "TestBlock",
        description: str = "",
        symbol_size: tuple[int, int] = (80, 60),
    ):
        self._accept = accept
        self._name = name
        self._desc = description
        self._size = symbol_size
        # Record what MainWindow passed in so the test can assert it
        self.selected_count = selected_count
        self.boundary_nets = list(boundary_nets or [])

    def exec(self) -> int:
        return 1 if self._accept else 0

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return self._desc

    def get_symbol_size(self) -> tuple[int, int]:
        return self._size

    def get_selected_ports(self) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# Model helper — unit-level, no Qt.
# ---------------------------------------------------------------------------
def test_create_empty_subcircuit_definition_default_shape() -> None:
    """The helper builds a definition with an empty body, no ports,
    and the default 80x60 symbol size."""
    d = create_empty_subcircuit_definition()
    assert d.name == "Subcircuit"
    assert d.description == ""
    assert len(d.circuit.components) == 0
    assert len(d.circuit.wires) == 0
    assert d.ports == []
    assert d.symbol_width == 80.0
    assert d.symbol_height == 60.0


def test_create_empty_subcircuit_definition_custom_params() -> None:
    """Caller-supplied name, description, and symbol size land on
    the returned definition."""
    d = create_empty_subcircuit_definition(
        name="BuckStage",
        description="2-MOSFET buck power stage",
        symbol_size=(160, 100),
    )
    assert d.name == "BuckStage"
    assert d.description == "2-MOSFET buck power stage"
    assert d.symbol_width == 160.0
    assert d.symbol_height == 100.0
    # Inner circuit name is derived from the user-facing name so it
    # shows up sensibly in the breadcrumb after descend.
    assert d.circuit.name == "BuckStage_internal"


def test_create_empty_subcircuit_definition_strips_whitespace_name() -> None:
    """Whitespace-only names fall back to ``Subcircuit`` instead of
    landing on the definition as an unreadable label."""
    d = create_empty_subcircuit_definition(name="   ")
    assert d.name == "Subcircuit"


# ---------------------------------------------------------------------------
# MainWindow integration — drives the no-selection branch.
# ---------------------------------------------------------------------------
def _install_stub_dialog(
    monkeypatch,
    *,
    accept: bool = True,
    name: str = "EmptyBlock",
    description: str = "",
    symbol_size: tuple[int, int] = (80, 60),
):
    """Patch CreateSubcircuitDialog in main_window's namespace so the
    real dialog never opens. Returns a list MainWindow will append
    to so the test can inspect what the dialog was called with."""
    instances: list[_StubDialog] = []

    def _factory(selected_count, boundary_nets, parent=None):
        stub = _StubDialog(
            selected_count, boundary_nets, parent,
            accept=accept, name=name, description=description,
            symbol_size=symbol_size,
        )
        instances.append(stub)
        return stub

    import pulsimgui.views.main_window as mw
    monkeypatch.setattr(mw, "CreateSubcircuitDialog", _factory)
    return instances


def test_no_selection_branch_opens_dialog_with_zero_count(qapp, monkeypatch) -> None:
    """When nothing is selected and the user runs the action,
    MainWindow must open the dialog with selected_count=0 and
    empty boundary_nets (not silently no-op)."""
    instances = _install_stub_dialog(monkeypatch, name="NewBlock")
    window = MainWindow()
    try:
        # No selection by default
        assert window._schematic_scene.selectedItems() == []

        window._on_create_subcircuit()

        assert len(instances) == 1, "Dialog must be opened exactly once"
        stub = instances[0]
        assert stub.selected_count == 0
        assert stub.boundary_nets == []
    finally:
        window.deleteLater()


def test_accepted_empty_creation_registers_definition_and_places_instance(
    qapp, monkeypatch
) -> None:
    """Accepting the dialog must:
      - add a SubcircuitDefinition to the project
      - register it with HierarchyService
      - place exactly one SUBCIRCUIT instance in the (then-) active
        circuit pointing at the new definition
    """
    _install_stub_dialog(monkeypatch, name="MyEmpty", symbol_size=(100, 80))
    window = MainWindow()
    try:
        root_circuit = window._current_circuit()
        before_subcircuits = dict(window._project.subcircuits)
        before_components = dict(root_circuit.components)

        window._on_create_subcircuit()

        # Definition was registered project-wide and on the service
        added_defs = [
            d for d_id, d in window._project.subcircuits.items()
            if d_id not in before_subcircuits
        ]
        assert len(added_defs) == 1
        defn = added_defs[0]
        assert defn.name == "MyEmpty"
        assert defn.symbol_width == 100.0
        assert defn.symbol_height == 80.0
        assert window._hierarchy_service.get_subcircuit_definition(defn.id) is defn

        # Instance was placed in the parent circuit (before descend)
        new_components = [
            c for c_id, c in root_circuit.components.items()
            if c_id not in before_components
        ]
        assert len(new_components) == 1
        instance = new_components[0]
        assert isinstance(instance, SubcircuitInstance)
        assert instance.subcircuit_id == defn.id
        # Empty body → no ports → no pins on the symbol yet.
        assert instance.pins == []
    finally:
        window.deleteLater()


def test_accepted_empty_creation_auto_descends_into_new_body(
    qapp, monkeypatch
) -> None:
    """After creation, the navigation stack must show that the user
    is now editing the empty body — not still at the root. The
    schematic scene should be viewing the (empty) inner circuit."""
    _install_stub_dialog(monkeypatch, name="EnterMe")
    window = MainWindow()
    try:
        assert window._hierarchy_service.is_at_root is True

        window._on_create_subcircuit()

        # We are now one level deep
        assert window._hierarchy_service.is_at_root is False
        assert window._hierarchy_service.depth == 1

        # The current view is the empty body
        current = window._hierarchy_service.get_current_circuit()
        assert current.name == "EnterMe_internal"
        assert len(current.components) == 0
    finally:
        window.deleteLater()


def test_rejected_dialog_does_not_modify_project(qapp, monkeypatch) -> None:
    """Cancelling the dialog must leave the project untouched —
    no new definition, no new instance, still at root."""
    _install_stub_dialog(monkeypatch, accept=False)
    window = MainWindow()
    try:
        before_subcircuits = dict(window._project.subcircuits)
        before_components = dict(window._current_circuit().components)

        window._on_create_subcircuit()

        assert window._project.subcircuits == before_subcircuits
        assert window._current_circuit().components == before_components
        assert window._hierarchy_service.is_at_root is True
    finally:
        window.deleteLater()


def test_selection_branch_still_works(qapp, monkeypatch) -> None:
    """Sanity: the existing path (one or more components selected)
    must still group them — we only added the empty branch, didn't
    accidentally break the grouping behavior."""
    _install_stub_dialog(monkeypatch, name="Grouped")
    window = MainWindow()
    try:
        circuit = window._current_circuit()
        # Drop a single resistor and select it
        r = Component(type=ComponentType.RESISTOR, name="R1", x=0, y=0,
                      parameters={"resistance": 100.0})
        circuit.add_component(r)
        window._schematic_scene.add_component(r)
        from pulsimgui.views.schematic.items import ComponentItem
        for item in window._schematic_scene.items():
            if isinstance(item, ComponentItem) and item.component is r:
                item.setSelected(True)
                break

        window._on_create_subcircuit()

        # The resistor moved into the new definition's body, and a
        # SUBCIRCUIT instance took its place in the root circuit.
        assert r.id not in circuit.components
        new_instances = [c for c in circuit.components.values()
                         if c.type == ComponentType.SUBCIRCUIT]
        assert len(new_instances) == 1
        defn = window._project.subcircuits[new_instances[0].subcircuit_id]
        assert r.id in defn.circuit.components
    finally:
        window.deleteLater()
