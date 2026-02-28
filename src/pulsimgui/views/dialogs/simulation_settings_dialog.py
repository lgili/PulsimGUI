"""Simulation settings dialog."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.simulation_service import (
    SimulationSettings,
    normalize_integration_method,
    normalize_step_mode,
)
from pulsimgui.services.theme_service import Theme
from pulsimgui.views.properties import SILineEdit


class SimulationSettingsDialog(QDialog):
    """Dialog for configuring simulation settings."""

    settings_applied = Signal()

    _INTEGRATION_OPTIONS: tuple[tuple[str, str], ...] = (
        ("Auto (Backend default)", "auto"),
        ("Trapezoidal", "trapezoidal"),
        ("BDF1", "bdf1"),
        ("BDF2", "bdf2"),
        ("BDF3", "bdf3"),
        ("BDF4", "bdf4"),
        ("BDF5", "bdf5"),
        ("Gear", "gear"),
        ("TRBDF2", "trbdf2"),
        ("RosenbrockW", "rosenbrockw"),
        ("SDIRK2", "sdirk2"),
    )

    _PRESET_CARDS: tuple[tuple[str, str, str], ...] = (
        ("fast_preview", "Fast Preview", "Quick, lower fidelity."),
        ("accurate", "Accurate", "Balanced speed/precision."),
        ("switching", "Switching Detailed", "Better switching transitions."),
    )

    _DURATION_PRESETS: tuple[tuple[str, float], ...] = (
        ("1us", 1e-6),
        ("10us", 10e-6),
        ("100us", 100e-6),
        ("1ms", 1e-3),
        ("10ms", 10e-3),
        ("100ms", 100e-3),
    )

    def __init__(
        self,
        settings: SimulationSettings,
        backend_info: BackendInfo | None = None,
        backend_warning: str | None = None,
        theme: Theme | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._backend_info = backend_info
        self._backend_warning = backend_warning
        self._theme = theme
        self._preset_cards: dict[str, QPushButton] = {}
        self._selected_preset = "accurate"

        self.setObjectName("simulationSettingsDialog")
        self.setWindowTitle("Simulation Settings")
        self.setMinimumSize(780, 620)

        self._setup_ui()
        self._load_settings()
        self._apply_dialog_style()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("simSettingsScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        root_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_content.setObjectName("simSettingsScrollContent")
        scroll_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        scroll_area.setWidget(scroll_content)

        self._panel = QFrame()
        self._panel.setObjectName("simSettingsPanel")
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)
        scroll_layout.addWidget(self._panel)
        scroll_layout.addStretch()

        title = QLabel("Simulation Settings")
        title.setObjectName("dialogTitle")
        panel_layout.addWidget(title)

        subtitle = QLabel("Configure solver and simulation behavior.")
        subtitle.setObjectName("dialogSubtitle")
        panel_layout.addWidget(subtitle)

        if self._backend_info is not None or self._backend_warning:
            panel_layout.addWidget(self._create_backend_banner())

        panel_layout.addWidget(self._create_divider())

        panel_layout.addWidget(self._create_section_label("PRESETS"))
        panel_layout.addLayout(self._create_preset_cards())
        panel_layout.addWidget(self._create_divider())

        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        content_layout.addWidget(self._create_solver_time_card(), 1)
        content_layout.addWidget(self._create_events_output_card(), 1)
        panel_layout.addLayout(content_layout)

        panel_layout.addWidget(self._create_advanced_section())
        panel_layout.addWidget(self._create_divider())
        panel_layout.addLayout(self._create_footer())

    def _create_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _create_divider(self) -> QFrame:
        divider = QFrame()
        divider.setObjectName("simDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        return divider

    def _create_preset_cards(self) -> QGridLayout:
        layout = QGridLayout()
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        for col, (preset_id, title, description) in enumerate(self._PRESET_CARDS):
            card = QPushButton(f"{title}\n{description}")
            card.setObjectName("presetCard")
            card.setCheckable(True)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.clicked.connect(partial(self._on_preset_selected, preset_id))
            layout.addWidget(card, 0, col)
            self._preset_cards[preset_id] = card

        return layout

    # ------------------------------------------------------------------
    # Preset definitions: each entry maps to SimulationSettings fields
    # ------------------------------------------------------------------
    _PRESET_PARAMS: dict[str, dict] = {
        "fast_preview": {
            "solver": "trapezoidal",
            "step_mode": "variable",
            "rel_tol": 1e-3,
            "abs_tol": 1e-6,
            "output_points": 5_000,
            "max_newton_iterations": 30,
            "enable_voltage_limiting": False,
            "transient_robust_mode": False,
            "dc_strategy": "auto",
        },
        "accurate": {
            "solver": "auto",
            "step_mode": "variable",
            "rel_tol": 1e-5,
            "abs_tol": 1e-8,
            "output_points": 10_000,
            "max_newton_iterations": 50,
            "enable_voltage_limiting": True,
            "transient_robust_mode": True,
            "dc_strategy": "auto",
        },
        "switching": {
            "solver": "bdf2",
            "step_mode": "variable",
            "rel_tol": 1e-6,
            "abs_tol": 1e-9,
            "output_points": 50_000,
            "max_newton_iterations": 80,
            "enable_voltage_limiting": True,
            "transient_robust_mode": True,
            "dc_strategy": "gmin",
        },
    }

    def _on_preset_selected(self, preset_id: str) -> None:
        self._selected_preset = preset_id
        for key, card in self._preset_cards.items():
            card.blockSignals(True)
            card.setChecked(key == preset_id)
            card.blockSignals(False)

        params = self._PRESET_PARAMS.get(preset_id)
        if params is None:
            return

        # Solver
        solver_val = normalize_integration_method(params["solver"])
        idx = self._solver_combo.findData(solver_val)
        if idx >= 0:
            self._solver_combo.setCurrentIndex(idx)

        # Step mode
        step_val = normalize_step_mode(params["step_mode"])
        idx = self._step_mode_combo.findData(step_val)
        if idx >= 0:
            self._step_mode_combo.setCurrentIndex(idx)

        # Tolerances
        self._rel_tol_spin.setValue(params["rel_tol"])
        self._abs_tol_spin.setValue(params["abs_tol"])

        # Output points
        self._output_points_spin.setValue(params["output_points"])

        # Newton / robustness
        self._max_iterations_spin.setValue(params["max_newton_iterations"])
        self._voltage_limiting_check.setChecked(params["enable_voltage_limiting"])
        self._max_voltage_step_spin.setEnabled(params["enable_voltage_limiting"])
        self._transient_robust_mode_check.setChecked(params["transient_robust_mode"])
        self._transient_auto_regularize_check.setEnabled(params["transient_robust_mode"])
        self._transient_auto_regularize_check.setChecked(params["transient_robust_mode"])

        # DC strategy
        dc_map = {"auto": 0, "direct": 1, "gmin": 2, "source": 3, "pseudo": 4}
        self._dc_strategy_combo.setCurrentIndex(dc_map.get(params["dc_strategy"], 0))

        self._update_solver_description()
        self._update_effective_step()

    def _create_solver_time_card(self) -> QWidget:
        card, layout = self._create_card("Solver & Time", "Core transient integration parameters.")

        form = self._create_form_layout()

        self._solver_combo = QComboBox()
        for label, value in self._INTEGRATION_OPTIONS:
            self._solver_combo.addItem(label, value)
        self._solver_combo.currentIndexChanged.connect(self._update_solver_description)
        form.addRow("Integration method:", self._solver_combo)

        self._step_mode_combo = QComboBox()
        self._step_mode_combo.addItem("Fixed step", "fixed")
        self._step_mode_combo.addItem("Variable step", "variable")
        form.addRow("Step mode:", self._step_mode_combo)

        self._solver_desc = QLabel("")
        self._solver_desc.setObjectName("fieldHint")
        self._solver_desc.setWordWrap(True)
        form.addRow("", self._solver_desc)

        self._t_start_edit = SILineEdit("s")
        form.addRow("Start time:", self._t_start_edit)

        self._t_step_edit = SILineEdit("s")
        form.addRow("Step size:", self._t_step_edit)

        self._t_stop_edit = SILineEdit("s")
        form.addRow("Stop time:", self._t_stop_edit)

        self._max_step_edit = SILineEdit("s")
        form.addRow("Max step:", self._max_step_edit)

        self._rel_tol_spin = QDoubleSpinBox()
        self._rel_tol_spin.setDecimals(8)
        self._rel_tol_spin.setRange(1e-10, 1e-1)
        self._rel_tol_spin.setValue(1e-4)
        self._rel_tol_spin.setSingleStep(1e-5)
        self._rel_tol_spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        form.addRow("Relative tolerance:", self._rel_tol_spin)

        self._abs_tol_spin = QDoubleSpinBox()
        self._abs_tol_spin.setDecimals(10)
        self._abs_tol_spin.setRange(1e-12, 1e-3)
        self._abs_tol_spin.setValue(1e-6)
        self._abs_tol_spin.setSingleStep(1e-7)
        self._abs_tol_spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        form.addRow("Absolute tolerance:", self._abs_tol_spin)

        layout.addLayout(form)
        return card

    def _create_events_output_card(self) -> QWidget:
        card, layout = self._create_card("Events & Output", "Event handling and waveform density.")

        form = self._create_form_layout()

        self._enable_events_check = QCheckBox("Enable simulation event detection")
        self._enable_events_check.setChecked(True)
        form.addRow(self._enable_events_check)

        self._max_step_retries_spin = QSpinBox()
        self._max_step_retries_spin.setRange(0, 100)
        self._max_step_retries_spin.setValue(8)
        form.addRow("Max step retries:", self._max_step_retries_spin)

        self._output_points_spin = QSpinBox()
        self._output_points_spin.setRange(100, 1_000_000)
        self._output_points_spin.setSingleStep(1000)
        self._output_points_spin.setValue(10_000)
        self._output_points_spin.valueChanged.connect(self._update_effective_step)
        form.addRow("Output points:", self._output_points_spin)

        self._effective_step_label = QLabel("-")
        self._effective_step_label.setObjectName("effectiveStepValue")
        form.addRow("Effective step:", self._effective_step_label)
        layout.addLayout(form)

        presets_label = QLabel("Duration presets")
        presets_label.setObjectName("cardSubtitle")
        layout.addWidget(presets_label)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for name, duration in self._DURATION_PRESETS:
            chip = QPushButton(name)
            chip.setObjectName("presetChip")
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            chip.clicked.connect(partial(self._set_duration_preset, duration))
            chips.addWidget(chip)
        chips.addStretch()
        layout.addLayout(chips)

        self._t_stop_edit.value_changed.connect(lambda _: self._update_effective_step())
        self._t_start_edit.value_changed.connect(lambda _: self._update_effective_step())

        return card

    def _create_advanced_section(self) -> QWidget:
        container = QFrame()
        container.setObjectName("advancedSection")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setObjectName("advancedToggle")
        self._advanced_toggle.setText("Advanced Section")
        self._advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setChecked(False)
        self._advanced_toggle.toggled.connect(self._on_advanced_toggled)
        layout.addWidget(self._advanced_toggle)

        self._advanced_body = QFrame()
        self._advanced_body.setObjectName("advancedBody")
        body_layout = QHBoxLayout(self._advanced_body)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(10)
        body_layout.addWidget(self._create_newton_card(), 1)
        body_layout.addWidget(self._create_dc_card(), 1)
        self._advanced_body.setVisible(False)
        layout.addWidget(self._advanced_body)

        return container

    def _on_advanced_toggled(self, checked: bool) -> None:
        self._advanced_body.setVisible(checked)
        arrow = Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        self._advanced_toggle.setArrowType(arrow)

    def _create_newton_card(self) -> QWidget:
        card, layout = self._create_card("Transient Robustness", "Newton controls for convergence.")
        form = self._create_form_layout()

        self._max_iterations_spin = QSpinBox()
        self._max_iterations_spin.setRange(10, 500)
        self._max_iterations_spin.setValue(50)
        self._max_iterations_spin.setToolTip("Maximum Newton iterations per timestep")
        form.addRow("Max iterations:", self._max_iterations_spin)

        self._voltage_limiting_check = QCheckBox("Enable voltage limiting")
        self._voltage_limiting_check.setToolTip("Limit voltage deltas during Newton iterations")
        form.addRow(self._voltage_limiting_check)

        self._max_voltage_step_spin = QDoubleSpinBox()
        self._max_voltage_step_spin.setRange(0.1, 100.0)
        self._max_voltage_step_spin.setValue(5.0)
        self._max_voltage_step_spin.setSuffix(" V")
        self._max_voltage_step_spin.setSingleStep(0.1)
        form.addRow("Max voltage step:", self._max_voltage_step_spin)

        self._transient_robust_mode_check = QCheckBox("Enable robust transient retries")
        self._transient_robust_mode_check.setChecked(True)
        form.addRow(self._transient_robust_mode_check)

        self._transient_auto_regularize_check = QCheckBox("Enable automatic regularization")
        self._transient_auto_regularize_check.setChecked(True)
        form.addRow(self._transient_auto_regularize_check)

        self._transient_robust_mode_check.toggled.connect(
            self._transient_auto_regularize_check.setEnabled
        )
        self._voltage_limiting_check.toggled.connect(self._max_voltage_step_spin.setEnabled)

        layout.addLayout(form)
        return card

    def _create_dc_card(self) -> QWidget:
        card, layout = self._create_card("DC Operating Point", "Fallback strategy before transient start.")
        form = self._create_form_layout()

        self._dc_strategy_combo = QComboBox()
        self._dc_strategy_combo.addItems([
            "Auto",
            "Direct Newton",
            "GMIN Stepping",
            "Source Stepping",
            "Pseudo-Transient",
        ])
        self._dc_strategy_combo.currentIndexChanged.connect(self._on_dc_strategy_changed)
        form.addRow("Strategy:", self._dc_strategy_combo)

        self._dc_strategy_desc = QLabel("")
        self._dc_strategy_desc.setObjectName("fieldHint")
        self._dc_strategy_desc.setWordWrap(True)
        form.addRow("", self._dc_strategy_desc)

        self._gmin_widget = QWidget()
        gmin_layout = self._create_form_layout()
        gmin_layout.setContentsMargins(0, 0, 0, 0)

        self._gmin_initial_spin = QDoubleSpinBox()
        self._gmin_initial_spin.setDecimals(6)
        self._gmin_initial_spin.setRange(1e-6, 1.0)
        self._gmin_initial_spin.setValue(1e-3)
        gmin_layout.addRow("GMIN initial:", self._gmin_initial_spin)

        self._gmin_final_spin = QDoubleSpinBox()
        self._gmin_final_spin.setDecimals(15)
        self._gmin_final_spin.setRange(1e-15, 1e-6)
        self._gmin_final_spin.setValue(1e-12)
        gmin_layout.addRow("GMIN final:", self._gmin_final_spin)

        self._gmin_widget.setLayout(gmin_layout)
        form.addRow(self._gmin_widget)

        self._source_widget = QWidget()
        source_layout = self._create_form_layout()
        source_layout.setContentsMargins(0, 0, 0, 0)

        self._source_steps_spin = QSpinBox()
        self._source_steps_spin.setRange(1, 500)
        self._source_steps_spin.setValue(10)
        source_layout.addRow("Source steps:", self._source_steps_spin)

        self._source_widget.setLayout(source_layout)
        form.addRow(self._source_widget)

        layout.addLayout(form)
        return card

    def _create_card(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("cardSubtitle")
        layout.addWidget(subtitle_label)

        return card, layout

    @staticmethod
    def _create_form_layout() -> QFormLayout:
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        return form

    def _create_footer(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self._reset_button = QPushButton("Reset to Defaults")
        self._reset_button.setObjectName("linkButton")
        self._reset_button.clicked.connect(self._on_reset_defaults)
        layout.addWidget(self._reset_button)

        layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("applyButton")
        apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(apply_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("runButton")
        ok_btn.clicked.connect(self._on_accept)
        layout.addWidget(ok_btn)

        return layout

    def _create_backend_banner(self) -> QWidget:
        banner = QFrame()
        banner.setObjectName("backendBanner")
        grid = QGridLayout(banner)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)

        self._backend_name_label = QLabel("-")
        self._backend_name_label.setObjectName("backendValue")
        self._backend_version_label = QLabel("-")
        self._backend_version_label.setObjectName("backendValue")
        self._backend_status_label = QLabel("-")
        self._backend_status_label.setObjectName("backendValue")
        self._backend_status_label.setWordWrap(True)
        self._backend_capabilities_label = QLabel("-")
        self._backend_capabilities_label.setObjectName("backendValue")
        self._backend_capabilities_label.setWordWrap(True)
        self._backend_warning_label = QLabel(self._backend_warning or "")
        self._backend_warning_label.setObjectName("backendWarning")
        self._backend_warning_label.setWordWrap(True)
        self._backend_warning_label.setVisible(bool(self._backend_warning))

        rows = [
            ("Backend:", self._backend_name_label),
            ("Version:", self._backend_version_label),
            ("Status:", self._backend_status_label),
            ("Capabilities:", self._backend_capabilities_label),
            ("Warning:", self._backend_warning_label),
        ]
        for row, (label_text, value_label) in enumerate(rows):
            key = QLabel(label_text)
            key.setObjectName("backendKey")
            key.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(key, row, 0)
            grid.addWidget(value_label, row, 1)

        self._refresh_backend_banner()
        return banner

    def _refresh_backend_banner(self) -> None:
        info = self._backend_info
        if not info:
            self._backend_name_label.setText("No backend detected")
            self._backend_version_label.setText("-")
            self._backend_status_label.setText(
                self._backend_warning or "Install Pulsim to enable simulations."
            )
            self._backend_capabilities_label.setText("-")
            return

        self._backend_name_label.setText(info.name or info.identifier)
        self._backend_version_label.setText(info.version or "-")
        status = info.message or info.status or "available"
        self._backend_status_label.setText(status)

        if info.capabilities:
            capabilities_text = ", ".join(sorted(info.capabilities))
            if hasattr(info, "unavailable_features") and info.unavailable_features:
                unavailable = ", ".join(info.unavailable_features)
                capabilities_text += f" (unavailable: {unavailable})"
            self._backend_capabilities_label.setText(capabilities_text)
        else:
            self._backend_capabilities_label.setText("-")

        if hasattr(info, "compatibility_warning") and info.compatibility_warning:
            self._backend_warning_label.setText(info.compatibility_warning)
            self._backend_warning_label.setVisible(True)
        elif self._backend_warning:
            self._backend_warning_label.setText(self._backend_warning)
            self._backend_warning_label.setVisible(True)
        else:
            self._backend_warning_label.setVisible(False)

    def _on_reset_defaults(self) -> None:
        defaults = SimulationSettings()
        self._populate_from(defaults)

    def _load_settings(self) -> None:
        self._populate_from(self._settings)

    def _populate_from(self, source: SimulationSettings) -> None:
        self._t_start_edit.value = source.t_start
        self._t_stop_edit.value = source.t_stop
        self._t_step_edit.value = source.t_step

        solver_value = normalize_integration_method(source.solver)
        solver_idx = self._solver_combo.findData(solver_value)
        self._solver_combo.setCurrentIndex(solver_idx if solver_idx >= 0 else 0)

        step_mode_value = normalize_step_mode(getattr(source, "step_mode", "fixed"))
        step_mode_idx = self._step_mode_combo.findData(step_mode_value)
        self._step_mode_combo.setCurrentIndex(step_mode_idx if step_mode_idx >= 0 else 0)

        self._max_step_edit.value = source.max_step
        self._rel_tol_spin.setValue(source.rel_tol)
        self._abs_tol_spin.setValue(source.abs_tol)

        self._max_iterations_spin.setValue(source.max_newton_iterations)
        self._voltage_limiting_check.setChecked(source.enable_voltage_limiting)
        self._max_voltage_step_spin.setValue(source.max_voltage_step)
        self._max_voltage_step_spin.setEnabled(source.enable_voltage_limiting)
        self._transient_robust_mode_check.setChecked(source.transient_robust_mode)
        self._transient_auto_regularize_check.setChecked(source.transient_auto_regularize)
        self._transient_auto_regularize_check.setEnabled(source.transient_robust_mode)

        dc_strategy_map = {"auto": 0, "direct": 1, "gmin": 2, "source": 3, "pseudo": 4}
        self._dc_strategy_combo.setCurrentIndex(dc_strategy_map.get(source.dc_strategy, 0))
        self._gmin_initial_spin.setValue(source.gmin_initial)
        self._gmin_final_spin.setValue(source.gmin_final)
        self._source_steps_spin.setValue(source.dc_source_steps)

        self._output_points_spin.setValue(source.output_points)
        self._enable_events_check.setChecked(bool(getattr(source, "enable_events", True)))
        self._max_step_retries_spin.setValue(max(0, int(getattr(source, "max_step_retries", 8))))

        self._update_solver_description()
        self._update_dc_strategy_description()
        self._on_dc_strategy_changed(self._dc_strategy_combo.currentIndex())
        self._update_effective_step()
        self._sync_preset_to_values()

    def _sync_preset_to_values(self) -> None:
        method = str(self._solver_combo.currentData() or "auto")
        if method in {"bdf2", "bdf3", "bdf4", "bdf5", "gear", "trbdf2", "rosenbrockw", "sdirk2"}:
            preset = "switching"
        elif self._output_points_spin.value() >= 50_000:
            preset = "switching"
        elif method in {"auto", "trapezoidal", "bdf1"} and self._rel_tol_spin.value() >= 1e-4:
            preset = "fast_preview"
        else:
            preset = "accurate"
        self._on_preset_selected(preset)

    def _on_apply(self) -> None:
        self._store_settings()
        self.settings_applied.emit()

    def _on_accept(self) -> None:
        """Apply settings and close."""
        self._store_settings()
        self.accept()

    def _store_settings(self) -> None:
        self._commit_pending_inputs()

        self._settings.t_start = self._t_start_edit.value
        self._settings.t_stop = self._t_stop_edit.value
        self._settings.t_step = self._t_step_edit.value

        self._settings.solver = normalize_integration_method(
            str(self._solver_combo.currentData() or "auto")
        )
        self._settings.step_mode = normalize_step_mode(
            str(self._step_mode_combo.currentData() or "fixed")
        )

        self._settings.max_step = self._max_step_edit.value
        self._settings.rel_tol = self._rel_tol_spin.value()
        self._settings.abs_tol = self._abs_tol_spin.value()

        self._settings.max_newton_iterations = self._max_iterations_spin.value()
        self._settings.enable_voltage_limiting = self._voltage_limiting_check.isChecked()
        self._settings.max_voltage_step = self._max_voltage_step_spin.value()
        self._settings.transient_robust_mode = self._transient_robust_mode_check.isChecked()
        self._settings.transient_auto_regularize = (
            self._transient_auto_regularize_check.isChecked()
            and self._transient_robust_mode_check.isChecked()
        )

        dc_strategy_map = {0: "auto", 1: "direct", 2: "gmin", 3: "source", 4: "pseudo"}
        self._settings.dc_strategy = dc_strategy_map.get(self._dc_strategy_combo.currentIndex(), "auto")
        self._settings.gmin_initial = self._gmin_initial_spin.value()
        self._settings.gmin_final = self._gmin_final_spin.value()
        self._settings.dc_source_steps = self._source_steps_spin.value()

        self._settings.output_points = self._output_points_spin.value()
        self._settings.enable_events = self._enable_events_check.isChecked()
        self._settings.max_step_retries = self._max_step_retries_spin.value()

    def _commit_pending_inputs(self) -> None:
        """Commit text still being edited before reading values."""
        for edit in (
            self._t_start_edit,
            self._t_stop_edit,
            self._t_step_edit,
            self._max_step_edit,
        ):
            edit.commit_pending_value()

        for spin in self.findChildren(QAbstractSpinBox):
            spin.interpretText()

    def _set_duration_preset(self, duration: float) -> None:
        """Set stop time to a preset duration."""
        self._t_start_edit.value = 0
        self._t_stop_edit.value = duration
        self._t_step_edit.value = duration / 1000
        self._update_effective_step()

    def _update_solver_description(self) -> None:
        """Update solver description based on selection."""
        descriptions = {
            "auto": "Backend selects the most robust default integrator.",
            "trapezoidal": "General-purpose method with good speed/accuracy balance.",
            "bdf1": "First-order implicit method; stable but more diffusive.",
            "bdf2": "Second-order implicit method for stiff switched circuits.",
            "bdf3": "Higher-order BDF for stiff systems with smooth intervals.",
            "bdf4": "Higher-order BDF prioritizing stability in stiff transients.",
            "bdf5": "Highest BDF order; use when stiff dynamics dominate.",
            "gear": "Gear integration; robust for hard-switching and stiff models.",
            "trbdf2": "TR-BDF2 blend with strong stiffness handling.",
            "rosenbrockw": "Linearly implicit stiff solver with adaptive behavior.",
            "sdirk2": "Second-order SDIRK method for difficult stiff dynamics.",
        }
        method = str(self._solver_combo.currentData() or "auto")
        self._solver_desc.setText(descriptions.get(method, descriptions["auto"]))

    def _update_dc_strategy_description(self) -> None:
        """Update DC strategy description based on selection."""
        descriptions = [
            "Select best DC method automatically.",
            "Direct Newton-Raphson for simpler circuits.",
            "Reduce GMIN progressively for nonlinear junction-heavy designs.",
            "Ramp sources gradually to stabilize hard startup points.",
            "Use pseudo-transient progression to reach operating point.",
        ]
        idx = self._dc_strategy_combo.currentIndex()
        self._dc_strategy_desc.setText(descriptions[idx] if idx < len(descriptions) else "")

    def _on_dc_strategy_changed(self, index: int) -> None:
        """Show/hide GMIN parameters based on strategy."""
        self._gmin_widget.setVisible(index == 2)
        self._source_widget.setVisible(index == 3)
        self._update_dc_strategy_description()

    def _update_effective_step(self) -> None:
        """Update effective step display."""
        duration = self._t_stop_edit.value - self._t_start_edit.value
        points = self._output_points_spin.value()
        if points > 0 and duration > 0:
            step = duration / points
            from pulsimgui.utils.si_prefix import format_si_value

            self._effective_step_label.setText(format_si_value(step, "s"))
        else:
            self._effective_step_label.setText("-")

    def get_settings(self) -> SimulationSettings:
        """Get the configured settings."""
        return self._settings

    @staticmethod
    def _mix(color: str, amount: float) -> str:
        base = QColor(color)
        if not base.isValid():
            return color
        amt = max(0.0, min(1.0, amount))
        r = int(base.red() + (255 - base.red()) * amt)
        g = int(base.green() + (255 - base.green()) * amt)
        b = int(base.blue() + (255 - base.blue()) * amt)
        return f"rgb({r}, {g}, {b})"

    def _apply_dialog_style(self) -> None:
        is_dark_theme = True
        if self._theme is not None:
            c = self._theme.colors
            bg = c.background
            panel = c.panel_background
            panel_alt = c.panel_header
            border = c.panel_border
            text = c.foreground
            muted = c.foreground_muted
            input_bg = c.input_background
            input_border = c.input_border
            focus = c.primary
            primary = c.primary
            primary_hover = c.primary_hover
            primary_fg = c.primary_foreground
            warning = c.warning
            is_dark_theme = self._theme.is_dark
        else:
            bg = "#0d1624"
            panel = "#121f30"
            panel_alt = "#1a2a3f"
            border = "#2b405c"
            text = "#dce8f8"
            muted = "#96abca"
            input_bg = "#101a28"
            input_border = "#31455f"
            focus = "#33b1ff"
            primary = "#33b1ff"
            primary_hover = "#57c0ff"
            primary_fg = "#04111c"
            warning = "#f7c948"
            is_dark_theme = True

        card_bg = self._mix(panel, 0.06)
        chip_bg = self._mix(panel_alt, 0.08)
        primary_q = QColor(primary)
        hover_bg = (
            self._mix(primary, 0.90)
            if is_dark_theme
            else f"rgba({primary_q.red()}, {primary_q.green()}, {primary_q.blue()}, 26)"
        )
        checked_bg = (
            f"rgba({primary_q.red()}, {primary_q.green()}, {primary_q.blue()},"
            f" {52 if is_dark_theme else 34})"
        )

        self.setStyleSheet(
            f"""
