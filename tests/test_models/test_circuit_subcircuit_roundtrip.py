"""Round-trip tests for SUBCIRCUIT components through Circuit.from_dict.

Regression for the "double-click on subcircuit shows 'Missing
definition' after save+load" bug. The root cause was
``Circuit.from_dict`` using ``Component.from_dict`` for every
component — including SUBCIRCUIT type — which silently dropped the
``subcircuit_id`` field carried only by ``SubcircuitInstance``.
"""
from __future__ import annotations

from uuid import uuid4

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import ComponentType
from pulsimgui.models.subcircuit import SubcircuitInstance


def _make_subcircuit_instance() -> SubcircuitInstance:
    return SubcircuitInstance(
        id=uuid4(),
        name="U1",
        x=10.0, y=20.0,
        rotation=0,
        mirrored_h=False, mirrored_v=False,
        parameters={"symbol_width": 80.0, "symbol_height": 60.0},
        pins=[],
        subcircuit_id=uuid4(),
    )


def test_subcircuit_instance_round_trips_through_circuit() -> None:
    """Save a circuit with a SUBCIRCUIT instance, reload it, and
    verify the ``subcircuit_id`` survives the round trip."""
    instance = _make_subcircuit_instance()
    original_id = instance.id
    original_defn_id = instance.subcircuit_id

    circuit = Circuit(name="parent")
    circuit.components[instance.id] = instance

    serialized = circuit.to_dict()
    rehydrated = Circuit.from_dict(serialized)

    assert original_id in rehydrated.components
    loaded = rehydrated.components[original_id]
    # The reloaded component must be a SubcircuitInstance (not a
    # plain Component) so its ``subcircuit_id`` field is reachable.
    assert isinstance(loaded, SubcircuitInstance), (
        f"expected SubcircuitInstance, got {type(loaded).__name__}"
    )
    assert loaded.subcircuit_id == original_defn_id
    assert loaded.type == ComponentType.SUBCIRCUIT


def test_subcircuit_id_accessible_via_getattr_after_load() -> None:
    """The main_window double-click handler uses
    ``getattr(component, 'subcircuit_id', None)``. Verify that
    pattern works on a freshly-loaded instance."""
    inst = _make_subcircuit_instance()
    circuit = Circuit(name="parent")
    circuit.components[inst.id] = inst
    rehydrated = Circuit.from_dict(circuit.to_dict())
    loaded = rehydrated.components[inst.id]

    defn_id = getattr(loaded, "subcircuit_id", None)
    assert defn_id is not None, (
        "Double-click would dead-end at 'Missing subcircuit' if "
        "subcircuit_id is not reachable via getattr"
    )
    assert defn_id == inst.subcircuit_id


def test_non_subcircuit_components_still_use_plain_loader() -> None:
    """Sanity check: the type-aware loader doesn't accidentally turn
    every component into a SubcircuitInstance."""
    from pulsimgui.models.component import Component, Pin

    resistor = Component(
        id=uuid4(),
        type=ComponentType.RESISTOR,
        name="R1",
        x=0.0, y=0.0,
        parameters={"resistance": 1000.0},
        pins=[
            Pin(index=0, name="1", x=-25.0, y=0.0),
            Pin(index=1, name="2", x=25.0, y=0.0),
        ],
    )
    circuit = Circuit(name="parent")
    circuit.components[resistor.id] = resistor
    rehydrated = Circuit.from_dict(circuit.to_dict())
    loaded = rehydrated.components[resistor.id]
    assert not isinstance(loaded, SubcircuitInstance)
    assert loaded.type == ComponentType.RESISTOR
    assert loaded.parameters["resistance"] == 1000.0


def test_legacy_subcircuit_with_id_in_parameters_can_be_repaired() -> None:
    """Older .pulsim files saved before SubcircuitInstance.to_dict
    might store ``subcircuit_id`` under the component's parameters
    dict instead of as a top-level field. The double-click handler
    has a fallback that reads from parameters and back-fills the
    attribute. This test exercises the fallback path."""
    from pulsimgui.models.component import Component, Pin

    defn_id = uuid4()
    # Build a plain Component with type=SUBCIRCUIT and the legacy
    # parameters layout (no top-level subcircuit_id).
    legacy = Component(
        id=uuid4(),
        type=ComponentType.SUBCIRCUIT,
        name="U_legacy",
        x=0.0, y=0.0,
        parameters={
            "symbol_width": 80.0,
            "symbol_height": 60.0,
            "subcircuit_id": str(defn_id),   # ← legacy location
        },
        pins=[Pin(index=0, name="P1", x=-40.0, y=0.0)],
    )
    serialized = legacy.to_dict()
    # Make sure the top-level field is absent (legacy shape)
    serialized.pop("subcircuit_id", None)

    rehydrated = Circuit.from_dict({
        "name": "x", "components": [serialized], "wires": [],
    })
    loaded = list(rehydrated.components.values())[0]
    # The type-aware loader uses SubcircuitInstance.from_dict, which
    # reads ``data["subcircuit_id"]``. Missing → loaded.subcircuit_id
    # is None. But the legacy parameters dict still has the UUID so
    # the GUI's repair path can recover it.
    params_uuid = loaded.parameters.get("subcircuit_id")
    assert params_uuid == str(defn_id), (
        "Legacy parameter must survive so the GUI can back-fill"
    )
