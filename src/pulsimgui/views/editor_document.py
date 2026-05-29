"""A single open schematic document — one tab in the editor.

PulsimGUI started single-document: MainWindow owned exactly one
``Project``. To let several circuits stay open at once (PSIM-style
tabs), the per-document state is bundled here and MainWindow keeps a
list of these, exposing the active one through its ``_project``
property.

What's per-document (lives here):
  * ``project`` — the :class:`Project` (its circuits, name, file
    ``path``, and ``is_dirty`` flag are all per-document already);
  * ``view_transform`` / ``h_scroll`` / ``v_scroll`` — the schematic
    view's zoom + pan, captured when switching away and restored when
    switching back, so each tab keeps its viewport.

What stays shared in MainWindow (reset on tab switch — documented v1
limitation): the HierarchyService (subcircuit-descend depth), the
undo/redo command stack, the simulation service, and scope windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pulsimgui.models.project import Project


@dataclass
class EditorDocument:
    """One open project + its saved viewport state."""

    project: Project
    # QGraphicsView.transform() captured on switch-away (opaque QTransform).
    view_transform: Any = None
    h_scroll: int = 0
    v_scroll: int = 0
    # Explicit tab label set via double-click rename. Overrides the
    # derived name while set; cleared on save so the on-disk filename
    # takes over as the document's identity.
    display_name: str | None = None
    # Per-document electrical result + scope-window state could live here
    # later; v1 keeps those shared in MainWindow.
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        """Tab label: explicit rename if any, else file stem if saved,
        else the project name, with a leading ``•`` when the document has
        unsaved changes."""
        if self.display_name:
            base = self.display_name
        elif self.project.path is not None:
            base = self.project.path.stem
        else:
            base = self.project.name or "untitled"
        return f"• {base}" if self.project.is_dirty else base

    @property
    def tooltip(self) -> str:
        """Full path (saved) or '(unsaved)' for the tab tooltip."""
        if self.project.path is not None:
            return str(self.project.path)
        return "(unsaved)"