QDialog#simulationSettingsDialog {{
    background-color: {bg};
}}

QScrollArea#simSettingsScrollArea,
QWidget#simSettingsScrollContent {{
    background-color: transparent;
    border: none;
}}

QScrollArea#simSettingsScrollArea::corner {{
    background: transparent;
}}

QFrame#simSettingsPanel {{
    background-color: {panel};
    border: 1px solid {border};
    border-radius: 12px;
    background-clip: padding;
}}

QLabel#dialogTitle {{
    color: {text};
    font-size: 20px;
    font-weight: 700;
}}

QLabel#dialogSubtitle {{
    color: {muted};
    font-size: 11px;
}}

QFrame#simDivider {{
    border: none;
    min-height: 1px;
    max-height: 1px;
    background-color: {border};
}}

QLabel#sectionLabel {{
    color: {muted};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}

QFrame#backendBanner {{
    background-color: {panel_alt};
    border: 1px solid {border};
    border-radius: 10px;
}}

QLabel#backendKey {{
    color: {muted};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#backendValue {{
    color: {text};
    font-size: 11px;
}}

QLabel#backendWarning {{
    color: {warning};
    font-size: 11px;
}}

QPushButton#presetCard {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: 10px;
    background-clip: padding;
    color: {text};
    font-size: 11px;
    font-weight: 650;
    text-align: left;
    padding: 9px;
    min-height: 62px;
}}

