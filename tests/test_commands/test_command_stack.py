"""Tests for command system."""


from pulsimgui.commands.base import Command
from pulsimgui.commands.component_commands import (
    AddComponentCommand,
    DeleteComponentCommand,
    FlipComponentCommand,
    MoveComponentCommand,
    RotateComponentCommand,
    UpdateComponentStateCommand,
)
from pulsimgui.models.component import (
    Component,
    ComponentType,
    set_cblock_input_count,
    set_cblock_output_count,
)
from pulsimgui.models.wire import Wire, WireConnection


class SimpleCommand(Command):
    """Simple test command that tracks execution."""

    def __init__(self, name: str = "test"):
        self._name = name
        self.executed = False
        self.undone = False

    def execute(self) -> None:
        self.executed = True
        self.undone = False

    def undo(self) -> None:
        self.undone = True
        self.executed = False

    @property
    def description(self) -> str:
        return self._name


class TestCommandStack:
    def test_execute_command(self, command_stack):
        cmd = SimpleCommand()
        command_stack.execute(cmd)

        assert cmd.executed
        assert command_stack.can_undo
        assert not command_stack.can_redo

    def test_undo(self, command_stack):
        cmd = SimpleCommand()
        command_stack.execute(cmd)
        command_stack.undo()

        assert cmd.undone
        assert not command_stack.can_undo
        assert command_stack.can_redo

    def test_redo(self, command_stack):
        cmd = SimpleCommand()
        command_stack.execute(cmd)
        command_stack.undo()
        command_stack.redo()

        assert cmd.executed
        assert command_stack.can_undo
        assert not command_stack.can_redo

    def test_redo_cleared_on_new_command(self, command_stack):
        cmd1 = SimpleCommand("cmd1")
        cmd2 = SimpleCommand("cmd2")

        command_stack.execute(cmd1)
        command_stack.undo()
        command_stack.execute(cmd2)

        assert not command_stack.can_redo

    def test_undo_text(self, command_stack):
        cmd = SimpleCommand("Add R1")
        command_stack.execute(cmd)

        assert command_stack.undo_text == "Undo Add R1"

    def test_clean_state(self, command_stack):
        assert command_stack.is_clean

        cmd = SimpleCommand()
        command_stack.execute(cmd)
        assert not command_stack.is_clean

        command_stack.set_clean()
        assert command_stack.is_clean

        command_stack.undo()
        assert not command_stack.is_clean

    def test_clear(self, command_stack):
        command_stack.execute(SimpleCommand())
        command_stack.execute(SimpleCommand())
        command_stack.undo()

        command_stack.clear()

        assert not command_stack.can_undo
        assert not command_stack.can_redo


