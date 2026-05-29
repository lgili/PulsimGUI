"""Regression tests for HierarchyService descend/ascend navigation.

The previous bug: ``HierarchyService.get_current_circuit`` looked up
``_subcircuit_definitions`` using ``HierarchyLevel.subcircuit_instance_id``
(the *component-instance* UUID). But that dict is keyed by the
*definition* UUID, so the lookup always missed and the method
fell through to returning the root circuit — making double-click
descend appear to do nothing in the GUI even though ``descend_into``
succeeded and the navigation stack updated.

These tests pin the contract: after ``descend_into`` succeeds,
``get_current_circuit`` must return the subcircuit definition's
internal circuit, not the parent.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from PySide6.QtCore import QCoreApplication

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType, Pin
from pulsimgui.models.project import Project
from pulsimgui.models.subcircuit import (
    SubcircuitDefinition,
    SubcircuitInstance,
    SubcircuitPort,
)
from pulsimgui.services.hierarchy_service import HierarchyService


@pytest.fixture
def qt_app():
    app = QCoreApplication.instance()
    if app is None:
        import sys
        app = QCoreApplication(sys.argv)
    return app


def _build_project_with_one_subcircuit() -> tuple[Project, SubcircuitDefinition, SubcircuitInstance]:
    """Build a project with: a root circuit holding one SUBCIRCUIT
    instance, and a registered definition the instance points to."""
    # Definition body — a tiny circuit with a single resistor so we can
    # tell it apart from the root.
    body = Circuit(name="LegBody")
    r = Component(
        id=uuid4(),
        type=ComponentType.RESISTOR,
        name="R_internal",
        x=0.0, y=0.0,
        parameters={"resistance": 50.0},
        pins=[Pin(index=0, name="1", x=-25, y=0), Pin(index=1, name="2", x=25, y=0)],
    )
    body.components[r.id] = r

    defn = SubcircuitDefinition(
        id=uuid4(),
        name="HalfBridgeLeg",
        circuit=body,
        ports=[
            SubcircuitPort(name="A", pin_index=0, x=-40, y=0),
            SubcircuitPort(name="B", pin_index=1, x=40, y=0),
        ],
    )

    # Root circuit holding one instance of the definition.
    root = Circuit(name="main")
    instance = SubcircuitInstance(
        id=uuid4(),
        name="U1",
        x=0, y=0,
        subcircuit_id=defn.id,
        pins=[Pin(index=0, name="A", x=-40, y=0), Pin(index=1, name="B", x=40, y=0)],
    )
    root.components[instance.id] = instance

    project = Project(name="proj")
    project.circuits["main"] = root
    project.active_circuit = "main"
    project.add_subcircuit(defn)

    return project, defn, instance


def test_descend_returns_subcircuit_body_not_root(qt_app) -> None:
    """The regression. Before the fix, ``get_current_circuit`` after
    ``descend_into`` returned the root circuit because of a key-type
    mismatch in the lookup. Now it must return the definition body."""
    project, defn, instance = _build_project_with_one_subcircuit()
    svc = HierarchyService(project)

    # Sanity: before descending we see the root
    assert svc.get_current_circuit().name == "main"

    assert svc.descend_into(instance.id, defn.id) is True

    current = svc.get_current_circuit()
    # The crux of the bug: this used to return the root circuit
    # because the lookup used instance.id (which isn't a key in
    # _subcircuit_definitions) and silently fell through.
    assert current.name == "LegBody", (
        f"After descending into a subcircuit, get_current_circuit "
        f"must return the subcircuit's internal circuit. Got "
        f"{current.name!r} instead — likely the lookup-key bug."
    )
    # And the body holds the components we put inside the definition.
    assert len(current.components) == 1
    assert next(iter(current.components.values())).name == "R_internal"


def test_parent_circuit_resolves_when_inside_subcircuit(qt_app) -> None:
    """``get_parent_circuit`` had the same lookup-key bug. After
    descending once, the parent (the root) must be reachable."""
    project, defn, instance = _build_project_with_one_subcircuit()
    svc = HierarchyService(project)
    assert svc.descend_into(instance.id, defn.id) is True

    parent = svc.get_parent_circuit()
    assert parent is not None
    assert parent.name == "main"
    # And it should be the same object we registered (no copy).
    assert parent is project.circuits["main"]


def test_ascend_returns_to_root(qt_app) -> None:
    """Round-trip: descend then ascend lands back on the root."""
    project, defn, instance = _build_project_with_one_subcircuit()
    svc = HierarchyService(project)

    svc.descend_into(instance.id, defn.id)
    assert svc.depth == 1
    assert svc.ascend() is True
    assert svc.depth == 0
    assert svc.is_at_root
    assert svc.get_current_circuit().name == "main"


def test_descend_into_unknown_definition_fails(qt_app) -> None:
    """Sanity: descending into an id that isn't registered must
    return False and leave the stack alone."""
    project, defn, instance = _build_project_with_one_subcircuit()
    svc = HierarchyService(project)

    bogus = uuid4()
    assert svc.descend_into(instance.id, bogus) is False
    assert svc.depth == 0
    assert svc.get_current_circuit().name == "main"


def test_navigation_after_loading_from_disk_format(qt_app, tmp_path) -> None:
    """Full GUI scenario: serialize a project with a subcircuit,
    reload from disk, then descend. This catches both the
    ``Circuit.from_dict`` type-aware loader regression *and* the
    HierarchyService lookup-key bug at once."""
    project, defn, instance = _build_project_with_one_subcircuit()

    path = tmp_path / "demo.pulsim"
    project.save(path)

    loaded = Project.load(path)
    svc = HierarchyService(loaded)

    # Find the subcircuit instance in the reloaded root circuit.
    root = loaded.get_active_circuit()
    sub_instance = next(
        c for c in root.components.values() if c.type == ComponentType.SUBCIRCUIT
    )
    defn_id = getattr(sub_instance, "subcircuit_id", None)
    assert defn_id is not None, "Round-trip must preserve subcircuit_id"

    assert svc.descend_into(sub_instance.id, defn_id) is True
    assert svc.get_current_circuit().name == "LegBody"


def test_nested_descend_resolves_each_level(qt_app) -> None:
    """If a subcircuit definition itself contains a SUBCIRCUIT
    instance, descending twice should land in the inner-most body."""
    # Inner-most body
    inner_body = Circuit(name="Inner")
    inner_body.components[uuid4()] = Component(
        id=uuid4(),
        type=ComponentType.RESISTOR,
        name="R_inner",
        x=0.0, y=0.0,
        parameters={"resistance": 10.0},
        pins=[Pin(index=0, name="1", x=-25, y=0), Pin(index=1, name="2", x=25, y=0)],
    )
    inner_defn = SubcircuitDefinition(
        id=uuid4(),
        name="InnerLeg",
        circuit=inner_body,
        ports=[
            SubcircuitPort(name="A", pin_index=0, x=-40, y=0),
            SubcircuitPort(name="B", pin_index=1, x=40, y=0),
        ],
    )

    # Outer body holds an instance of the inner definition
    outer_body = Circuit(name="Outer")
    inner_inst = SubcircuitInstance(
        id=uuid4(),
        name="U_inner",
        x=0, y=0,
        subcircuit_id=inner_defn.id,
        pins=[Pin(index=0, name="A", x=-40, y=0), Pin(index=1, name="B", x=40, y=0)],
    )
    outer_body.components[inner_inst.id] = inner_inst
    outer_defn = SubcircuitDefinition(
        id=uuid4(),
        name="OuterLeg",
        circuit=outer_body,
        ports=[
            SubcircuitPort(name="X", pin_index=0, x=-40, y=0),
            SubcircuitPort(name="Y", pin_index=1, x=40, y=0),
        ],
    )

    # Root holds an instance of the outer definition
    root = Circuit(name="main")
    outer_inst = SubcircuitInstance(
        id=uuid4(),
        name="U_outer",
        x=0, y=0,
        subcircuit_id=outer_defn.id,
        pins=[Pin(index=0, name="X", x=-40, y=0), Pin(index=1, name="Y", x=40, y=0)],
    )
    root.components[outer_inst.id] = outer_inst

    project = Project(name="proj")
    project.circuits["main"] = root
    project.active_circuit = "main"
    project.add_subcircuit(inner_defn)
    project.add_subcircuit(outer_defn)

    svc = HierarchyService(project)
    assert svc.descend_into(outer_inst.id, outer_defn.id) is True
    assert svc.get_current_circuit().name == "Outer"
    assert svc.descend_into(inner_inst.id, inner_defn.id) is True
    assert svc.get_current_circuit().name == "Inner"
    # Parent of Inner is Outer (not the root)
    parent = svc.get_parent_circuit()
    assert parent is not None
    assert parent.name == "Outer"
