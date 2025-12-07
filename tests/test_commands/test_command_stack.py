"""Tests for command system."""

import pytest

from pulsimgui.commands.base import Command, CommandStack
from pulsimgui.commands.component_commands import (
    AddComponentCommand,
    DeleteComponentCommand,
    MoveComponentCommand,
)
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType


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