class TestAddComponentCommand:
    def test_execute_add(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        cmd = AddComponentCommand(circuit, comp)
        cmd.execute()

        assert comp.id in circuit.components
        assert circuit.get_component_by_name("R1") == comp

    def test_undo_add(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        cmd = AddComponentCommand(circuit, comp)
        cmd.execute()
        cmd.undo()

        assert comp.id not in circuit.components


class TestDeleteComponentCommand:
    def test_execute_delete(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        circuit.add_component(comp)

        cmd = DeleteComponentCommand(circuit, comp.id)
        cmd.execute()

        assert comp.id not in circuit.components

    def test_undo_delete(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        circuit.add_component(comp)

        cmd = DeleteComponentCommand(circuit, comp.id)
        cmd.execute()
        cmd.undo()

        assert comp.id in circuit.components

    def test_delete_removes_connected_wires_and_undo_restores_them(self, circuit):
        comp1 = Component(type=ComponentType.RESISTOR, name="R1")
        comp2 = Component(type=ComponentType.RESISTOR, name="R2")
        circuit.add_component(comp1)
        circuit.add_component(comp2)

        wire = Wire()
        wire.start_connection = WireConnection(component_id=comp1.id, pin_index=0)
        wire.end_connection = WireConnection(component_id=comp2.id, pin_index=0)
        circuit.add_wire(wire)

        cmd = DeleteComponentCommand(circuit, comp1.id)
        cmd.execute()

        assert comp1.id not in circuit.components
        assert wire.id not in circuit.wires

        cmd.undo()

        assert comp1.id in circuit.components
        assert wire.id in circuit.wires


class TestMoveComponentCommand:
    def test_execute_move(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=0, y=0)
        circuit.add_component(comp)

        cmd = MoveComponentCommand(circuit, comp.id, 100, 200)
        cmd.execute()

        assert comp.x == 100
        assert comp.y == 200

    def test_undo_move(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=50, y=75)
        circuit.add_component(comp)

        cmd = MoveComponentCommand(circuit, comp.id, 100, 200)
        cmd.execute()
        cmd.undo()

        assert comp.x == 50
        assert comp.y == 75


class TestRotateComponentCommand:
    def test_execute_rotate(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", rotation=0)
        circuit.add_component(comp)

        cmd = RotateComponentCommand(circuit, comp.id, 90)
        cmd.execute()

        assert comp.rotation == 90

    def test_undo_rotate(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", rotation=270)
        circuit.add_component(comp)

        cmd = RotateComponentCommand(circuit, comp.id, 90)
        cmd.execute()
        cmd.undo()

        assert comp.rotation == 270


class TestFlipComponentCommand:
    def test_execute_horizontal_flip(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", mirrored_h=False)
        circuit.add_component(comp)

        cmd = FlipComponentCommand(circuit, comp.id, horizontal=True)
        cmd.execute()

        assert comp.mirrored_h

    def test_execute_vertical_flip(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", mirrored_v=False)
        circuit.add_component(comp)

        cmd = FlipComponentCommand(circuit, comp.id, horizontal=False)
        cmd.execute()

        assert comp.mirrored_v

    def test_undo_flip(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", mirrored_h=False)
        circuit.add_component(comp)

        cmd = FlipComponentCommand(circuit, comp.id, horizontal=True)
        cmd.execute()
        cmd.undo()

        assert not comp.mirrored_h


class TestUpdateComponentStateCommand:
    def test_execute_state_update(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=10, y=20, rotation=0)
        circuit.add_component(comp)

        new_state = {
            "name": "R99",
            "x": 100.0,
            "y": 200.0,
            "rotation": 90,
            "mirrored_h": True,
            "mirrored_v": False,
            "parameters": {"resistance": 2200.0},
            "pins": comp.pins,
        }

        cmd = UpdateComponentStateCommand(circuit, comp.id, new_state)
        cmd.execute()

        assert comp.name == "R99"
        assert comp.x == 100.0
        assert comp.y == 200.0
        assert comp.rotation == 90
        assert comp.mirrored_h
        assert comp.parameters["resistance"] == 2200.0

    def test_undo_state_update(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=10, y=20, rotation=0)
        circuit.add_component(comp)

        old_name = comp.name
        old_x = comp.x
        old_y = comp.y
        old_rotation = comp.rotation
        old_mirror_h = comp.mirrored_h
        old_parameters = dict(comp.parameters)

        new_state = {
            "name": "R99",
            "x": 100.0,
            "y": 200.0,
            "rotation": 90,
            "mirrored_h": True,
            "mirrored_v": False,
            "parameters": {"resistance": 2200.0},
            "pins": comp.pins,
        }

        cmd = UpdateComponentStateCommand(circuit, comp.id, new_state)
        cmd.execute()
        cmd.undo()

        assert comp.name == old_name
        assert comp.x == old_x
        assert comp.y == old_y
        assert comp.rotation == old_rotation
        assert comp.mirrored_h == old_mirror_h
        assert comp.parameters == old_parameters

    def test_execute_when_state_already_applied(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=10, y=20, rotation=0)
        circuit.add_component(comp)

        old_state = UpdateComponentStateCommand.snapshot(comp)
        comp.name = "R99"
        comp.x = 100.0
        comp.y = 200.0

        new_state = UpdateComponentStateCommand.snapshot(comp)
        cmd = UpdateComponentStateCommand(
            circuit,
            comp.id,
            new_state,
            old_state=old_state,
            already_applied=True,
        )

        cmd.execute()

        assert comp.name == "R99"
        assert comp.x == 100.0
        assert comp.y == 200.0

        cmd.undo()

        assert comp.name == old_state["name"]
        assert comp.x == old_state["x"]
        assert comp.y == old_state["y"]

    def test_merge_updates_keeps_original_old_state(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=10, y=20, rotation=0)
        circuit.add_component(comp)

        first_new = {
            "name": "R2",
            "x": 20.0,
            "y": 30.0,
            "rotation": 90,
            "mirrored_h": False,
            "mirrored_v": False,
            "parameters": dict(comp.parameters),
            "pins": comp.pins,
        }
        second_new = {
            "name": "R3",
            "x": 40.0,
            "y": 50.0,
            "rotation": 180,
            "mirrored_h": True,
            "mirrored_v": False,
            "parameters": {"resistance": 470.0},
            "pins": comp.pins,
        }

        cmd1 = UpdateComponentStateCommand(circuit, comp.id, first_new)
        cmd2 = UpdateComponentStateCommand(circuit, comp.id, second_new)

        assert cmd1.can_merge(cmd2)
        cmd1.execute()
        cmd1.merge(cmd2)
        cmd1.execute()
        cmd1.undo()

        assert comp.name == "R1"

    def test_remaps_wire_pin_indices_when_dynamic_pin_layout_changes(self, circuit):
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1", x=0, y=0)
        load = Component(type=ComponentType.RESISTOR, name="R1", x=120, y=0)
        circuit.add_component(cblock)
        circuit.add_component(load)

        old_state = UpdateComponentStateCommand.snapshot(cblock)

        wire = Wire()
        cb_out_x, cb_out_y = cblock.get_pin_position(1)  # OUT
        load_in_x, load_in_y = load.get_pin_position(0)
        wire.add_segment(cb_out_x, cb_out_y, load_in_x, load_in_y)
        wire.start_connection = WireConnection(component_id=cblock.id, pin_index=1)
        wire.end_connection = WireConnection(component_id=load.id, pin_index=0)
        circuit.add_wire(wire)

        # Increase inputs: OUT moves from pin index 1 -> 2.
        set_cblock_input_count(cblock, 2)
        new_state = UpdateComponentStateCommand.snapshot(cblock)

        cmd = UpdateComponentStateCommand(
            circuit,
            cblock.id,
            new_state,
            old_state=old_state,
            already_applied=True,
        )
        cmd.execute()

        assert wire.start_connection is not None
        assert wire.start_connection.pin_index == 2
        new_out_x, new_out_y = cblock.get_pin_position(2)
        assert wire.segments[0].x1 == new_out_x
        assert wire.segments[0].y1 == new_out_y

        cmd.undo()
        assert wire.start_connection is not None
        assert wire.start_connection.pin_index == 1
        old_out_x, old_out_y = cblock.get_pin_position(1)
        assert wire.segments[0].x1 == old_out_x
        assert wire.segments[0].y1 == old_out_y

    def test_disconnects_wire_when_pin_removed_after_layout_change(self, circuit):
        cblock = Component(type=ComponentType.C_BLOCK, name="CB1", x=0, y=0)
        sensor = Component(type=ComponentType.RESISTOR, name="R2", x=120, y=40)
        circuit.add_component(cblock)
        circuit.add_component(sensor)

        # OUT1 exists when n_outputs=2.
        set_cblock_output_count(cblock, 2)
        old_state = UpdateComponentStateCommand.snapshot(cblock)

        wire = Wire()
        out1_x, out1_y = cblock.get_pin_position(2)  # OUT1
        in_x, in_y = sensor.get_pin_position(0)
        wire.add_segment(out1_x, out1_y, in_x, in_y)
        wire.start_connection = WireConnection(component_id=cblock.id, pin_index=2)
        wire.end_connection = WireConnection(component_id=sensor.id, pin_index=0)
        circuit.add_wire(wire)

        # Reduce outputs to one pin (OUT), removing OUT1.
        set_cblock_output_count(cblock, 1)
        new_state = UpdateComponentStateCommand.snapshot(cblock)

        cmd = UpdateComponentStateCommand(
            circuit,
            cblock.id,
            new_state,
            old_state=old_state,
            already_applied=True,
        )
        cmd.execute()

        assert wire.start_connection is None

        cmd.undo()
        assert wire.start_connection is not None
        assert wire.start_connection.pin_index == 2


class TestMoveComponentCommandMerge:
    def test_merge_moves(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=0, y=0)
        circuit.add_component(comp)

        cmd1 = MoveComponentCommand(circuit, comp.id, 50, 50)
        cmd2 = MoveComponentCommand(circuit, comp.id, 100, 100)

        assert cmd1.can_merge(cmd2)
        cmd1.merge(cmd2)
        cmd1.execute()

        assert comp.x == 100
        assert comp.y == 100

    def test_execute_when_move_already_applied(self, circuit):
        comp = Component(type=ComponentType.RESISTOR, name="R1", x=50, y=75)
        circuit.add_component(comp)

        # Simulate drag having already updated the model position.
        comp.x = 100
        comp.y = 200

        cmd = MoveComponentCommand(
            circuit,
            comp.id,
            100,
            200,
            old_x=50,
            old_y=75,
            already_applied=True,
        )
        cmd.execute()

        assert comp.x == 100
        assert comp.y == 200

        cmd.undo()

        assert comp.x == 50
        assert comp.y == 75
