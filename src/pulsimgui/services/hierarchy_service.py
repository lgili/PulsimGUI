"""Service for managing hierarchical schematic navigation."""

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from PySide6.QtCore import QObject, Signal

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.project import Project
from pulsimgui.models.subcircuit import SubcircuitDefinition


@dataclass
class HierarchyLevel:
    """Represents a level in the hierarchy navigation stack."""

    circuit_id: str  # ID of the circuit being viewed
    circuit_name: str  # Display name
    subcircuit_instance_id: Optional[UUID] = None  # If viewing inside a subcircuit instance


class HierarchyService(QObject):
    """Service for managing hierarchical schematic navigation.

    This service tracks the navigation stack as users descend into
    subcircuits and provides breadcrumb navigation.

    Signals:
        hierarchy_changed: Emitted when the current view level changes
        breadcrumb_updated: Emitted when the breadcrumb path changes
    """

    hierarchy_changed = Signal(object)  # HierarchyLevel
    breadcrumb_updated = Signal(list)  # list[HierarchyLevel]

    def __init__(self, project: Project, parent: QObject | None = None):
        super().__init__(parent)
        self._project = project
        self._navigation_stack: list[HierarchyLevel] = []
        self._subcircuit_definitions: dict[UUID, SubcircuitDefinition] = {}

        # Initialize at root level
        self._push_root()
        self._register_existing_subcircuits()

    def _push_root(self) -> None:
        """Push the root circuit level onto the stack."""
        root_circuit = self._project.get_active_circuit()
        root_level = HierarchyLevel(
            circuit_id=self._project.active_circuit,
            circuit_name=root_circuit.name,
            subcircuit_instance_id=None,
        )
        self._navigation_stack = [root_level]
        self.breadcrumb_updated.emit(self._navigation_stack.copy())

    def set_project(self, project: Project) -> None:
        """Set the current project and reset navigation."""
        self._project = project
        self._register_existing_subcircuits()
        self._push_root()
        self.hierarchy_changed.emit(self.current_level)

    @property
    def current_level(self) -> HierarchyLevel:
        """Get the current hierarchy level."""
        return self._navigation_stack[-1] if self._navigation_stack else None

    @property
    def breadcrumb_path(self) -> list[HierarchyLevel]:
        """Get the full breadcrumb path from root to current level."""
        return self._navigation_stack.copy()

    @property
    def depth(self) -> int:
        """Get the current depth in the hierarchy (0 = root)."""
        return len(self._navigation_stack) - 1

    @property
    def is_at_root(self) -> bool:
        """Check if currently at the root level."""
        return len(self._navigation_stack) <= 1

    def get_current_circuit(self) -> Circuit:
        """Get the circuit for the current view level."""
        if not self._navigation_stack:
            return self._project.get_active_circuit()

        current = self.current_level

        # If at root, return the active project circuit
        if current.subcircuit_instance_id is None:
            return self._project.circuits.get(
                current.circuit_id, self._project.get_active_circuit()
            )

        # If inside a subcircuit, get the subcircuit definition's circuit
        definition = self._subcircuit_definitions.get(current.subcircuit_instance_id)
        if definition:
            return definition.circuit

        return self._project.get_active_circuit()

    def register_subcircuit(self, definition: SubcircuitDefinition) -> None:
        """Register a subcircuit definition for navigation."""
        self._subcircuit_definitions[definition.id] = definition

    def unregister_subcircuit(self, definition_id: UUID) -> None:
        """Unregister a subcircuit definition."""
        self._subcircuit_definitions.pop(definition_id, None)

    def _register_existing_subcircuits(self) -> None:
        """Register all subcircuits present in the project."""
        self._subcircuit_definitions.clear()
        for definition in getattr(self._project, "subcircuits", {}).values():
            self._subcircuit_definitions[definition.id] = definition

    def get_subcircuit_definition(self, definition_id: UUID) -> Optional[SubcircuitDefinition]:
        """Get a registered subcircuit definition."""
        return self._subcircuit_definitions.get(definition_id)

    def descend_into(self, subcircuit_instance_id: UUID, definition_id: UUID) -> bool:
        """Navigate into a subcircuit instance.

        Args:
            subcircuit_instance_id: The instance ID of the subcircuit component
            definition_id: The ID of the subcircuit definition

        Returns:
            True if navigation succeeded, False otherwise
        """
        definition = self._subcircuit_definitions.get(definition_id)
        if definition is None:
            return False

        new_level = HierarchyLevel(
            circuit_id=str(definition.id),
            circuit_name=definition.name,
            subcircuit_instance_id=subcircuit_instance_id,
        )

        self._navigation_stack.append(new_level)
        self.breadcrumb_updated.emit(self._navigation_stack.copy())
        self.hierarchy_changed.emit(new_level)
        return True

    def ascend(self) -> bool:
        """Navigate up one level in the hierarchy.

        Returns:
            True if navigation succeeded, False if already at root
        """
        if self.is_at_root:
            return False

        self._navigation_stack.pop()
        self.breadcrumb_updated.emit(self._navigation_stack.copy())
        self.hierarchy_changed.emit(self.current_level)
        return True

    def navigate_to_level(self, level_index: int) -> bool:
        """Navigate to a specific level in the breadcrumb.

        Args:
            level_index: Index in the navigation stack (0 = root)

        Returns:
            True if navigation succeeded
        """
        if level_index < 0 or level_index >= len(self._navigation_stack):
            return False

        # Pop all levels above the target
        self._navigation_stack = self._navigation_stack[: level_index + 1]
        self.breadcrumb_updated.emit(self._navigation_stack.copy())
        self.hierarchy_changed.emit(self.current_level)
        return True

    def navigate_to_root(self) -> None:
        """Navigate directly to the root level."""
        self.navigate_to_level(0)

    def get_parent_circuit(self) -> Optional[Circuit]:
        """Get the parent circuit (one level up).

        Returns:
            The parent circuit, or None if at root
        """
        if self.is_at_root:
            return None

        # Get the level one up
        parent_level = self._navigation_stack[-2]

        if parent_level.subcircuit_instance_id is None:
            return self._project.circuits.get(
                parent_level.circuit_id, self._project.get_active_circuit()
            )

        definition = self._subcircuit_definitions.get(parent_level.subcircuit_instance_id)
        if definition:
            return definition.circuit

        return None
