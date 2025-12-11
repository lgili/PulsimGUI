"""Main application window."""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QDockWidget,
    QToolBar,
    QStatusBar,
    QLabel,
    QWidget,
    QVBoxLayout,
    QMessageBox,
    QFileDialog,
    QApplication,
    QMenu,
)

from pulsimgui.commands.base import CommandStack
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import ComponentType
from pulsimgui.models.project import Project
from pulsimgui.models.subcircuit import (
    SubcircuitInstance,
    create_subcircuit_from_selection,
    detect_boundary_ports,
)
from pulsimgui.services.settings_service import SettingsService
from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.simulation_service import (
    SimulationResult,
    SimulationService,
    SimulationState,
    ParameterSweepResult,
)
from pulsimgui.services.thermal_service import ThermalAnalysisService
from pulsimgui.services.theme_service import ThemeService, Theme
from pulsimgui.services.export_service import ExportService
from pulsimgui.services.shortcut_service import ShortcutService
from pulsimgui.services.hierarchy_service import HierarchyService
from pulsimgui.resources.icons import IconService
from pulsimgui.views.dialogs import (
    PreferencesDialog,
    SimulationSettingsDialog,
    DCResultsDialog,
    BodePlotDialog,
    KeyboardShortcutsDialog,
    TemplateDialog,
    CreateSubcircuitDialog,
    ParameterSweepDialog,
    ParameterSweepResultsDialog,
    ThermalViewerDialog,
)
from pulsimgui.services.template_service import TemplateService
from pulsimgui.views.library import LibraryPanel
from pulsimgui.views.properties import PropertiesPanel
from pulsimgui.views.schematic import SchematicScene, SchematicView
from pulsimgui.views.scope import ScopeWindow, build_scope_channel_bindings
from pulsimgui.views.waveform import WaveformViewer
from pulsimgui.views.widgets import HierarchyBar, MinimapOverlay


