"""Base command classes for undo/redo support."""

from abc import ABC, abstractmethod
from typing import Callable

from PySide6.QtCore import QObject, Signal


class Command(ABC):
    """Abstract base class for undoable commands."""

    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the command."""
        pass

    def can_merge(self, other: "Command") -> bool:
        """Check if this command can be merged with another."""
        return False

    def merge(self, other: "Command") -> None:
        """Merge another command into this one."""
        pass


class CommandStack(QObject):
    """
    Stack of commands supporting undo/redo.

    Signals:
        can_undo_changed: Emitted when undo availability changes
        can_redo_changed: Emitted when redo availability changes
        stack_changed: Emitted when the stack changes (for UI updates)
    """

    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    stack_changed = Signal()

    def __init__(self, max_size: int = 100, parent: QObject | None = None):
        super().__init__(parent)
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._max_size = max_size
        self._clean_index = 0
        self._callbacks: list[Callable[[], None]] = []

    @property
    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return len(self._redo_stack) > 0

    @property
    def is_clean(self) -> bool:
        """Check if stack is at clean state (no unsaved changes)."""
        return len(self._undo_stack) == self._clean_index

    @property
    def undo_text(self) -> str:
        """Get description of next undo command."""
        if self._undo_stack:
            return f"Undo {self._undo_stack[-1].description}"
        return "Undo"

    @property
    def redo_text(self) -> str:
        """Get description of next redo command."""
        if self._redo_stack:
            return f"Redo {self._redo_stack[-1].description}"
        return "Redo"

    def execute(self, command: Command, merge: bool = True) -> None:
        """
        Execute a command and add it to the undo stack.

        Args:
            command: The command to execute
            merge: If True, try to merge with previous command
        """
        command.execute()

        # Try to merge with previous command
        if merge and self._undo_stack and self._undo_stack[-1].can_merge(command):
            self._undo_stack[-1].merge(command)
        else:
            self._undo_stack.append(command)

            # Limit stack size
            if len(self._undo_stack) > self._max_size:
                self._undo_stack.pop(0)
                if self._clean_index > 0:
                    self._clean_index -= 1

        # Clear redo stack on new command
        self._redo_stack.clear()

        self._emit_changes()

    def undo(self) -> None:
        """Undo the last command."""
        if not self.can_undo:
            return

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

        self._emit_changes()

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self.can_redo:
            return

        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)

        self._emit_changes()

    def clear(self) -> None:
        """Clear all commands from the stack."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._clean_index = 0
        self._emit_changes()

    def set_clean(self) -> None:
        """Mark current state as clean (saved)."""
        self._clean_index = len(self._undo_stack)

    def _emit_changes(self) -> None:
        """Emit signals for state changes."""
        self.can_undo_changed.emit(self.can_undo)
        self.can_redo_changed.emit(self.can_redo)
        self.stack_changed.emit()
        for callback in self._callbacks:
            callback()

    def add_change_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback to be called when the stack changes."""
        self._callbacks.append(callback)

    def remove_change_callback(self, callback: Callable[[], None]) -> None:
        """Remove a change callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