QPushButton#presetCard:hover {{
    background-color: {hover_bg};
    border-color: {focus};
    color: {text};
}}

QPushButton#presetCard:checked {{
    background-color: {checked_bg};
    border-color: {focus};
    color: {text};
}}

QPushButton#presetCard:pressed {{
    background-color: {checked_bg};
    border-color: {focus};
    color: {text};
}}

QFrame#settingsCard {{
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: 10px;
    background-clip: padding;
}}

QLabel#cardTitle {{
    color: {text};
    font-size: 12px;
    font-weight: 700;
}}

QLabel#cardSubtitle {{
    color: {muted};
    font-size: 11px;
}}

QLabel#fieldHint {{
    color: {muted};
    font-size: 11px;
}}

QLabel#effectiveStepValue {{
    color: {focus};
    font-weight: 700;
}}

QFrame#advancedBody {{
    background-color: {panel_alt};
    border: 1px solid {border};
    border-radius: 10px;
    background-clip: padding;
}}

QToolButton#advancedToggle {{
    color: {text};
    background-color: {card_bg};
    border: 1px solid {border};
    border-radius: 10px;
    background-clip: padding;
    font-size: 11px;
    font-weight: 650;
    text-align: left;
    padding: 6px 9px;
}}

QToolButton#advancedToggle:hover {{
    border-color: {focus};
}}