class MainWindow(QMainWindow):
    """Main application window with docking panels."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._settings = SettingsService()
        self._theme_service = ThemeService(parent=self)
        self._shortcut_service = ShortcutService(self._settings, parent=self)
        self._command_stack = CommandStack(parent=self)
        self._project = Project()
        self._hierarchy_service = HierarchyService(self._project, parent=self)
        self._simulation_service = SimulationService(settings_service=self._settings, parent=self)
        self._thermal_service = ThermalAnalysisService(parent=self)
        self._scope_windows: dict[str, ScopeWindow] = {}
        self._suppress_scope_state = False
        self._latest_electrical_result: SimulationResult | None = None
        self._latest_thermal_waveform: SimulationResult | None = None

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

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._hierarchy_bar)
        layout.addWidget(self._schematic_view)
        self.setCentralWidget(central)

        # Ensure scene reflects current hierarchy level
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()

        # Create minimap overlay in corner of schematic view
        self._minimap = MinimapOverlay(self._schematic_view)
        self._minimap.set_source_view(self._schematic_view)
        self._minimap.navigation_requested.connect(self._on_minimap_navigation)
        self._minimap.move(10, 10)  # Position in top-left corner
        self._minimap.raise_()
        self._minimap.hide()  # Hidden by default

        # Connect schematic signals
        self._schematic_view.zoom_changed.connect(self.update_zoom)
        self._schematic_view.zoom_changed.connect(lambda _: self._minimap.update_minimap())
        self._schematic_view.mouse_moved.connect(self.update_coordinates)
        self._schematic_view.component_dropped.connect(self._on_component_dropped)
        self._schematic_view.wire_created.connect(self._on_wire_created)
        self._schematic_view.grid_toggle_requested.connect(self._on_grid_toggle_from_view)
        self._schematic_view.subcircuit_open_requested.connect(self._on_subcircuit_open_requested)
        self._schematic_view.scope_open_requested.connect(self._on_scope_open_requested)
        self._schematic_view.wire_alias_changed.connect(self._on_wire_alias_changed)
        self._schematic_view.quick_add_component.connect(self._on_quick_add_component)
        self._schematic_scene.selection_changed_custom.connect(self.update_selection)
        self._schematic_scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._schematic_scene.component_removed.connect(self._on_component_removed)
        # Throttle minimap updates to avoid performance issues during rapid changes
        self._minimap_update_timer = QTimer(self)
        self._minimap_update_timer.setSingleShot(True)
        self._minimap_update_timer.setInterval(50)  # 50ms throttle
        self._minimap_update_timer.timeout.connect(self._minimap.update_minimap)
        self._schematic_scene.changed.connect(lambda _: self._schedule_minimap_update())
        self._hierarchy_bar.update_hierarchy(self._hierarchy_service.breadcrumb_path)

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

        self.action_create_subcircuit = QAction("Create &Subcircuit...", self)
        self.action_create_subcircuit.setEnabled(False)
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
        self.action_toggle_minimap.setChecked(False)  # Hidden by default
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
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_new_from_template)
        file_menu.addAction(self.action_open)
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._update_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_close)
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("&Export")
        export_menu.addAction(self.action_export_spice)
        export_menu.addAction(self.action_export_json)
        export_menu.addSeparator()
        export_menu.addAction(self.action_export_png)
        export_menu.addAction(self.action_export_svg)
        export_menu.addSeparator()
        export_menu.addAction(self.action_export_csv)
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
        edit_menu.addAction(self.action_create_subcircuit)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_preferences)
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
        # Theme menu hidden for now - focusing on polishing light theme first
        # view_menu.addSeparator()
        # theme_menu = view_menu.addMenu("&Theme")
        # theme_menu.addAction(self.action_theme_light)
        # theme_menu.addAction(self.action_theme_dark)
        # theme_menu.addAction(self.action_theme_modern_dark)

        # Simulation menu
        sim_menu = menubar.addMenu("&Simulation")
        sim_menu.addAction(self.action_run)
        sim_menu.addAction(self.action_pause)
        sim_menu.addAction(self.action_stop)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_dc_op)
        sim_menu.addAction(self.action_ac)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_parameter_sweep)
        sim_menu.addAction(self.action_thermal_viewer)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_sim_settings)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.action_about)

    def _create_toolbar(self) -> None:
        """Create the main toolbar with professional icons and overflow menu."""
        from PySide6.QtWidgets import QToolButton

        self._toolbar = QToolBar("Main Toolbar")
        self._toolbar.setObjectName("MainToolbar")
        self._toolbar.setIconSize(QSize(20, 20))
        self._toolbar.setMovable(False)
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(self._toolbar)

        # File actions with icons
        self._toolbar.addAction(self.action_new)
        self._toolbar.addAction(self.action_open)
        self._toolbar.addAction(self.action_save)
        self._toolbar.addSeparator()

        # Edit actions
        self._toolbar.addAction(self.action_undo)
        self._toolbar.addAction(self.action_redo)
        self._toolbar.addSeparator()

        # Zoom actions
        self._toolbar.addAction(self.action_zoom_in)
        self._toolbar.addAction(self.action_zoom_out)
        self._toolbar.addAction(self.action_zoom_fit)
        self._toolbar.addSeparator()

        # Simulation actions
        self._toolbar.addAction(self.action_run)
        self._toolbar.addAction(self.action_stop)

        # Add flexible spacer
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(), spacer.sizePolicy().verticalPolicy())
        self._toolbar.addWidget(spacer)

        # Overflow menu button for additional actions
        self._overflow_btn = QToolButton()
        self._overflow_btn.setIcon(IconService.get_icon("menu", "#374151"))
        self._overflow_btn.setToolTip("More actions")
        self._overflow_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._overflow_btn.setAutoRaise(True)

        overflow_menu = QMenu(self._overflow_btn)
        overflow_menu.addAction(self.action_toggle_grid)
        overflow_menu.addAction(self.action_toggle_dc_overlay)
        overflow_menu.addSeparator()
        overflow_menu.addAction(self.action_dc_op)
        overflow_menu.addAction(self.action_ac)
        overflow_menu.addAction(self.action_parameter_sweep)
        overflow_menu.addSeparator()
        overflow_menu.addAction(self.action_sim_settings)
        overflow_menu.addAction(self.action_preferences)

        self._overflow_btn.setMenu(overflow_menu)
        self._toolbar.addWidget(self._overflow_btn)

    def _create_status_bar(self) -> None:
        """Create the status bar with icons."""
        from PySide6.QtWidgets import QProgressBar
        from pulsimgui.views.widgets import (
            CoordinateWidget,
            ZoomWidget,
            SelectionWidget,
            ModifiedWidget,
            SimulationStatusWidget,
        )

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # Coordinate display with icon
        self._coord_widget = CoordinateWidget()
        status_bar.addWidget(self._coord_widget)

        # Zoom level with icon
        self._zoom_widget = ZoomWidget()
        status_bar.addWidget(self._zoom_widget)

        # Selection count with icon
        self._selection_widget = SelectionWidget()
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
        self._sim_progress.setVisible(False)
        status_bar.addPermanentWidget(self._sim_progress)

        # Simulation status with icon
        self._sim_status_widget = SimulationStatusWidget()
        status_bar.addPermanentWidget(self._sim_status_widget)

        # Modified indicator with icon
        self._modified_widget = ModifiedWidget()
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
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.library_dock)

        # Properties Panel (right)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("PropertiesDock")
        self.properties_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._properties_panel = PropertiesPanel()
        self._properties_panel.property_changed.connect(self._on_property_changed)
        self._properties_panel.flip_requested.connect(self._on_flip_from_panel)
        self._properties_panel.rotate_requested.connect(self._on_rotate_from_panel)
        self.properties_dock.setWidget(self._properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        # Waveform Viewer (bottom)
        self.waveform_dock = QDockWidget("Waveform Viewer", self)
        self.waveform_dock.setObjectName("WaveformDock")
        self.waveform_dock.setAllowedAreas(
            Qt.DockWidgetArea.TopDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._waveform_viewer = WaveformViewer()
        self.waveform_dock.setWidget(self._waveform_viewer)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.waveform_dock)

        # Add toggle actions to panels menu
        self.panels_menu.addAction(self.library_dock.toggleViewAction())
        self.panels_menu.addAction(self.properties_dock.toggleViewAction())
        self.panels_menu.addAction(self.waveform_dock.toggleViewAction())

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

        # Simulation service signals
        self._simulation_service.state_changed.connect(self._on_simulation_state_changed)
        self._simulation_service.progress.connect(self._on_simulation_progress)
        self._simulation_service.data_point.connect(self._on_simulation_data_point)
        self._simulation_service.simulation_finished.connect(self._on_simulation_finished)
        self._simulation_service.dc_finished.connect(self._on_dc_finished)
        self._simulation_service.ac_finished.connect(self._on_ac_finished)
        self._simulation_service.parameter_sweep_finished.connect(
            self._on_parameter_sweep_finished
        )
        self._simulation_service.error.connect(self._on_simulation_error)
        self._simulation_service.backend_changed.connect(self._on_backend_changed)

        # Hierarchy service signals
        self._hierarchy_service.hierarchy_changed.connect(self._on_hierarchy_changed)
        self._hierarchy_service.breadcrumb_updated.connect(self._on_breadcrumb_updated)
        self._hierarchy_bar.navigate_up.connect(self._hierarchy_service.ascend)
        self._hierarchy_bar.navigate_to_level.connect(self._hierarchy_service.navigate_to_level)

    def _update_simulation_actions(self) -> None:
        """Enable or disable simulation actions based on backend readiness."""
        backend_ready = self._simulation_service.is_backend_ready
        is_running = self._simulation_service.is_running
        self.action_run.setEnabled(backend_ready and not is_running)
        self.action_stop.setEnabled(backend_ready and is_running)
        self.action_pause.setEnabled(backend_ready and is_running)
        self.action_dc_op.setEnabled(backend_ready and not is_running)
        self.action_ac.setEnabled(backend_ready and not is_running)
        self.action_parameter_sweep.setEnabled(backend_ready and not is_running)

    def _update_backend_status(self, info: BackendInfo | None = None) -> None:
        """Refresh the status bar text to describe backend state."""
        backend_info = info or self._simulation_service.backend_info
        backend_ready = self._simulation_service.is_backend_ready
        self._update_simulation_actions()
        if backend_ready:
            if not self._simulation_service.is_running:
                self._sim_status_widget.setStatus(backend_info.label())
            return
        warning = (
            self._simulation_service.backend_issue_message
            or "Simulation backend unavailable."
        )
        self._sim_status_widget.setStatus(f"Backend unavailable: {warning}", is_error=True)
        self._sim_progress.setVisible(False)

    def _handle_backend_changed(self, info: BackendInfo, notify: bool) -> None:
        """Apply backend changes and optionally notify the user."""
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

        # Apply stylesheet
        self.setStyleSheet(self._theme_service.generate_stylesheet())

        # Update schematic colors from theme
        from PySide6.QtGui import QColor
        bg_color = QColor(theme.colors.schematic_background)
        grid_color = QColor(theme.colors.schematic_grid)
        self._schematic_scene.set_background_color(bg_color)
        self._schematic_scene.set_grid_color(grid_color)

        # Update component colors (dark mode affects line colors)
        self._schematic_scene.set_dark_mode(theme.is_dark)

        # Update minimap colors
        self._minimap.set_dark_mode(theme.is_dark)

        # Update properties panel colors
        self._properties_panel.set_dark_mode(theme.is_dark)

        # Clear icon cache BEFORE updating icons
        IconService.clear_cache()

        # Update toolbar icons for current theme
        self._update_toolbar_icons()

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
            self.action_run: "play",
            self.action_stop: "square",
        }

        for action, icon_name in icon_map.items():
            action.setIcon(IconService.get_icon(icon_name, icon_color, 20))

        # Update overflow button icon
        self._overflow_btn.setIcon(IconService.get_icon("menu", icon_color, 20))

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
        """Update window title based on project state."""
        if self._project.path:
            title = f"PulsimGui - {self._project.path.name}"
        else:
            title = f"PulsimGui - {self._project.name}"
        if self._project.is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def _update_modified_indicator(self) -> None:
        """Update the modified indicator in the status bar."""
        self._modified_widget.setModified(self._project.is_dirty)

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
        """Handle auto-save timer timeout."""
        if not self._project.is_dirty:
            return

        # Save backup copy
        if self._project.path:
            # Save to backup file (original.pulsim.bak)
            backup_path = Path(str(self._project.path) + ".bak")
            try:
                self._project.save(str(backup_path))
                self.statusBar().showMessage("Auto-saved backup", 2000)
            except Exception:
                pass  # Silently fail on backup
        else:
            # No file yet - save to temp location
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "pulsimgui_autosave"
            temp_dir.mkdir(exist_ok=True)
            backup_path = temp_dir / f"{self._project.name}.pulsim"
            try:
                self._project.save(str(backup_path))
                self.statusBar().showMessage(f"Auto-saved to {backup_path}", 2000)
            except Exception:
                pass  # Silently fail on backup

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
        from pulsimgui.views.schematic.items import ComponentItem

        selected_items = self._schematic_scene.selectedItems()

        # Filter to get only ComponentItems
        selected_components = [
            item.component for item in selected_items
            if isinstance(item, ComponentItem)
        ]

        self.action_create_subcircuit.setEnabled(len(selected_components) > 0)

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

    def _on_hierarchy_changed(self, _level) -> None:
        """Refresh scene when hierarchy level changes."""
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()
        self._schematic_scene.clearSelection()
        self._properties_panel.set_component(None)
        self.update_selection(0)

    def _on_breadcrumb_updated(self, levels: list) -> None:
        """Update hierarchy bar breadcrumb display."""
        self._hierarchy_bar.update_hierarchy(levels)

    def _on_subcircuit_open_requested(self, component) -> None:
        """Handle double-click on a subcircuit instance to descend."""
        definition_id = getattr(component, "subcircuit_id", None)
        if not definition_id:
            QMessageBox.warning(self, "Missing subcircuit", "This subcircuit has no definition attached.")
            return

        if not self._hierarchy_service.descend_into(component.id, definition_id):
            QMessageBox.warning(self, "Cannot navigate", "Subcircuit definition could not be loaded.")

    def _on_create_subcircuit(self) -> None:
        """Create a subcircuit definition from the current selection."""
        from pulsimgui.views.schematic.items import ComponentItem, WireItem
        from pulsimgui.models.component import ComponentType

        selected_items = self._schematic_scene.selectedItems()
        component_items = [item for item in selected_items if isinstance(item, ComponentItem)]
        wire_items = [item for item in selected_items if isinstance(item, WireItem)]

        if not component_items:
            QMessageBox.information(self, "Create Subcircuit", "Select at least one component.")
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

    def _clear_scene(self) -> None:
        """Clear all items from the schematic scene."""
        self._schematic_scene.clear()
        self._properties_panel.set_component(None)

    def _load_project_to_scene(self) -> None:
        """Load the current project's circuit into the schematic scene."""
        self._hierarchy_service.set_project(self._project)
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()
        self._hierarchy_bar.update_hierarchy(self._hierarchy_service.breadcrumb_path)
        self._apply_current_theme()

    # Slots
    def _on_new_project(self) -> None:
        """Create a new project."""
        if not self._check_save():
            return
        self._close_all_scope_windows(persist_state=False)
        self._project = Project()
        self._latest_electrical_result = None
        self._latest_thermal_waveform = None
        self._command_stack.clear()
        self._hierarchy_service.set_project(self._project)
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()
        self._hierarchy_bar.update_hierarchy(self._hierarchy_service.breadcrumb_path)
        self._update_title()
        self._update_modified_indicator()

    def _on_new_from_template(self) -> None:
        """Create a new project from a template."""
        if not self._check_save():
            return

        dialog = TemplateDialog(self)
        if dialog.exec():
            template_id = dialog.get_selected_template_id()
            if template_id:
                # Create circuit from template
                circuit = TemplateService.create_circuit_from_template(template_id)
                if circuit:
                    # Create new project with the template circuit
                    self._close_all_scope_windows(persist_state=False)
                    self._project = Project(name=circuit.name)
                    self._latest_electrical_result = None
                    self._latest_thermal_waveform = None
                    self._project._circuits = {circuit.id: circuit}
                    self._project._active_circuit_id = circuit.id
                    self._command_stack.clear()
                    self._load_project_to_scene()
                    self._project.mark_dirty()
                    self._update_title()
                    self._update_modified_indicator()
                    self.statusBar().showMessage(
                        f"Created new project from template: {circuit.name}", 3000
                    )

    def _on_open_project(self) -> None:
        """Open a project file."""
        if not self._check_save():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            self._settings.get_default_project_location(),
            "Pulsim Projects (*.pulsim);;All Files (*)",
        )
        if path:
            self._open_project_file(path)

    def _open_project_file(self, path: str) -> None:
        """Open a project from the given path."""
        try:
            self._close_all_scope_windows(persist_state=False)
            self._project = Project.load(path)
            self._latest_electrical_result = None
            self._latest_thermal_waveform = None
            self._command_stack.clear()
            self._load_project_to_scene()
            self._settings.add_recent_project(path)
            self._update_recent_menu()
            self._update_title()
            self._update_modified_indicator()
            self.statusBar().showMessage(f"Opened: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def _on_save(self) -> None:
        """Save the current project."""
        if self._project.path is None:
            self._on_save_as()
        else:
            try:
                self._project.save()
                self._command_stack.set_clean()
                self._update_title()
                self._update_modified_indicator()
                self.statusBar().showMessage("Project saved", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _on_save_as(self) -> None:
        """Save the project with a new name."""
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
                self._settings.add_recent_project(path)
                self._update_recent_menu()
                self._update_title()
                self._update_modified_indicator()
                self.statusBar().showMessage(f"Saved: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _on_close_project(self) -> None:
        """Close the current project and create a new empty one."""
        if not self._check_save():
            return
        self._close_all_scope_windows(persist_state=False)
        self._project = Project()
        self._latest_electrical_result = None
        self._latest_thermal_waveform = None
        self._command_stack.clear()
        self._hierarchy_service.set_project(self._project)
        self._schematic_scene.circuit = self._hierarchy_service.get_current_circuit()
        self._hierarchy_bar.update_hierarchy(self._hierarchy_service.breadcrumb_path)
        self._update_title()
        self._update_modified_indicator()
        self.statusBar().showMessage("Project closed", 3000)

    def _on_undo(self) -> None:
        """Undo the last command."""
        self._command_stack.undo()
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _on_redo(self) -> None:
        """Redo the last undone command."""
        self._command_stack.redo()
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _on_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About PulsimGui",
            "<h3>PulsimGui</h3>"
            "<p>Cross-platform GUI for Pulsim power electronics simulator.</p>"
            "<p>Version 0.1.0</p>"
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
        from PySide6.QtCore import QPointF

        scene = self._schematic_view.scene()
        grid_spacing = 20  # Default grid spacing

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

        # Create component
        component = Component(comp_type, x=x, y=y)
        circuit = self._current_circuit()
        circuit.add_component(component)

        # Update scene
        if scene:
            scene.load_circuit(circuit)

        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

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
        """Toggle minimap visibility."""
        self._minimap.setVisible(checked)

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

        # Add to circuit and scene
        self._current_circuit().add_component(component)
        self._schematic_scene.add_component(component)

        # Update library recent list
        self._library_panel.add_to_recent(comp_type)

        # Mark project dirty
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

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

        # Add to circuit and scene
        self._current_circuit().add_component(component)
        self._schematic_scene.add_component(component)

        # Update library recent list
        self._library_panel.add_to_recent(comp_type)

        # Mark project dirty
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _on_component_removed(self, component) -> None:
        """Tear down scope window state when a component disappears."""
        comp_id = str(component.id)
        window = self._scope_windows.get(comp_id)
        if window is not None:
            window.close()
        if comp_id in self._project.scope_windows:
            del self._project.scope_windows[comp_id]
            self._project.mark_dirty()
            self._update_modified_indicator()

    def _on_wire_created(self, segments: list) -> None:
        """Handle wire creation from schematic view."""
        from pulsimgui.models.wire import Wire, WireSegment, WireConnection
        from pulsimgui.views.schematic.items import WireItem, ComponentItem
        from PySide6.QtCore import QPointF

        if not segments:
            return

        # Create wire model
        wire_segments = [
            WireSegment(x1=seg[0], y1=seg[1], x2=seg[2], y2=seg[3])
            for seg in segments
        ]
        wire = Wire(segments=wire_segments)

        # Detect connections at wire endpoints
        start_pt = QPointF(segments[0][0], segments[0][1])
        end_pt = QPointF(segments[-1][2], segments[-1][3])

        # Find connected components at start and end points
        SNAP_TOLERANCE = 15.0
        for item in self._schematic_scene.items():
            if not isinstance(item, ComponentItem):
                continue

            component = item.component
            for pin_index in range(len(component.pins)):
                pin_pos = item.get_pin_position(pin_index)

                # Check start connection
                dist_start = ((start_pt.x() - pin_pos.x()) ** 2 +
                              (start_pt.y() - pin_pos.y()) ** 2) ** 0.5
                if dist_start < SNAP_TOLERANCE:
                    wire.start_connection = WireConnection(
                        component_id=component.id,
                        pin_index=pin_index
                    )

                # Check end connection
                dist_end = ((end_pt.x() - pin_pos.x()) ** 2 +
                            (end_pt.y() - pin_pos.y()) ** 2) ** 0.5
                if dist_end < SNAP_TOLERANCE:
                    wire.end_connection = WireConnection(
                        component_id=component.id,
                        pin_index=pin_index
                    )

        # Add to circuit
        self._current_circuit().add_wire(wire)

        # Add to scene
        wire_item = WireItem(wire)
        wire_item.set_dark_mode(self._theme_service.is_dark)
        self._schematic_scene.addItem(wire_item)

        # Mark project dirty
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

    def _on_wire_alias_changed(self, wire) -> None:
        """Update project state when a wire alias is renamed."""
        self._project.mark_dirty()
        self._update_modified_indicator()
        self._refresh_scope_window_bindings()

    def _on_scope_open_requested(self, component) -> None:
        """Open (or focus) a dedicated window for the requested scope."""
        if component is None:
            return
        self._open_scope_window(component)

    def _on_scope_window_closed(self, component_id: str, geometry: tuple[int, int, int, int]) -> None:
        """Persist window state whenever a scope window closes."""
        self._scope_windows.pop(component_id, None)
        if self._suppress_scope_state:
            return
        state = self._project.scope_state_for(component_id)
        state.is_open = False
        state.geometry = list(geometry)
        self._project.mark_dirty()
        self._update_modified_indicator()

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

        # Mark project dirty and update display
        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

        # Get the component being edited from properties panel
        edited_component = self._properties_panel._component
        if edited_component is None:
            return

        # Find and update the corresponding component item in the scene
        for item in self._schematic_scene.items():
            if isinstance(item, ComponentItem) and item.component is edited_component:
                # Update position if changed
                if name == "position_x":
                    item.setPos(edited_component.x, edited_component.y)
                elif name == "position_y":
                    item.setPos(edited_component.x, edited_component.y)
                elif name == "rotation":
                    item.setRotation(edited_component.rotation)
                # Update name label
                item._name_label.setPlainText(edited_component.name)
                # Update labels for parameter changes (value text)
                item._update_labels()
                item.update()
                break

        self._schematic_scene.update()
        self._refresh_scope_window_bindings()

    def _on_flip_from_panel(self, axis: str) -> None:
        """Handle flip request from properties panel."""
        from pulsimgui.views.schematic.items import ComponentItem

        edited_component = self._properties_panel._component
        if edited_component is None:
            return

        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

        # Find and update the corresponding component item in the scene
        for item in self._schematic_scene.items():
            if isinstance(item, ComponentItem) and item.component is edited_component:
                item.update_transform()
                item.update()
                break

        self._schematic_scene.update()

    def _on_rotate_from_panel(self, degrees: int) -> None:
        """Handle rotate request from properties panel."""
        from pulsimgui.views.schematic.items import ComponentItem

        edited_component = self._properties_panel._component
        if edited_component is None:
            return

        self._project.mark_dirty()
        self._update_title()
        self._update_modified_indicator()

        # Find and update the corresponding component item in the scene
        for item in self._schematic_scene.items():
            if isinstance(item, ComponentItem) and item.component is edited_component:
                item.setRotation(edited_component.rotation)
                item.update_transform()
                item.update()
                break

        self._schematic_scene.update()

    # ------------------------------------------------------------------
    # Scope window helpers
    # ------------------------------------------------------------------
    def _open_scope_window(
        self,
        component,
        geometry: list[int] | None = None,
        update_state: bool = True,
    ) -> ScopeWindow:
        comp_id = str(component.id)
        window = self._scope_windows.get(comp_id)
        if window is None:
            window = ScopeWindow(comp_id, component.name, component.type, self)
            window.closed.connect(self._on_scope_window_closed)
            self._scope_windows[comp_id] = window

        window.set_component_name(component.name)
        circuit = self._current_circuit()
        window.set_bindings(build_scope_channel_bindings(component, circuit))

        target_geometry = geometry
        if target_geometry is None:
            state = self._project.scope_windows.get(comp_id)
            if state and state.geometry:
                target_geometry = state.geometry
        window.apply_geometry_state(target_geometry)
        window.apply_simulation_result(self._scope_result_for_component(component))

        window.show()
        window.raise_()
        window.activateWindow()

        if update_state and not self._suppress_scope_state:
            state = self._project.scope_state_for(comp_id)
            state.is_open = True
            state.geometry = list(window.capture_geometry_state())
            self._project.mark_dirty()
            self._update_modified_indicator()
        return window

    def _close_all_scope_windows(self, persist_state: bool = True) -> None:
        if not self._scope_windows:
            return
        previous = self._suppress_scope_state
        self._suppress_scope_state = not persist_state
        try:
            for window in list(self._scope_windows.values()):
                window.close()
        finally:
            self._suppress_scope_state = previous
        if not persist_state:
            self._scope_windows.clear()

    def _refresh_scope_window_bindings(self) -> None:
        if not self._scope_windows:
            return
        circuit = self._current_circuit()
        for comp_id, window in list(self._scope_windows.items()):
            component = self._get_component_by_id(comp_id, circuit)
            if component is None:
                window.close()
                continue
            window.set_component_name(component.name)
            window.set_bindings(build_scope_channel_bindings(component, circuit))
            window.apply_simulation_result(self._scope_result_for_component(component))

    def _scope_result_for_component(self, component) -> SimulationResult | None:
        if component.type == ComponentType.THERMAL_SCOPE:
            return self._ensure_thermal_waveform()
        return self._latest_electrical_result

    def _ensure_thermal_waveform(self) -> SimulationResult | None:
        if self._latest_thermal_waveform is not None:
            return self._latest_thermal_waveform
        if not self._latest_electrical_result:
            return None
        circuit = self._current_circuit()
        if circuit is None or not circuit.components:
            return None
        try:
            thermal_result = self._thermal_service.build_result(
                circuit,
                self._latest_electrical_result,
            )
        except Exception as exc:  # pragma: no cover - UI feedback only
            self.statusBar().showMessage(f"Unable to update thermal scopes: {exc}", 5000)
            self._latest_thermal_waveform = None
            return None

        self._latest_thermal_waveform = self._thermal_result_to_waveform(thermal_result)
        return self._latest_thermal_waveform

    def _update_scope_results(self) -> None:
        """Refresh scope windows after simulation state changes."""
        self._latest_thermal_waveform = None
        self._refresh_scope_window_bindings()

    def _thermal_result_to_waveform(self, thermal_result) -> SimulationResult | None:
        if not thermal_result or not thermal_result.time:
            return None
        subset = SimulationResult()
        subset.time = list(thermal_result.time)
        subset.signals = {}
        subset.statistics = {
            "ambient": thermal_result.ambient_temperature,
            "devices": len(thermal_result.devices),
        }
        for device in thermal_result.devices:
            if not device.temperature_trace:
                continue
            key = f"T({device.component_name})"
            subset.signals[key] = list(device.temperature_trace)
        return subset if subset.signals else None

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

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        if not self._check_save():
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
    def _on_run_simulation(self) -> None:
        """Run transient simulation."""
        circuit_data = self._simulation_service.convert_gui_circuit(self._project)
        self._simulation_service.run_transient(circuit_data)

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
        circuit_data = self._simulation_service.convert_gui_circuit(self._project)
        self._simulation_service.run_dc_operating_point(circuit_data)

    def _on_ac_analysis(self) -> None:
        """Run AC analysis."""
        # TODO: Show AC settings dialog first
        circuit_data = self._simulation_service.convert_gui_circuit(self._project)
        self._simulation_service.run_ac_analysis(circuit_data, 1, 1e6, 10)

    def _on_simulation_settings(self) -> None:
        """Show simulation settings dialog."""
        dialog = SimulationSettingsDialog(
            self._simulation_service.settings,
            backend_info=self._simulation_service.backend_info,
            backend_warning=self._simulation_service.backend_issue_message,
            parent=self,
        )
        if dialog.exec():
            self._simulation_service.settings = dialog.get_settings()

    def _on_parameter_sweep(self) -> None:
        """Open the parameter sweep configuration dialog."""
        circuit = self._current_circuit()
        if not circuit.components:
            QMessageBox.information(
                self,
                "No Components",
                "Add at least one component with numeric parameters before running a sweep.",
            )
            return

        dialog = ParameterSweepDialog(circuit, self)
        if dialog.exec():
            sweep_settings = dialog.get_settings()
            if not sweep_settings:
                return
            circuit_data = self._simulation_service.convert_gui_circuit(self._project)
            self._simulation_service.run_parameter_sweep(circuit_data, sweep_settings)

    def _on_show_thermal_viewer(self) -> None:
        """Generate synthetic thermal data and open the viewer dialog."""
        circuit = self._current_circuit()
        if not circuit or not circuit.components:
            QMessageBox.information(
                self,
                "No Components",
                "Add components to the schematic before opening the thermal viewer.",
            )
            return

        try:
            result = self._thermal_service.build_result(
                circuit,
                self._simulation_service.last_result,
            )
        except Exception as exc:  # pragma: no cover - defensive dialog
            QMessageBox.warning(
                self,
                "Thermal Viewer",
                f"Unable to generate thermal data:\n{exc}",
            )
            return

        dialog = ThermalViewerDialog(result, self)
        dialog.exec()

    def _on_simulation_state_changed(self, state: SimulationState) -> None:
        """Handle simulation state change."""
        is_running = state in (SimulationState.RUNNING, SimulationState.PAUSED)
        is_paused = state == SimulationState.PAUSED

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
        self._sim_progress.setValue(int(value))
        self._sim_status_widget.setStatus(message, is_running=True)

    def _on_simulation_data_point(self, time: float, signals: dict) -> None:
        """Handle streaming data point during simulation."""
        # Make waveform dock visible if not already
        if not self.waveform_dock.isVisible():
            self.waveform_dock.setVisible(True)

        # Add data point to waveform viewer for real-time display
        self._waveform_viewer.add_data_point(time, signals)

    def _on_simulation_finished(self, result) -> None:
        """Handle simulation completion."""
        if result.is_valid:
            # Finalize streaming and show complete results in waveform viewer
            self._waveform_viewer.finalize_streaming(result)

            # Make waveform dock visible
            self.waveform_dock.setVisible(True)

            self.statusBar().showMessage(
                f"Simulation complete: {len(result.time)} points, "
                f"{len(result.signals)} signals",
                5000,
            )
            self._latest_electrical_result = result
        else:
            QMessageBox.warning(
                self, "Simulation Error", f"Simulation failed:\n{result.error_message}"
            )
            self._latest_electrical_result = None

        self._update_scope_results()

    def _on_dc_finished(self, result) -> None:
        """Handle DC analysis completion."""
        if result.is_valid:
            # Update schematic with DC values and show overlay
            self._schematic_scene.set_dc_results(result)
            self.action_toggle_dc_overlay.setChecked(True)

            # Show results dialog
            dialog = DCResultsDialog(result, self)
            dialog.exec()
        else:
            QMessageBox.warning(
                self, "DC Analysis Error", f"DC analysis failed:\n{result.error_message}"
            )

    def _on_ac_finished(self, result) -> None:
        """Handle AC analysis completion."""
        if result.is_valid:
            # Show Bode plot dialog
            dialog = BodePlotDialog(result, self)
            dialog.exec()
        else:
            QMessageBox.warning(
                self, "AC Analysis Error", f"AC analysis failed:\n{result.error_message}"
            )

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
        QMessageBox.critical(self, "Simulation Error", message)

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
