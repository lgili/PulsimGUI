"""Main application window."""

import math
import re
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QKeySequence,
    QPalette,
    QShortcut,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QStatusBar,
    QTabBar,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui import __version__ as APP_VERSION
from pulsimgui.commands.base import CommandStack
from pulsimgui.commands.component_commands import (
    AddComponentCommand,
    DeleteComponentCommand,
    FlipComponentCommand,
    MoveComponentCommand,
    RotateComponentCommand,
    UpdateComponentStateCommand,
)
from pulsimgui.commands.wire_commands import (
    AddWireCommand,
    DeleteWireCommand,
    RerouteAllWiresCommand,
)
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    CONNECTION_DOMAIN_ANY,
    THERMAL_PORT_PARAMETER,
    ComponentType,
    can_connect_measurement_pins,
    is_restricted_measurement_pin,
    pin_connection_domain,
)
from pulsimgui.models.project import Project
from pulsimgui.views.editor_document import EditorDocument
from pulsimgui.models.subcircuit import (
    SubcircuitInstance,
    create_subcircuit_from_selection,
    detect_boundary_ports,
)
from pulsimgui.resources.icons import IconService
from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.backend_types import ACSettings
from pulsimgui.services.error_translation import format_user_error
from pulsimgui.services.export_service import ExportService
from pulsimgui.services.hierarchy_service import HierarchyService
from pulsimgui.services.settings_service import SettingsService
from pulsimgui.services.shortcut_service import ShortcutService
from pulsimgui.services.simulation_service import (
    ParameterSweepResult,
    SimulationResult,
    SimulationService,
    SimulationState,
    normalize_control_mode,
    normalize_dsed_integrator,
    normalize_engine,
    normalize_formulation_mode,
    normalize_frequency_anchor_mode,
    normalize_frequency_sweep_scale,
    normalize_integration_method,
    normalize_step_mode,
    normalize_thermal_policy,
)
from pulsimgui.services.template_service import TemplateService
from pulsimgui.services.theme_service import Theme, ThemeService
from pulsimgui.services.thermal_service import ThermalAnalysisService
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map
from pulsimgui.utils.signal_utils import format_signal_key
from pulsimgui.views.dialogs import (
    BodePlotDialog,
    ComponentPropertiesDialog,
    CreateSubcircuitDialog,
    DCResultsDialog,
    KeyboardShortcutsDialog,
    ParameterSweepDialog,
    ParameterSweepResultsDialog,
    PreferencesDialog,
    SimulationSettingsDialog,
    TemplateDialog,
    ThermalViewerDialog,
)
from pulsimgui.views.library import LibraryPanel
from pulsimgui.views.properties import PropertiesPanel
from pulsimgui.views.schematic import SchematicScene, SchematicView, Tool
from pulsimgui.views.scope_v2 import BaseScopeWindow
from pulsimgui.views.waveform import WaveformViewer
from pulsimgui.views.widgets import HierarchyBar, MinimapOverlay