QPushButton#presetChip {{
    background-color: {chip_bg};
    border: 1px solid {border};
    border-radius: 8px;
    background-clip: padding;
    color: {text};
    font-size: 10px;
    font-weight: 650;
    min-height: 22px;
    padding: 1px 8px;
}}

QPushButton#presetChip:hover {{
    border-color: {focus};
}}

QPushButton#linkButton {{
    background: transparent;
    border: none;
    color: {focus};
    font-weight: 600;
    padding: 4px 2px;
    text-align: left;
}}

QPushButton#linkButton:hover {{
    color: {primary_hover};
}}

QPushButton#cancelButton,
QPushButton#applyButton {{
    background-color: {chip_bg};
    border: 1px solid {border};
    border-radius: 9px;
    background-clip: padding;
    color: {text};
    min-height: 30px;
    min-width: 84px;
    font-weight: 650;
}}

QPushButton#cancelButton:hover,
QPushButton#applyButton:hover {{
    border-color: {focus};
}}

QPushButton#runButton {{
    background-color: {primary};
    border: 1px solid {primary};
    border-radius: 9px;
    background-clip: padding;
    color: {primary_fg};
    min-height: 30px;
    min-width: 126px;
    font-weight: 700;
}}

QPushButton#runButton:hover {{
    background-color: {primary_hover};
}}

QDialog#simulationSettingsDialog QLineEdit,
QDialog#simulationSettingsDialog QTextEdit,
QDialog#simulationSettingsDialog QPlainTextEdit,
QDialog#simulationSettingsDialog QSpinBox,
QDialog#simulationSettingsDialog QDoubleSpinBox,
QDialog#simulationSettingsDialog QComboBox {{
    background-color: {input_bg};
    border: 1px solid {input_border};
    border-radius: 8px;
    background-clip: padding;
    color: {text};
    padding: 5px 8px;
}}

QDialog#simulationSettingsDialog QLineEdit:focus,
QDialog#simulationSettingsDialog QSpinBox:focus,
QDialog#simulationSettingsDialog QDoubleSpinBox:focus,
QDialog#simulationSettingsDialog QComboBox:focus {{
    border-color: {focus};
}}

QDialog#simulationSettingsDialog QCheckBox {{
    color: {text};
    spacing: 6px;
}}

QDialog#simulationSettingsDialog QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid {input_border};
    background-color: {input_bg};
}}

QDialog#simulationSettingsDialog QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
}}
"""
        )
