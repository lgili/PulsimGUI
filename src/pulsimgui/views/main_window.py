"""Main application window."""

from PySide6.QtCore import Qt, QSize
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
)

from pulsimgui.commands.base import CommandStack
from pulsimgui.models.project import Project
from pulsimgui.services.settings_service import SettingsService
from pulsimgui.services.simulation_service import SimulationService, SimulationState
from pulsimgui.services.theme_service import ThemeService, Theme
from pulsimgui.views.dialogs import PreferencesDialog, SimulationSettingsDialog, DCResultsDialog
from pulsimgui.views.library import LibraryPanel
from pulsimgui.views.properties import PropertiesPanel
from pulsimgui.views.schematic import SchematicScene, SchematicView


class MainWindow(QMainWindow):
    """Main application window with docking panels."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._settings = SettingsService()
        self._theme_service = ThemeService(parent=self)
        self._command_stack = CommandStack(parent=self)
        self._project = Project()
        self._simulation_service = SimulationService(parent=self)

        self._setup_window()
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_status_bar()
        self._create_dock_widgets()
        self._connect_signals()
        self._restore_state()
        self._apply_theme()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle("PulsimGui - Untitled Project")
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)

        # Central widget - Schematic Editor
        self._schematic_scene = SchematicScene()
        self._schematic_view = SchematicView(self._schematic_scene)
        self.setCentralWidget(self._schematic_view)

        # Connect schematic signals
        self._schematic_view.zoom_changed.connect(self.update_zoom)
        self._schematic_view.mouse_moved.connect(self.update_coordinates)
        self._schematic_view.component_dropped.connect(self._on_component_dropped)
        self._schematic_view.wire_created.connect(self._on_wire_created)
        self._schematic_scene.selection_changed_custom.connect(self.update_selection)

    def _create_actions(self) -> None:
        """Create all menu and toolbar actions."""
        # File actions
        self.action_new = QAction("&New Project", self)
        self.action_new.setShortcut(QKeySequence.StandardKey.New)
        self.action_new.triggered.connect(self._on_new_project)

        self.action_open = QAction("&Open Project...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self._on_open_project)

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self._on_save)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self._on_save_as)

        self.action_export_netlist = QAction("Export &Netlist...", self)
        self.action_export_netlist.setShortcut(QKeySequence("Ctrl+E"))

        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)

        # Edit actions
        self.action_undo = QAction("&Undo", self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_undo.setEnabled(False)
        self.action_undo.triggered.connect(self._on_undo)

        self.action_redo = QAction("&Redo", self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
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

        self.action_preferences = QAction("&Preferences...", self)
        self.action_preferences.setShortcut(QKeySequence("Ctrl+,"))
        self.action_preferences.triggered.connect(self._on_preferences)

        # View actions
        self.action_zoom_in = QAction("Zoom &In", self)
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.triggered.connect(self._on_zoom_in)

        self.action_zoom_out = QAction("Zoom &Out", self)
        self.action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.action_zoom_out.triggered.connect(self._on_zoom_out)

        self.action_zoom_fit = QAction("Zoom to &Fit", self)
        self.action_zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.action_zoom_fit.triggered.connect(self._on_zoom_fit)

        self.action_toggle_grid = QAction("Show &Grid", self)
        self.action_toggle_grid.setCheckable(True)
        self.action_toggle_grid.setChecked(self._settings.get_show_grid())
        self.action_toggle_grid.setShortcut(QKeySequence("G"))
        self.action_toggle_grid.triggered.connect(self._on_toggle_grid)

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
        self.action_run.triggered.connect(self._on_run_simulation)

        self.action_stop = QAction("&Stop Simulation", self)
        self.action_stop.setShortcut(QKeySequence("Shift+F5"))
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

        # Help actions
        self.action_about = QAction("&About PulsimGui", self)
        self.action_about.triggered.connect(self._on_about)

    def _create_menus(self) -> None:
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_open)
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._update_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export_netlist)
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
        edit_menu.addAction(self.action_preferences)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addAction(self.action_zoom_fit)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_grid)
        view_menu.addSeparator()
        self.panels_menu = view_menu.addMenu("&Panels")
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        theme_menu.addAction(self.action_theme_light)
        theme_menu.addAction(self.action_theme_dark)
        theme_menu.addAction(self.action_theme_modern_dark)

        # Simulation menu
        sim_menu = menubar.addMenu("&Simulation")
        sim_menu.addAction(self.action_run)
        sim_menu.addAction(self.action_pause)
        sim_menu.addAction(self.action_stop)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_dc_op)
        sim_menu.addAction(self.action_ac)
        sim_menu.addSeparator()
        sim_menu.addAction(self.action_sim_settings)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.action_about)

    def _create_toolbar(self) -> None:
        """Create the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("MainToolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.action_new)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_save)
        toolbar.addSeparator()
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_redo)
        toolbar.addSeparator()
        toolbar.addAction(self.action_cut)
        toolbar.addAction(self.action_copy)
        toolbar.addAction(self.action_paste)
        toolbar.addSeparator()
        toolbar.addAction(self.action_zoom_in)
        toolbar.addAction(self.action_zoom_out)
        toolbar.addAction(self.action_zoom_fit)
        toolbar.addSeparator()
        toolbar.addAction(self.action_run)
        toolbar.addAction(self.action_stop)

    def _create_status_bar(self) -> None:
        """Create the status bar."""
        from PySide6.QtWidgets import QProgressBar

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # Coordinate display
        self._coord_label = QLabel("X: 0, Y: 0")
        self._coord_label.setMinimumWidth(100)
        status_bar.addWidget(self._coord_label)

        # Zoom level
        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(60)
        status_bar.addWidget(self._zoom_label)

        # Selection count
        self._selection_label = QLabel("")
        status_bar.addWidget(self._selection_label)

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

        # Simulation status label
        self._sim_status_label = QLabel("")
        self._sim_status_label.setMinimumWidth(150)
        status_bar.addPermanentWidget(self._sim_status_label)

        # Modified indicator
        self._modified_label = QLabel("")
        status_bar.addPermanentWidget(self._modified_label)

    def _create_dock_widgets(self) -> None:
        """Create dockable panels."""
        # Component Library (left)
        self.library_dock = QDockWidget("Component Library", self)
        self.library_dock.setObjectName("LibraryDock")
        self.library_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._library_panel = LibraryPanel()
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
        self.properties_dock.setWidget(self._properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        # Waveform Viewer (bottom)
        self.waveform_dock = QDockWidget("Waveform Viewer", self)
        self.waveform_dock.setObjectName("WaveformDock")
        self.waveform_dock.setAllowedAreas(
            Qt.DockWidgetArea.TopDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        waveform_placeholder = QLabel("Waveform Viewer\n(Coming Soon)")
        waveform_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.waveform_dock.setWidget(waveform_placeholder)
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
        self._simulation_service.simulation_finished.connect(self._on_simulation_finished)
        self._simulation_service.dc_finished.connect(self._on_dc_finished)
        self._simulation_service.error.connect(self._on_simulation_error)

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

        # Update schematic view
        self._schematic_view.set_dark_mode(theme.is_dark)
        self._schematic_scene.set_dark_mode(theme.is_dark)

        # Update schematic colors from theme
        from PySide6.QtGui import QColor, QBrush
        bg_color = QColor(theme.colors.schematic_background)
        grid_color = QColor(theme.colors.schematic_grid)
        self._schematic_view.setBackgroundBrush(QBrush(bg_color))
        self._schematic_scene.set_grid_color(grid_color)

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
        title = f"PulsimGui - {self._project.name}"
        if self._project.is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def update_coordinates(self, x: float, y: float) -> None:
        """Update coordinate display in status bar."""
        self._coord_label.setText(f"X: {x:.1f}, Y: {y:.1f}")

    def update_zoom(self, zoom_percent: float) -> None:
        """Update zoom level display in status bar."""
        self._zoom_label.setText(f"{zoom_percent:.0f}%")

    def update_selection(self, count: int) -> None:
        """Update selection count in status bar."""
        if count > 0:
            self._selection_label.setText(f"{count} selected")
        else:
            self._selection_label.setText("")

    # Slots
    def _on_new_project(self) -> None:
        """Create a new project."""
        if not self._check_save():
            return
        self._project = Project()
        self._command_stack.clear()
        self._update_title()

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
            self._project = Project.load(path)
            self._command_stack.clear()
            self._settings.add_recent_project(path)
            self._update_recent_menu()
            self._update_title()
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
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _on_undo(self) -> None:
        """Undo the last command."""
        self._command_stack.undo()
        self._project.mark_dirty()
        self._update_title()

    def _on_redo(self) -> None:
        """Redo the last undone command."""
        self._command_stack.redo()
        self._project.mark_dirty()
        self._update_title()

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

    def _on_zoom_in(self) -> None:
        """Zoom in the schematic view."""
        self._schematic_view.zoom_in()

    def _on_zoom_out(self) -> None:
        """Zoom out the schematic view."""
        self._schematic_view.zoom_out()

    def _on_zoom_fit(self) -> None:
        """Zoom to fit all items."""
        self._schematic_view.zoom_to_fit()

    def _on_toggle_grid(self, checked: bool) -> None:
        """Toggle grid visibility."""
        self._schematic_scene.show_grid = checked
        self._settings.set_show_grid(checked)

    def _on_preferences(self) -> None:
        """Show preferences dialog."""
        dialog = PreferencesDialog(self._settings, self)
        if dialog.exec():
            # Apply settings that may have changed
            self._apply_theme()
            self._schematic_scene.grid_size = self._settings.get_grid_size()
            self._schematic_scene.show_grid = self._settings.get_show_grid()
            self.action_toggle_grid.setChecked(self._settings.get_show_grid())

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
        self._project.get_active_circuit().add_component(component)
        self._schematic_scene.add_component(component)

        # Update library recent list
        self._library_panel.add_to_recent(comp_type)

        # Mark project dirty
        self._project.mark_dirty()
        self._update_title()

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
        self._project.get_active_circuit().add_component(component)
        self._schematic_scene.add_component(component)

        # Update library recent list
        self._library_panel.add_to_recent(comp_type)

        # Mark project dirty
        self._project.mark_dirty()
        self._update_title()

    def _on_wire_created(self, segments: list) -> None:
        """Handle wire creation from schematic view."""
        from pulsimgui.models.wire import Wire, WireSegment
        from pulsimgui.views.schematic.items import WireItem

        if not segments:
            return

        # Create wire model
        wire_segments = [
            WireSegment(x1=seg[0], y1=seg[1], x2=seg[2], y2=seg[3])
            for seg in segments
        ]
        wire = Wire(segments=wire_segments)

        # Add to circuit
        self._project.get_active_circuit().add_wire(wire)

        # Add to scene
        wire_item = WireItem(wire)
        wire_item.set_dark_mode(self._theme_service.is_dark)
        self._schematic_scene.addItem(wire_item)

        # Mark project dirty
        self._project.mark_dirty()
        self._update_title()

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
            c.name for c in self._project.get_active_circuit().components.values()
        }
        num = 1
        while f"{prefix}{num}" in existing_names:
            num += 1

        return f"{prefix}{num}"

    def _on_property_changed(self, name: str, value) -> None:
        """Handle property change from properties panel."""
        # Mark project dirty and update display
        self._project.mark_dirty()
        self._update_title()
        self._schematic_scene.update()

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
        dialog = SimulationSettingsDialog(self._simulation_service.settings, self)
        if dialog.exec():
            self._simulation_service.settings = dialog.get_settings()

    def _on_simulation_state_changed(self, state: SimulationState) -> None:
        """Handle simulation state change."""
        is_running = state in (SimulationState.RUNNING, SimulationState.PAUSED)
        is_paused = state == SimulationState.PAUSED

        # Update UI
        self.action_run.setEnabled(not is_running)
        self.action_stop.setEnabled(is_running)
        self.action_pause.setEnabled(is_running)
        self.action_dc_op.setEnabled(not is_running)
        self.action_ac.setEnabled(not is_running)

        self._sim_progress.setVisible(is_running)

        if state == SimulationState.IDLE:
            self._sim_status_label.setText("")
        elif state == SimulationState.RUNNING:
            self._sim_status_label.setText("Running...")
        elif state == SimulationState.PAUSED:
            self._sim_status_label.setText("Paused")
        elif state == SimulationState.COMPLETED:
            self._sim_status_label.setText("Completed")
        elif state == SimulationState.CANCELLED:
            self._sim_status_label.setText("Cancelled")
        elif state == SimulationState.ERROR:
            self._sim_status_label.setText("Error")

    def _on_simulation_progress(self, value: float, message: str) -> None:
        """Handle simulation progress update."""
        self._sim_progress.setValue(int(value))
        self._sim_status_label.setText(message)

    def _on_simulation_finished(self, result) -> None:
        """Handle simulation completion."""
        if result.is_valid:
            # Show results in waveform viewer
            # TODO: Update waveform viewer with results
            self.statusBar().showMessage(
                f"Simulation complete: {len(result.time)} points, "
                f"{len(result.signals)} signals",
                5000,
            )
        else:
            QMessageBox.warning(
                self, "Simulation Error", f"Simulation failed:\n{result.error_message}"
            )

    def _on_dc_finished(self, result) -> None:
        """Handle DC analysis completion."""
        if result.is_valid:
            dialog = DCResultsDialog(result, self)
            dialog.exec()
        else:
            QMessageBox.warning(
                self, "DC Analysis Error", f"DC analysis failed:\n{result.error_message}"
            )

    def _on_simulation_error(self, message: str) -> None:
        """Handle simulation error."""
        QMessageBox.critical(self, "Simulation Error", message)