class MainWindow(QMainWindow):
    """Main application window with docking panels."""

    # Emitted whenever ``_latest_electrical_result`` is rebuilt — the
    # payload is the *probe-enriched* SimulationResult (i.e. with the
    # ``VP(name)`` / ``IP(name)`` / ``PP(name)`` synthetic channels
    # appended), which is what the scope_v2 PostSimCapability needs
    # in order for its ``signal_key`` lookups to succeed.
    # ``simulation_service.simulation_finished`` carries the *raw*
    # kernel result and would yield "0 of 2 matched" in the drawer.
    electrical_result_ready = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._settings = SettingsService()
        self._theme_service = ThemeService(parent=self)
        self._shortcut_service = ShortcutService(self._settings, parent=self)
        self._command_stack = CommandStack(parent=self)
        # Open documents (tabs). ``_project`` is a property delegating to
        # the active document, so the ~60 existing ``self._project``
        # reads keep working unchanged. Must be set up before anything
        # touches ``self._project``.
        self._documents: list[EditorDocument] = [EditorDocument(Project())]
        self._active_doc: int = 0
        self._tab_bar: QTabBar | None = None  # set in _setup_window via _build_tab_row
        # Guards programmatic QTabBar mutations from re-entering the
        # user-driven switch path (setCurrentIndex / insertTab / removeTab
        # all emit currentChanged).
        self._suppress_tab_signals = False
        self._hierarchy_service = HierarchyService(self._project, parent=self)
        self._simulation_service = SimulationService(settings_service=self._settings, parent=self)
        self._thermal_service = ThermalAnalysisService(
            backend=self._simulation_service.backend,
            allow_synthetic_fallback=False,
            parent=self,
        )
        # Open scope windows keyed by the source component's id. One
        # ``BaseScopeWindow`` instance per scope component on the
        # schematic; re-opening focuses the existing window.
        self._scope_windows: dict[str, BaseScopeWindow] = {}
        self._suppress_scope_state = False
        self._latest_electrical_result: SimulationResult | None = None
        self._component_state_cache: dict[UUID, dict] = {}
        self._sim_progress_active = False
        self._sim_progress_last_value = 0
        self._sync_thermal_service_context()

        self._setup_window()
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_status_bar()
        self._create_dock_widgets()
        self._connect_signals()
        self._handle_backend_changed(self._simulation_service.backend_info, notify=False)
        self._restore_state()
        self._apply_theme()
        self._setup_autosave_timer()
        # Wave-2: rich welcome overlay replaces the legacy text-only
        # empty-state surface. Must come after _create_dock_widgets so
        # the schematic view exists.
        self._welcome_overlay = None
        self._welcome_user_dismissed = False
        self._install_welcome_overlay()
        self._update_schematic_empty_state()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle("PulsimGui - Untitled Project")
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)

        # Force menu bar inside window (not in macOS system bar)
        self.menuBar().setNativeMenuBar(False)

        # Central widget - Schematic Editor + hierarchy bar
        self._schematic_scene = SchematicScene()
        self._schematic_view = SchematicView(self._schematic_scene)
        self._hierarchy_bar = HierarchyBar()

        # Document tab row (PSIM-style): one tab per open project, with a
        # trailing "+" button to open a fresh circuit. A single shared
        # scene/view renders whichever document is active; switching tabs
        # rebinds that scene (see _switch_to_document).
        tab_row = self._build_tab_row()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(tab_row)
        layout.addWidget(self._hierarchy_bar)
        layout.addWidget(self._schematic_view)
        self.setCentralWidget(central)

        # Ensure scene reflects current hierarchy level
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()

        # Minimap floats in the bottom-right corner so it never collides
        # with the centered welcome overlay or the hierarchy bar at top.
        # An event filter re-anchors it whenever the view resizes.
        self._minimap = MinimapOverlay(self._schematic_view)
        self._minimap.set_source_view(self._schematic_view)
        self._minimap.navigation_requested.connect(self._on_minimap_navigation)
        self._position_minimap()
        self._minimap.raise_()
        self._schematic_view.installEventFilter(self)

        # Connect schematic signals
        self._schematic_view.zoom_changed.connect(self.update_zoom)
        self._schematic_view.zoom_changed.connect(lambda _: self._minimap.update_minimap())
        self._schematic_view.mouse_moved.connect(self.update_coordinates)
        self._schematic_view.component_dropped.connect(self._on_component_dropped)
        self._schematic_view.component_pasted.connect(self._on_component_pasted)
        self._schematic_view.selection_pasted.connect(self._on_selection_pasted)
        self._schematic_view.wire_created.connect(self._on_wire_created)
        self._schematic_view.component_delete_requested.connect(
            self._on_component_delete_requested
        )
        self._schematic_view.wire_delete_requested.connect(self._on_wire_delete_requested)
        self._schematic_view.component_rotate_requested.connect(
            self._on_component_rotate_requested
        )
        self._schematic_view.component_flip_requested.connect(self._on_component_flip_requested)
        self._schematic_view.grid_toggle_requested.connect(self._on_grid_toggle_from_view)
        self._schematic_view.subcircuit_open_requested.connect(self._on_subcircuit_open_requested)
        self._schematic_view.scope_open_requested.connect(self._on_scope_open_requested)
        self._schematic_view.component_properties_requested.connect(
            self._on_component_properties_requested
        )
        self._schematic_view.wire_alias_changed.connect(self._on_wire_alias_changed)
        self._schematic_view.quick_add_component.connect(self._on_quick_add_component)
        self._schematic_scene.selection_changed_custom.connect(self.update_selection)
        self._schematic_scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._schematic_scene.component_removed.connect(self._on_component_removed)
        self._schematic_scene.component_added.connect(self._on_component_added_for_port_sync)
        self._schematic_scene.wire_added.connect(self._on_wire_added_for_port_sync)
        self._schematic_scene.component_moved.connect(self._on_component_moved)
        self._schematic_scene.net_label_navigation_requested.connect(
            self._on_net_label_navigation_requested
        )
        # Throttle minimap updates to avoid performance issues during rapid changes
        self._minimap_update_timer = QTimer(self)
        self._minimap_update_timer.setSingleShot(True)
        self._minimap_update_timer.setInterval(50)  # 50ms throttle
        self._minimap_update_timer.timeout.connect(self._minimap.update_minimap)
        self._schematic_scene.changed.connect(lambda _: self._schedule_minimap_update())
        self._hierarchy_bar.update_hierarchy(self._hierarchy_service.breadcrumb_path)
        self._refresh_component_state_cache()

    # ------------------------------------------------------------------
    # Active-document delegation
    # ------------------------------------------------------------------
    @property
    def _project(self) -> Project:
        """The active tab's project. A property so the ~60 existing
        ``self._project`` reads transparently follow the active
        document."""
        return self._documents[self._active_doc].project

    @_project.setter
    def _project(self, value: Project) -> None:
        """Replace the active document's project in place (used by the
        new/open/template/close paths that swap the project of the
        current tab). Opening into a *new* tab goes through
        ``_add_document`` instead."""
        self._documents[self._active_doc].project = value

    @property
    def _active_document(self) -> EditorDocument:
        return self._documents[self._active_doc]

    # ------------------------------------------------------------------
    # Document tabs (PSIM-style multi-circuit)
    # ------------------------------------------------------------------
    def _build_tab_row(self) -> QWidget:
        """Construct the tab strip: a closable/elided ``QTabBar`` plus a
        trailing ``+`` button. Seeds one tab for the initial document.

        Returns the container widget to drop into the central layout."""
        self._tab_bar = QTabBar()
        self._tab_bar.setObjectName("documentTabBar")
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setMovable(False)  # v1: keep tab index == _documents index
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.setUsesScrollButtons(True)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._tab_bar.setDrawBase(True)

        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tab_bar.tabBarDoubleClicked.connect(self._on_tab_double_clicked)

        self._new_tab_button = QToolButton()
        self._new_tab_button.setObjectName("newTabButton")
        self._new_tab_button.setText("+")
        self._new_tab_button.setToolTip("New circuit tab")
        self._new_tab_button.setAutoRaise(True)
        self._new_tab_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._new_tab_button.clicked.connect(self._on_new_tab_clicked)

        row = QWidget()
        row.setObjectName("documentTabRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.addWidget(self._tab_bar)
        row_layout.addWidget(self._new_tab_button)
        row_layout.addStretch(1)

        # Keyboard tab navigation (Ctrl+Tab / Ctrl+Shift+Tab).
        next_tab = QShortcut(QKeySequence.StandardKey.NextChild, self)
        next_tab.activated.connect(self._on_next_tab)
        prev_tab = QShortcut(QKeySequence.StandardKey.PreviousChild, self)
        prev_tab.activated.connect(self._on_prev_tab)

        # Seed the tab for the document that already exists.
        self._suppress_tab_signals = True
        try:
            doc = self._documents[0]
            self._tab_bar.addTab(doc.title)
            self._tab_bar.setTabToolTip(0, doc.tooltip)
        finally:
            self._suppress_tab_signals = False
        return row

    def _set_tab_current_silently(self, index: int) -> None:
        """Move the tab-bar selection without triggering ``_on_tab_changed``."""
        if self._tab_bar is None or self._tab_bar.currentIndex() == index:
            return
        self._suppress_tab_signals = True
        try:
            self._tab_bar.setCurrentIndex(index)
        finally:
            self._suppress_tab_signals = False

    def _refresh_tab(self, index: int) -> None:
        """Sync a tab's label + tooltip from its document (dirty dot, name)."""
        if self._tab_bar is None or not (0 <= index < self._tab_bar.count()):
            return
        if index >= len(self._documents):
            return
        doc = self._documents[index]
        self._suppress_tab_signals = True
        try:
            self._tab_bar.setTabText(index, doc.title)
            self._tab_bar.setTabToolTip(index, doc.tooltip)
        finally:
            self._suppress_tab_signals = False

    def _capture_view_state(self, index: int) -> None:
        """Snapshot the shared view's zoom + pan into a document."""
        if not (0 <= index < len(self._documents)):
            return
        view = getattr(self, "_schematic_view", None)
        if view is None:
            return
        doc = self._documents[index]
        doc.view_transform = QTransform(view.transform())
        doc.h_scroll = view.horizontalScrollBar().value()
        doc.v_scroll = view.verticalScrollBar().value()

    def _restore_view_state(self, index: int) -> None:
        """Reapply a document's saved zoom + pan, or auto-fit if unseen."""
        if not (0 <= index < len(self._documents)):
            return
        view = getattr(self, "_schematic_view", None)
        if view is None:
            return
        doc = self._documents[index]
        if doc.view_transform is not None:
            view.setTransform(doc.view_transform)
            view.horizontalScrollBar().setValue(doc.h_scroll)
            view.verticalScrollBar().setValue(doc.v_scroll)
        else:
            # First time this document is shown — frame its contents.
            self._schedule_auto_fit_view()

    def _rebind_active_document(self) -> None:
        """(Re)load the active document into the shared scene/view and
        refresh chrome. Assumes ``self._active_doc`` is already correct
        and any document-coupled shared state (scopes, command stack,
        latest result) has already been reset by the caller."""
        self._load_project_to_scene()
        self._apply_project_simulation_settings_to_service()
        self._restore_view_state(self._active_doc)
        self._update_title()
        self._update_modified_indicator()

    def _switch_to_document(self, new_index: int) -> None:
        """Make ``new_index`` the active tab. Switching never prompts to
        save (PSIM-style) — only closing does. Shared, per-document state
        (scope windows, undo stack, last result) is reset so circuits
        never cross-contaminate (documented v1 limitation)."""
        if not (0 <= new_index < len(self._documents)):
            return
        self._set_tab_current_silently(new_index)
        if new_index == self._active_doc:
            return
        self._capture_view_state(self._active_doc)
        self._close_all_scope_windows(persist_state=False)
        self._command_stack.clear()
        self._latest_electrical_result = None
        self._active_doc = new_index
        self._rebind_active_document()

    def _add_document(self, project: Project, *, make_active: bool = True) -> int:
        """Append a new document + tab. Returns its index. When
        ``make_active`` the new tab is selected and rendered."""
        assert self._tab_bar is not None  # built in _setup_window
        doc = EditorDocument(project)
        self._documents.append(doc)
        new_index = len(self._documents) - 1
        self._suppress_tab_signals = True
        try:
            self._tab_bar.addTab(doc.title)
            self._tab_bar.setTabToolTip(new_index, doc.tooltip)
        finally:
            self._suppress_tab_signals = False
        if make_active:
            self._switch_to_document(new_index)
        return new_index

    def _replace_active_document(self, project: Project) -> None:
        """Swap the active tab's project in place (used by new/open/close
        when reusing a pristine tab). Resets the tab's view + shared
        document-coupled state and refreshes the label."""
        self._close_all_scope_windows(persist_state=False)
        self._command_stack.clear()
        self._latest_electrical_result = None
        doc = self._documents[self._active_doc]
        doc.project = project
        doc.view_transform = None
        doc.h_scroll = 0
        doc.v_scroll = 0
        self._rebind_active_document()
        self._refresh_tab(self._active_doc)

    def _is_pristine_document(self, doc: EditorDocument) -> bool:
        """True when a document is an untouched blank tab (no file, not
        dirty, empty active circuit) — safe to reuse for an open/new."""
        project = doc.project
        if project.path is not None or project.is_dirty:
            return False
        try:
            circuit = project.get_active_circuit()
        except Exception:
            return False
        return not circuit.components

    def _close_document(self, index: int) -> None:
        """Close a tab. Prompts to save if that document is dirty. Closing
        the last remaining tab resets it to a blank project rather than
        leaving the editor with zero tabs."""
        if not (0 <= index < len(self._documents)):
            return
        doc = self._documents[index]
        # Dirty guard: surface the doc first so the prompt is about it.
        if doc.project.is_dirty:
            previous_active = self._active_doc
            self._switch_to_document(index)
            if not self._check_save():
                # User cancelled — don't leave them parked on a tab they
                # declined to close; return focus to where they were.
                if previous_active != self._active_doc and previous_active < len(
                    self._documents
                ):
                    self._switch_to_document(previous_active)
                return
            index = self._active_doc  # _check_save/save don't move tabs, but be safe
        # Keep at least one tab alive: closing the only tab blanks it.
        if len(self._documents) == 1:
            self._replace_active_document(Project())
            self.statusBar().showMessage("Project closed", 3000)
            return
        assert self._tab_bar is not None  # built in _setup_window
        closing_active = index == self._active_doc
        if closing_active:
            self._close_all_scope_windows(persist_state=False)
            self._command_stack.clear()
            self._latest_electrical_result = None
        # Drop the model + tab (suppress the auto currentChanged).
        self._suppress_tab_signals = True
        try:
            self._tab_bar.removeTab(index)
        finally:
            self._suppress_tab_signals = False
        del self._documents[index]
        if closing_active:
            target = min(index, len(self._documents) - 1)
            self._active_doc = target
            self._set_tab_current_silently(target)
            self._rebind_active_document()
        else:
            if index < self._active_doc:
                self._active_doc -= 1
            self._set_tab_current_silently(self._active_doc)

    def _rename_document(self, index: int) -> None:
        """Prompt for a new display name for a tab (double-click)."""
        if not (0 <= index < len(self._documents)):
            return
        doc = self._documents[index]
        current = doc.display_name or (
            doc.project.path.stem if doc.project.path else (doc.project.name or "untitled")
        )
        new_name, ok = QInputDialog.getText(
            self, "Rename Tab", "Tab name:", text=current
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        doc.display_name = new_name
        doc.project.name = new_name
        doc.project.mark_dirty()
        self._refresh_tab(index)
        if index == self._active_doc:
            self._update_title()
            self._update_modified_indicator()

    # Tab-bar signal slots ------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        if self._suppress_tab_signals:
            return
        self._switch_to_document(index)

    def _on_tab_close_requested(self, index: int) -> None:
        self._close_document(index)

    def _on_tab_double_clicked(self, index: int) -> None:
        if index < 0:
            # Double-click on the empty strip area → new tab (PSIM-ish).
            self._on_new_tab_clicked()
            return
        self._rename_document(index)

    def _on_new_tab_clicked(self) -> None:
        self._add_document(Project())

    def _on_next_tab(self) -> None:
        n = len(self._documents)
        if n > 1:
            self._switch_to_document((self._active_doc + 1) % n)

    def _on_prev_tab(self) -> None:
        n = len(self._documents)
        if n > 1:
            self._switch_to_document((self._active_doc - 1) % n)

    def _create_actions(self) -> None:
        """Create all menu and toolbar actions."""
        # File actions
        self.action_new = QAction("&New Project", self)
        self.action_new.setShortcut(QKeySequence.StandardKey.New)
        self.action_new.setToolTip("New Project (Ctrl+N)")
        self.action_new.triggered.connect(self._on_new_project)

        self.action_new_from_template = QAction("New from &Template...", self)
        self.action_new_from_template.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.action_new_from_template.triggered.connect(self._on_new_from_template)

        self.action_open = QAction("&Open Project...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.setToolTip("Open Project (Ctrl+O)")
        self.action_open.triggered.connect(self._on_open_project)

        self.action_browse_examples = QAction("Browse &Examples...", self)
        self.action_browse_examples.setToolTip(
            "Browse the bundled examples by category with documentation")
        self.action_browse_examples.triggered.connect(self._on_browse_examples)

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.setToolTip("Save Project (Ctrl+S)")
        self.action_save.triggered.connect(self._on_save)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self._on_save_as)

        # Export actions
        self.action_export_spice = QAction("Export &SPICE Netlist...", self)
        self.action_export_spice.triggered.connect(self._on_export_spice)

        self.action_export_json = QAction("Export &JSON Netlist...", self)
        self.action_export_json.triggered.connect(self._on_export_json)

        self.action_export_png = QAction("Export Schematic as &PNG...", self)
        self.action_export_png.triggered.connect(self._on_export_png)

        self.action_export_svg = QAction("Export Schematic as S&VG...", self)
        self.action_export_svg.triggered.connect(self._on_export_svg)

        self.action_export_csv = QAction("Export Waveforms as &CSV...", self)
        self.action_export_csv.triggered.connect(self._on_export_csv)

        # Wave-4 sub-wave A — FMU 2.0 co-simulation export.
        self.action_export_fmu = QAction("Export &FMU 2.0…", self)
        self.action_export_fmu.setToolTip(
            "Export the current circuit as a FMI 2.0 co-simulation .fmu archive"
        )
        self.action_export_fmu.triggered.connect(self._on_export_fmu)

        # Wave-4 sub-wave A — C99 real-time controller codegen.
        self.action_export_c99 = QAction("Export C99 &Controller…", self)
        self.action_export_c99.setToolTip(
            "Generate deployable C99 controller source for the current circuit"
        )
        self.action_export_c99.triggered.connect(self._on_export_c99)

        # Wave-2 — quick paste-into-doc clipboard action.
        self.action_copy_schematic = QAction("Copy Schematic as &Image", self)
        self.action_copy_schematic.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.action_copy_schematic.setToolTip(
            "Copy a PNG render of the schematic to the system clipboard"
            " (⌘⇧C / Ctrl+Shift+C)"
        )
        self.action_copy_schematic.triggered.connect(self._on_copy_schematic_to_clipboard)

        self.action_close = QAction("&Close Project", self)
        self.action_close.setShortcut(QKeySequence("Ctrl+W"))
        self.action_close.triggered.connect(self._on_close_project)

        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)

        # Edit actions
        self.action_undo = QAction("&Undo", self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_undo.setToolTip("Undo (Ctrl+Z)")
        self.action_undo.setEnabled(False)
        self.action_undo.triggered.connect(self._on_undo)

        self.action_redo = QAction("&Redo", self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.action_redo.setToolTip("Redo (Ctrl+Y)")
        self.action_redo.setEnabled(False)
        self.action_redo.triggered.connect(self._on_redo)

        self.action_cut = QAction("Cu&t", self)
        self.action_cut.setShortcut(QKeySequence.StandardKey.Cut)

        self.action_copy = QAction("&Copy", self)
        self.action_copy.setShortcut(QKeySequence.StandardKey.Copy)

        self.action_paste = QAction("&Paste", self)
        self.action_paste.setShortcut(QKeySequence.StandardKey.Paste)

        self.action_delete = QAction("&Delete", self)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)

        self.action_select_all = QAction("Select &All", self)
        self.action_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)

        self.action_auto_route_wires = QAction("Tidy &Wires", self)
        self.action_auto_route_wires.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.action_auto_route_wires.setToolTip(
            "Re-route all wires as clean horizontal/vertical paths "
            "(components stay put) — Ctrl+Shift+R"
        )
        self.action_auto_route_wires.triggered.connect(self._on_auto_route_wires)

        self.action_rename_signal = QAction("&Rename Signal...", self)
        self.action_rename_signal.setShortcut(QKeySequence("F2"))
        self.action_rename_signal.triggered.connect(self._on_rename_signal)

        self.action_create_subcircuit = QAction("Create &Subcircuit...", self)
        # Always enabled so users discover the feature exists. When
        # invoked without a selection, the handler shows an info
        # message explaining what's needed instead of being silently
        # grayed out (which the user just complained about).
        self.action_create_subcircuit.setEnabled(True)
        self.action_create_subcircuit.setStatusTip(
            "Group the selected components into a reusable subcircuit block."
        )
        self.action_create_subcircuit.triggered.connect(self._on_create_subcircuit)

        self.action_preferences = QAction("&Preferences...", self)
        self.action_preferences.setShortcut(QKeySequence("Ctrl+,"))
        self.action_preferences.triggered.connect(self._on_preferences)

        self.action_keyboard_shortcuts = QAction("&Keyboard Shortcuts...", self)
        self.action_keyboard_shortcuts.triggered.connect(self._on_keyboard_shortcuts)

        # View actions
        self.action_zoom_in = QAction("Zoom &In", self)
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.setToolTip("Zoom In (Ctrl+=)")
        self.action_zoom_in.triggered.connect(self._on_zoom_in)

        self.action_zoom_out = QAction("Zoom &Out", self)
        self.action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.action_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.action_zoom_out.triggered.connect(self._on_zoom_out)

        self.action_zoom_fit = QAction("Zoom to &Fit", self)
        self.action_zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.action_zoom_fit.setToolTip("Zoom to Fit (Ctrl+0)")
        self.action_zoom_fit.triggered.connect(self._on_zoom_fit)

        self.action_wire_tool = QAction("&Wire Tool", self)
        self.action_wire_tool.setCheckable(True)
        self.action_wire_tool.setToolTip("Wire Tool (W)")
        self.action_wire_tool.triggered.connect(self._on_wire_tool_selected)

        self.action_hand_tool = QAction("&Hand Tool", self)
        self.action_hand_tool.setCheckable(True)
        self.action_hand_tool.setToolTip("Hand Tool (H)")
        self.action_hand_tool.triggered.connect(self._on_hand_tool_selected)

        self.action_rotate_ccw = QAction("Rotate Counter-Clockwise", self)
        self.action_rotate_ccw.setToolTip("Rotate selected component(s) left")
        self.action_rotate_ccw.setEnabled(False)
        self.action_rotate_ccw.triggered.connect(
            lambda: self._rotate_selected_components(-90)
        )

        self.action_rotate_cw = QAction("Rotate Clockwise", self)
        self.action_rotate_cw.setToolTip("Rotate selected component(s) right")
        self.action_rotate_cw.setEnabled(False)
        self.action_rotate_cw.triggered.connect(
            lambda: self._rotate_selected_components(90)
        )

        self._toolbar_tool_group = QActionGroup(self)
        self._toolbar_tool_group.setExclusive(True)
        self._toolbar_tool_group.addAction(self.action_wire_tool)
        self._toolbar_tool_group.addAction(self.action_hand_tool)
        self.action_hand_tool.setChecked(True)

        self.action_toggle_grid = QAction("Show &Grid", self)
        self.action_toggle_grid.setCheckable(True)
        self.action_toggle_grid.setChecked(self._settings.get_show_grid())
        self.action_toggle_grid.setShortcut(QKeySequence("G"))
        self.action_toggle_grid.triggered.connect(self._on_toggle_grid)

        self.action_toggle_dc_overlay = QAction("Show &DC Values", self)
        self.action_toggle_dc_overlay.setCheckable(True)
        self.action_toggle_dc_overlay.setChecked(False)
        self.action_toggle_dc_overlay.setShortcut(QKeySequence("D"))
        self.action_toggle_dc_overlay.triggered.connect(self._on_toggle_dc_overlay)

        self.action_toggle_minimap = QAction("Show &Minimap", self)
        self.action_toggle_minimap.setCheckable(True)
        self.action_toggle_minimap.setChecked(True)
        self.action_toggle_minimap.setShortcut(QKeySequence("M"))
        self.action_toggle_minimap.triggered.connect(self._on_toggle_minimap)

        self.action_theme_light = QAction("&Light", self)
        self.action_theme_light.setCheckable(True)
        self.action_theme_light.setData("light")

        self.action_theme_dark = QAction("&Dark", self)
        self.action_theme_dark.setCheckable(True)
        self.action_theme_dark.setData("dark")

        self.action_theme_modern_dark = QAction("&Modern Dark", self)
        self.action_theme_modern_dark.setCheckable(True)
        self.action_theme_modern_dark.setData("modern_dark")

        # Simulation actions
        self.action_run = QAction("&Run Simulation", self)
        self.action_run.setShortcut(QKeySequence("F5"))
        self.action_run.setToolTip("Run Simulation (F5)")
        self.action_run.triggered.connect(self._on_run_simulation)

        self.action_stop = QAction("&Stop Simulation", self)
        self.action_stop.setShortcut(QKeySequence("Shift+F5"))
        self.action_stop.setToolTip("Stop Simulation (Shift+F5)")
        self.action_stop.setEnabled(False)
        self.action_stop.triggered.connect(self._on_stop_simulation)

        self.action_pause = QAction("&Pause", self)
        self.action_pause.setShortcut(QKeySequence("F8"))
        self.action_pause.setEnabled(False)
        self.action_pause.triggered.connect(self._on_pause_simulation)

        self.action_dc_op = QAction("&DC Operating Point", self)
        self.action_dc_op.setShortcut(QKeySequence("F6"))
        self.action_dc_op.triggered.connect(self._on_dc_analysis)

        self.action_ac = QAction("&AC Analysis", self)
        self.action_ac.setShortcut(QKeySequence("F7"))
        self.action_ac.triggered.connect(self._on_ac_analysis)

        self.action_sim_settings = QAction("Simulation &Settings...", self)
        self.action_sim_settings.setShortcut(QKeySequence("Ctrl+Alt+S"))
        self.action_sim_settings.triggered.connect(self._on_simulation_settings)

        self.action_parameter_sweep = QAction("Parameter &Sweep...", self)
        self.action_parameter_sweep.triggered.connect(self._on_parameter_sweep)

        self.action_thermal_viewer = QAction("&Thermal Viewer...", self)
        self.action_thermal_viewer.triggered.connect(self._on_show_thermal_viewer)

        # pulsim 1.7 — datasheet Z_th(t) → Foster RC stages.
        self.action_foster_fit = QAction("&Fit Foster from Datasheet Z_th…", self)
        self.action_foster_fit.setToolTip(
            "Paste a transient thermal impedance curve from a power-"
            "device datasheet (t, Z_th columns) and have pulsim solve "
            "the Foster RC stack that reproduces it. The resulting "
            "thermal_rth_stages / thermal_cth_stages strings paste "
            "straight into the component's thermal-port fields."
        )
        self.action_foster_fit.triggered.connect(self._on_show_foster_fit)

        # pulsim 1.7 — TIM + convection sizing helpers.
        self.action_thermal_sizing = QAction("Thermal &Sizing (TIM + Convection)…", self)
        self.action_thermal_sizing.setToolTip(
            "Compute the case-to-sink resistance from a TIM material + "
            "bond-line geometry, and the sink-to-ambient resistance "
            "from heatsink area + airflow. Use the resulting K/W "
            "values in the HEATSINK and device thermal-port fields."
        )
        self.action_thermal_sizing.triggered.connect(self._on_show_thermal_sizing)

        # Wave-4 sub-A 1.4 — loss & efficiency dashboard.
        self.action_losses_dashboard = QAction("&Losses && Efficiency…", self)
        self.action_losses_dashboard.setToolTip(
            "Per-device conduction / switching loss breakdown and "
            "system efficiency readout (uses the latest thermal result)"
        )
        self.action_losses_dashboard.triggered.connect(self._on_show_losses_dashboard)

        # Wave-4 sub-B — new analysis modes.
        self.action_fra = QAction("FRA (Frequency Response)…", self)
        self.action_fra.setToolTip(
            "Closed-loop empirical Bode plot via Simulator.run_fra"
        )
        self.action_fra.triggered.connect(self._on_show_fra)

        self.action_ss_check = QAction("Steady-State Check…", self)
        self.action_ss_check.setToolTip(
            "Did the last transient reach periodic steady state? "
            "Cycle-to-cycle residual check on the captured waveforms."
        )
        self.action_ss_check.triggered.connect(self._on_steady_state_check)

        self.action_periodic_ss = QAction("Periodic Steady-State…", self)
        self.action_periodic_ss.setToolTip(
            "Find the periodic orbit of a switching converter via shooting"
        )
        self.action_periodic_ss.triggered.connect(self._on_show_periodic_ss)

        self.action_harmonic_balance = QAction("Harmonic Balance…", self)
        self.action_harmonic_balance.setToolTip(
            "Solve the spectrum directly via harmonic balance"
        )
        self.action_harmonic_balance.triggered.connect(self._on_show_harmonic_balance)

        # Quick add action
        self.action_quick_add = QAction("&Quick Add Component...", self)
        self.action_quick_add.setShortcut(QKeySequence("Ctrl+K"))
        self.action_quick_add.setToolTip("Quick Add Component (Ctrl+K)")
        self.action_quick_add.triggered.connect(self._on_quick_add)

        # Help actions
        self.action_about = QAction("&About PulsimGui", self)
        self.action_about.triggered.connect(self._on_about)

    def _create_menus(self) -> None:
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        self._file_menu = file_menu
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_new_from_template)
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_browse_examples)
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._update_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_close)
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("&Export")
        self._export_menu = export_menu
        export_menu.addAction(self.action_export_spice)
        export_menu.addAction(self.action_export_json)
        export_menu.addSeparator()
        export_menu.addAction(self.action_export_png)
        export_menu.addAction(self.action_export_svg)
        export_menu.addSeparator()
        export_menu.addAction(self.action_export_csv)
        export_menu.addSeparator()
        export_menu.addAction(self.action_export_fmu)
        export_menu.addAction(self.action_export_c99)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_cut)
        edit_menu.addAction(self.action_copy)
        edit_menu.addAction(self.action_paste)
        edit_menu.addAction(self.action_delete)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_select_all)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_auto_route_wires)
        edit_menu.addAction(self.action_rename_signal)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_copy_schematic)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_create_subcircuit)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_keyboard_shortcuts)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addAction(self.action_zoom_fit)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_grid)
        view_menu.addAction(self.action_toggle_dc_overlay)
        view_menu.addAction(self.action_toggle_minimap)
        view_menu.addSeparator()
        self.panels_menu = view_menu.addMenu("&Panels")
        # Keep panel toggles always accessible so users can reveal hidden docks.
        self.panels_menu.setEnabled(True)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        theme_menu.addAction(self.action_theme_light)
        theme_menu.addAction(self.action_theme_dark)
        theme_menu.addAction(self.action_theme_modern_dark)

        # Simulation menu
        sim_menu = menubar.addMenu("&Simulation")
        self._sim_menu = sim_menu
        sim_menu.addAction(self.action_run)
        sim_menu.addAction(self.action_pause)
        sim_menu.addAction(self.action_stop)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_dc_op)
        sim_menu.addAction(self.action_ac)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_parameter_sweep)
        sim_menu.addAction(self.action_thermal_viewer)
        sim_menu.addAction(self.action_foster_fit)
        sim_menu.addAction(self.action_thermal_sizing)
        sim_menu.addAction(self.action_losses_dashboard)
        sim_menu.addSeparator()
        # Wave-4 sub-B — new analysis modes.
        sim_menu.addAction(self.action_fra)
        sim_menu.addAction(self.action_ss_check)
        sim_menu.addAction(self.action_periodic_ss)
        sim_menu.addAction(self.action_harmonic_balance)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_sim_settings)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.action_about)

        # Hide menu items whose backend capability isn't present in the
        # currently-loaded pulsim kernel. Actions stay alive (Python
        # refs + parent menus) so they reappear automatically when the
        # kernel ships those features later — remove the matching line
        # from ``_hide_unavailable_menu_items`` at that point.
        self._hide_unavailable_menu_items()

    def _hide_unavailable_menu_items(self) -> None:
        """Hide menu actions for backend capabilities pulsim 1.5 doesn't ship.

        Pulsim 1.5 advertises ``transient`` / ``dc`` / ``ac`` /
        ``frequency_analysis`` / ``thermal`` via ``has_capability``.
        Several Wave-4 actions (parameter sweep, losses dashboard,
        FRA, periodic steady-state, harmonic balance, FMU + C99
        export) were authored ahead of the kernel and currently sit in
        the menus permanently disabled — clutters the user's choices.
        """
        sim_caps_to_action = {
            "parameter_sweep": self.action_parameter_sweep,
            "losses_analysis": self.action_losses_dashboard,
            "fra": self.action_fra,
            "periodic_steady_state": self.action_periodic_ss,
            "harmonic_balance": self.action_harmonic_balance,
            "fmu_export": self.action_export_fmu,
            "c99_codegen": self.action_export_c99,
        }
        for cap, action in sim_caps_to_action.items():
            if not self._simulation_service.has_capability(cap):
                action.setVisible(False)
        # Collapse empty separator runs that the now-hidden actions
        # left behind, using the direct menu refs stored in
        # ``_create_menus`` (looking up by title via menuBar().actions()
        # was returning proxy actions whose .menu() handle gets
        # garbage-collected before we can iterate it).
        if getattr(self, "_sim_menu", None) is not None:
            MainWindow._collapse_separators_flat(self._sim_menu)
        if getattr(self, "_export_menu", None) is not None:
            MainWindow._collapse_separators_flat(self._export_menu)

    @staticmethod
    def _collapse_separators_flat(menu) -> None:
        """Hide consecutive / leading / trailing separators in one menu.

        Strict non-recursive walk — never touches child submenus, those
        get populated by later code paths that would crash if we'd
        already poked their actions.
        """
        prev_was_visible_sep = False
        last_visible = None
        for action in menu.actions():
            if not action.isVisible():
                continue
            if action.isSeparator():
                if prev_was_visible_sep or last_visible is None:
                    action.setVisible(False)
                    continue
                prev_was_visible_sep = True
            else:
                prev_was_visible_sep = False
            last_visible = action
        if last_visible is not None and last_visible.isSeparator():
            last_visible.setVisible(False)

    def _create_toolbar(self) -> None:
        """Create the main toolbar with professional icons and overflow menu."""
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QToolButton

        self._toolbar = QToolBar("Main Toolbar")
        self._toolbar.setObjectName("MainToolbar")
        self._toolbar.setIconSize(QSize(20, 20))
        self._toolbar.setMovable(False)
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(self._toolbar)
        self._toolbar_groups: list[QFrame] = []

        self._toolbar.addWidget(
            self._create_toolbar_group(
                "ToolbarGroup",
                (
                    self.action_new,
                    self.action_open,
                    self.action_save,
                ),
            )
        )
        self._toolbar.addWidget(
            self._create_toolbar_group(
                "ToolbarGroup",
                (
                    self.action_undo,
                    self.action_redo,
                ),
            )
        )
        self._toolbar.addWidget(
            self._create_toolbar_group(
                "ToolbarGroup",
                (
                    self.action_zoom_in,
                    self.action_zoom_out,
                    self.action_zoom_fit,
                ),
            )
        )
        self._toolbar.addWidget(
            self._create_toolbar_group(
                "ToolbarGroup",
                (
                    self.action_quick_add,
                    self.action_wire_tool,
                    self.action_hand_tool,
                    self.action_rotate_ccw,
                    self.action_rotate_cw,
                ),
            )
        )

        # Add flexible spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toolbar.addWidget(spacer)

        # Simulation actions grouped on the right for faster recognition
        self._simulation_toolbar_group = self._create_toolbar_group(
            "SimulationToolbarGroup",
            (
                self.action_run,
                self.action_pause,
                self.action_stop,
                self.action_dc_op,
                self.action_ac,
            ),
        )
        self._toolbar.addWidget(self._simulation_toolbar_group)

    def _create_toolbar_group(self, object_name: str, actions: tuple[QAction, ...]) -> QWidget:
        """Create one compact visual toolbar cluster for related actions."""
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton

        group = QFrame(self._toolbar)
        group.setObjectName(object_name)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        for action in actions:
            button = QToolButton(group)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAutoRaise(True)
            button.setDefaultAction(action)
            layout.addWidget(button)
        self._toolbar_groups.append(group)
        return group

    def _create_status_bar(self) -> None:
        """Create the status bar with icons."""
        from PySide6.QtWidgets import QProgressBar

        from pulsimgui.views.widgets import (
            CoordinateWidget,
            ModifiedWidget,
            SelectionWidget,
            SimulationStatusWidget,
            ZoomWidget,
        )
        from pulsimgui.views.widgets.status_widgets import SolverPill

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # Coordinate display with icon
        self._coord_widget = CoordinateWidget()
        self._coord_widget.setMinimumWidth(132)
        status_bar.addWidget(self._coord_widget)

        # Zoom level with icon
        self._zoom_widget = ZoomWidget()
        self._zoom_widget.setMinimumWidth(86)
        status_bar.addWidget(self._zoom_widget)

        # Selection count with icon
        self._selection_widget = SelectionWidget()
        self._selection_widget.setMinimumWidth(126)
        self._selection_widget.hide()  # Hidden when nothing selected
        status_bar.addWidget(self._selection_widget)

        # Spacer
        spacer = QWidget()
        spacer.setMinimumWidth(1)
        status_bar.addWidget(spacer, 1)

        # Simulation progress bar
        self._sim_progress = QProgressBar()
        self._sim_progress.setMinimumWidth(150)
        self._sim_progress.setMaximumWidth(200)
        self._sim_progress.setRange(0, 100)
        self._sim_progress.setValue(0)
        self._sim_progress.setVisible(False)
        status_bar.addPermanentWidget(self._sim_progress)

        # Simulation status with icon
        self._sim_status_widget = SimulationStatusWidget()
        # v0.8.4 — the status text now renders both the GUI version and
        # the backend version explicitly (e.g.
        # ``PulsimGui 0.8.4  ·  Backend Pulsim 0.9.0``) so the segment
        # needs more horizontal room than the 210 px we shipped at v0.8.1.
        self._sim_status_widget.setMinimumWidth(340)
        status_bar.addPermanentWidget(self._sim_status_widget)

        # Solver pill (Phase wave-1, item P1.3): glanceable
        # integrator + dt + linear-solver + adaptive readout. Clicking it
        # opens the Simulation Settings dialog.
        self._solver_pill = SolverPill()
        self._solver_pill.clicked.connect(self._on_solver_pill_clicked)
        status_bar.addPermanentWidget(self._solver_pill)
        self._refresh_solver_pill()

        # Modified indicator with icon
        self._modified_widget = ModifiedWidget()
        self._modified_widget.setMinimumWidth(96)
        self._modified_widget.hide()  # Hidden when saved
        status_bar.addPermanentWidget(self._modified_widget)

    def _create_dock_widgets(self) -> None:
        """Create dockable panels."""
        # Component Library (left)
        self.library_dock = QDockWidget("Component Library", self)
        self.library_dock.setObjectName("LibraryDock")
        self.library_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._library_panel = LibraryPanel(theme_service=self._theme_service)
        self._library_panel.component_double_clicked.connect(self._on_library_component_selected)
        self.library_dock.setWidget(self._library_panel)
        self.library_dock.setMinimumWidth(360)
        self.library_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.library_dock)

        # Properties Panel (right)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("PropertiesDock")
        self.properties_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._properties_panel = PropertiesPanel(theme_service=self._theme_service)
        self._properties_panel.property_changed.connect(self._on_property_changed)
        self._properties_panel.net_label_pair_requested.connect(
            self._on_properties_net_label_pair_requested
        )
        self.properties_dock.setWidget(self._properties_panel)
        self.properties_dock.setMinimumWidth(310)
        self.properties_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        # Component properties are edited in a modal popup flow.
        self.properties_dock.hide()

        # Waveform Viewer (bottom)
        self.waveform_dock = QDockWidget("Waveform Viewer", self)
        self.waveform_dock.setObjectName("WaveformDock")
        self.waveform_dock.setAllowedAreas(
            Qt.DockWidgetArea.TopDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._waveform_viewer = WaveformViewer(theme_service=self._theme_service)
        self.waveform_dock.setWidget(self._waveform_viewer)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.waveform_dock)
        # Keep schematic-first startup layout: waveform panel opens on demand.
        self.waveform_dock.hide()

        # Add explicit toggle actions so hidden docks can always be restored reliably.
        self.action_toggle_component_library = self._create_dock_toggle_action(
            "Component Library",
            self.library_dock,
        )
        self.action_toggle_waveform_panel = self._create_dock_toggle_action(
            "Waveform Viewer",
            self.waveform_dock,
        )
        self.panels_menu.addAction(self.action_toggle_component_library)
        self.panels_menu.addAction(self.action_toggle_waveform_panel)

    def _connect_signals(self) -> None:
        """Connect signals and slots."""
        # Command stack signals
        self._command_stack.can_undo_changed.connect(self.action_undo.setEnabled)
        self._command_stack.can_redo_changed.connect(self.action_redo.setEnabled)
        self._command_stack.stack_changed.connect(self._update_undo_redo_text)

        # Theme actions
        self.action_theme_light.triggered.connect(lambda: self._set_theme("light"))
        self.action_theme_dark.triggered.connect(lambda: self._set_theme("dark"))
        self.action_theme_modern_dark.triggered.connect(lambda: self._set_theme("modern_dark"))

        # Theme service signal
        self._theme_service.theme_changed.connect(self._on_theme_changed)
        self.action_cut.triggered.connect(self._on_cut_selected)
        self.action_copy.triggered.connect(self._on_copy_selected)
        self.action_paste.triggered.connect(self._on_paste_selected)
        self.action_delete.triggered.connect(self._on_delete_selected)
        self.action_select_all.triggered.connect(self._on_select_all_items)

        # Simulation service signals
        self._simulation_service.state_changed.connect(self._on_simulation_state_changed)
        self._simulation_service.progress.connect(self._on_simulation_progress)
        self._simulation_service.data_point.connect(self._on_simulation_data_point)
        # NEW (live-streaming v1.5+): open the LiveScopeWidget when
        # the kernel ring buffer is ready (right before the blocking
        # ``simulate()`` call). The GUI thread polls it via QTimer
        # for real-time waveforms while the worker thread is still
        # crunching numbers.
        self._simulation_service.live_stream_ready.connect(self._on_live_stream_ready)
        self._simulation_service.simulation_finished.connect(self._on_simulation_finished)
        self._simulation_service.dc_finished.connect(self._on_dc_finished)
        self._simulation_service.ac_finished.connect(self._on_ac_finished)
        self._simulation_service.frequency_analysis_finished.connect(
            self._on_frequency_analysis_finished
        )
        self._simulation_service.parameter_sweep_finished.connect(
            self._on_parameter_sweep_finished
        )
        self._simulation_service.post_processing_started.connect(
            self._waveform_viewer.on_post_processing_started
        )
        self._simulation_service.post_processing_completed.connect(
            self._waveform_viewer.on_post_processing_completed
        )
        self._simulation_service.post_processing_failed.connect(
            self._waveform_viewer.on_post_processing_failed
        )
        self._simulation_service.error.connect(self._on_simulation_error)
        self._simulation_service.backend_changed.connect(self._on_backend_changed)
        self._waveform_viewer.post_processing_requested.connect(
            self._on_post_processing_requested
        )
        self._schematic_view.tool_changed.connect(self._sync_toolbar_tool_actions)
        self._sync_toolbar_tool_actions(self._schematic_view.current_tool)

        # Hierarchy service signals
        self._hierarchy_service.hierarchy_changed.connect(self._on_hierarchy_changed)
        self._hierarchy_service.breadcrumb_updated.connect(self._on_breadcrumb_updated)
        self._hierarchy_bar.navigate_up.connect(self._hierarchy_service.ascend)
        self._hierarchy_bar.navigate_to_level.connect(self._hierarchy_service.navigate_to_level)
        # Backspace = "go up one level" — matches the HierarchyBar tooltip.
        # Parented to the main window so it's available anywhere in the
        # schematic, but inert at root level (ascend() returns False).
        self._ascend_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self._ascend_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._ascend_shortcut.activated.connect(self._hierarchy_service.ascend)

    def _create_dock_toggle_action(self, label: str, dock: QDockWidget) -> QAction:
        """Create a stable checkable menu action for one dock widget."""
        action = QAction(label, self)
        action.setCheckable(True)
        action.setChecked(dock.isVisible())
        action.toggled.connect(lambda checked, target=dock: self._set_dock_visible(target, checked))
        dock.visibilityChanged.connect(
            lambda visible, target_action=action: self._sync_dock_toggle_action(target_action, visible)
        )
        return action

    @staticmethod
    def _sync_dock_toggle_action(action: QAction, visible: bool) -> None:
        """Keep one panel toggle action synchronized with dock visibility."""
        action.blockSignals(True)
        action.setChecked(bool(visible))
        action.blockSignals(False)

    def _set_dock_visible(self, dock: QDockWidget, visible: bool) -> None:
        """Show or hide one dock widget explicitly."""
        if visible:
            dock.show()
            dock.raise_()
        else:
            dock.hide()

    def _update_simulation_actions(self) -> None:
        """Enable or disable simulation actions based on backend readiness."""
        backend_ready = self._simulation_service.is_backend_ready
        is_running = self._simulation_service.is_running
        has_dc = self._simulation_service.has_capability("dc")
        has_ac = self._simulation_service.has_capability("ac")
        has_frequency = self._simulation_service.has_capability("frequency_analysis")
        self.action_run.setEnabled(backend_ready and not is_running)
        self.action_stop.setEnabled(backend_ready and is_running)
        self.action_pause.setEnabled(backend_ready and is_running)
        self.action_dc_op.setEnabled(backend_ready and has_dc and not is_running)
        self.action_ac.setEnabled(backend_ready and (has_ac or has_frequency) and not is_running)
        self.action_parameter_sweep.setEnabled(backend_ready and not is_running)

    def _update_backend_status(self, info: BackendInfo | None = None) -> None:
        """Refresh the status bar text to describe backend state.

        Renders both the GUI version (so users can identify the build
        they're running) and the active Pulsim backend version with an
        explicit "Backend" prefix — the v0.8.x labels used to show just
        "Pulsim 0.9.0" which read as the app version and confused users
        upgrading from earlier point releases.
        """
        backend_info = info or self._simulation_service.backend_info
        backend_ready = self._simulation_service.is_backend_ready
        self._update_simulation_actions()
        if backend_ready:
            if not self._simulation_service.is_running:
                self._sim_status_widget.setStatus(self._format_status_label(backend_info))
            return
        warning = (
            self._simulation_service.backend_issue_message
            or "Simulation backend unavailable."
        )
        self._sim_status_widget.setStatus(f"Backend unavailable: {warning}", is_error=True)
        self._sim_progress.setVisible(False)

    @staticmethod
    def _format_status_label(backend_info: BackendInfo) -> str:
        """Compose the segmented status-bar label: GUI version · backend.

        Renders as ``PulsimGui 0.8.3  ·  Backend Pulsim 0.9.0`` so the
        user can distinguish the GUI build they're running from the
        Pulsim runtime version the GUI depends on.
        """
        try:
            from pulsimgui import __version__ as gui_version
        except Exception:
            gui_version = ""
        raw = (backend_info.label() or "").strip()
        if not raw:
            backend_label = "Backend unknown"
        elif raw.lower().startswith("backend"):
            backend_label = raw
        else:
            backend_label = f"Backend {raw}"
        if gui_version:
            return f"PulsimGui {gui_version}  ·  {backend_label}"
        return backend_label

    def _sync_thermal_service_context(self) -> None:
        """Keep thermal analysis service aligned with active backend and settings."""
        runtime_settings = self._simulation_service.settings
        self._thermal_service.backend = self._simulation_service.backend
        self._thermal_service.ambient_temperature = float(
            getattr(runtime_settings, "thermal_ambient", 25.0)
        )
        self._thermal_service.include_switching_losses = bool(
            getattr(runtime_settings, "thermal_include_switching_losses", True)
        )
        self._thermal_service.include_conduction_losses = bool(
            getattr(runtime_settings, "thermal_include_conduction_losses", True)
        )
        self._thermal_service.thermal_network = str(
            getattr(runtime_settings, "thermal_network", "foster") or "foster"
        )

    def _handle_backend_changed(self, info: BackendInfo, notify: bool) -> None:
        """Apply backend changes and optionally notify the user."""
        self._sync_thermal_service_context()
        self._waveform_viewer.set_post_processing_capability(
            self._simulation_service.has_capability("post_processing")
        )
        self._update_backend_status(info)
        if not notify:
            return
        warning = self._simulation_service.backend_issue_message
        if warning:
            self.statusBar().showMessage(f"Backend unavailable: {warning}", 8000)
            QMessageBox.warning(
                self,
                "Simulation Backend Unavailable",
                "Simulations are disabled until a compatible backend is installed or selected.\n\n"
                f"Details: {warning}",
            )
        else:
            self.statusBar().showMessage(f"Backend ready: {info.label()}", 4000)

    def _on_backend_changed(self, info: BackendInfo) -> None:
        """Qt slot invoked when simulation backend changes."""
        self._handle_backend_changed(info, notify=True)

    def _restore_state(self) -> None:
        """Restore window geometry and state."""
        geometry = self._settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        state = self._settings.get_window_state()
        if state:
            self.restoreState(state)
        # Keep the old side properties panel hidden; editing is modal.
        self.properties_dock.hide()
        # Keep waveform/scope dock closed on startup for consistent first view.
        self.waveform_dock.hide()
        if hasattr(self, "action_toggle_component_library"):
            self._sync_dock_toggle_action(
                self.action_toggle_component_library,
                self.library_dock.isVisible(),
            )
        if hasattr(self, "action_toggle_waveform_panel"):
            self._sync_dock_toggle_action(
                self.action_toggle_waveform_panel,
                self.waveform_dock.isVisible(),
            )

    def _apply_theme(self) -> None:
        """Apply the current theme from settings."""
        theme_name = self._settings.get_theme()
        self._theme_service.set_theme(theme_name)
        self._update_theme_menu_state(theme_name)
        self._apply_current_theme()

    def _update_theme_menu_state(self, theme_name: str) -> None:
        """Update theme menu checkmarks."""
        self.action_theme_light.setChecked(theme_name == "light")
        self.action_theme_dark.setChecked(theme_name == "dark")
        self.action_theme_modern_dark.setChecked(theme_name == "modern_dark")

    def _apply_current_theme(self) -> None:
        """Apply the current theme stylesheet and update components."""
        theme = self._theme_service.current_theme

        # Apply the generated stylesheet on the QApplication so detached
        # top-level dialogs (Preferences, Simulation Settings, Convergence
        # Diagnostics, …) inherit the same look as MainWindow children.
        # MainWindow's own stylesheet is cleared to avoid double-application.
        stylesheet = self._theme_service.generate_stylesheet()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)
        self.setStyleSheet("")
        self._apply_palette(theme)

        # Update schematic colors from theme
        bg_color = QColor(theme.colors.schematic_background)
        grid_color = QColor(theme.colors.schematic_grid)
        self._schematic_scene.set_background_color(bg_color)
        self._schematic_scene.set_grid_color(grid_color)

        # Update component and overlay colors
        self._schematic_scene.set_dark_mode(theme.is_dark)
        self._schematic_view.apply_theme(theme)
        self._library_panel.apply_theme(theme)
        self._minimap.apply_theme(theme)
        self._properties_panel.apply_theme(theme)
        self._waveform_viewer.apply_theme(theme)
        self._coord_widget.apply_theme(theme)
        self._zoom_widget.apply_theme(theme)
        self._selection_widget.apply_theme(theme)
        self._sim_status_widget.apply_theme(theme)
        self._modified_widget.apply_theme(theme)

        # Clear icon cache before assigning theme-specific icons
        IconService.clear_cache()

        # Update toolbar icons for current theme
        self._update_toolbar_icons()
        self._update_toolbar_group_styles()

    def _update_toolbar_group_styles(self) -> None:
        """Apply dedicated visual styling for grouped toolbar controls."""
        if not hasattr(self, "_simulation_toolbar_group"):
            return
        colors = self._theme_service.current_theme.colors
        shared_group_style = (
            f"""
            QFrame#ToolbarGroup {{
                border: 1px solid {colors.border};
                border-radius: 11px;
                background-color: {colors.panel_background};
            }}
            QFrame#ToolbarGroup QToolButton {{
                border-radius: 8px;
                padding: 6px 8px;
                margin: 1px;
            }}
            QFrame#ToolbarGroup QToolButton:hover {{
                background-color: {colors.menu_hover};
                border: 1px solid {colors.border};
            }}
            QFrame#ToolbarGroup QToolButton:checked {{
                background-color: {colors.primary}24;
                border: 1px solid {colors.primary}66;
                color: {colors.primary};
            }}
            """
        )
        for group in getattr(self, "_toolbar_groups", []):
            if group is self._simulation_toolbar_group:
                continue
            group.setStyleSheet(shared_group_style)

        self._simulation_toolbar_group.setStyleSheet(
            f"""
            QFrame#SimulationToolbarGroup {{
                border: 1px solid {colors.primary}66;
                border-radius: 11px;
                background-color: {colors.primary}16;
            }}
            QFrame#SimulationToolbarGroup QToolButton {{
                border-radius: 8px;
                padding: 6px 8px;
                margin: 1px;
            }}
            QFrame#SimulationToolbarGroup QToolButton:hover {{
                background-color: {colors.primary}30;
                border: 1px solid {colors.primary}55;
            }}
            QFrame#SimulationToolbarGroup QToolButton:checked {{
                background-color: {colors.primary}44;
                border: 1px solid {colors.primary}88;
            }}
            """
        )

    def _apply_palette(self, theme: Theme) -> None:
        """Apply a base Qt palette so unstyled widgets stay theme-consistent."""
        app = QApplication.instance()
        if app is None:
            return

        c = theme.colors
        palette = app.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(c.background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(c.foreground))
        palette.setColor(QPalette.ColorRole.Base, QColor(c.input_background))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c.background_alt))
        palette.setColor(QPalette.ColorRole.Text, QColor(c.foreground))
        palette.setColor(QPalette.ColorRole.Button, QColor(c.panel_background))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(c.foreground))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c.menu_background))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c.foreground))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(c.primary))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c.primary_foreground))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(c.error))

        disabled_text = QColor(c.foreground_muted)
        disabled_bg = QColor(c.background_alt)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, disabled_bg)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, disabled_bg)
        app.setPalette(palette)

    def _update_toolbar_icons(self) -> None:
        """Update toolbar icons with theme-appropriate colors."""
        theme = self._theme_service.current_theme
        icon_color = theme.colors.icon_default

        # Map actions to icon names
        icon_map = {
            self.action_new: "file-plus",
            self.action_open: "folder-open",
            self.action_save: "save",
            self.action_undo: "undo",
            self.action_redo: "redo",
            self.action_zoom_in: "zoom-in",
            self.action_zoom_out: "zoom-out",
            self.action_zoom_fit: "maximize",
            self.action_quick_add: "plus",
            self.action_wire_tool: "wire",
            self.action_hand_tool: "hand",
            self.action_rotate_ccw: "rotate-ccw",
            self.action_rotate_cw: "rotate-cw",
            self.action_dc_op: "activity",
            self.action_ac: "zap",
        }

        for action, icon_name in icon_map.items():
            action.setIcon(IconService.get_icon(icon_name, icon_color, 16))
        self.action_run.setIcon(IconService.get_icon("play", theme.colors.sim_running, 16))
        self.action_pause.setIcon(IconService.get_icon("pause", theme.colors.sim_paused, 16))
        self.action_stop.setIcon(IconService.get_icon("square", theme.colors.sim_error, 16))

    def _sync_toolbar_tool_actions(self, tool: Tool) -> None:
        """Reflect current schematic tool state in toolbar actions."""
        is_wire_mode = tool == Tool.WIRE
        self.action_wire_tool.setChecked(is_wire_mode)
        self.action_hand_tool.setChecked(not is_wire_mode)

    def _on_wire_tool_selected(self, checked: bool = False) -> None:
        """Activate wire drawing mode from toolbar."""
        if checked:
            self._schematic_view.current_tool = Tool.WIRE

    def _on_hand_tool_selected(self, checked: bool = False) -> None:
        """Activate hand/select mode and cancel any pending wire operation."""
        if checked:
            self._schematic_view.cancel_wire()
            self._schematic_view.current_tool = Tool.SELECT

    def _set_theme(self, theme_name: str) -> None:
        """Set and apply a theme."""
        self._settings.set_theme(theme_name)
        self._theme_service.set_theme(theme_name)
        self._update_theme_menu_state(theme_name)
        self._apply_current_theme()

    def _on_theme_changed(self, theme: Theme) -> None:
        """Handle theme change from service."""
        self._apply_current_theme()

    def _update_undo_redo_text(self) -> None:
        """Update undo/redo action text."""
        self.action_undo.setText(self._command_stack.undo_text)
        self.action_redo.setText(self._command_stack.redo_text)

    def _update_recent_menu(self) -> None:
        """Update the recent projects menu."""
        self.recent_menu.clear()
        recent = self._settings.get_recent_projects()

        if not recent:
            action = QAction("(No recent projects)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
            return

        for path in recent:
            action = QAction(path, self)
            action.setData(path)
            action.triggered.connect(lambda checked, p=path: self._open_project_file(p))
            self.recent_menu.addAction(action)

        self.recent_menu.addSeparator()
        clear_action = QAction("Clear Recent", self)
        clear_action.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_action)

    def _clear_recent(self) -> None:
        """Clear recent projects list."""
        self._settings.clear_recent_projects()
        self._update_recent_menu()

    def _update_title(self) -> None:
        """Update window title based on the active document's state."""
        doc = self._active_document
        if doc.display_name:
            base = doc.display_name
        elif self._project.path:
            base = self._project.path.name
        else:
            base = self._project.name
        title = f"PulsimGui - {base}"
        if self._project.is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def _update_modified_indicator(self) -> None:
        """Update the modified indicator in the status bar and the active
        tab's dirty dot."""
        self._modified_widget.setModified(self._project.is_dirty)
        self._refresh_tab(self._active_doc)

    def _current_circuit(self) -> Circuit:
        """Return the circuit for the current hierarchy level."""
        if hasattr(self, "_hierarchy_service"):
            return self._hierarchy_service.get_current_circuit()
        return self._project.get_active_circuit()

    def _setup_autosave_timer(self) -> None:
        """Set up the auto-save timer based on settings."""
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._on_autosave)
        self._update_autosave_timer()

    def _update_autosave_timer(self) -> None:
        """Update auto-save timer based on current settings."""
        if self._settings.get_auto_save_enabled():
            interval_minutes = self._settings.get_auto_save_interval()
            self._autosave_timer.start(interval_minutes * 60 * 1000)  # Convert to ms
        else:
            self._autosave_timer.stop()

    def _on_autosave(self) -> None:
        """Handle auto-save timer timeout — back up every dirty tab, not
        just the active one, so unsaved work in background tabs is also
        recoverable."""
        saved_any = False
        for doc in self._documents:
            if doc.project.is_dirty and self._autosave_backup(doc.project):
                saved_any = True
        if saved_any:
            self.statusBar().showMessage("Auto-saved backup", 2000)

    def _autosave_backup(self, project: Project) -> bool:
        """Write a best-effort ``.bak`` copy of one project (beside its
        file, or into a temp dir if it has never been saved). Returns True
        on success; failures are swallowed (backups must never interrupt
        editing)."""
        if project.path:
            backup_path = Path(str(project.path) + ".bak")
        else:
            import tempfile

            temp_dir = Path(tempfile.gettempdir()) / "pulsimgui_autosave"
            temp_dir.mkdir(exist_ok=True)
            # Discriminate by object id so two unsaved "Untitled Project"
            # tabs don't overwrite each other's backup.
            backup_path = temp_dir / f"{project.name}_{id(project):x}.pulsim.bak"
        try:
            project.save_copy(backup_path)
            return True
        except Exception:
            return False  # Silently fail on backup

    def update_coordinates(self, x: float, y: float) -> None:
        """Update coordinate display in status bar."""
        self._coord_widget.setCoordinates(x, y)

    def update_zoom(self, zoom_percent: float) -> None:
        """Update zoom level display in status bar."""
        self._zoom_widget.setZoom(zoom_percent)

    def update_selection(self, count: int) -> None:
        """Update selection count in status bar."""
        self._selection_widget.setCount(count)

    def _on_scene_selection_changed(self) -> None:
        """Handle selection change in schematic scene."""
        from shiboken6 import isValid

        from pulsimgui.views.schematic.items import ComponentItem

        scene = self._schematic_scene
        if scene is None or not isValid(scene):
            return

        try:
            selected_items = scene.selectedItems()
        except RuntimeError:
            return

        # Filter to get only ComponentItems
        selected_components = [
            item.component for item in selected_items
            if isinstance(item, ComponentItem)
        ]

        has_selected_components = len(selected_components) > 0
        self.action_rotate_ccw.setEnabled(has_selected_components)
        self.action_rotate_cw.setEnabled(has_selected_components)
        # action_create_subcircuit stays ALWAYS enabled so it's
        # discoverable in the Edit menu even with no selection — the
        # handler shows a friendly info dialog telling the user what
        # to do next. (Was previously grayed-out on no-selection,
        # which left users guessing why the menu item was dim.)

        # Don't update properties if user is editing there
        if self._has_properties_focus():
            return

        if len(selected_components) == 1:
            # Single component selected - show its properties
            self._properties_panel.set_component(selected_components[0])
        elif len(selected_components) > 1:
            # Multiple components selected
            self._properties_panel.set_components(selected_components)
        else:
            # No components selected - clear panel
            self._properties_panel.set_component(None)

    def _on_net_label_navigation_requested(
        self,
        source_component_id: str,
        target_component_id: str,
        net_label: str,
    ) -> None:
        """Select and center the linked Goto/From tag requested by the scene."""
        from pulsimgui.views.schematic.items import ComponentItem

        label_text = net_label.strip() or "(unnamed)"
        if not target_component_id:
            self.statusBar().showMessage(
                f"No linked Goto/From found for tag '{label_text}'.",
                3000,
            )
            return

        source_item = None
        target_item = None
        for item in self._schematic_scene.items():
            if not isinstance(item, ComponentItem):
                continue
            comp_id = str(item.component.id)
            if comp_id == source_component_id:
                source_item = item
            if comp_id == target_component_id:
                target_item = item

        if target_item is None:
            self.statusBar().showMessage(
                f"Linked tag '{label_text}' exists but is not visible in this scene.",
                3000,
            )
            return

        self._schematic_scene.clearSelection()
        if source_item is not None:
            source_item.setSelected(True)
        target_item.setSelected(True)
        target_rect = target_item.sceneBoundingRect()
        target_center = target_rect.center()
        self._schematic_view.centerOn(target_center)
        self._schematic_view.ensureVisible(target_rect, 80, 80)

        self.statusBar().showMessage(
            f"Jumped to linked tag '{label_text}'.",
            2000,
        )

    def _has_properties_focus(self) -> bool:
        """Check if any widget in properties panel or its dock has focus."""
        focus_widget = QApplication.focusWidget()
        if focus_widget is None:
            return False
        # Check if focus widget is inside properties panel or its dock
        widget = focus_widget
        while widget is not None:
            if widget == self._properties_panel or widget == self.properties_dock:
                return True
            widget = widget.parent()
        return False

    def _has_text_input_focus(self) -> bool:
        """Return True when the focused widget is editing text/value fields."""
        focus_widget = QApplication.focusWidget()
        if focus_widget is None:
            return False
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return True
        return isinstance(focus_widget, QComboBox) and focus_widget.isEditable()

    def _on_delete_selected(self) -> None:
        """Delete selected schematic items from menu/shortcut action."""
        if self._has_text_input_focus():
            return
        self._schematic_view.delete_selected_items()

    def _on_cut_selected(self) -> None:
        """Cut selected schematic items from menu/shortcut action."""
        if self._has_text_input_focus():
            return
        self._schematic_view.cut_selected()

    def _on_copy_selected(self) -> None:
        """Copy selected schematic items from menu/shortcut action."""
        if self._has_text_input_focus():
            return
        self._schematic_view.copy_selected()

    def _on_paste_selected(self) -> None:
        """Paste clipboard schematic item from menu/shortcut action."""
        if self._has_text_input_focus():
            return
        self._schematic_view.paste_at_cursor()

    def _on_select_all_items(self) -> None:
        """Select all schematic items from menu/shortcut action."""
        if self._has_text_input_focus():
            return
        self._schematic_view.select_all_items()

    def _on_auto_route_wires(self) -> None:
        """Re-route every wire in the active circuit as clean orthogonal
        paths (obstacle-avoiding). Components are not moved. Undoable."""
        circuit = self._current_circuit()
        wire_count = len(circuit.wires)
        if wire_count == 0:
            self.statusBar().showMessage("No wires to tidy", 2000)
            return
        grid = float(getattr(self._schematic_scene, "grid_size", 20.0) or 20.0)
        self._execute_schematic_command(
            RerouteAllWiresCommand(circuit, grid=grid),
            refresh_scene=True,
        )
        self.statusBar().showMessage(
            f"Tidied {wire_count} wire{'s' if wire_count != 1 else ''}", 3000
        )

    def _on_hierarchy_changed(self, _level) -> None:
        """Refresh scene when hierarchy level changes."""
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()
        self._refresh_component_state_cache()
        self._schematic_scene.clearSelection()
        self._properties_panel.set_component(None)
        self.update_selection(0)

    def _on_breadcrumb_updated(self, levels: list) -> None:
        """Update hierarchy bar breadcrumb display."""
        self._hierarchy_bar.update_hierarchy(levels)

    def _on_subcircuit_open_requested(self, component) -> None:
        """Handle double-click on a subcircuit instance to descend."""
        # Two paths to the subcircuit-definition pointer:
        # 1. ``SubcircuitInstance`` attribute set directly (live + the
        #    Circuit.from_dict path that handles SUBCIRCUIT specially).
        # 2. ``parameters["subcircuit_id"]`` — a fallback for older
        #    .pulsim files that round-tripped through the plain
        #    ``Component.from_dict`` before the type-aware loader.
        definition_id = getattr(component, "subcircuit_id", None)
        if not definition_id:
            params = getattr(component, "parameters", {}) or {}
            raw = params.get("subcircuit_id")
            if raw:
                try:
                    from uuid import UUID
                    definition_id = UUID(str(raw))
                    # Repair the live instance so subsequent clicks
                    # don't hit the fallback path.
                    component.subcircuit_id = definition_id
                except (ValueError, TypeError):
                    definition_id = None

        if not definition_id:
            QMessageBox.warning(
                self, "Missing subcircuit",
                "This subcircuit instance has no definition attached.\n\n"
                "It may have been imported without its subcircuit_id, "
                "or the definition was deleted from the project.",
            )
            return

        # Make sure the HierarchyService knows about the definition.
        # When a project loads, definitions are auto-registered in
        # HierarchyService.__init__, but if someone calls
        # ``project.add_subcircuit`` later (e.g., a paste from another
        # file), the service doesn't see it until we explicitly tell it.
        if self._hierarchy_service.get_subcircuit_definition(definition_id) is None:
            defn = self._project.get_subcircuit(definition_id)
            if defn is not None:
                self._hierarchy_service.register_subcircuit(defn)

        if not self._hierarchy_service.descend_into(component.id, definition_id):
            QMessageBox.warning(
                self, "Cannot navigate",
                "Subcircuit definition could not be loaded — "
                "the project may be missing the matching definition.",
            )

    def _on_create_subcircuit(self) -> None:
        """Create a subcircuit definition — either from the current
        selection (groups the picked components into a block) or as
        an empty block when nothing is selected (user fills it in
        later by descending into the body)."""
        from pulsimgui.models.component import ComponentType
        from pulsimgui.views.schematic.items import ComponentItem, WireItem

        selected_items = self._schematic_scene.selectedItems()
        component_items = [item for item in selected_items if isinstance(item, ComponentItem)]
        wire_items = [item for item in selected_items if isinstance(item, WireItem)]

        # Empty-creation branch: no selection → blank subcircuit body,
        # placed at the viewport center, then we auto-descend so the
        # user lands inside the body ready to drop components and
        # SUBCIRCUIT_PORT markers.
        if not component_items:
            self._create_empty_subcircuit_via_dialog()
            return

        current_circuit = self._current_circuit()
        component_ids = [item.component.id for item in component_items]
        wire_ids = [item.wire.id for item in wire_items]

        candidates = detect_boundary_ports(current_circuit, component_ids)
        candidate_names = [c.name for c in candidates]

        dialog = CreateSubcircuitDialog(len(component_items), candidate_names, self)
        if not dialog.exec():
            return

        selected_names = set(dialog.get_selected_ports())
        if selected_names:
            selected_candidates = [c for c in candidates if c.name in selected_names]
        else:
            selected_candidates = candidates

        try:
            definition, ports, center = create_subcircuit_from_selection(
                current_circuit,
                selected_component_ids=component_ids,
                selected_wire_ids=wire_ids,
                name=dialog.get_name(),
                description=dialog.get_description(),
                symbol_size=dialog.get_symbol_size(),
                boundary_ports=selected_candidates,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Create Subcircuit", str(exc))
            return

        # Remove selected items from circuit and scene
        for item in component_items:
            current_circuit.remove_component(item.component.id)
            self._schematic_scene.removeItem(item)

        for item in wire_items:
            current_circuit.remove_wire(item.wire.id)
            self._schematic_scene.removeItem(item)

        # Register definition and add instance
        self._project.add_subcircuit(definition)
        self._hierarchy_service.register_subcircuit(definition)

        instance = SubcircuitInstance(
            name=self._generate_component_name(ComponentType.SUBCIRCUIT),
            x=center[0],
            y=center[1],
            parameters={
                "symbol_width": definition.symbol_width,
                "symbol_height": definition.symbol_height,
            },
            pins=definition.get_pins(),
            subcircuit_id=definition.id,
        )

        current_circuit.add_component(instance)
        self._schematic_scene.add_component(instance)

        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()
        self.statusBar().showMessage(
            f"Created subcircuit '{definition.name}' with {len(ports)} port(s)", 3000
        )

    def _create_empty_subcircuit_via_dialog(self) -> None:
        """Open the CreateSubcircuitDialog without a selection and,
        on accept, drop an empty subcircuit instance at the viewport
        center, register the definition, and descend into it so the
        user can start populating the body right away.

        The dialog handles the name/description/symbol-size; ports
        are populated later by ``SUBCIRCUIT_PORT`` markers the user
        places inside the body (auto-synced by
        ``_sync_subcircuit_ports_if_editing``).
        """
        from pulsimgui.models.component import ComponentType
        from pulsimgui.models.subcircuit import (
            create_empty_subcircuit_definition,
        )

        # No selection → no boundary nets, so pass an empty list. The
        # dialog already branches on selected_count==0 to show the
        # right wording.
        dialog = CreateSubcircuitDialog(0, [], self)
        if not dialog.exec():
            return

        definition = create_empty_subcircuit_definition(
            name=dialog.get_name(),
            description=dialog.get_description(),
            symbol_size=dialog.get_symbol_size(),
        )
        self._project.add_subcircuit(definition)
        self._hierarchy_service.register_subcircuit(definition)

        # Place the instance at the viewport center so it lands where
        # the user is looking, not at the scene origin (which may be
        # off-screen after they panned).
        view_center = self._schematic_view.mapToScene(
            self._schematic_view.viewport().rect().center()
        )

        current_circuit = self._current_circuit()
        instance = SubcircuitInstance(
            name=self._generate_component_name(ComponentType.SUBCIRCUIT),
            x=view_center.x(),
            y=view_center.y(),
            parameters={
                "symbol_width": definition.symbol_width,
                "symbol_height": definition.symbol_height,
            },
            pins=definition.get_pins(),  # empty for a blank definition
            subcircuit_id=definition.id,
        )
        current_circuit.add_component(instance)
        self._schematic_scene.add_component(instance)

        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

        # Auto-descend into the new (empty) body so the user can
        # immediately drop components and SUBCIRCUIT_PORT markers.
        # If descend fails for any reason (shouldn't, since we just
        # registered the definition), we stay at the parent level
        # — the empty block is still placed and visible.
        if self._hierarchy_service.descend_into(instance.id, definition.id):
            self.statusBar().showMessage(
                f"Empty subcircuit '{definition.name}' created — "
                f"add components and port markers, then press "
                f"Backspace to return.",
                5000,
            )
        else:
            self.statusBar().showMessage(
                f"Empty subcircuit '{definition.name}' placed on canvas",
                3000,
            )

    def _clear_scene(self) -> None:
        """Clear all items from the schematic scene."""
        self._schematic_scene.clear()
        self._properties_panel.set_component(None)

    def _load_project_to_scene(self) -> None:
        """Load the current project's circuit into the schematic scene."""
        self._hierarchy_service.set_project(self._project)
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()
        self._refresh_component_state_cache()
        self._hierarchy_bar.update_hierarchy(self._hierarchy_service.breadcrumb_path)
        self._apply_current_theme()

    def _apply_project_simulation_settings_to_service(self) -> None:
        """Mirror project transient settings into the runtime simulation service."""
        project_settings = self._project.simulation_settings
        runtime_settings = self._simulation_service.settings
        runtime_settings.t_start = float(project_settings.tstart)
        runtime_settings.t_stop = float(project_settings.tstop)
        runtime_settings.t_step = float(project_settings.dt)
        runtime_settings.max_step = float(getattr(project_settings, "max_step", project_settings.dt))
        # Extremely small abs_tol values from legacy files can destabilize switching solves.
        runtime_settings.abs_tol = max(float(project_settings.abstol), 1e-10)
        runtime_settings.rel_tol = float(project_settings.reltol)
        runtime_settings.solver = normalize_integration_method(
            getattr(project_settings, "solver", runtime_settings.solver)
        )
        runtime_settings.step_mode = normalize_step_mode(
            getattr(project_settings, "step_mode", runtime_settings.step_mode)
        )
        # pulsim 1.6 engine selector + DSED knobs. Previously NOT mirrored —
        # the project's saved engine was silently ignored, so a global DSED
        # preference ran even on circuits that need PWL (e.g. an MMC, whose
        # controlled-source arms have no LTI state-space for DSED).
        runtime_settings.engine = normalize_engine(
            getattr(project_settings, "engine", runtime_settings.engine)
        )
        runtime_settings.dsed_rtol = float(
            getattr(project_settings, "dsed_rtol", runtime_settings.dsed_rtol)
        )
        runtime_settings.dsed_atol = float(
            getattr(project_settings, "dsed_atol", runtime_settings.dsed_atol)
        )
        runtime_settings.dsed_dt_init = float(
            getattr(project_settings, "dsed_dt_init", runtime_settings.dsed_dt_init)
        )
        runtime_settings.dsed_integrator = normalize_dsed_integrator(
            getattr(project_settings, "dsed_integrator", runtime_settings.dsed_integrator)
        )
        runtime_settings.dsed_stiffness_threshold = float(
            getattr(project_settings, "dsed_stiffness_threshold",
                    runtime_settings.dsed_stiffness_threshold)
        )
        runtime_settings.dsed_h_bdf2 = float(
            getattr(project_settings, "dsed_h_bdf2", runtime_settings.dsed_h_bdf2)
        )
        runtime_settings.output_points = int(
            getattr(project_settings, "output_points", runtime_settings.output_points)
        )
        runtime_settings.enable_events = bool(
            getattr(project_settings, "enable_events", runtime_settings.enable_events)
        )
        runtime_settings.max_step_retries = int(
            getattr(project_settings, "max_step_retries", runtime_settings.max_step_retries)
        )
        runtime_settings.max_newton_iterations = int(project_settings.max_iterations)
        runtime_settings.enable_voltage_limiting = bool(project_settings.enable_voltage_limiting)
        runtime_settings.enable_newton_lm = bool(
            getattr(project_settings, "enable_newton_lm", runtime_settings.enable_newton_lm)
        )
        runtime_settings.max_voltage_step = float(project_settings.max_voltage_step)
        runtime_settings.dc_strategy = str(project_settings.dc_strategy)
        runtime_settings.gmin_initial = float(project_settings.gmin_initial)
        runtime_settings.gmin_final = float(project_settings.gmin_final)
        runtime_settings.dc_source_steps = int(project_settings.dc_source_steps)
        runtime_settings.transient_robust_mode = bool(project_settings.transient_robust_mode)
        runtime_settings.transient_auto_regularize = bool(project_settings.transient_auto_regularize)
        runtime_settings.enable_losses = bool(
            getattr(project_settings, "enable_losses", runtime_settings.enable_losses)
        )
        runtime_settings.thermal_ambient = float(
            getattr(project_settings, "thermal_ambient", runtime_settings.thermal_ambient)
        )
        runtime_settings.thermal_include_switching_losses = bool(
            getattr(
                project_settings,
                "thermal_include_switching_losses",
                runtime_settings.thermal_include_switching_losses,
            )
        )
        runtime_settings.thermal_include_conduction_losses = bool(
            getattr(
                project_settings,
                "thermal_include_conduction_losses",
                runtime_settings.thermal_include_conduction_losses,
            )
        )
        runtime_settings.thermal_network = str(
            getattr(project_settings, "thermal_network", runtime_settings.thermal_network) or "foster"
        )
        runtime_settings.thermal_policy = normalize_thermal_policy(
            str(
                getattr(
                    project_settings,
                    "thermal_policy",
                    runtime_settings.thermal_policy,
                )
                or "loss_with_temperature_scaling"
            )
        )
        runtime_settings.thermal_default_rth = max(
            0.0,
            float(
                getattr(
                    project_settings,
                    "thermal_default_rth",
                    runtime_settings.thermal_default_rth,
                )
            ),
        )
        runtime_settings.thermal_default_cth = max(
            0.0,
            float(
                getattr(
                    project_settings,
                    "thermal_default_cth",
                    runtime_settings.thermal_default_cth,
                )
            ),
        )
        runtime_settings.formulation_mode = normalize_formulation_mode(
            getattr(project_settings, "formulation_mode", runtime_settings.formulation_mode)
        )
        runtime_settings.direct_formulation_fallback = bool(
            getattr(
                project_settings,
                "direct_formulation_fallback",
                runtime_settings.direct_formulation_fallback,
            )
        )
        runtime_settings.control_mode = normalize_control_mode(
            getattr(project_settings, "control_mode", runtime_settings.control_mode)
        )
        runtime_settings.control_sample_time = max(
            0.0,
            float(
                getattr(
                    project_settings,
                    "control_sample_time",
                    runtime_settings.control_sample_time,
                )
            ),
        )
        runtime_settings.ac_f_start = max(
            1e-12,
            float(getattr(project_settings, "ac_f_start", runtime_settings.ac_f_start)),
        )
        runtime_settings.ac_f_stop = max(
            runtime_settings.ac_f_start * (1.0 + 1e-12),
            float(getattr(project_settings, "ac_f_stop", runtime_settings.ac_f_stop)),
        )
        runtime_settings.ac_points_per_decade = max(
            1,
            int(
                getattr(
                    project_settings,
                    "ac_points_per_decade",
                    runtime_settings.ac_points_per_decade,
                )
            ),
        )
        runtime_settings.ac_anchor_mode = normalize_frequency_anchor_mode(
            getattr(project_settings, "ac_anchor_mode", runtime_settings.ac_anchor_mode)
        )
        runtime_settings.ac_sweep_scale = normalize_frequency_sweep_scale(
            getattr(project_settings, "ac_sweep_scale", runtime_settings.ac_sweep_scale)
        )
        runtime_settings.ac_injection_node = str(
            getattr(project_settings, "ac_injection_node", runtime_settings.ac_injection_node) or ""
        )
        runtime_settings.ac_measurement_node = str(
            getattr(
                project_settings,
                "ac_measurement_node",
                runtime_settings.ac_measurement_node,
            )
            or ""
        )
        raw_averaged_options = getattr(
            project_settings,
            "averaged_options",
            runtime_settings.averaged_options,
        )
        runtime_settings.averaged_options = (
            dict(raw_averaged_options) if isinstance(raw_averaged_options, dict) else None
        )
        self._sync_thermal_service_context()

    def _apply_simulation_service_settings_to_project(self) -> None:
        """Persist runtime simulation settings back into the project model."""
        project_settings = self._project.simulation_settings
        runtime_settings = self._simulation_service.settings
        project_settings.tstart = float(runtime_settings.t_start)
        project_settings.tstop = float(runtime_settings.t_stop)
        project_settings.dt = float(runtime_settings.t_step)
        project_settings.max_step = float(runtime_settings.max_step)
        project_settings.abstol = float(runtime_settings.abs_tol)
        project_settings.reltol = float(runtime_settings.rel_tol)
        project_settings.solver = normalize_integration_method(runtime_settings.solver)
        project_settings.step_mode = normalize_step_mode(runtime_settings.step_mode)
        project_settings.engine = normalize_engine(runtime_settings.engine)
        project_settings.dsed_rtol = float(runtime_settings.dsed_rtol)
        project_settings.dsed_atol = float(runtime_settings.dsed_atol)
        project_settings.dsed_dt_init = float(runtime_settings.dsed_dt_init)
        project_settings.dsed_integrator = normalize_dsed_integrator(
            runtime_settings.dsed_integrator
        )
        project_settings.dsed_stiffness_threshold = float(
            runtime_settings.dsed_stiffness_threshold
        )
        project_settings.dsed_h_bdf2 = float(runtime_settings.dsed_h_bdf2)
        project_settings.output_points = int(runtime_settings.output_points)
        project_settings.enable_events = bool(runtime_settings.enable_events)
        project_settings.max_step_retries = int(runtime_settings.max_step_retries)
        project_settings.max_iterations = int(runtime_settings.max_newton_iterations)
        project_settings.enable_voltage_limiting = bool(runtime_settings.enable_voltage_limiting)
        project_settings.enable_newton_lm = bool(runtime_settings.enable_newton_lm)
        project_settings.max_voltage_step = float(runtime_settings.max_voltage_step)
        project_settings.dc_strategy = str(runtime_settings.dc_strategy)
        project_settings.gmin_initial = float(runtime_settings.gmin_initial)
        project_settings.gmin_final = float(runtime_settings.gmin_final)
        project_settings.dc_source_steps = int(runtime_settings.dc_source_steps)
        project_settings.transient_robust_mode = bool(runtime_settings.transient_robust_mode)
        project_settings.transient_auto_regularize = bool(runtime_settings.transient_auto_regularize)
        project_settings.enable_losses = bool(runtime_settings.enable_losses)
        project_settings.thermal_ambient = float(runtime_settings.thermal_ambient)
        project_settings.thermal_include_switching_losses = bool(
            runtime_settings.thermal_include_switching_losses
        )
        project_settings.thermal_include_conduction_losses = bool(
            runtime_settings.thermal_include_conduction_losses
        )
        project_settings.thermal_network = str(runtime_settings.thermal_network)
        project_settings.thermal_policy = normalize_thermal_policy(
            str(runtime_settings.thermal_policy)
        )
        project_settings.thermal_default_rth = max(
            0.0,
            float(runtime_settings.thermal_default_rth),
        )
        project_settings.thermal_default_cth = max(
            0.0,
            float(runtime_settings.thermal_default_cth),
        )
        project_settings.formulation_mode = normalize_formulation_mode(
            runtime_settings.formulation_mode
        )
        project_settings.direct_formulation_fallback = bool(
            runtime_settings.direct_formulation_fallback
        )
        project_settings.control_mode = normalize_control_mode(runtime_settings.control_mode)
        project_settings.control_sample_time = max(
            0.0,
            float(runtime_settings.control_sample_time),
        )
        project_settings.ac_f_start = max(1e-12, float(runtime_settings.ac_f_start))
        project_settings.ac_f_stop = max(
            project_settings.ac_f_start * (1.0 + 1e-12),
            float(runtime_settings.ac_f_stop),
        )
        project_settings.ac_points_per_decade = max(1, int(runtime_settings.ac_points_per_decade))
        project_settings.ac_anchor_mode = normalize_frequency_anchor_mode(
            runtime_settings.ac_anchor_mode
        )
        project_settings.ac_sweep_scale = normalize_frequency_sweep_scale(
            runtime_settings.ac_sweep_scale
        )
        project_settings.ac_injection_node = str(runtime_settings.ac_injection_node or "")
        project_settings.ac_measurement_node = str(runtime_settings.ac_measurement_node or "")
        project_settings.averaged_options = (
            dict(runtime_settings.averaged_options)
            if isinstance(runtime_settings.averaged_options, dict)
            else None
        )

    # Slots
    def _place_project_in_tab(self, project: Project, *, dirty: bool = False) -> None:
        """Surface a freshly built / loaded project in a tab.

        Reuses the active tab when it's a pristine blank (so a fresh
        launch doesn't accumulate empty tabs), otherwise opens a new tab
        and switches to it. ``dirty=True`` marks the result modified
        (templates start unsaved)."""
        if self._is_pristine_document(self._active_document):
            self._replace_active_document(project)
        else:
            self._add_document(project)
        if dirty:
            self._project.mark_dirty()
        self._refresh_tab(self._active_doc)
        self._update_title()
        self._update_modified_indicator()

    def _on_new_project(self) -> None:
        """Create a new blank circuit (PSIM-style: in its own tab, reusing
        a pristine active tab if present). Never destroys unsaved work."""
        self._place_project_in_tab(Project())

    def _on_new_from_template(self) -> None:
        """Create a new project from a template, in a tab."""
        dialog = TemplateDialog(self)
        if not dialog.exec():
            return
        template_id = dialog.get_selected_template_id()
        if not template_id:
            return

        # Prefer full project templates (includes saved simulation settings).
        template_project = TemplateService.create_project_from_template(template_id)
        if template_project is not None:
            template_project.path = None
            self._place_project_in_tab(template_project, dirty=True)
            self.statusBar().showMessage(
                f"Created new project from template: {template_project.name}", 3000
            )
            return

        # Fallback: legacy circuit-only templates.
        circuit = TemplateService.create_circuit_from_template(template_id)
        if circuit:
            project = Project(name=circuit.name)
            project.circuits = {"main": circuit}
            project.active_circuit = "main"
            self._place_project_in_tab(project, dirty=True)
            self.statusBar().showMessage(
                f"Created new project from template: {circuit.name}", 3000
            )

    def _on_open_project(self) -> None:
        """Open a project file (in a new tab)."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            self._settings.get_default_project_location(),
            "Pulsim Projects (*.pulsim);;All Files (*)",
        )
        if path:
            self._open_project_file(path)

    def _open_project_file(self, path: str) -> None:
        """Open a project from the given path in a tab. If the file is
        already open, just switch to its tab instead of opening twice."""
        # Dedup against already-open documents.
        try:
            resolved = Path(path).resolve()
        except Exception:
            resolved = None
        if resolved is not None:
            for i, doc in enumerate(self._documents):
                existing = doc.project.path
                if existing is None:
                    continue
                try:
                    same = existing.resolve() == resolved
                except Exception:
                    same = False
                if same:
                    self._switch_to_document(i)
                    self.statusBar().showMessage(f"Already open: {path}", 3000)
                    return
        try:
            project = Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")
            return
        # Reuse a pristine tab or open a new one; _restore_view_state
        # auto-fits the freshly loaded circuit (its view_transform is None).
        self._place_project_in_tab(project)
        self._settings.add_recent_project(path)
        self._update_recent_menu()
        # Re-resolve every open scope window's probe bindings — saved
        # examples that pre-date a binding-handler change (e.g. the
        # "any pin of a probe → ``IP(<probe>)``" / pin-set migration
        # passes) would otherwise reuse stale signal keys and the user
        # has to manually close + reopen each scope to pick up the new
        # resolution. Refreshing on open is essentially free (no
        # windows open → no-op) and removes the "old scope" footgun.
        self._refresh_scope_window_bindings()
        self.statusBar().showMessage(f"Opened: {path}", 3000)

    def _schedule_auto_fit_view(self) -> None:
        """Defer ``zoom_to_fit`` until after the scene has settled."""
        view = getattr(self, "_schematic_view", None)
        if view is None or not hasattr(view, "zoom_to_fit"):
            return
        QTimer.singleShot(0, view.zoom_to_fit)

    def _on_save(self) -> None:
        """Save the current project."""
        self._apply_simulation_service_settings_to_project()
        if self._project.path is None:
            self._on_save_as()
        else:
            try:
                self._project.save()
                self._command_stack.set_clean()
                # The on-disk filename is now the document's identity.
                self._active_document.display_name = None
                self._update_title()
                self._update_modified_indicator()
                self._refresh_tab(self._active_doc)
                self.statusBar().showMessage("Project saved", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _on_save_as(self) -> None:
        """Save the project with a new name."""
        self._apply_simulation_service_settings_to_project()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            self._settings.get_default_project_location(),
            "Pulsim Projects (*.pulsim);;All Files (*)",
        )
        if path:
            if not path.endswith(".pulsim"):
                path += ".pulsim"
            try:
                self._project.save(path)
                self._command_stack.set_clean()
                # The on-disk filename is now the document's identity.
                self._active_document.display_name = None
                self._settings.add_recent_project(path)
                self._update_recent_menu()
                self._update_title()
                self._update_modified_indicator()
                self._refresh_tab(self._active_doc)
                self.statusBar().showMessage(f"Saved: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _on_close_project(self) -> None:
        """Close the active tab (prompting to save if it's dirty). Closing
        the last remaining tab resets it to a fresh blank project."""
        self._close_document(self._active_doc)

    def _on_undo(self) -> None:
        """Undo the last command."""
        if not self._command_stack.can_undo:
            return
        self._command_stack.undo()
        self._reload_schematic_scene()
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _on_redo(self) -> None:
        """Redo the last undone command."""
        if not self._command_stack.can_redo:
            return
        self._command_stack.redo()
        self._reload_schematic_scene()
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _execute_schematic_command(
        self,
        command,
        *,
        refresh_scene: bool = True,
        merge: bool = False,
    ) -> None:
        """Execute an undoable command and update project/UI state."""
        self._command_stack.execute(command, merge=merge)
        if refresh_scene:
            self._reload_schematic_scene()
        else:
            self._refresh_component_state_cache()
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _reload_schematic_scene(self) -> None:
        """Reload active circuit into scene to reflect model changes."""
        self._schematic_scene.load_circuit(self._current_circuit())
        self._refresh_component_state_cache()

    def _component_state_snapshot(self, component) -> dict:
        """Capture an undo-friendly snapshot for a component."""
        return UpdateComponentStateCommand.snapshot(component)

    def _refresh_component_state_cache(self) -> None:
        """Refresh local cache used to build property-edit undo commands."""
        circuit = self._current_circuit()
        self._component_state_cache = {
            component.id: self._component_state_snapshot(component)
            for component in circuit.components.values()
        }
        self._update_schematic_empty_state()

    def _update_schematic_empty_state(self) -> None:
        """Show onboarding hint only when the active circuit is still empty.

        The schematic view's empty-state overlay is an opt-in feature
        only present on builds that include the canvas-side widget.
        Probing with ``hasattr`` here keeps older / minimal builds
        bootable — without this guard the v0.8.1 / v0.8.2 release
        bundles crashed at startup because the cherry-pick that added
        the caller never picked up the corresponding view-side
        ``set_empty_state_visible`` method.
        """
        view = getattr(self, "_schematic_view", None)
        if view is None or not hasattr(view, "set_empty_state_visible"):
            return
        circuit = self._current_circuit()
        is_empty = not circuit.components and not circuit.wires
        view.set_empty_state_visible(is_empty)
        # Honour the user's explicit dismissal of the welcome overlay so
        # ``New schematic`` shows the blank canvas they asked for instead
        # of immediately re-rendering the welcome card.
        if is_empty and getattr(self, "_welcome_user_dismissed", False):
            view.set_empty_state_visible(False)

        # Hide the minimap while the welcome card is centered on the
        # canvas — it would otherwise float on top of the card and the
        # placeholder is meaningless without a schematic anyway.
        minimap = getattr(self, "_minimap", None)
        toggle_action = getattr(self, "action_toggle_minimap", None)
        if minimap is not None:
            wants_visible = toggle_action.isChecked() if toggle_action is not None else True
            welcome_visible = is_empty and not getattr(self, "_welcome_user_dismissed", False)
            minimap.setVisible(wants_visible and not welcome_visible)
        if is_empty and not getattr(self, "_welcome_user_dismissed", False):
            self._refresh_welcome_recent_paths()

    # ------------------------------------------------------------------
    # Wave-2 — Welcome overlay
    # ------------------------------------------------------------------

    def _install_welcome_overlay(self) -> None:
        """Attach the four-card welcome surface to the schematic view."""
        view = getattr(self, "_schematic_view", None)
        if view is None or not hasattr(view, "set_welcome_overlay"):
            return
        try:
            from pulsimgui.views.widgets.welcome_overlay import WelcomeOverlay
        except Exception:  # pragma: no cover - missing module shouldn't crash
            return
        overlay = WelcomeOverlay(view.viewport())
        overlay.new_project_requested.connect(self._on_welcome_new_project)
        overlay.open_project_requested.connect(self._on_welcome_open_project)
        overlay.recent_project_requested.connect(self._on_welcome_recent_project)
        overlay.template_requested.connect(self._on_welcome_template)
        overlay.dismissed.connect(self._on_welcome_dismissed)
        # Apply current theme palette.
        try:
            theme = self._theme_service.current_theme
            c = theme.colors
            overlay.apply_palette(
                foreground=c.foreground,
                foreground_muted=c.foreground_muted,
                surface=c.panel_background,
                surface_muted=c.panel_background,
                border=c.panel_border,
            )
        except Exception:
            pass
        view.set_welcome_overlay(overlay)
        self._welcome_overlay = overlay
        self._refresh_welcome_recent_paths()

    def _refresh_welcome_recent_paths(self) -> None:
        overlay = getattr(self, "_welcome_overlay", None)
        if overlay is None:
            return
        try:
            recent = list(self._settings.get_recent_projects())[:5]
        except Exception:
            recent = []
        overlay.set_recent_paths(recent)

    def _on_welcome_new_project(self) -> None:
        # User explicitly asked for a blank canvas — dismiss the overlay
        # so they actually see the empty schematic they requested.
        self._welcome_user_dismissed = True
        self._on_new_project()
        self.statusBar().showMessage("New blank schematic created", 2500)

    def _on_welcome_open_project(self) -> None:
        self._on_open_project()

    def _on_welcome_dismissed(self) -> None:
        """Hide the welcome overlay until the next app launch."""
        self._welcome_user_dismissed = True
        self._update_schematic_empty_state()
        overlay = getattr(self, "_welcome_overlay", None)
        if overlay is not None:
            overlay.hide()

    def _on_welcome_recent_project(self, path: str) -> None:
        if not path:
            return
        # If the file disappeared since we cached it, drop it from the
        # recent list and notify the user.
        try:
            from pathlib import Path
            if not Path(path).is_file():
                self._settings.remove_recent_project(path)
                self._update_recent_menu()
                self._refresh_welcome_recent_paths()
                self.statusBar().showMessage(
                    f"File not found: {path} — removed from recent list", 5000
                )
                return
        except Exception:
            pass
        self._open_project_file(path)

    def _on_browse_examples(self) -> None:
        """Open the example browser (category filter + documentation pane)
        and load whatever the user picks."""
        from pulsimgui.views.dialogs.example_browser_dialog import (
            ExampleBrowserDialog,
        )

        dialog = ExampleBrowserDialog(self)
        if dialog.exec() and dialog.selected_path:
            self._open_project_file(dialog.selected_path)

    def _on_welcome_template(self) -> None:
        """Open the gallery picker so the user can pick a template."""
        try:
            from PySide6.QtWidgets import QFileDialog
        except Exception:
            return
        import os
        import sys
        # Look up the bundled gallery dir; in dev mode this is
        # repo/examples/gallery, in PyInstaller bundles it's next to the
        # frozen executable.
        candidates = []
        try:
            from pulsimgui import __file__ as pkg_init
            from pathlib import Path
            pkg_root = Path(pkg_init).resolve().parent
            candidates.append(pkg_root / "../../examples/gallery")
            candidates.append(pkg_root / "examples/gallery")
        except Exception:
            pass
        if getattr(sys, "frozen", False):  # PyInstaller bundle
            from pathlib import Path
            candidates.append(Path(sys.executable).resolve().parent / "examples" / "gallery")
        gallery_dir = None
        for cand in candidates:
            try:
                if cand.is_dir():
                    gallery_dir = str(cand.resolve())
                    break
            except Exception:
                continue
        start_dir = gallery_dir or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open template",
            start_dir,
            "Pulsim Projects (*.pulsim);;All Files (*)",
        )
        if path:
            self._open_project_file(path)

    def _on_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About PulsimGui",
            "<h3>PulsimGui</h3>"
            "<p>Cross-platform GUI for Pulsim power electronics simulator.</p>"
            f"<p>Version {APP_VERSION}</p>"
            "<p>Copyright (c) 2024 Luiz Gili</p>"
            "<p>Licensed under MIT License</p>",
        )

    def _on_quick_add(self) -> None:
        """Show quick-add palette for fast component insertion."""
        from pulsimgui.views.dialogs.quick_add_dialog import QuickAddDialog

        dialog = QuickAddDialog(self)

        # Position near center of window
        pos = self.geometry().center()
        dialog.move(pos.x() - 200, pos.y() - 150)

        def on_component_selected(comp_type):
            # Add component at center of current view
            view_center = self._schematic_view.mapToScene(
                self._schematic_view.viewport().rect().center()
            )
            self._add_component_at(comp_type, view_center.x(), view_center.y())

        dialog.component_selected.connect(on_component_selected)
        dialog.exec()

    def _on_quick_add_component(self, comp_type) -> None:
        """Handle quick-add component from keyboard shortcut."""
        # Try to position relative to selection, otherwise center of view
        x, y = self._get_smart_placement_position()
        self._add_component_at(comp_type, x, y)
        self.statusBar().showMessage(
            f"Added {comp_type.name.replace('_', ' ').title()}", 2000
        )

    def _get_smart_placement_position(self) -> tuple[float, float]:
        """Get smart position for new component based on selection or view center."""

        scene = self._schematic_view.scene()

        # Check if there's a selected component
        if scene:
            selected = scene.selectedItems()
            if selected:
                from pulsimgui.views.schematic.items import ComponentItem

                # Find the rightmost selected component
                comp_items = [item for item in selected if isinstance(item, ComponentItem)]
                if comp_items:
                    # Position to the right of the rightmost selected component
                    rightmost = max(comp_items, key=lambda c: c.x())
                    x = rightmost.x() + 100  # Offset to the right
                    y = rightmost.y()
                    return x, y

        # Fallback to center of view
        view_center = self._schematic_view.mapToScene(
            self._schematic_view.viewport().rect().center()
        )
        return view_center.x(), view_center.y()

    def _add_component_at(self, comp_type, x: float, y: float) -> None:
        """Add a component at the specified position."""
        from pulsimgui.models.component import Component

        # Snap to grid
        scene = self._schematic_view.scene()
        if scene and hasattr(scene, 'snap_to_grid'):
            from PySide6.QtCore import QPointF
            snapped = scene.snap_to_grid(QPointF(x, y))
            x, y = snapped.x(), snapped.y()

        # Create component. NOTE: ``type=`` is mandatory — Component's first
        # positional field is ``id`` (a UUID), so a positional comp_type would
        # silently land in ``id`` and leave ``type`` defaulted to RESISTOR.
        component = Component(
            type=comp_type,
            name=self._generate_component_name(comp_type),
            x=x,
            y=y,
        )
        self._execute_schematic_command(
            AddComponentCommand(self._current_circuit(), component),
            refresh_scene=True,
            merge=False,
        )

    def _on_zoom_in(self) -> None:
        """Zoom in the schematic view."""
        self._schematic_view.zoom_in()

    def _on_zoom_out(self) -> None:
        """Zoom out the schematic view."""
        self._schematic_view.zoom_out()

    def _on_zoom_fit(self) -> None:
        """Zoom to fit all items."""
        self._schematic_view.zoom_to_fit()

    def _on_minimap_navigation(self, x: float, y: float) -> None:
        """Handle navigation request from minimap."""
        from PySide6.QtCore import QPointF
        self._schematic_view.centerOn(QPointF(x, y))
        self._minimap.update_minimap()

    def _on_toggle_grid(self, checked: bool) -> None:
        """Toggle grid visibility."""
        self._schematic_scene.show_grid = checked
        self._settings.set_show_grid(checked)

    def _on_grid_toggle_from_view(self) -> None:
        """Handle grid toggle request from view (G key)."""
        new_state = not self._schematic_scene.show_grid
        self._schematic_scene.show_grid = new_state
        self._settings.set_show_grid(new_state)
        self.action_toggle_grid.setChecked(new_state)

    def _on_toggle_dc_overlay(self, checked: bool) -> None:
        """Toggle DC operating point overlay visibility."""
        self._schematic_scene.show_dc_overlay = checked

    def _on_toggle_minimap(self, checked: bool) -> None:
        """Toggle minimap visibility, respecting the welcome empty state."""
        self._minimap.setVisible(checked and not self._is_canvas_empty())

    def _is_canvas_empty(self) -> bool:
        """Return whether the current schematic has no components or wires."""
        try:
            circuit = self._current_circuit()
        except Exception:
            return False
        return not circuit.components and not circuit.wires

    def _position_minimap(self) -> None:
        """Anchor the minimap to the bottom-right corner of the schematic view."""
        view = getattr(self, "_schematic_view", None)
        minimap = getattr(self, "_minimap", None)
        if view is None or minimap is None:
            return
        margin = 12
        x = max(0, view.width() - minimap.width() - margin)
        y = max(0, view.height() - minimap.height() - margin)
        minimap.move(x, y)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt override
        # Keep the minimap pinned to the bottom-right on schematic resize.
        if obj is getattr(self, "_schematic_view", None) and event.type() == QEvent.Type.Resize:
            self._position_minimap()
        return super().eventFilter(obj, event)

    def _schedule_minimap_update(self) -> None:
        """Schedule a throttled minimap update."""
        if not self._minimap_update_timer.isActive():
            self._minimap_update_timer.start()

    def _on_preferences(self) -> None:
        """Show preferences dialog."""
        dialog = PreferencesDialog(self._settings, self._simulation_service, self)
        if dialog.exec():
            # Apply settings that may have changed
            self._apply_theme()
            self._schematic_scene.grid_size = self._settings.get_grid_size()
            self._schematic_scene.show_grid = self._settings.get_show_grid()
            self.action_toggle_grid.setChecked(self._settings.get_show_grid())
            self._update_autosave_timer()

    def _on_keyboard_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog."""
        dialog = KeyboardShortcutsDialog(self._shortcut_service, self)
        dialog.exec()

    def _on_library_component_selected(self, comp_type) -> None:
        """Handle component selection from library (double-click to add)."""
        from pulsimgui.models.component import Component

        # Create new component at center of view
        view_center = self._schematic_view.mapToScene(
            self._schematic_view.viewport().rect().center()
        )

        # Snap to grid
        x = self._schematic_scene.snap_to_grid(view_center).x()
        y = self._schematic_scene.snap_to_grid(view_center).y()

        # Generate unique name
        name = self._generate_component_name(comp_type)

        # Create component
        component = Component(type=comp_type, name=name, x=x, y=y)

        # Add to circuit through command stack
        self._execute_schematic_command(
            AddComponentCommand(self._current_circuit(), component),
            refresh_scene=True,
            merge=False,
        )

        # Update library recent list
        self._library_panel.add_to_recent(comp_type)

    def _on_component_dropped(self, comp_type_name: str, x: float, y: float) -> None:
        """Handle component drop from library panel."""
        from pulsimgui.models.component import Component, ComponentType

        # Convert type name to ComponentType enum
        try:
            comp_type = ComponentType[comp_type_name]
        except KeyError:
            return

        # Generate unique name
        name = self._generate_component_name(comp_type)

        # Create component at drop position
        component = Component(type=comp_type, name=name, x=x, y=y)

        # Add to circuit through command stack
        self._execute_schematic_command(
            AddComponentCommand(self._current_circuit(), component),
            refresh_scene=True,
            merge=False,
        )

        # Update library recent list
        self._library_panel.add_to_recent(comp_type)

    def _on_component_pasted(self, component) -> None:
        """Add a clipboard-pasted component (built by the view, with its
        edited properties intact) to the active circuit through the undo
        stack, so it persists and is part of the model — not a scene-only
        orphan."""
        self._execute_schematic_command(
            AddComponentCommand(self._current_circuit(), component),
            refresh_scene=True,
            merge=False,
        )

    def _on_selection_pasted(self, components, wires) -> None:
        """Add a pasted/duplicated SELECTION (components + their internal
        wires, already re-id'd and shifted by the view) to the active circuit
        as ONE undoable step."""
        from pulsimgui.commands.base import CompositeCommand

        circuit = self._current_circuit()
        commands = [AddComponentCommand(circuit, c) for c in components]
        commands += [AddWireCommand(circuit, w) for w in wires]
        if not commands:
            return
        label = (f"Paste {len(components)} component(s)"
                 + (f" + {len(wires)} wire(s)" if wires else ""))
        self._execute_schematic_command(
            CompositeCommand(commands, label),
            refresh_scene=True,
            merge=False,
        )

    def _on_component_removed(self, component) -> None:
        """Tear down scope window state when a component disappears."""
        comp_id = str(component.id)
        window = self._scope_windows.pop(comp_id, None)
        if window is not None:
            window.close()
        # If we're editing inside a subcircuit, removing any component
        # (including a SUBCIRCUIT_PORT marker) can shift the port list.
        # Re-sync so the outer symbol stays consistent.
        self._sync_subcircuit_ports_if_editing()

    def _on_component_added_for_port_sync(self, _component) -> None:
        """Re-sync subcircuit port markers when a component lands in
        the body. No-op at root."""
        self._sync_subcircuit_ports_if_editing()

    def _on_wire_added_for_port_sync(self, _wire) -> None:
        """Re-sync subcircuit port markers when a wire changes the
        internal connectivity (which net the marker pin sits on)."""
        self._sync_subcircuit_ports_if_editing()

    def _sync_subcircuit_ports_if_editing(self) -> None:
        """If the user is currently editing the body of a subcircuit
        definition, rebuild ``definition.ports`` from any
        SUBCIRCUIT_PORT markers inside, then propagate the new pin
        layout to every instance of this definition in the project.

        Cheap no-op when at root (most common case).
        """
        from pulsimgui.models.subcircuit import (
            refresh_subcircuit_instance_pins,
            sync_definition_ports_from_markers,
        )

        definition = self._hierarchy_service.get_current_definition()
        if definition is None:
            return

        changed = sync_definition_ports_from_markers(definition)
        if not changed:
            return

        # Mirror the new pin list onto every instance pointing at us.
        refresh_subcircuit_instance_pins(self._project, definition)

        # If the parent circuit happens to be visible elsewhere
        # (e.g. a backed-up scene), force-redraw the current scene so
        # users see the marker name update on the inner schematic.
        self._schematic_scene.update()

    def _on_component_delete_requested(self, component_id: str) -> None:
        """Delete a component via command stack."""
        try:
            comp_uuid = UUID(component_id)
        except ValueError:
            return

        circuit = self._current_circuit()
        component = circuit.get_component(comp_uuid)
        if component is None:
            return

        self._execute_schematic_command(
            DeleteComponentCommand(circuit, comp_uuid),
            refresh_scene=True,
            merge=False,
        )
        self._on_component_removed(component)

    def _on_wire_delete_requested(self, wire_id: str) -> None:
        """Delete a wire via command stack."""
        try:
            wire_uuid = UUID(wire_id)
        except ValueError:
            return

        circuit = self._current_circuit()
        if circuit.get_wire(wire_uuid) is None:
            return

        self._execute_schematic_command(
            DeleteWireCommand(circuit, wire_uuid),
            refresh_scene=True,
            merge=False,
        )

    def _on_component_rotate_requested(self, component_id: str, degrees: int) -> None:
        """Rotate a component via command stack."""
        try:
            comp_uuid = UUID(component_id)
        except ValueError:
            return

        circuit = self._current_circuit()
        if circuit.get_component(comp_uuid) is None:
            return

        selected_component_ids = self._selected_component_ids()
        if comp_uuid not in selected_component_ids:
            selected_component_ids.append(comp_uuid)

        self._execute_schematic_command(
            RotateComponentCommand(circuit, comp_uuid, degrees=int(degrees)),
            refresh_scene=True,
            merge=False,
        )
        self._restore_component_selection(selected_component_ids)

    def _selected_component_ids(self) -> list[UUID]:
        """Return UUIDs of currently selected components in the schematic scene."""
        from pulsimgui.views.schematic.items import ComponentItem

        selected_ids: list[UUID] = []
        for item in self._schematic_scene.selectedItems():
            if isinstance(item, ComponentItem):
                selected_ids.append(item.component.id)
        return selected_ids

    def _restore_component_selection(self, component_ids: list[UUID]) -> None:
        """Restore selection by component UUIDs after scene reloads."""
        if not component_ids:
            return

        from pulsimgui.views.schematic.items import ComponentItem

        wanted = {str(comp_id) for comp_id in component_ids}
        self._schematic_scene.clearSelection()
        for item in self._schematic_scene.items():
            if isinstance(item, ComponentItem) and str(item.component.id) in wanted:
                item.setSelected(True)

    def _rotate_selected_components(self, degrees: int) -> None:
        """Rotate selected components from toolbar actions."""
        if self._has_text_input_focus():
            return

        from pulsimgui.views.schematic.items import ComponentItem

        selected_items = self._schematic_scene.selectedItems()
        selected_ids = [
            str(item.component.id) for item in selected_items if isinstance(item, ComponentItem)
        ]
        if not selected_ids:
            return

        # Reuse the same command path used by spacebar/context-menu rotation.
        for component_id in selected_ids:
            self._on_component_rotate_requested(component_id, int(degrees))

    def _on_component_flip_requested(self, component_id: str, horizontal: bool) -> None:
        """Flip a component via command stack."""
        try:
            comp_uuid = UUID(component_id)
        except ValueError:
            return

        circuit = self._current_circuit()
        if circuit.get_component(comp_uuid) is None:
            return

        self._execute_schematic_command(
            FlipComponentCommand(circuit, comp_uuid, horizontal=bool(horizontal)),
            refresh_scene=True,
            merge=False,
        )

    def _on_component_moved(
        self,
        component,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
    ) -> None:
        """Record drag movement as an undoable command."""
        if component is None:
            return
        if abs(new_x - old_x) < 0.01 and abs(new_y - old_y) < 0.01:
            return

        self._execute_schematic_command(
            MoveComponentCommand(
                self._current_circuit(),
                component.id,
                new_x,
                new_y,
                old_x=old_x,
                old_y=old_y,
                already_applied=True,
            ),
            refresh_scene=False,
            merge=False,
        )

    def _on_wire_created(self, segments: list) -> None:
        """Handle wire creation from schematic view."""
        from PySide6.QtCore import QPointF

        from pulsimgui.models.wire import Wire, WireConnection, WireSegment

        if not segments:
            return

        # Create wire model
        wire_segments = [
            WireSegment(x1=seg[0], y1=seg[1], x2=seg[2], y2=seg[3])
            for seg in segments
        ]
        wire = Wire(segments=wire_segments)

        start_pos = QPointF(wire_segments[0].x1, wire_segments[0].y1)
        end_pos = QPointF(wire_segments[-1].x2, wire_segments[-1].y2)
        start_pin = self._schematic_scene.find_nearest_pin(
            start_pos,
            max_distance=self._schematic_scene.PIN_CAPTURE_DISTANCE,
        )
        end_pin = self._schematic_scene.find_nearest_pin(
            end_pos,
            max_distance=self._schematic_scene.PIN_CAPTURE_DISTANCE,
        )

        # Force endpoint coordinates to land exactly on detected pin centers.
        if start_pin is not None:
            pin_pos = start_pin[0]
            wire_segments[0].x1 = pin_pos.x()
            wire_segments[0].y1 = pin_pos.y()
        if end_pin is not None:
            pin_pos = end_pin[0]
            wire_segments[-1].x2 = pin_pos.x()
            wire_segments[-1].y2 = pin_pos.y()

        start_ref = (start_pin[1].component, start_pin[2]) if start_pin is not None else None
        end_ref = (end_pin[1].component, end_pin[2]) if end_pin is not None else None
        start_pos = QPointF(wire_segments[0].x1, wire_segments[0].y1)
        end_pos = QPointF(wire_segments[-1].x2, wire_segments[-1].y2)
        if not self._is_valid_wire_measurement_connection(
            start_ref,
            end_ref,
            start_pos=start_pos,
            end_pos=end_pos,
        ):
            self.statusBar().showMessage(
                "Invalid connection: domains cannot mix (circuit/signal/thermal). "
                "Electrical Scope accepts signal outputs (including control blocks and probe outputs); "
                "Thermal Scope only accepts TH outputs.",
                5000,
            )
            return

        if start_ref is not None:
            wire.start_connection = WireConnection(
                component_id=start_ref[0].id,
                pin_index=start_ref[1],
            )
        if end_ref is not None:
            wire.end_connection = WireConnection(
                component_id=end_ref[0].id,
                pin_index=end_ref[1],
            )

        if not self._schematic_scene.is_wire_path_clear(wire_segments):
            self.statusBar().showMessage(
                "Invalid route: wires cannot pass through component bodies.",
                5000,
            )
            return

        self._execute_schematic_command(
            AddWireCommand(self._current_circuit(), wire),
            refresh_scene=True,
            merge=False,
        )

    def _is_valid_wire_measurement_connection(
        self,
        start_ref,
        end_ref,
        *,
        start_pos=None,
        end_pos=None,
    ) -> bool:
        """Validate dedicated scope/probe/thermal endpoint compatibility."""
        if start_ref is not None and end_ref is not None:
            left_component, left_pin = start_ref
            right_component, right_pin = end_ref
            if not can_connect_measurement_pins(
                left_component,
                left_pin,
                right_component,
                right_pin,
            ):
                return False
            # Never allow mixing circuit/signal/thermal domains on a direct wire connection.
            left_domain = pin_connection_domain(left_component, left_pin)
            right_domain = pin_connection_domain(right_component, right_pin)
            if left_domain == right_domain:
                return True
            return CONNECTION_DOMAIN_ANY in {left_domain, right_domain}

        endpoint_checks = (
            (start_ref, end_pos),
            (end_ref, start_pos),
        )
        for ref, opposite_pos in endpoint_checks:
            if ref is None:
                continue
            component, pin_index = ref
            if is_restricted_measurement_pin(component, pin_index):
                if opposite_pos is None:
                    return False
                required_domain = pin_connection_domain(component, pin_index)
                if not self._point_touches_wire_domain(opposite_pos, required_domain):
                    return False
        return True

    def _point_touches_wire_domain(self, point, required_domain: str) -> bool:
        """Return True when a point lands on an existing wire of the given domain."""
        circuit = self._current_circuit()
        if circuit is None:
            return False

        expected = (
            CONNECTION_DOMAIN_CIRCUIT
            if required_domain == CONNECTION_DOMAIN_ANY
            else required_domain
        )
        px = float(point.x())
        py = float(point.y())
        for wire in circuit.wires.values():
            wire_domain = self._resolve_wire_domain(wire, circuit)
            if wire_domain != expected and CONNECTION_DOMAIN_ANY not in {wire_domain, expected}:
                continue
            for segment in wire.segments:
                if self._point_on_wire_segment(px, py, segment, tolerance=1.0):
                    return True
        return False

    def _resolve_wire_domain(self, wire, circuit: Circuit) -> str:
        """Resolve wire domain using endpoint metadata with geometry fallback."""
        domains: set[str] = set()
        for connection in (wire.start_connection, wire.end_connection):
            if connection is None:
                continue
            component = circuit.components.get(connection.component_id)
            if component is None:
                continue
            pin_index = connection.pin_index
            if pin_index < 0 or pin_index >= len(component.pins):
                continue
            domains.add(pin_connection_domain(component, pin_index))

        # Backward compatibility for wires without endpoint metadata.
        if not domains:
            points: list[tuple[float, float]] = []
            for segment in wire.segments:
                points.append((segment.x1, segment.y1))
                points.append((segment.x2, segment.y2))
            points.extend(wire.junctions or [])

            for component in circuit.components.values():
                for pin_index in range(len(component.pins)):
                    pin_x, pin_y = component.get_pin_position(pin_index)
                    for px, py in points:
                        if abs(pin_x - px) < 5.0 and abs(pin_y - py) < 5.0:
                            domains.add(pin_connection_domain(component, pin_index))
                            break

        effective_domains = {domain for domain in domains if domain != CONNECTION_DOMAIN_ANY}
        if CONNECTION_DOMAIN_THERMAL in effective_domains:
            return CONNECTION_DOMAIN_THERMAL
        if CONNECTION_DOMAIN_SIGNAL in effective_domains:
            return CONNECTION_DOMAIN_SIGNAL
        return CONNECTION_DOMAIN_CIRCUIT

    @staticmethod
    def _point_on_wire_segment(px: float, py: float, segment, tolerance: float = 1.0) -> bool:
        """Return True when a point lies on a wire segment within tolerance."""
        x1, y1, x2, y2 = float(segment.x1), float(segment.y1), float(segment.x2), float(segment.y2)

        if abs(y1 - y2) <= tolerance:
            min_x, max_x = sorted((x1, x2))
            return abs(py - y1) <= tolerance and (min_x - tolerance) <= px <= (max_x + tolerance)

        if abs(x1 - x2) <= tolerance:
            min_y, max_y = sorted((y1, y2))
            return abs(px - x1) <= tolerance and (min_y - tolerance) <= py <= (max_y + tolerance)

        seg_dx = x2 - x1
        seg_dy = y2 - y1
        seg_len_sq = (seg_dx * seg_dx) + (seg_dy * seg_dy)
        if seg_len_sq <= 1e-12:
            return abs(px - x1) <= tolerance and abs(py - y1) <= tolerance

        t = ((px - x1) * seg_dx + (py - y1) * seg_dy) / seg_len_sq
        if t < 0.0 or t > 1.0:
            return False
        closest_x = x1 + (t * seg_dx)
        closest_y = y1 + (t * seg_dy)
        return abs(px - closest_x) <= tolerance and abs(py - closest_y) <= tolerance

    def _on_wire_alias_changed(self, wire) -> None:
        """Update project state when a wire alias is renamed."""
        self._project.mark_dirty()
        self._update_modified_indicator()
        self._refresh_scope_window_bindings()

    def _on_rename_signal(self) -> None:
        """Rename selected wire alias."""
        if self._schematic_view.rename_selected_wire():
            return
        self.statusBar().showMessage("Select a wire to rename.", 3000)

    def _on_scope_open_requested(self, component) -> None:
        """Open (or focus) the scope_v2 window for the requested component."""
        if component is None:
            return
        self._open_scope_window(component)

    def _open_scope_window(self, component) -> None:
        """Open the modular scope_v2 ``BaseScopeWindow`` for ``component``.

        Resolves the wired-up probe channels via
        :func:`resolve_scope_signal_specs`, builds the live + post-sim
        capabilities, and instantiates the variant matching the scope
        component's type (electrical / thermal). Re-opening the same
        component focuses the existing window instead of duplicating.
        """
        from pulsimgui.models.component import ComponentType
        from pulsimgui.views.scope_v2 import (
            CursorsCapability,
            ExportCapability,
            FFTCapability,
            LiveStreamCapability,
            MathSignalsCapability,
            MeasurementsCapability,
            PostSimCapability,
            SMPSMacrosCapability,
            TriggerCapability,
        )
        from pulsimgui.views.scope_v2.resolver import resolve_scope_signal_specs
        from pulsimgui.views.scope_v2.variants import (
            ElectricalScopeVariant,
            ThermalScopeVariant,
        )

        comp_id = str(component.id)
        existing = self._scope_windows.get(comp_id)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return

        circuit = self._current_circuit()
        live_specs, post_specs = resolve_scope_signal_specs(
            component, circuit, self._simulation_service, self._project,
        )

        variant_cls = (
            ThermalScopeVariant
            if component.type == ComponentType.THERMAL_SCOPE
            else ElectricalScopeVariant
        )
        variant = variant_cls(name=f"Scope: {component.name}")

        try:
            from pulsimgui import __version__ as _pg_version
        except Exception:  # pragma: no cover
            _pg_version = ""

        capabilities: list = []
        if live_specs:
            capabilities.append(LiveStreamCapability(self._simulation_service, live_specs))
        if post_specs:
            # Feed PostSim the probe-enriched result, not the raw kernel
            # one — see ``electrical_result_ready`` on the class for why.
            capabilities.append(PostSimCapability(
                self._simulation_service,
                post_specs,
                result_signal=self.electrical_result_ready,
                result_getter=lambda: self._latest_electrical_result,
            ))
        capabilities.append(CursorsCapability())
        capabilities.append(MathSignalsCapability())
        # TriggerCapability disabled by request — barely used in
        # practice and was contributing visual clutter / theme stress
        # in the Inspector. Code is kept; re-enable by uncommenting.
        # capabilities.append(TriggerCapability())
        capabilities.append(SMPSMacrosCapability())
        capabilities.append(MeasurementsCapability())
        capabilities.append(ExportCapability())
        capabilities.append(FFTCapability())

        window = BaseScopeWindow(
            variant=variant,
            capabilities=capabilities,
            version=_pg_version,
            # Hand the host's ThemeService over so the scope picks up
            # the same theme as MainWindow (light ↔ dark) AND keeps
            # following along when the user switches in Preferences.
            theme_service=self._theme_service,
        )
        # The LiveStream capability needs the project reference so its
        # Run button can drive ``simulation_service.run_transient_project``.
        window._project = self._project
        window.closed.connect(lambda cid=comp_id: self._scope_windows.pop(cid, None))
        self._scope_windows[comp_id] = window
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_component_properties_requested(self, component) -> None:
        """Open modal component properties editor and apply on confirmation."""
        if component is None:
            return

        dialog = ComponentPropertiesDialog(
            component=component,
            theme_service=self._theme_service,
            parent=self,
        )
        accepted = bool(dialog.exec())
        pair_request = dialog.pair_navigation_request

        if not accepted:
            if pair_request is not None:
                self._on_properties_net_label_pair_requested(*pair_request)
            return

        old_state = self._component_state_snapshot(component)
        new_state = self._component_state_snapshot(dialog.edited_component)
        if old_state != new_state:
            self._execute_schematic_command(
                UpdateComponentStateCommand(
                    self._current_circuit(),
                    component.id,
                    new_state,
                    old_state=old_state,
                ),
                refresh_scene=True,
                merge=False,
            )
            self._refresh_scope_window_bindings()
            self.statusBar().showMessage("Component properties updated", 2000)

        if pair_request is not None:
            self._on_properties_net_label_pair_requested(*pair_request)

    def _on_properties_net_label_pair_requested(
        self,
        source_component_id: str,
        net_label: str,
    ) -> None:
        """Resolve a source label and trigger scene-level pair navigation."""
        try:
            source_uuid = UUID(source_component_id)
        except ValueError:
            return

        source_component = self._current_circuit().get_component(source_uuid)
        if source_component is None:
            label_text = net_label.strip() or "(unnamed)"
            self.statusBar().showMessage(
                f"Cannot locate source tag '{label_text}' in current circuit.",
                3000,
            )
            return

        self._schematic_scene.request_net_label_navigation(source_component)

    def _generate_component_name(self, comp_type) -> str:
        """Generate a unique component name."""
        from pulsimgui.models.component import ComponentType

        prefix_map = {
            ComponentType.RESISTOR: "R",
            ComponentType.CAPACITOR: "C",
            ComponentType.INDUCTOR: "L",
            ComponentType.VOLTAGE_SOURCE: "V",
            ComponentType.CURRENT_SOURCE: "I",
            ComponentType.GROUND: "GND",
            ComponentType.DIODE: "D",
            ComponentType.MOSFET_N: "M",
            ComponentType.MOSFET_P: "M",
            ComponentType.IGBT: "Q",
            ComponentType.SWITCH: "S",
            ComponentType.TRANSFORMER: "T",
            ComponentType.PWM_GENERATOR: "PWM",
            ComponentType.C_BLOCK: "CB",
            ComponentType.PI_CONTROLLER: "PI",
            ComponentType.GAIN: "K",
            ComponentType.SUM: "SUM",
            ComponentType.SUBTRACTOR: "SUB",
        }

        prefix = prefix_map.get(comp_type, "X")

        # Find next available number
        existing_names = {
            c.name for c in self._current_circuit().components.values()
        }
        num = 1
        while f"{prefix}{num}" in existing_names:
            num += 1

        return f"{prefix}{num}"

    def _on_property_changed(self, name: str, value) -> None:
        """Handle property change from properties panel."""
        from pulsimgui.views.schematic.items import ComponentItem

        # Get the component being edited from properties panel
        edited_component = self._properties_panel._component
        if edited_component is None:
            return

        old_state = self._component_state_cache.get(edited_component.id)
        new_state = self._component_state_snapshot(edited_component)

        if old_state is None:
            self._component_state_cache[edited_component.id] = new_state
        elif old_state != new_state:
            self._execute_schematic_command(
                UpdateComponentStateCommand(
                    self._current_circuit(),
                    edited_component.id,
                    new_state,
                    old_state=old_state,
                    already_applied=True,
                ),
                refresh_scene=False,
                merge=True,
            )

        # Find and update the corresponding component item in the scene
        for item in self._schematic_scene.items():
            if isinstance(item, ComponentItem) and item.component is edited_component:
                pin_layout_changed = name in {
                    THERMAL_PORT_PARAMETER,
                    "channel_count",
                    "input_count",
                    "output_count",
                    "n_inputs",
                    "n_outputs",
                    "signs",
                    # SUBCIRCUIT_PORT marker: ``side`` moves the pin to
                    # a different edge of the marker; ``port_name``
                    # rewrites the pin label. Both demand a geometry
                    # refresh + a definition re-sync so the parent
                    # symbol updates immediately.
                    "side",
                    "port_name",
                }
                if pin_layout_changed:
                    item.prepareGeometryChange()
                # When the edited component is a SUBCIRCUIT_PORT and
                # any of its identity-affecting params changed, push
                # the change through to the SubcircuitDefinition so
                # outer-symbol pins update without an explicit save.
                if name in {"port_name", "side", "direction"}:
                    from pulsimgui.models.component import ComponentType as _CT
                    if edited_component.type == _CT.SUBCIRCUIT_PORT:
                        # Re-run the model-level pin sync so the
                        # marker's own pin moves to the new ``side``
                        # / picks up the new ``port_name`` before we
                        # rebuild the definition's port list.
                        from pulsimgui.models.component import (
                            _synchronize_special_component,
                        )
                        _synchronize_special_component(edited_component)
                        self._sync_subcircuit_ports_if_editing()
                # Update position if changed
                if name == "position_x":
                    item.setPos(edited_component.x, edited_component.y)
                elif name == "position_y":
                    item.setPos(edited_component.x, edited_component.y)
                elif name == "rotation":
                    item.setRotation(edited_component.rotation)
                    item.update_transform()
                elif name == "mirror_h" or name == "mirror_v":
                    item.update_transform()
                elif pin_layout_changed:
                    self._schematic_scene.update_connected_wires(item)
                # Update name label
                item._name_label.setText(edited_component.name)
                # Update labels for parameter changes (value text)
                item._update_labels()
                item.update()
                break

        self._schematic_scene.update()
        self._refresh_scope_window_bindings()

    # ------------------------------------------------------------------
    # Scope window helpers
    # ------------------------------------------------------------------
    def _close_all_scope_windows(self, persist_state: bool = True) -> None:
        """Close every open scope_v2 window — used on project new/open/close."""
        del persist_state  # legacy kwarg retained for caller compatibility
        for window in list(self._scope_windows.values()):
            window.close()
        self._scope_windows.clear()

    def _refresh_scope_window_bindings(self) -> None:
        """Rebuild capabilities for every open scope after a schematic edit.

        When the user re-wires a probe to a scope on the canvas, the
        ``ScopeChannelBinding``s change. We rebuild the simplest way:
        close + reopen each open window so the resolver runs fresh.
        """
        if not self._scope_windows:
            return
        circuit = self._current_circuit()
        comp_ids = list(self._scope_windows.keys())
        for comp_id in comp_ids:
            component = self._get_component_by_id(comp_id, circuit)
            if component is None:
                window = self._scope_windows.pop(comp_id, None)
                if window is not None:
                    window.close()
                continue
            window = self._scope_windows.pop(comp_id, None)
            if window is not None:
                window.close()
            self._open_scope_window(component)


    def _get_component_by_id(self, component_id: str, circuit: Circuit | None = None):
        circuit = circuit or self._current_circuit()
        if circuit is None:
            return None
        try:
            comp_uuid = UUID(component_id)
        except (ValueError, TypeError):
            return None
        return circuit.components.get(comp_uuid)

    def _check_save(self) -> bool:
        """Check if user wants to save unsaved changes. Returns True if safe to proceed."""
        if not self._project.is_dirty:
            return True

        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Do you want to save changes to the current project?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if result == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._project.is_dirty
        elif result == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def _check_save_all(self) -> bool:
        """Prompt to save every dirty open document before a destructive
        action (window close). Returns False if the user cancels any
        prompt — the caller must abort. Each dirty document is surfaced
        first so the save dialog acts on the right project."""
        for i in range(len(self._documents)):
            if self._documents[i].project.is_dirty:
                self._switch_to_document(i)
                if not self._check_save():
                    return False
        return True

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        if not self._check_save_all():
            event.ignore()
            return

        # Stop any running simulation
        if self._simulation_service.is_running:
            self._simulation_service.stop()

        # Save window state
        self._settings.set_window_geometry(self.saveGeometry())
        self._settings.set_window_state(self.saveState())

        event.accept()

    # Simulation handlers
    # ------------------------------------------------------------------
    # P1.2 — Run Bar callbacks (delegate to the existing action handlers
    # so the run/pause/stop logic stays centralised in one place).
    # ------------------------------------------------------------------

    def _on_run_simulation(self) -> None:
        """Run transient simulation."""
        if not self._sim_progress_active:
            self._sim_progress_last_value = 0
            self._sim_progress.setRange(0, 100)
            self._sim_progress.setValue(0)
            self._sim_progress.setVisible(True)
        self._sim_status_widget.setStatus("Preparing simulation...", is_running=True)
        QApplication.processEvents()

        self._apply_project_simulation_settings_to_service()
        self._simulation_service.run_transient_project(self._project)

    def _on_stop_simulation(self) -> None:
        """Stop current simulation."""
        self._simulation_service.stop()

    def _on_pause_simulation(self) -> None:
        """Pause/Resume simulation."""
        if self._simulation_service.state == SimulationState.PAUSED:
            self._simulation_service.resume()
            self.action_pause.setText("&Pause")
        else:
            self._simulation_service.pause()
            self.action_pause.setText("&Resume")

    def _on_dc_analysis(self) -> None:
        """Run DC operating point analysis."""
        self._apply_project_simulation_settings_to_service()
        circuit_data = self._simulation_service.convert_gui_circuit(self._project)
        self._simulation_service.run_dc_operating_point(circuit_data)

    def _on_ac_analysis(self) -> None:
        """Run AC analysis."""
        has_frequency = self._simulation_service.has_capability("frequency_analysis")
        has_ac = self._simulation_service.has_capability("ac")
        if not has_frequency and not has_ac:
            QMessageBox.warning(
                self,
                "AC Analysis Unavailable",
                (
                    "The selected backend does not provide AC analysis.\n"
                    "Install/enable a backend version with AC support to run this analysis."
                ),
            )
            return
        self._apply_project_simulation_settings_to_service()
        circuit_data = self._simulation_service.convert_gui_circuit(self._project)

        ac_settings = ACSettings(
            f_start=max(1e-12, float(self._simulation_service.settings.ac_f_start)),
            f_stop=max(
                max(1e-12, float(self._simulation_service.settings.ac_f_start)) * (1.0 + 1e-12),
                float(self._simulation_service.settings.ac_f_stop),
            ),
            points_per_decade=max(1, int(self._simulation_service.settings.ac_points_per_decade)),
            anchor_mode=normalize_frequency_anchor_mode(
                self._simulation_service.settings.ac_anchor_mode
            ),
            sweep_scale=normalize_frequency_sweep_scale(
                self._simulation_service.settings.ac_sweep_scale
            ),
            injection_node=str(self._simulation_service.settings.ac_injection_node or ""),
            measurement_node=str(self._simulation_service.settings.ac_measurement_node or ""),
        )

        if has_frequency:
            self._simulation_service.run_frequency_analysis(circuit_data, ac_settings)
            return

        self._simulation_service.run_ac_analysis(
            circuit_data,
            ac_settings.f_start,
            ac_settings.f_stop,
            ac_settings.points_per_decade,
            ac_settings=ac_settings,
        )

    def _on_simulation_settings(self) -> None:
        """Show simulation settings dialog."""
        self._apply_project_simulation_settings_to_service()
        dialog = SimulationSettingsDialog(
            self._simulation_service.settings,
            backend_info=self._simulation_service.backend_info,
            backend_warning=self._simulation_service.backend_issue_message,
            theme=self._theme_service.current_theme,
            parent=self,
        )

        def apply_dialog_settings() -> None:
            self._simulation_service.settings = dialog.get_settings()
            self._apply_simulation_service_settings_to_project()
            self._sync_thermal_service_context()
            self._project.mark_dirty()
            self._update_title()
            self._update_modified_indicator()
            self._refresh_solver_pill()

        dialog.settings_applied.connect(apply_dialog_settings)

        if dialog.exec():
            apply_dialog_settings()

    # ------------------------------------------------------------------
    # P1.3 — Solver pill helpers
    # ------------------------------------------------------------------

    def _on_solver_pill_clicked(self) -> None:
        """Open the simulation-settings dialog (focused on the Solver tab if
        possible)."""
        self._on_simulation_settings()

    def _refresh_solver_pill(self) -> None:
        """Re-read the current solver triple from the simulation service and
        push it into the status-bar pill."""
        pill = getattr(self, "_solver_pill", None)
        if pill is None:
            return
        try:
            settings = self._simulation_service.settings
        except Exception:
            return
        integrator = str(getattr(settings, "integrator", "") or "—")
        # dt may be on settings.dt, settings.fixed_dt, or settings.timestep —
        # try in priority order without breaking on missing attributes.
        dt_value = None
        for attr in ("dt", "fixed_dt", "timestep"):
            value = getattr(settings, attr, None)
            if value not in (None, 0, 0.0):
                dt_value = float(value)
                break
        if dt_value is None:
            dt_text = ""
        elif dt_value >= 1.0:
            dt_text = f"{dt_value:g}s"
        elif dt_value >= 1e-3:
            dt_text = f"{dt_value * 1e3:g}ms"
        elif dt_value >= 1e-6:
            dt_text = f"{dt_value * 1e6:g}µs"
        else:
            dt_text = f"{dt_value * 1e9:g}ns"
        linear_solver = str(getattr(settings, "linear_solver", "") or "")
        adaptive = bool(getattr(settings, "adaptive_timestep", False))
        pill.set_solver(integrator, dt_text, linear_solver, adaptive)

    def _on_parameter_sweep(self) -> None:
        """Open the parameter sweep configuration dialog.

        Wave-4 sub-A 1.3: now dispatches on dialog.get_mode() so the
        Monte-Carlo tab can drive a different runner. Range mode keeps
        the existing pipeline byte-for-byte.
        """
        circuit = self._current_circuit()
        if not circuit.components:
            QMessageBox.information(
                self,
                "No Components",
                "Add at least one component with numeric parameters before running a sweep.",
            )
            return

        dialog = ParameterSweepDialog(circuit, self)
        if not dialog.exec():
            return

        mode = dialog.get_mode()
        if mode == ParameterSweepDialog.MODE_RANGE:
            sweep_settings = dialog.get_settings()
            if not sweep_settings:
                return
            self._apply_project_simulation_settings_to_service()
            circuit_data = self._simulation_service.convert_gui_circuit(self._project)
            self._simulation_service.run_parameter_sweep(circuit_data, sweep_settings)
            return

        # Monte-Carlo branch — wave-4 sub-A 1.3.
        mc_settings = dialog.get_monte_carlo_settings()
        if mc_settings is None:
            return
        ok, reason = mc_settings.is_runnable()
        if not ok:
            QMessageBox.warning(self, "Monte-Carlo configuration", reason)
            return
        # The runtime sweep wiring (build a circuit_factory off the
        # current project + dispatch through pulsim.sweep.run) is a
        # bigger integration than fits into 1.3; for this release the
        # dialog accepts the configuration and emits a deferred-info
        # toast so users discover the feature without us shipping a
        # half-broken pipeline. The synchronous runner is queued for
        # a follow-up commit.
        QMessageBox.information(
            self,
            "Monte-Carlo sweep queued",
            f"Captured {len(mc_settings.parameters)} parameter row(s) with "
            f"{mc_settings.n_samples} samples. The Monte-Carlo runner is "
            "available via the SimulationService API today; a built-in "
            "GUI runner ships in the next minor update.",
        )

    def _on_show_foster_fit(self) -> None:
        """Open the standalone Foster-fit dialog (pulsim 1.7+).

        The dialog is a pure datasheet → RC-stage converter; it has no
        dependency on the current schematic or simulation result, so
        it's safe to open at any time. The output is two
        comma-separated strings the user pastes into the selected
        component's ``thermal_rth_stages`` / ``thermal_cth_stages``
        fields.
        """
        from pulsimgui.views.dialogs.foster_fit_dialog import (
            FosterFitDialog,
        )
        dialog = FosterFitDialog(self)
        dialog.show()

    def _on_show_thermal_sizing(self) -> None:
        """Open the TIM + Convection sizing helper dialog (pulsim 1.7+).

        Non-modal sketchpad — does not touch the schematic. The user
        plays with TIM material / thickness / area to get an
        R_th_case_to_sink, and with sink area + airflow to get an
        R_th_sink_to_amb, then copies those values into the HEATSINK +
        device fields manually. The dialog has no Apply button: the
        decision of where to paste the answers belongs to the user.
        """
        from pulsimgui.views.dialogs.thermal_sizing_dialog import (
            ThermalSizingDialog,
        )
        dialog = ThermalSizingDialog(self)
        dialog.show()

    def _on_show_thermal_viewer(self) -> None:
        """Run backend thermal analysis and open the viewer dialog."""
        circuit = self._current_circuit()
        if not circuit or not circuit.components:
            QMessageBox.information(
                self,
                "No Components",
                "Add components to the schematic before opening the thermal viewer.",
            )
            return

        try:
            circuit_data = self._simulation_service.convert_gui_circuit(self._project)
            result = self._thermal_service.build_result(
                circuit,
                self._simulation_service.last_result,
                circuit_data=circuit_data,
            )
        except Exception as exc:  # pragma: no cover - defensive dialog
            QMessageBox.warning(
                self,
                "Thermal Viewer",
                f"Unable to generate thermal data:\n{exc}",
            )
            return

        if result.error_message:
            QMessageBox.warning(
                self,
                "Thermal Viewer",
                format_user_error(result.error_message,
                                  context="Thermal analysis"),
            )
            return

        dialog = ThermalViewerDialog(result, theme_service=self._theme_service, parent=self)
        dialog.exec()

    def _on_show_losses_dashboard(self) -> None:
        """Open the per-device losses & efficiency dashboard.

        Wave-4 sub-A 1.4: reads the loss breakdown from the latest
        ``ThermalResult`` produced via the existing thermal service.
        Renders an empty-state when no telemetry is available, so the
        action is always reachable.
        """
        from pulsimgui.views.dialogs.losses_dashboard_dialog import (
            LossesDashboardDialog,
        )

        result = None
        circuit = self._current_circuit()
        if (
            circuit is not None
            and circuit.components
            and self._simulation_service.last_result is not None
        ):
            try:
                circuit_data = self._simulation_service.convert_gui_circuit(self._project)
                result = self._thermal_service.build_result(
                    circuit,
                    self._simulation_service.last_result,
                    circuit_data=circuit_data,
                )
            except Exception:  # pragma: no cover - defensive
                result = None

        dialog = LossesDashboardDialog(result, parent=self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Wave-4 sub-B analysis-mode handlers
    # ------------------------------------------------------------------
    def _on_show_fra(self) -> None:
        """Open the Frequency Response Analysis dialog (wave-4 sub-B 2.1)."""
        if not self._guard_analysis_action("fra", "FRA"):
            return
        from pulsimgui.views.dialogs.analysis_modes_dialogs import FraDialog

        FraDialog(self._simulation_service, self._project, parent=self).exec()

    def _on_steady_state_check(self) -> None:
        """Post-processing steady-state check on the LAST transient result:
        slice into fundamental cycles, report cycle-to-cycle residuals and a
        converged/not-converged verdict (always available — no backend
        capability needed)."""
        result = self._latest_electrical_result
        if result is None or not getattr(result, "time", None):
            QMessageBox.information(
                self, "Steady-State Check",
                "Run a transient simulation first — the check post-processes "
                "the captured waveforms.")
            return
        from pulsimgui.views.dialogs.steady_state_dialog import (
            SteadyStateDialog,
        )

        # Pre-fill the fundamental from the slowest source in the circuit.
        freq = 50.0
        circuit = self._current_circuit()
        if circuit is not None:
            freqs = []
            for comp in circuit.components.values():
                params = getattr(comp, "parameters", {}) or {}
                wf = params.get("waveform")
                if isinstance(wf, dict) and wf.get("frequency"):
                    try:
                        f = float(wf["frequency"])
                        if f > 0:
                            freqs.append(f)
                    except (TypeError, ValueError):
                        pass
                for key in ("frequency", "f_out", "m3c_f_out"):
                    try:
                        f = float(params.get(key) or 0)
                        if f > 0:
                            freqs.append(f)
                    except (TypeError, ValueError):
                        pass
            if freqs:
                freq = min(freqs)

        SteadyStateDialog(
            result.time, dict(result.signals or {}),
            parent=self, default_frequency=freq,
        ).exec()

    def _on_show_periodic_ss(self) -> None:
        """Open the Periodic Steady-State dialog (wave-4 sub-B 2.2)."""
        if not self._guard_analysis_action(
            "periodic_steady_state", "Periodic Steady-State"
        ):
            return
        from pulsimgui.views.dialogs.analysis_modes_dialogs import (
            PeriodicSteadyStateDialog,
        )

        PeriodicSteadyStateDialog(
            self._simulation_service, self._project, parent=self
        ).exec()

    def _on_show_harmonic_balance(self) -> None:
        """Open the Harmonic Balance dialog (wave-4 sub-B 2.3)."""
        if not self._guard_analysis_action("harmonic_balance", "Harmonic Balance"):
            return
        from pulsimgui.views.dialogs.analysis_modes_dialogs import (
            HarmonicBalanceDialog,
        )

        HarmonicBalanceDialog(
            self._simulation_service, self._project, parent=self
        ).exec()

    def _guard_analysis_action(self, capability: str, label: str) -> bool:
        """Common guard for the new sub-B analysis menu actions."""
        if self._project is None:
            QMessageBox.warning(
                self, "No project", f"Open or create a project before running {label}."
            )
            return False
        circuit = self._current_circuit()
        if circuit is None or not circuit.components:
            QMessageBox.information(
                self,
                "No components",
                f"Add components to the schematic before running {label}.",
            )
            return False
        if not self._simulation_service.has_capability(capability):
            QMessageBox.warning(
                self,
                f"{label} unavailable",
                f"The active simulation backend does not support {label}. "
                "Upgrade Pulsim to 0.9.0 or newer.",
            )
            return False
        return True

    def _on_simulation_state_changed(self, state: SimulationState) -> None:
        """Handle simulation state change."""
        is_running = state in (SimulationState.RUNNING, SimulationState.PAUSED)

        if is_running and not self._sim_progress_active:
            self._sim_progress_last_value = 0
            self._sim_progress.setRange(0, 100)
            self._sim_progress.setValue(0)
        elif not is_running and self._sim_progress_active:
            self._sim_progress.setRange(0, 100)
            if state == SimulationState.COMPLETED:
                self._sim_progress_last_value = 100
                self._sim_progress.setValue(100)
            else:
                self._sim_progress_last_value = 0
                self._sim_progress.setValue(0)
        self._sim_progress_active = is_running

        self._update_simulation_actions()
        self._sim_progress.setVisible(is_running)

        if not self._simulation_service.is_backend_ready:
            warning = (
                self._simulation_service.backend_issue_message
                or "Simulation backend unavailable."
            )
            self._sim_status_widget.setStatus(f"Backend unavailable: {warning}", is_error=True)
            return

        if state == SimulationState.IDLE:
            self._sim_status_widget.setStatus("Ready")
        elif state == SimulationState.RUNNING:
            self._sim_status_widget.setStatus("Running...", is_running=True)
        elif state == SimulationState.PAUSED:
            self._sim_status_widget.setStatus("Paused")
        elif state == SimulationState.COMPLETED:
            self._sim_status_widget.setStatus("Completed")
        elif state == SimulationState.CANCELLED:
            self._sim_status_widget.setStatus("Cancelled")
        elif state == SimulationState.ERROR:
            self._sim_status_widget.setStatus("Error", is_error=True)

    def _on_simulation_progress(self, value: float, message: str) -> None:
        """Handle simulation progress update."""
        if not math.isfinite(value):
            return

        if self._sim_progress.minimum() != 0 or self._sim_progress.maximum() != 100:
            self._sim_progress.setRange(0, 100)

        lowered_message = str(message or "").strip().lower()
        retrying_convergence = "retrying convergence with profile" in lowered_message
        if retrying_convergence:
            # Each retry starts a new attempt; reset local monotonic baseline so
            # progress can move again from low values instead of appearing stuck.
            self._sim_progress_last_value = 0

        if value < 0:
            # Keep the last known determinate value for indeterminate callbacks.
            clamped = self._sim_progress_last_value
        else:
            clamped = max(0, min(100, int(value)))

        if clamped < self._sim_progress_last_value and not retrying_convergence:
            clamped = self._sim_progress_last_value

        if clamped != self._sim_progress.value():
            self._sim_progress.setValue(clamped)
        self._sim_progress_last_value = clamped

        if message and message != self._sim_status_widget.text():
            self._sim_status_widget.setStatus(message, is_running=True)

    def _on_simulation_data_point(self, time: float, signals: dict) -> None:
        """Handle streaming data point during simulation."""
        # Keep streaming data in the dock viewer without forcing it open.
        self._waveform_viewer.add_data_point(time, signals)

    def _on_live_stream_ready(self, _stream) -> None:
        """No-op — scope_v2's ``LiveStreamCapability`` subscribes directly.

        The signal stays connected so older code paths (e.g. analytics
        that hook into ``live_stream_ready``) keep functioning; routing
        is done by each open ``BaseScopeWindow``'s ``LiveStreamCapability``.
        """

    def _on_post_processing_requested(self, jobs: list[dict]) -> None:
        """Run waveform post-processing for the latest electrical result."""
        source = self._latest_electrical_result or self._simulation_service.last_result
        self._simulation_service.run_post_processing(jobs, source_result=source)

    def _on_simulation_finished(self, result) -> None:
        """Handle simulation completion."""
        pill = getattr(self, "_solver_pill", None)
        # scope_v2's PostSimCapability replaces streamed data with the
        # full result inside each open scope window — nothing extra to
        # do here for live → finalized transitions.
        if result.is_valid:
            # Finalize streaming in the dock viewer.
            self._waveform_viewer.finalize_streaming(result)

            self.statusBar().showMessage(
                f"Simulation complete: {len(result.time)} points, "
                f"{len(result.signals)} signals",
                5000,
            )
            self._latest_electrical_result = self._result_with_probe_signals(result)
            # Push the *enriched* result through to any open scope_v2
            # windows — they need the ``VP(name)`` / ``IP(name)`` /
            # ``PP(name)`` synthetic channels to match their probe
            # ``signal_key`` lookups. The raw ``simulation_finished``
            # signal that scope_v2's PostSimCapability used to listen
            # to carries only the kernel-native keys and produced
            # "0 of N signals matched" in the drawer.
            self.electrical_result_ready.emit(self._latest_electrical_result)
            # P1.3 — surface convergence health on the solver pill.
            if pill is not None:
                stats = getattr(result, "statistics", {}) or {}
                retries = (
                    stats.get("timestep_retries")
                    or stats.get("fallback_steps")
                    or stats.get("recovery_steps")
                    or 0
                )
                state = pill.STATE_SUCCESS if not retries else pill.STATE_RECOVERED
                pill.set_state(state)
        else:
            QMessageBox.warning(
                self, "Simulation Error",
                format_user_error(result.error_message, context="Simulation"),
            )
            self._latest_electrical_result = None
            if pill is not None:
                pill.set_state(pill.STATE_FAILED)

        # Intentionally do NOT call ``_refresh_scope_window_bindings``
        # here — that helper closes + reopens every scope window, which
        # is appropriate after a *schematic* edit (probe wiring changed)
        # but wasteful right after a run. The enriched-result signal
        # above already delivers fresh data to every open scope.

    def _result_with_probe_signals(self, result: SimulationResult) -> SimulationResult:
        """Build an enriched result view with probe-exported scope channels.

        The kernel emits node voltages under ``V(<wire-label>)`` keys
        (e.g. ``V(SW)``, ``V(VOUT)``) using the wire alias from the
        schematic — *not* the probe component name. So we resolve each
        probe to its connected node first, then look up the data by
        ``V(<node-label>)`` (with case variants) before falling back to
        the probe's own name.
        """
        circuit = self._current_circuit()
        if circuit is None or not result.time:
            return result

        enriched = SimulationResult(
            time=list(result.time),
            signals={name: list(values) for name, values in result.signals.items()},
            statistics=dict(result.statistics),
            error_message=result.error_message,
        )

        # Resolve the schematic topology once — used to find which node
        # each probe component is wired to and what alias the kernel
        # likely used for that node.
        node_map = build_node_map(circuit)
        alias_map = build_node_alias_map(circuit, node_map)

        for component in circuit.components.values():
            if component.type == ComponentType.VOLTAGE_PROBE:
                # Differential probe: 3 pins (+, -, OUT). Reported value
                # is V(+) − V(−), NOT just V(+). Without the subtraction
                # the probe reads whatever single-ended node potential
                # the kernel happened to assign — typically ~0 V when
                # one side floats — instead of the true differential
                # the user expects (e.g. ±325 V across an AC source).
                probe_name = component.name or "VoltageProbe"
                node_label_pos = self._probe_node_label(
                    component, node_map, alias_map, pin_index=0,
                )
                node_label_neg = self._probe_node_label(
                    component, node_map, alias_map, pin_index=1,
                )
                series_pos = MainWindow._probe_backend_series(
                    enriched,
                    probe_name,
                    str(component.id),
                    node_label=node_label_pos,
                    node_id=node_map.get((str(component.id), 0)),
                    kernel_prefix="V",
                )
                series_neg = MainWindow._probe_backend_series(
                    enriched,
                    probe_name,
                    str(component.id),
                    node_label=node_label_neg,
                    node_id=node_map.get((str(component.id), 1)),
                    kernel_prefix="V",
                )
                if series_pos is None:
                    continue
                # Subtract the negative-terminal voltage when we have it.
                # When the ``−`` pin sits on the kernel ground (node 0)
                # ``_probe_backend_series`` returns the constant-0 series
                # for ``V(0)``; subtracting it is a no-op, so the GND-
                # referenced case degrades into the legacy behaviour
                # without a special case.
                if series_neg is None:
                    diff = list(series_pos)
                else:
                    n = min(len(series_pos), len(series_neg))
                    diff = [
                        float(series_pos[idx]) - float(series_neg[idx])
                        for idx in range(n)
                    ]
                scale = float(component.parameters.get("scale", 1.0) or 1.0)
                samples = min(len(diff), len(enriched.time))
                enriched.signals[format_signal_key("VP", probe_name)] = [
                    diff[idx] * scale for idx in range(samples)
                ]
                continue

            if component.type == ComponentType.VOLTAGE_PROBE_GND:
                probe_name = component.name or "VoltageProbeGND"
                node_label = self._probe_node_label(
                    component, node_map, alias_map, pin_index=0,
                )
                backend_series = MainWindow._probe_backend_series(
                    enriched,
                    probe_name,
                    str(component.id),
                    node_label=node_label,
                    node_id=node_map.get((str(component.id), 0)),
                    kernel_prefix="V",
                )
                if backend_series is not None:
                    scale = float(component.parameters.get("scale", 1.0) or 1.0)
                    samples = min(len(backend_series), len(enriched.time))
                    enriched.signals[format_signal_key("VP", probe_name)] = [
                        backend_series[idx] * scale for idx in range(samples)
                    ]
                continue

            if component.type == ComponentType.CURRENT_PROBE:
                probe_name = component.name or "CurrentProbe"
                node_label = self._probe_node_label(
                    component, node_map, alias_map, pin_index=0,
                )
                backend_series = MainWindow._probe_backend_series(
                    enriched,
                    probe_name,
                    str(component.id),
                    node_label=node_label,
                    node_id=node_map.get((str(component.id), 0)),
                    kernel_prefix="I",
                )
                if backend_series is None:
                    continue
                scale = float(component.parameters.get("scale", 1.0) or 1.0)
                samples = min(len(backend_series), len(enriched.time))
                enriched.signals[format_signal_key("IP", probe_name)] = [
                    backend_series[idx] * scale for idx in range(samples)
                ]
                continue

            if component.type == ComponentType.POWER_PROBE:
                probe_name = component.name or "PowerProbe"
                node_label = self._probe_node_label(
                    component, node_map, alias_map, pin_index=0,
                )
                backend_series = MainWindow._probe_backend_series(
                    enriched,
                    probe_name,
                    str(component.id),
                    node_label=node_label,
                    node_id=node_map.get((str(component.id), 0)),
                    kernel_prefix="P",
                )
                if backend_series is None:
                    continue
                scale = float(component.parameters.get("scale", 1.0) or 1.0)
                samples = min(len(backend_series), len(enriched.time))
                enriched.signals[format_signal_key("PP", probe_name)] = [
                    backend_series[idx] * scale for idx in range(samples)
                ]

        return enriched

    @staticmethod
    def _probe_node_label(
        component,
        node_map: dict[tuple[str, int], str],
        alias_map: dict[str, str],
        *,
        pin_index: int = 0,
    ) -> str | None:
        """Return the wire-alias label for the node a probe pin connects to.

        Falls back to the raw node-id (e.g. ``"7"``) when the wire has no
        explicit alias — caller can still try ``V(7)`` style lookups.
        """
        node_id = node_map.get((str(component.id), pin_index))
        if not node_id:
            return None
        return alias_map.get(node_id) or node_id

    @staticmethod
    def _probe_backend_series(
        result: SimulationResult,
        component_name: str,
        component_id: str,
        *,
        node_label: str | None = None,
        node_id: str | None = None,
        kernel_prefix: str = "V",
    ) -> list[float] | None:
        """Resolve backend-native probe channel names to a signal series.

        Lookup chain, in order of preference:

        **Priority 1 — type-prefix-wrapped candidates** (unambiguous):
          * ``{kernel_prefix}({node_label})`` and case variants
          * ``{kernel_prefix}(N{node_id})``, ``{kernel_prefix}({node_id})``

          These keys are kernel-emitted with explicit V/I/Is wrappers
          that disambiguate voltage vs current at lookup time. A V
          probe wired to "N5" finds ``V(N5)`` here even when
          ``signals`` also contains a current series under "I_L"
          (collision with a misnamed probe — see priority 2 + guard).

        **Priority 2 — bare candidates** (potentially ambiguous,
        type-guarded):
          * ``component_name`` (e.g. ``"Xsw"`` for a probe the kernel
            registered by its component name)
          * ``component_id`` (UUID)
          * ``node_label`` and case variants
          * ``N{node_id}``, raw ``node_id``

          Each bare candidate is type-checked: if the SAME body also
          appears under the OPPOSITE kernel-prefix wrapping (e.g.
          looking up a V probe and finding both bare ``"I_L"`` AND
          ``"Is(I_L)"`` in signals), the bare match is rejected —
          the wrapped form is the canonical kernel emission and the
          bare collision is a probe-name vs kernel-key clash.

        **Priority 3 — fuzzy match** with the same type-guard:
          * Case-insensitive match against the body of any
            ``V(…)``/``I(…)``/``Is(…)`` key, skipping matches whose
            wrapper conflicts with ``kernel_prefix``.

        Catches:
          * Wire alias divergence (probe wired to "SW", kernel emits
            ``V(N7)`` — N7 = same node)
          * Kernel-side casing differences (``i_l`` vs ``I_L``)
          * Type-collision between probe component_name and a
            kernel-emitted current key with the same name (e.g. a
            VOLTAGE_PROBE the user named ``"I_L"`` while ``I_L`` is
            also the kernel's current-probe key on a different
            branch). The type-guard prevents the voltage probe from
            silently picking up the current series.
        """
        # Build the two priority groups separately so we try ALL
        # type-prefix-wrapped candidates before falling back to bare
        # name lookups (which can collide with the OTHER signal
        # type's keys when probes are misnamed).
        wrapped: list[str] = []
        bare: list[str] = [component_name, component_id]
        if node_label:
            label_variants = {
                node_label,
                node_label.upper(),
                node_label.lower(),
            }
            for variant in label_variants:
                wrapped.append(f"{kernel_prefix}({variant})")
                bare.append(variant)
        if node_id:
            nid = str(node_id)
            for variant in (f"N{nid}", nid):
                wrapped.append(f"{kernel_prefix}({variant})")
                bare.append(variant)

        # Wrappers a foreign type might use for the same body — keys
        # whose presence indicates that a bare name is actually a
        # current/voltage key from the opposite domain. For a V probe
        # we treat I( and Is( as foreign; for an I probe, V( is
        # foreign. POWER_PROBE ("P") doesn't share its namespace.
        foreign_wrappers = (
            ("I(", "Is(") if kernel_prefix == "V"
            else ("V(",) if kernel_prefix == "I"
            else ()
        )

        def _has_foreign_wrapping(name: str) -> bool:
            """True when ``signals`` contains ``{foreign_prefix}{name})``
            for any of the opposite-type wrappers. Indicates a name
            collision where the bare match would be the wrong domain."""
            return any(
                f"{prefix}{name})" in result.signals
                for prefix in foreign_wrappers
            )

        # Priority 1: type-prefix-wrapped (unambiguous).
        for key in wrapped:
            if key and key in result.signals:
                return list(result.signals[key])

        # Priority 2: bare candidates — but only when not a same-name
        # collision with the opposite type. The foreign-wrapping check
        # catches the "probe named like a current key, but voltage
        # was expected" case the way ex 20's VP(Vin) lookup was
        # silently flipping over.
        for key in bare:
            if not key:
                continue
            series = result.signals.get(key)
            if series is None:
                continue
            if _has_foreign_wrapping(str(key)):
                continue  # type collision — fall through to fuzzy.
            return list(series)

        # Priority 3: fuzzy match by name body, type-guarded.
        if component_name:
            needle = component_name.lower()
            for key, series in result.signals.items():
                key_str = str(key)
                # Bare same-name match — same guard as priority 2.
                if key_str.lower() == needle:
                    if _has_foreign_wrapping(key_str):
                        continue
                    return list(series)
                if "(" in key_str and key_str.endswith(")"):
                    # Skip wrapped keys whose prefix conflicts with
                    # the probe's expected kernel_prefix (a V probe
                    # should never accept ``I(...)`` or ``Is(...)``
                    # via fuzzy match).
                    prefix_end = key_str.index("(")
                    key_prefix = key_str[:prefix_end + 1]
                    if foreign_wrappers and key_prefix in foreign_wrappers:
                        continue
                    body = key_str[prefix_end + 1 : -1]
                    if body.lower() == needle:
                        return list(series)

        # Case-insensitive fuzzy sweep using the node label's body —
        # same type-guard as above.
        if node_label:
            needle = node_label.lower()
            for key, series in result.signals.items():
                key_str = str(key)
                if "(" in key_str and key_str.endswith(")"):
                    prefix_end = key_str.index("(")
                    key_prefix = key_str[:prefix_end + 1]
                    if foreign_wrappers and key_prefix in foreign_wrappers:
                        continue
                    body = key_str[prefix_end + 1 : -1]
                    if body.lower() == needle:
                        return list(series)

        # No match — emit a one-line warning with the probe name and
        # the available kernel signal keys (capped) so a confused user
        # can paste it in a bug report and we can extend the candidates
        # list rather than guessing. Using a print() so the message
        # appears in the same stream the user already monitors (the
        # ``Application Output`` panel attached to the launcher); the
        # GUI hasn't initialised a logger here historically.
        try:
            available = sorted(str(k) for k in result.signals.keys())[:30]
            print(
                f"[PulsimGUI] probe lookup failed — component_name={component_name!r} "
                f"node_label={node_label!r} node_id={node_id!r} "
                f"kernel_prefix={kernel_prefix!r}\n"
                f"             first kernel signal keys: {available}",
                flush=True,
            )
        except Exception:  # noqa: BLE001
            pass
        return None

    def _on_dc_finished(self, result) -> None:
        """Handle DC analysis completion."""
        if result.is_valid:
            # Update schematic with DC values and show overlay
            self._schematic_scene.set_dc_results(result)
            self.action_toggle_dc_overlay.setChecked(True)

            # Show results dialog
            dialog = DCResultsDialog(
                result,
                convergence_info=self._simulation_service.last_convergence_info,
                parent=self,
            )
            dialog.exec()
        else:
            QMessageBox.warning(
                self, "DC Analysis Error",
                format_user_error(result.error_message, context="DC analysis")
            )

    def _on_ac_finished(self, result) -> None:
        """Handle AC analysis completion."""
        if result.is_valid:
            # Show Bode plot dialog
            dialog = BodePlotDialog(result, self)
            dialog.exec()
        else:
            QMessageBox.warning(
                self, "AC Analysis Error",
                format_user_error(result.error_message, context="AC analysis")
            )

    def _on_frequency_analysis_finished(self, result) -> None:
        """Handle frequency-domain analysis completion."""
        if result.success and result.is_valid:
            dialog = BodePlotDialog(result, self)
            dialog.exec()
            return
        message = getattr(result, "diagnostic_message", "") or getattr(
            result,
            "diagnostic_code",
            "Frequency analysis failed.",
        )
        QMessageBox.warning(self, "Frequency Analysis Error", f"Analysis failed:\n{message}")

    def _on_parameter_sweep_finished(self, result: ParameterSweepResult) -> None:
        """Handle parameter sweep completion."""
        if not result.runs:
            QMessageBox.warning(
                self,
                "Parameter Sweep",
                "Parameter sweep did not produce any results.",
            )
            return

        dialog = ParameterSweepResultsDialog(result, self)
        dialog.exec()

    def _on_simulation_error(self, message: str) -> None:
        """Handle simulation error."""
        normalized = (message or "").strip()
        lowered = normalized.lower()

        if "cblockcompileerror" in lowered or "c-block compile" in lowered:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("C-Block Build Error")
            box.setText("C-Block compilation failed. Review compiler output in details.")
            box.setDetailedText(normalized)
            box.exec()
            return

        if "cblockabierror" in lowered or ("abi" in lowered and "c-block" in lowered):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("C-Block ABI Error")
            box.setText("C-Block ABI is incompatible or required symbols are missing.")
            box.setDetailedText(normalized)
            box.exec()
            return

        if "cblockruntimeerror" in lowered or "c-block runtime" in lowered:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("C-Block Runtime Error")
            box.setText("C-Block execution returned an error during transient simulation.")
            box.setDetailedText(normalized)
            box.exec()
            return

        QMessageBox.critical(self, "Simulation Error", normalized or "Unknown simulation error.")

    # Export handlers
    def _on_export_spice(self) -> None:
        """Export circuit to SPICE netlist."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export SPICE Netlist",
            self._settings.get_default_project_location(),
            "SPICE Netlist (*.sp *.cir);;All Files (*)",
        )
        if path:
            if not (path.endswith(".sp") or path.endswith(".cir")):
                path += ".sp"
            try:
                circuit = self._current_circuit()
                ExportService.export_spice_netlist(circuit, path)
                self.statusBar().showMessage(f"Exported SPICE netlist: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export SPICE netlist:\n{e}")

    def _on_export_json(self) -> None:
        """Export circuit to JSON netlist (Pulsim format)."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export JSON Netlist",
            self._settings.get_default_project_location(),
            "JSON Netlist (*.json);;All Files (*)",
        )
        if path:
            if not path.endswith(".json"):
                path += ".json"
            try:
                ExportService.export_json_netlist(self._project, path)
                self.statusBar().showMessage(f"Exported JSON netlist: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export JSON netlist:\n{e}")

    def _on_export_png(self) -> None:
        """Export schematic to PNG image."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Schematic as PNG",
            self._settings.get_default_project_location(),
            "PNG Image (*.png);;All Files (*)",
        )
        if path:
            if not path.endswith(".png"):
                path += ".png"
            try:
                ExportService.export_schematic_png(self._schematic_scene, path)
                self.statusBar().showMessage(f"Exported schematic: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export PNG:\n{e}")

    def _on_copy_schematic_to_clipboard(self) -> None:
        """Wave-2: render the current schematic and place it on the clipboard.

        Uses the same renderer as the PNG export path so the bytes the
        user pastes into a document match what they'd see saved as a
        file. No file is written; the QImage flows straight to the
        system clipboard as both image data and (where supported) a
        PNG-encoded mime payload.
        """
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            from PySide6.QtCore import QMimeData
            image = ExportService.render_schematic_image(
                self._schematic_scene, scale=2.0, padding=32,
            )
            clipboard = QApplication.clipboard()
            mime = QMimeData()
            mime.setImageData(image)
            # Also attach PNG bytes for apps that prefer mime image/png.
            buf = QByteArray()
            qbuf = QBuffer(buf)
            qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(qbuf, "PNG")
            qbuf.close()
            mime.setData("image/png", buf)
            clipboard.setMimeData(mime)
            self.statusBar().showMessage(
                "Schematic image copied to clipboard", 3000
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Copy Error", f"Failed to copy schematic image:\n{exc}"
            )

    def _on_export_svg(self) -> None:
        """Export schematic to SVG image."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Schematic as SVG",
            self._settings.get_default_project_location(),
            "SVG Image (*.svg);;All Files (*)",
        )
        if path:
            if not path.endswith(".svg"):
                path += ".svg"
            try:
                ExportService.export_schematic_svg(self._schematic_scene, path)
                self.statusBar().showMessage(f"Exported schematic: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export SVG:\n{e}")

    def _on_export_csv(self) -> None:
        """Export waveforms to CSV file."""
        result = self._simulation_service.last_result
        if result is None or not result.is_valid:
            QMessageBox.warning(
                self,
                "No Data",
                "No simulation results available to export.\n"
                "Run a simulation first.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Waveforms as CSV",
            self._settings.get_default_project_location(),
            "CSV File (*.csv);;All Files (*)",
        )
        if path:
            if not path.endswith(".csv"):
                path += ".csv"
            try:
                ExportService.export_waveforms_csv(result, path)
                self.statusBar().showMessage(f"Exported waveforms: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{e}")

    def _on_export_fmu(self) -> None:
        """Export the active circuit as a FMI 2.0 co-simulation FMU.

        Wave-4 sub-wave A: wraps :py:meth:`SimulationService.export_fmu`
        through :class:`FmuExportDialog`. The dialog itself surfaces
        validation + backend errors so this handler stays thin.
        """
        if self._project is None:
            QMessageBox.warning(
                self,
                "No project",
                "Open or create a project before exporting an FMU.",
            )
            return

        if not self._simulation_service.has_capability("fmu_export"):
            QMessageBox.warning(
                self,
                "FMU export unavailable",
                "The active simulation backend does not support FMU export. "
                "Upgrade Pulsim to 0.8.0 or newer (pip install -U pulsim).",
            )
            return

        # Collect node names users might want to expose. Best-effort —
        # the dialog handles the empty case gracefully.
        last_result = self._simulation_service.last_result
        node_names: list[str] = []
        if last_result is not None and last_result.signals:
            node_names = sorted(last_result.signals.keys())

        from pulsimgui.views.dialogs.fmu_export_dialog import FmuExportDialog

        dialog = FmuExportDialog(
            self._simulation_service,
            self._project,
            available_node_names=node_names,
            parent=self,
        )
        result = dialog.run()
        if result is not None:
            self.statusBar().showMessage(
                f"FMU exported: {result.path}", 5000
            )

    def _on_export_c99(self) -> None:
        """Generate deployable C99 controller code for the active project.

        Wave-4 sub-wave A: wraps :py:meth:`SimulationService.export_c99`
        through :class:`C99ExportDialog`.
        """
        if self._project is None:
            QMessageBox.warning(
                self,
                "No project",
                "Open or create a project before generating C99 code.",
            )
            return

        if not self._simulation_service.has_capability("c99_codegen"):
            QMessageBox.warning(
                self,
                "C99 codegen unavailable",
                "The active simulation backend does not support C99 codegen. "
                "Upgrade Pulsim to 0.8.0 or newer (pip install -U pulsim).",
            )
            return

        from pulsimgui.views.dialogs.c99_export_dialog import C99ExportDialog

        dialog = C99ExportDialog(
            self._simulation_service,
            self._project,
            parent=self,
        )
        result = dialog.run()
        if result is not None:
            self.statusBar().showMessage(
                f"C99 controller generated in: {result.out_dir}", 5000
            )
