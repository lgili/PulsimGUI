"""Simulation settings dialog."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.resources.icons import IconService
from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.simulation_service import (
    SimulationSettings,
    normalize_formulation_mode,
    normalize_frequency_anchor_mode,
    normalize_frequency_sweep_scale,
    normalize_integration_method,
    normalize_step_mode,
    normalize_thermal_policy,
)
from pulsimgui.services.theme_service import Theme
from pulsimgui.utils.si_prefix import format_si_value
from pulsimgui.views.properties import SILineEdit


class SimulationSettingsDialog(QDialog):
    """Dialog for configuring simulation settings."""

    settings_applied = Signal()
    #: Emitted when the user chooses "Save & Run" — the host window
    #: applies the settings (normal accept path) and then triggers the
    #: run action. ``run_after_accept`` carries the same fact for
    #: callers using the modal ``exec()`` result.
    run_requested = Signal()

    # Pulsim 1.5+ uses a discrete-time PWL state-space simulator; the
    # only integration scheme implemented is trapezoidal. The retired
    # BDF1-5 / Gear / TRBDF2 / RosenbrockW / SDIRK2 options are not in
    # the kernel anymore, so we don't expose them. ``Auto`` is kept as
    # an alias for trapezoidal so legacy projects with ``solver="auto"``
    # keep loading without warnings.
    # Surfaces the integration schemes that round-trip through
    # SimulationSettings.solver. ``normalize_integration_method`` (in
    # simulation_service) maps legacy aliases (rk4/rk45 → trapezoidal,
    # bdf → bdf2) onto these canonical values, so the combo's
    # ``findData`` always lands on a row when loading old projects.
    _INTEGRATION_OPTIONS: tuple[tuple[str, str], ...] = (
        ("Auto (let backend choose)", "auto"),
        ("Trapezoidal", "trapezoidal"),
        ("BDF1 (Backward Euler)", "bdf1"),
        ("BDF2 (2nd-order BDF)", "bdf2"),
        ("TR-BDF2 (hybrid)", "trbdf2"),
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
        switching_frequencies: list[float] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._backend_info = backend_info
        self._backend_warning = backend_warning
        self._theme = theme
        self._preset_cards: dict[str, QPushButton] = {}
        self._selected_preset = "accurate"
        # Switching frequencies harvested from the circuit (PWM
        # generators, pulse sources). Drives the dt-aliasing check on
        # the Solver page; empty list disables it.
        self._switching_frequencies = [
            float(f) for f in (switching_frequencies or []) if f and f > 0
        ]
        self._alias_suggested_dt = 0.0
        #: True after "Save & Run" — hosts check it after ``exec()``.
        self.run_after_accept = False

        self.setObjectName("simulationSettingsDialog")
        self.setWindowTitle("Simulation Settings")
        self.setMinimumSize(700, 520)

        self._setup_ui()
        self._load_settings()
        self._apply_dialog_style()

    def _setup_ui(self) -> None:
        """Set up the dialog UI with PLECS-style nav + content layout."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Main split: nav sidebar | content pages ───────────────────────
        main_widget = QWidget()
        main_widget.setObjectName("simSettingsMain")
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        root_layout.addWidget(main_widget, 1)

        # Left navigation sidebar
        self._nav_panel = QFrame()
        self._nav_panel.setObjectName("simSettingsNav")
        self._nav_panel.setFixedWidth(178)
        nav_layout = QVBoxLayout(self._nav_panel)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        nav_title = QLabel("Simulation\nSettings")
        nav_title.setObjectName("simNavTitle")
        nav_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        nav_title.setContentsMargins(14, 16, 10, 12)
        nav_layout.addWidget(nav_title)

        self._nav_buttons: list[QPushButton] = []

        def _nav_btn(label: str, icon_name: str) -> QPushButton:
            # "&" in QPushButton text declares a mnemonic and renders
            # as an underline — double it so "Thermal & Losses" shows
            # its ampersand. ``navLabel`` keeps the logical name for
            # tests and tooling.
            btn = QPushButton(label.replace("&", "&&"))
            btn.setObjectName("simNavBtn")
            btn.setProperty("navLabel", label)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setProperty("iconName", icon_name)
            btn.setIconSize(QSize(14, 14))
            index = len(self._nav_buttons)
            btn.clicked.connect(partial(self._on_nav_clicked, index))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)
            return btn

        # Order must match the ``_content_stack`` page order below.
        _nav_btn("General", "sliders-horizontal")
        _nav_btn("Solver", "engine")
        _nav_btn("Output", "waveform")
        _nav_btn("Events", "zap")

        adv_header = QLabel("ADVANCED")
        adv_header.setObjectName("simNavSection")
        adv_header.setContentsMargins(14, 14, 10, 4)
        nav_layout.addWidget(adv_header)

        _nav_btn("Transient", "activity")
        _nav_btn("DC Setup", "crosshair-simple")
        _nav_btn("Thermal & Losses", "thermometer")
        _nav_btn("Frequency Analysis", "wave")
        _nav_btn("Solver Stack", "layers")

        nav_layout.addStretch()
        main_layout.addWidget(self._nav_panel)

        nav_sep = QFrame()
        nav_sep.setObjectName("simNavSeparator")
        nav_sep.setFrameShape(QFrame.Shape.VLine)
        nav_sep.setFixedWidth(1)
        main_layout.addWidget(nav_sep)

        # Right stacked content pages
        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("simSettingsContent")
        self._content_stack.addWidget(self._wrap_page(self._build_general_page()))
        self._content_stack.addWidget(self._wrap_page(self._build_solver_page()))
        self._content_stack.addWidget(self._wrap_page(self._build_output_page()))
        self._content_stack.addWidget(self._wrap_page(self._build_events_page()))
        # Advanced sections — previously a nested QTabWidget on an
        # "Advanced" page; now first-class nav entries so no settings
        # hide two levels deep. The card builders are unchanged.
        for title, card in (
            ("Transient", self._create_newton_card()),
            ("DC Setup", self._create_dc_card()),
            ("Thermal & Losses", self._create_thermal_card()),
            ("Frequency Analysis", self._create_frequency_card()),
            ("Solver Stack", self._create_solver_stack_card()),
        ):
            self._content_stack.addWidget(
                self._wrap_page(self._build_advanced_subpage(title, card))
            )
        main_layout.addWidget(self._content_stack, 1)

        # ── Footer ────────────────────────────────────────────────────────
        footer_widget = QWidget()
        footer_widget.setObjectName("simSettingsFooter")
        footer_container = QVBoxLayout(footer_widget)
        footer_container.setContentsMargins(16, 6, 16, 8)
        footer_container.setSpacing(0)
        footer_container.addLayout(self._create_footer())
        root_layout.addWidget(footer_widget)

        self._connect_cross_page_signals()
        self._on_nav_clicked(0)
        self._apply_capability_gates()

    @staticmethod
    def _wrap_page(content: QWidget) -> QScrollArea:
        """Wrap a page widget in a scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _on_nav_clicked(self, index: int) -> None:
        self._content_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)
        self._refresh_nav_icons()

    def _refresh_nav_icons(self) -> None:
        """Tint nav icons — active entry gets the accent color.

        Icon names ride on each button's ``iconName`` property (set at
        construction); colors come from ``_apply_dialog_style``. Safe
        to call before styling: falls back to neutral grays.
        """
        colors = getattr(self, "_nav_icon_colors", None)
        if colors is None:
            # First _apply_dialog_style call hasn't run yet; it ends
            # with a _refresh_nav_icons() so icons appear then.
            return
        muted, active = colors
        for btn in self._nav_buttons:
            name = btn.property("iconName")
            if not name:
                continue
            color = active if btn.isChecked() else muted
            btn.setIcon(IconService.get_icon(str(name), color))

    def _connect_cross_page_signals(self) -> None:
        self._t_stop_edit.value_changed.connect(lambda _: self._update_effective_step())
        self._t_start_edit.value_changed.connect(lambda _: self._update_effective_step())
        self._t_stop_edit.value_changed.connect(lambda _: self._update_run_estimate())
        self._t_start_edit.value_changed.connect(lambda _: self._update_run_estimate())
        self._t_step_edit.value_changed.connect(lambda _: self._update_run_estimate())

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("General")
        title.setObjectName("simPageTitle")
        layout.addWidget(title)

        preset_section = QLabel("QUICK PRESETS")
        preset_section.setObjectName("simSectionLabel")
        layout.addWidget(preset_section)

        layout.addLayout(self._create_preset_cards())

        if self._backend_info is not None or self._backend_warning:
            backend_section = QLabel("BACKEND")
            backend_section.setObjectName("simSectionLabel")
            layout.addWidget(backend_section)
            layout.addWidget(self._create_backend_banner())

        layout.addStretch()
        return page

    def _build_solver_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Solver")
        title.setObjectName("simPageTitle")
        layout.addWidget(title)

        form = self._create_form_layout()

        # ── Engine selector (pulsim 1.6) ─────────────────────────────
        # PWL is the v1.4-compatible fixed-step path (uses Step size
        # below). DSED is the Path-Based Event-Driven variable-step
        # engine added in pulsim 1.6.0 — ~24× faster than PWL on buck
        # CCM, but ignores the fixed Step size and uses rtol/atol +
        # adaptive RK45/BDF2 dispatch instead.
        self._engine_combo = QComboBox()
        self._engine_combo.addItem("PWL  —  fixed-step trapezoidal (v1.4-compat)", "pwl")
        self._engine_combo.addItem("DSED — variable-step + event prediction (v1.6+)", "dsed")
        self._engine_combo.currentIndexChanged.connect(self._update_solver_description)
        self._engine_combo.currentIndexChanged.connect(self._apply_engine_visibility)
        self._engine_combo.currentIndexChanged.connect(self._sync_engine_segment)
        self._engine_combo.currentIndexChanged.connect(
            lambda _i: self._update_run_estimate()
        )
        # The combo stays as the value store (tests and persistence
        # drive it via findData/currentData); the visible control is
        # the segmented row below.
        self._engine_combo.setParent(page)
        self._engine_combo.hide()
        form.addRow("Engine:", self._create_engine_segment())

        # Integration method — for the PWL engine. Hidden when DSED
        # is selected (DSED has its own integrator selector below).
        self._solver_combo = QComboBox()
        for label_text, value in self._INTEGRATION_OPTIONS:
            self._solver_combo.addItem(label_text, value)
        self._solver_combo.currentIndexChanged.connect(self._update_solver_description)
        self._solver_label = QLabel("Integration method:")
        form.addRow(self._solver_label, self._solver_combo)

        # Step mode is hidden in the current GUI (pulsim 1.5 is
        # fixed-step PWL only), but BOTH options need to be in the
        # combo so legacy projects with step_mode="variable" round-trip
        # through the dialog without dropping the value silently —
        # findData("variable") otherwise returns -1 and load falls
        # back to "fixed", which corrupts the user's saved setting.
        self._step_mode_combo = QComboBox()
        self._step_mode_combo.addItem("Fixed step", "fixed")
        self._step_mode_combo.addItem("Variable step", "variable")
        self._step_mode_combo.hide()

        self._solver_desc = QLabel("")
        self._solver_desc.setObjectName("fieldHint")
        self._solver_desc.setWordWrap(True)
        form.addRow("", self._solver_desc)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setObjectName("formSeparator")
        form.addRow(sep1)

        # ── Time window ─────────────────────────────────────────────
        self._t_start_edit = SILineEdit("s")
        form.addRow("Start time:", self._t_start_edit)

        self._t_step_edit = SILineEdit("s")
        form.addRow("Step size (dt):", self._t_step_edit)

        self._t_stop_edit = SILineEdit("s")
        form.addRow("Stop time:", self._t_stop_edit)

        self._run_estimate_label = QLabel("\u2014")
        self._run_estimate_label.setObjectName("simRunEstimate")
        form.addRow("Run size:", self._run_estimate_label)

        # Aliasing banner — hidden until dt undersamples the fastest
        # harvested switching frequency (see _update_run_estimate).
        self._alias_banner = QFrame()
        self._alias_banner.setObjectName("simAliasWarning")
        alias_row = QHBoxLayout(self._alias_banner)
        alias_row.setContentsMargins(10, 8, 10, 8)
        alias_row.setSpacing(10)
        self._alias_text = QLabel("")
        self._alias_text.setObjectName("simAliasText")
        self._alias_text.setWordWrap(True)
        alias_row.addWidget(self._alias_text, 1)
        self._alias_apply_btn = QPushButton("Apply")
        self._alias_apply_btn.setObjectName("aliasApplyBtn")
        self._alias_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._alias_apply_btn.clicked.connect(self._on_alias_apply)
        alias_row.addWidget(self._alias_apply_btn, 0)
        form.addRow(self._alias_banner)
        self._alias_banner.hide()

        # ``max_step`` only existed for the legacy variable-step path.
        # Keep the LineEdit hidden so legacy projects load without
        # raising AttributeError in ``_save_settings``.
        self._max_step_edit = SILineEdit("s")
        self._max_step_edit.hide()

        # ── DSED engine knobs (pulsim 1.6) ───────────────────────────
        # Shown only when ``engine='dsed'`` is selected above. Drives
        # ``simulate(engine='dsed', rtol=, atol=, dt_init=,
        # integrator=, stiffness_threshold=, h_bdf2=)``.
        sep_dsed = QFrame()
        sep_dsed.setFrameShape(QFrame.Shape.HLine)
        sep_dsed.setObjectName("formSeparator")
        form.addRow(sep_dsed)
        self._dsed_separator = sep_dsed

        self._dsed_section_label = QLabel("DSED variable-step controls")
        self._dsed_section_label.setObjectName("simSectionLabel")
        form.addRow(self._dsed_section_label)

        self._dsed_rtol_spin = QDoubleSpinBox()
        self._dsed_rtol_spin.setDecimals(12)
        self._dsed_rtol_spin.setRange(1e-12, 1e-2)
        self._dsed_rtol_spin.setSingleStep(1e-7)
        self._dsed_rtol_spin.setValue(1e-6)
        self._dsed_rtol_spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._dsed_rtol_spin.setToolTip(
            "Relative tolerance for the DSED PI step controller. "
            "Smaller → finer steps, more accuracy, slower. "
            "1e-6 is a sensible default for most SMPS work."
        )
        self._dsed_rtol_label = QLabel("Relative tolerance:")
        form.addRow(self._dsed_rtol_label, self._dsed_rtol_spin)

        self._dsed_atol_spin = QDoubleSpinBox()
        self._dsed_atol_spin.setDecimals(14)
        self._dsed_atol_spin.setRange(1e-15, 1e-4)
        self._dsed_atol_spin.setSingleStep(1e-10)
        self._dsed_atol_spin.setValue(1e-9)
        self._dsed_atol_spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._dsed_atol_spin.setToolTip(
            "Absolute tolerance for the DSED PI step controller. "
            "Floors the relative-tolerance check near zero state."
        )
        self._dsed_atol_label = QLabel("Absolute tolerance:")
        form.addRow(self._dsed_atol_label, self._dsed_atol_spin)

        self._dsed_integrator_combo = QComboBox()
        self._dsed_integrator_combo.addItem(
            "Auto (RK45/BDF2 per mode via stiffness detector)", "auto"
        )
        self._dsed_integrator_combo.addItem("RK45 (Dormand-Prince 5)", "rk45")
        self._dsed_integrator_combo.addItem("BDF2 (2nd-order backward)", "bdf2")
        self._dsed_integrator_combo.setToolTip(
            "DSED integrator override. ``Auto`` lets the stiffness "
            "detector pick RK45 for non-stiff modes (PWM-driven SMPS, "
            "filter coast) and BDF2 for stiff ones (heavy snubbers). "
            "Force one for debug / repeatability."
        )
        self._dsed_integrator_label = QLabel("DSED integrator:")
        form.addRow(self._dsed_integrator_label, self._dsed_integrator_combo)

        self._dsed_dt_init_edit = SILineEdit("s")
        self._dsed_dt_init_edit.value = 1e-9
        self._dsed_dt_init_label = QLabel("Initial step:")
        form.addRow(self._dsed_dt_init_label, self._dsed_dt_init_edit)

        self._dsed_h_bdf2_edit = SILineEdit("s")
        self._dsed_h_bdf2_edit.value = 1e-6
        self._dsed_h_bdf2_label = QLabel("BDF2 step:")
        form.addRow(self._dsed_h_bdf2_label, self._dsed_h_bdf2_edit)

        self._dsed_stiffness_spin = QDoubleSpinBox()
        self._dsed_stiffness_spin.setDecimals(3)
        self._dsed_stiffness_spin.setRange(0.0, 1000.0)
        self._dsed_stiffness_spin.setValue(10.0)
        self._dsed_stiffness_spin.setSingleStep(1.0)
        self._dsed_stiffness_spin.setToolTip(
            "|λ_max|·h ratio above which the auto-dispatcher switches "
            "to BDF2 instead of RK45. Higher → more aggressive "
            "stiffness threshold (favors RK45). Default 10.0."
        )
        self._dsed_stiffness_label = QLabel("Stiffness threshold:")
        form.addRow(self._dsed_stiffness_label, self._dsed_stiffness_spin)

        self._dsed_widgets = [
            self._dsed_separator,
            self._dsed_section_label,
            self._dsed_rtol_label,
            self._dsed_rtol_spin,
            self._dsed_atol_label,
            self._dsed_atol_spin,
            self._dsed_integrator_label,
            self._dsed_integrator_combo,
            self._dsed_dt_init_label,
            self._dsed_dt_init_edit,
            self._dsed_h_bdf2_label,
            self._dsed_h_bdf2_edit,
            self._dsed_stiffness_label,
            self._dsed_stiffness_spin,
        ]

        # rel/abs tolerance: also legacy variable-step controls.
        # NOTE: ``setDecimals`` MUST come before ``setValue`` — QDoubleSpinBox
        # defaults to 2 decimal places, which silently rounds 1e-4 → 0.00
        # and 1e-6 → 0.00. Hidden ≠ value-less; ``_save_settings`` reads
        # these and writes them back to ``SimulationSettings``.
        self._rel_tol_spin = QDoubleSpinBox()
        self._rel_tol_spin.setDecimals(10)
        self._rel_tol_spin.setRange(1e-10, 1e-1)
        self._rel_tol_spin.setValue(1e-4)
        self._rel_tol_spin.hide()
        self._abs_tol_spin = QDoubleSpinBox()
        self._abs_tol_spin.setDecimals(12)
        self._abs_tol_spin.setRange(1e-12, 1e-3)
        self._abs_tol_spin.setValue(1e-6)
        self._abs_tol_spin.hide()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("formSeparator")
        form.addRow(sep2)

        # ── Initial state ───────────────────────────────────────────
        self._start_from_dc_op_check = QCheckBox(
            "Start from DC operating point"
        )
        self._start_from_dc_op_check.setToolTip(
            "When checked, the simulation starts from the steady-state "
            "DC solution instead of an all-zero initial vector. Useful "
            "for fast transients where you only care about disturbances."
        )
        form.addRow("Initial state:", self._start_from_dc_op_check)

        layout.addLayout(form)
        layout.addStretch()
        return page

    def _create_engine_segment(self) -> QWidget:
        """Segmented PWL / DSED selector backed by ``_engine_combo``."""
        wrap = QWidget()
        wrap.setObjectName("simEngineSegment")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._engine_group = QButtonGroup(wrap)
        self._engine_group.setExclusive(True)
        self._engine_buttons: dict[str, QPushButton] = {}
        for key, label in (
            ("pwl", "PWL \u00b7 fixed-step"),
            ("dsed", "DSED \u00b7 variable-step"),
        ):
            btn = QPushButton(label)
            btn.setObjectName("simEngineSegmentItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(partial(self._on_engine_segment_clicked, key))
            self._engine_group.addButton(btn)
            self._engine_buttons[key] = btn
            row.addWidget(btn)
        row.addStretch()
        return wrap

    def _on_engine_segment_clicked(self, key: str) -> None:
        index = self._engine_combo.findData(key)
        if index >= 0:
            self._engine_combo.setCurrentIndex(index)

    def _sync_engine_segment(self) -> None:
        key = str(self._engine_combo.currentData() or "pwl")
        buttons = getattr(self, "_engine_buttons", None)
        if buttons and key in buttons:
            buttons[key].setChecked(True)

    def _update_run_estimate(self) -> None:
        """Refresh the run-size chip and the dt-aliasing banner.

        PWL is fixed-step: steps = window / dt, and the wall-clock
        estimate uses a deliberately rough 200k steps/s throughput —
        an order-of-magnitude hint, not a promise. DSED is adaptive,
        so the chip says so instead of inventing a number. The
        aliasing check compares dt against the fastest switching
        frequency harvested from the circuit: under 10 samples per
        switching cycle, edges start landing between steps and the
        waveform aliases; the suggestion targets 20 samples/cycle.
        """
        engine = str(self._engine_combo.currentData() or "pwl")
        if engine == "dsed":
            self._run_estimate_label.setText(
                "adaptive \u2014 step count set by rtol / atol"
            )
            self._alias_banner.hide()
            return
        window = self._t_stop_edit.value - self._t_start_edit.value
        dt = self._t_step_edit.value
        if window <= 0 or dt <= 0:
            self._run_estimate_label.setText("\u2014")
            self._alias_banner.hide()
            return
        steps = int(round(window / dt))
        est_seconds = steps / 2.0e5
        steps_txt = f"{steps:,}".replace(",", "\u2009")
        self._run_estimate_label.setText(
            f"\u2248 {steps_txt} steps \u00b7 est. "
            f"{format_si_value(est_seconds, 's')}"
        )
        f_max = max(self._switching_frequencies, default=0.0)
        if f_max > 0:
            samples_per_cycle = 1.0 / (f_max * dt)
            if samples_per_cycle < 10.0:
                self._alias_suggested_dt = 1.0 / (f_max * 20.0)
                self._alias_text.setText(
                    f"dt gives {samples_per_cycle:.1f} samples per "
                    f"switching cycle at {format_si_value(f_max, 'Hz')} "
                    f"\u2014 switching events may alias."
                )
                self._alias_apply_btn.setText(
                    f"Set dt = {format_si_value(self._alias_suggested_dt, 's')}"
                )
                self._alias_banner.show()
                return
        self._alias_banner.hide()

    def _on_alias_apply(self) -> None:
        if self._alias_suggested_dt > 0:
            self._t_step_edit.value = self._alias_suggested_dt
            self._update_run_estimate()

    def _build_output_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Output")
        title.setObjectName("simPageTitle")
        layout.addWidget(title)

        form = self._create_form_layout()

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

        dur_section = QLabel("DURATION PRESETS")
        dur_section.setObjectName("simSectionLabel")
        layout.addWidget(dur_section)

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

        layout.addStretch()
        return page

    def _build_events_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Events")
        title.setObjectName("simPageTitle")
        layout.addWidget(title)

        form = self._create_form_layout()

        self._enable_events_check = QCheckBox("Enable simulation event detection")
        self._enable_events_check.setChecked(True)
        form.addRow(self._enable_events_check)

        self._max_step_retries_spin = QSpinBox()
        self._max_step_retries_spin.setRange(0, 100)
        self._max_step_retries_spin.setValue(8)
        form.addRow("Max step retries:", self._max_step_retries_spin)

        layout.addLayout(form)
        layout.addStretch()
        return page

    def _build_advanced_subpage(self, title: str, card: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        page_title = QLabel(title)
        page_title.setObjectName("simPageTitle")
        layout.addWidget(page_title)

        layout.addWidget(card)
        layout.addStretch()
        return page

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

    def _create_newton_card(self) -> QWidget:
        card, layout = self._create_card(
            "Newton + Events",
            "Convergence controls forwarded to pulsim.simulate().",
            compact=True,
            show_header=False,
        )
        form = self._create_form_layout()
        form.setVerticalSpacing(6)

        self._max_iterations_spin = QSpinBox()
        self._max_iterations_spin.setRange(0, 500)
        self._max_iterations_spin.setValue(50)
        self._max_iterations_spin.setToolTip(
            "Maximum Newton iterations per timestep. 0 = kernel default."
        )
        form.addRow("Max Newton iterations:", self._max_iterations_spin)

        # New: explicit Newton tolerances (pulsim 1.5+ kwargs).
        self._tol_newton_dx_spin = QDoubleSpinBox()
        self._tol_newton_dx_spin.setDecimals(12)
        self._tol_newton_dx_spin.setRange(0.0, 1.0)
        self._tol_newton_dx_spin.setValue(0.0)  # 0 = use kernel default
        self._tol_newton_dx_spin.setSingleStep(1e-7)
        self._tol_newton_dx_spin.setStepType(
            QAbstractSpinBox.StepType.AdaptiveDecimalStepType,
        )
        self._tol_newton_dx_spin.setToolTip(
            "Convergence tolerance on |Δx| between iterations. "
            "0 = use pulsim's SimulationOptions default (~1e-9)."
        )
        form.addRow("Tol. Newton |Δx|:", self._tol_newton_dx_spin)

        self._tol_newton_res_spin = QDoubleSpinBox()
        self._tol_newton_res_spin.setDecimals(12)
        self._tol_newton_res_spin.setRange(0.0, 1.0)
        self._tol_newton_res_spin.setValue(0.0)
        self._tol_newton_res_spin.setSingleStep(1e-7)
        self._tol_newton_res_spin.setStepType(
            QAbstractSpinBox.StepType.AdaptiveDecimalStepType,
        )
        self._tol_newton_res_spin.setToolTip(
            "Convergence tolerance on the residual norm. "
            "0 = use pulsim's SimulationOptions default."
        )
        form.addRow("Tol. Newton residual:", self._tol_newton_res_spin)

        # New: line-search + Levenberg-Marquardt + sub-step correction.
        self._line_search_check = QCheckBox("Enable Newton line search")
        self._line_search_check.setToolTip(
            "Backtrack the Newton step when the residual increases. "
            "Improves robustness on stiff transitions."
        )
        self._line_search_check.setChecked(True)
        form.addRow(self._line_search_check)

        self._newton_lm_check = QCheckBox("Enable Levenberg-Marquardt")
        self._newton_lm_check.setToolTip(
            "Damp the Newton iteration with LM regularization. Off by "
            "default — turn on when seeing oscillating non-convergence."
        )
        form.addRow(self._newton_lm_check)

        self._substep_correction_check = QCheckBox(
            "Enable sub-step state correction"
        )
        self._substep_correction_check.setToolTip(
            "Refine intra-step states after switching events for "
            "tighter event capture. Default on."
        )
        self._substep_correction_check.setChecked(True)
        form.addRow(self._substep_correction_check)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("formSeparator")
        form.addRow(sep)

        # New: enable_nonlinear_refresh combo (auto / on / off).
        self._nonlinear_refresh_combo = QComboBox()
        self._nonlinear_refresh_combo.addItem(
            "Auto (detect from circuit)", "auto",
        )
        self._nonlinear_refresh_combo.addItem("Always on", "on")
        self._nonlinear_refresh_combo.addItem("Always off", "off")
        self._nonlinear_refresh_combo.setToolTip(
            "Nonlinear-refresh runs Newton per timestep. Auto turns "
            "it on only when the circuit has smooth-blend diodes, SH1 "
            "MOSFETs, IGBT level-1, or saturable inductors."
        )
        form.addRow("Nonlinear refresh:", self._nonlinear_refresh_combo)

        # New: max_event_iterations.
        self._max_event_iterations_spin = QSpinBox()
        self._max_event_iterations_spin.setRange(0, 200)
        self._max_event_iterations_spin.setValue(0)
        self._max_event_iterations_spin.setToolTip(
            "Maximum solver passes for a single switching event. "
            "0 = use pulsim's default."
        )
        form.addRow("Max event iterations:", self._max_event_iterations_spin)

        # ── LEGACY hidden widgets — kept so old projects load and
        # ``_save_settings`` doesn't AttributeError. None of these are
        # forwarded to pulsim 1.5+ anymore. They're parented to ``self``
        # (the dialog) so the C++ side stays alive even though they're
        # never added to any visible layout. ───────────────────────
        self._voltage_limiting_check = QCheckBox(self)
        self._voltage_limiting_check.hide()
        self._max_voltage_step_spin = QDoubleSpinBox(self)
        self._max_voltage_step_spin.setRange(0.1, 100.0)
        self._max_voltage_step_spin.setValue(5.0)
        self._max_voltage_step_spin.hide()
        # Spinbox enable state mirrors the limiting check — both for
        # the GUI (when these widgets are eventually surfaced) and for
        # tests that drive the checkbox programmatically.
        self._voltage_limiting_check.toggled.connect(
            self._max_voltage_step_spin.setEnabled
        )
        self._max_voltage_step_spin.setEnabled(
            self._voltage_limiting_check.isChecked()
        )
        self._transient_robust_mode_check = QCheckBox(self)
        self._transient_robust_mode_check.setChecked(True)
        self._transient_robust_mode_check.hide()
        self._transient_auto_regularize_check = QCheckBox(self)
        self._transient_auto_regularize_check.setChecked(True)
        self._transient_auto_regularize_check.hide()
        self._formulation_mode_combo = QComboBox(self)
        # Both formulation modes must be in the combo so legacy
        # projects with formulation_mode="direct" round-trip without
        # findData("direct") missing and falling back to index 0.
        self._formulation_mode_combo.addItem("projected_wrapper", "projected_wrapper")
        self._formulation_mode_combo.addItem("direct", "direct")
        self._formulation_mode_combo.hide()
        self._direct_formulation_fallback_check = QCheckBox(self)
        self._direct_formulation_fallback_check.setChecked(True)
        self._direct_formulation_fallback_check.hide()
        self._averaged_enabled_check = QCheckBox(self)
        self._averaged_enabled_check.hide()
        self._averaged_topology_combo = QComboBox(self)
        for v in ("buck", "boost", "buckboost", "flyback", "forward"):
            self._averaged_topology_combo.addItem(v, v)
        self._averaged_topology_combo.hide()
        self._averaged_mode_combo = QComboBox(self)
        for v in ("ccm", "auto"):
            self._averaged_mode_combo.addItem(v, v)
        self._averaged_mode_combo.hide()
        self._averaged_envelope_combo = QComboBox(self)
        for v in ("strict", "lenient", "ignore"):
            self._averaged_envelope_combo.addItem(v, v)
        self._averaged_envelope_combo.hide()

        layout.addLayout(form)
        return card

    def _create_dc_card(self) -> QWidget:
        card, layout = self._create_card(
            "DC Operating Point",
            "Fallback strategy before transient start.",
            compact=True,
            show_header=False,
        )
        form = self._create_form_layout()
        form.setVerticalSpacing(4)

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

    def _create_thermal_card(self) -> QWidget:
        card, layout = self._create_card(
            "Thermal & Losses",
            "Controls for thermal analysis fidelity.",
            compact=True,
            show_header=False,
        )
        form = self._create_form_layout()
        form.setVerticalSpacing(4)

        self._enable_losses_check = QCheckBox("Enable electrical loss tracking")
        self._enable_losses_check.setChecked(True)
        self._enable_losses_check.setToolTip("Expose loss telemetry used by thermal/loss post-processing.")
        form.addRow(self._enable_losses_check)

        self._thermal_ambient_spin = QDoubleSpinBox()
        self._thermal_ambient_spin.setRange(-80.0, 250.0)
        self._thermal_ambient_spin.setDecimals(1)
        self._thermal_ambient_spin.setSingleStep(1.0)
        self._thermal_ambient_spin.setSuffix(" °C")
        self._thermal_ambient_spin.setValue(25.0)
        form.addRow("Ambient temperature:", self._thermal_ambient_spin)

        self._thermal_network_combo = QComboBox()
        self._thermal_network_combo.addItem("Foster", "foster")
        self._thermal_network_combo.addItem("Cauer", "cauer")
        form.addRow("Thermal network:", self._thermal_network_combo)

        self._thermal_policy_combo = QComboBox()
        self._thermal_policy_combo.addItem("Loss + temperature scaling", "loss_with_temperature_scaling")
        self._thermal_policy_combo.addItem("Loss only", "loss_only")
        self._thermal_policy_combo.setToolTip(
            "Defines if losses are temperature-scaled during electrothermal coupling."
        )
        form.addRow("Coupling policy:", self._thermal_policy_combo)

        self._thermal_default_rth_spin = QDoubleSpinBox()
        self._thermal_default_rth_spin.setRange(0.0, 1e6)
        self._thermal_default_rth_spin.setDecimals(4)
        self._thermal_default_rth_spin.setSingleStep(0.1)
        self._thermal_default_rth_spin.setValue(1.0)
        self._thermal_default_rth_spin.setSuffix(" K/W")
        form.addRow("Default Rth:", self._thermal_default_rth_spin)

        self._thermal_default_cth_spin = QDoubleSpinBox()
        self._thermal_default_cth_spin.setRange(0.0, 1e6)
        self._thermal_default_cth_spin.setDecimals(4)
        self._thermal_default_cth_spin.setSingleStep(0.1)
        self._thermal_default_cth_spin.setValue(0.1)
        self._thermal_default_cth_spin.setSuffix(" J/K")
        form.addRow("Default Cth:", self._thermal_default_cth_spin)

        self._thermal_include_conduction_check = QCheckBox("Include conduction losses")
        self._thermal_include_conduction_check.setChecked(True)
        form.addRow(self._thermal_include_conduction_check)

        self._thermal_include_switching_check = QCheckBox("Include switching losses")
        self._thermal_include_switching_check.setChecked(True)
        form.addRow(self._thermal_include_switching_check)

        layout.addLayout(form)
        return card

    def _create_frequency_card(self) -> QWidget:
        card, layout = self._create_card(
            "Frequency Analysis",
            "Parameters used by AC/frequency sweep analysis.",
            compact=True,
            show_header=False,
        )
        form = self._create_form_layout()
        form.setVerticalSpacing(4)

        self._ac_start_freq_spin = QDoubleSpinBox()
        self._ac_start_freq_spin.setRange(1e-12, 1e12)
        self._ac_start_freq_spin.setDecimals(6)
        self._ac_start_freq_spin.setSingleStep(10.0)
        self._ac_start_freq_spin.setSuffix(" Hz")
        self._ac_start_freq_spin.setValue(1.0)
        form.addRow("Start frequency:", self._ac_start_freq_spin)

        self._ac_stop_freq_spin = QDoubleSpinBox()
        self._ac_stop_freq_spin.setRange(1e-12, 1e12)
        self._ac_stop_freq_spin.setDecimals(6)
        self._ac_stop_freq_spin.setSingleStep(1000.0)
        self._ac_stop_freq_spin.setSuffix(" Hz")
        self._ac_stop_freq_spin.setValue(1e6)
        form.addRow("Stop frequency:", self._ac_stop_freq_spin)

        self._ac_points_spin = QSpinBox()
        self._ac_points_spin.setRange(1, 1000)
        self._ac_points_spin.setValue(10)
        form.addRow("Points/decade:", self._ac_points_spin)

        self._ac_anchor_mode_combo = QComboBox()
        self._ac_anchor_mode_combo.addItem("Auto", "auto")
        self._ac_anchor_mode_combo.addItem("DC", "dc")
        self._ac_anchor_mode_combo.addItem("Periodic", "periodic")
        self._ac_anchor_mode_combo.addItem("Averaged", "averaged")
        form.addRow("Anchor mode:", self._ac_anchor_mode_combo)

        self._ac_sweep_scale_combo = QComboBox()
        self._ac_sweep_scale_combo.addItem("Decade", "decade")
        self._ac_sweep_scale_combo.addItem("Log", "log")
        self._ac_sweep_scale_combo.addItem("Linear", "linear")
        form.addRow("Sweep scale:", self._ac_sweep_scale_combo)

        self._ac_injection_node_edit = QLineEdit()
        self._ac_injection_node_edit.setPlaceholderText("vin,0")
        form.addRow("Injection node:", self._ac_injection_node_edit)

        self._ac_measurement_node_edit = QLineEdit()
        self._ac_measurement_node_edit.setPlaceholderText("vout,0")
        form.addRow("Measurement node:", self._ac_measurement_node_edit)

        layout.addLayout(form)
        return card

    # ------------------------------------------------------------------
    # Wave-4 sub-A 1.6 — Solver Stack advanced tab
    # ------------------------------------------------------------------
    def _create_solver_stack_card(self) -> QWidget:
        """Advanced linear / iterative solver + BDF knobs.

        Only the most impactful four configs from the Pulsim solver
        suite are surfaced here in this commit:

        * ``LinearSolverStackConfig`` → linear solver combobox
          (auto / KLU / EnhancedSparseLU / GMRES / BiCGSTAB).
        * ``IterativeSolverConfig`` → max iterations + GMRES restart
          length for the iterative branches.
        * ``BDFOrderConfig`` → BDF max-order spinbox.

        The remaining suites (``GminConfig``, ``SourceSteppingConfig``,
        ``PseudoTransientConfig``, ``InitializationConfig``,
        ``DCConvergenceConfig``, ``RichardsonLTEConfig``,
        ``AdvancedTimestepConfig``) are deferred — they need backend
        plumbing the wave-4 spec marked as optional follow-up.
        """
        card, layout = self._create_card(
            "Solver Stack (Advanced)",
            "Choose how Pulsim factors and iterates the linear systems.",
            compact=True,
            show_header=False,
        )
        form = self._create_form_layout()
        form.setVerticalSpacing(4)

        self._linear_solver_combo = QComboBox()
        self._linear_solver_combo.addItem("Auto (let Pulsim choose)", "auto")
        self._linear_solver_combo.addItem("KLU (sparse direct, default)", "klu")
        self._linear_solver_combo.addItem(
            "Enhanced Sparse LU (robust)", "enhanced_sparse_lu"
        )
        self._linear_solver_combo.addItem(
            "GMRES (iterative, restarts)", "gmres"
        )
        self._linear_solver_combo.addItem(
            "BiCGSTAB (iterative, no restart)", "bicgstab"
        )
        self._linear_solver_combo.setToolTip(
            "Linear solver back-end. Direct solvers (KLU / EnhancedSparseLU) "
            "are usually fastest for small/medium circuits; iterative "
            "solvers help with very large or extremely sparse systems."
        )
        form.addRow("Linear solver:", self._linear_solver_combo)

        self._iterative_max_iter_spin = QSpinBox()
        self._iterative_max_iter_spin.setRange(10, 5000)
        self._iterative_max_iter_spin.setValue(200)
        self._iterative_max_iter_spin.setToolTip(
            "Maximum iterations per linear solve (GMRES / BiCGSTAB)."
        )
        form.addRow("Iterative max iter:", self._iterative_max_iter_spin)

        self._iterative_restart_spin = QSpinBox()
        self._iterative_restart_spin.setRange(5, 500)
        self._iterative_restart_spin.setValue(30)
        self._iterative_restart_spin.setToolTip(
            "GMRES restart length. Ignored by BiCGSTAB and direct solvers."
        )
        form.addRow("GMRES restart:", self._iterative_restart_spin)

        self._bdf_max_order_spin = QSpinBox()
        self._bdf_max_order_spin.setRange(1, 5)
        self._bdf_max_order_spin.setValue(5)
        self._bdf_max_order_spin.setToolTip(
            "Highest BDF order Pulsim is allowed to use. Lower values "
            "trade accuracy for stability on stiff circuits."
        )
        form.addRow("BDF max order:", self._bdf_max_order_spin)

        layout.addLayout(form)

        helper = QLabel(
            "Note: additional solver suites (Gmin / source stepping / "
            "pseudo-transient / Richardson LTE / Advanced timestep) are "
            "queued for a future release. The fields above already feed "
            "the backend; older Pulsim versions silently ignore unknown "
            "keys."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #6b7280; font-size: 11px; font-style: italic;")
        layout.addWidget(helper)
        return card

    def _create_card(
        self,
        title: str,
        subtitle: str,
        *,
        compact: bool = False,
        show_header: bool = True,
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        if compact:
            layout.setContentsMargins(8, 6, 8, 8)
            layout.setSpacing(3)
        else:
            layout.setContentsMargins(10, 9, 10, 10)
            layout.setSpacing(6)

        if show_header:
            title_label = QLabel(title)
            title_label.setObjectName("cardTitle")
            layout.addWidget(title_label)

            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("cardSubtitle")
            subtitle_label.setWordWrap(True)
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

        save_btn = QPushButton("Save")
        save_btn.setObjectName("saveButton")
        save_btn.clicked.connect(self._on_accept)
        layout.addWidget(save_btn)

        run_btn = QPushButton("Save && Run")
        run_btn.setObjectName("runButton")
        run_btn.setIconSize(QSize(11, 11))
        run_btn.clicked.connect(self._on_save_and_run)
        self._run_btn = run_btn
        layout.addWidget(run_btn)

        return layout

    def _on_save_and_run(self) -> None:
        self.run_after_accept = True
        self.run_requested.emit()
        self._on_accept()

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

    def _backend_has_capability(self, capability: str) -> bool:
        """Return True when the active backend advertises a capability."""
        if self._backend_info is None:
            return True
        return capability in set(self._backend_info.capabilities or set())

    def _set_capability_widgets_enabled(
        self,
        widgets: list[QWidget],
        *,
        enabled: bool,
        tooltip: str,
    ) -> None:
        for widget in widgets:
            widget.setEnabled(enabled)
            widget.setToolTip("" if enabled else tooltip)

    def _apply_capability_gates(self) -> None:
        """Disable unavailable controls based on backend feature flags."""
        averaged_enabled = self._backend_has_capability("averaged")
        averaged_tip = "Requires backend capability: averaged (pulsim >= 0.7.0)."
        self._set_capability_widgets_enabled(
            [
                self._averaged_enabled_check,
                self._averaged_topology_combo,
                self._averaged_mode_combo,
                self._averaged_envelope_combo,
            ],
            enabled=averaged_enabled,
            tooltip=averaged_tip,
        )
        if not averaged_enabled:
            self._averaged_enabled_check.setChecked(False)
        self._sync_averaged_controls(self._averaged_enabled_check.isChecked())

        frequency_enabled = self._backend_has_capability("frequency_analysis")
        frequency_tip = "Requires backend capability: frequency_analysis (pulsim >= 0.7.0)."
        self._set_capability_widgets_enabled(
            [
                self._ac_start_freq_spin,
                self._ac_stop_freq_spin,
                self._ac_points_spin,
                self._ac_anchor_mode_combo,
                self._ac_sweep_scale_combo,
                self._ac_injection_node_edit,
                self._ac_measurement_node_edit,
            ],
            enabled=frequency_enabled,
            tooltip=frequency_tip,
        )

    def _sync_averaged_controls(self, enabled: bool) -> None:
        """Keep averaged option fields enabled only when averaged mode is active."""
        fields_enabled = bool(enabled and self._averaged_enabled_check.isEnabled())
        self._averaged_topology_combo.setEnabled(fields_enabled)
        self._averaged_mode_combo.setEnabled(fields_enabled)
        self._averaged_envelope_combo.setEnabled(fields_enabled)

    def _on_reset_defaults(self) -> None:
        defaults = SimulationSettings()
        self._populate_from(defaults)

    def _load_settings(self) -> None:
        self._populate_from(self._settings)
        self._sync_engine_segment()
        self._update_run_estimate()

    def _populate_from(self, source: SimulationSettings) -> None:
        self._t_start_edit.value = source.t_start
        self._t_stop_edit.value = source.t_stop
        self._t_step_edit.value = source.t_step

        # pulsim 1.6 engine selector. Set BEFORE the integration combo
        # so ``_apply_engine_visibility`` runs against the right
        # engine on the very first paint.
        engine_value = str(getattr(source, "engine", "pwl") or "pwl").lower()
        if engine_value not in {"pwl", "dsed"}:
            engine_value = "pwl"
        engine_idx = self._engine_combo.findData(engine_value)
        self._engine_combo.setCurrentIndex(engine_idx if engine_idx >= 0 else 0)

        # DSED knobs — populated whether or not DSED is the active
        # engine, so flipping engine='pwl'→'dsed' later doesn't reset
        # the user's saved tunings.
        self._dsed_rtol_spin.setValue(float(getattr(source, "dsed_rtol", 1e-6)))
        self._dsed_atol_spin.setValue(float(getattr(source, "dsed_atol", 1e-9)))
        self._dsed_dt_init_edit.value = float(getattr(source, "dsed_dt_init", 1e-9))
        self._dsed_h_bdf2_edit.value = float(getattr(source, "dsed_h_bdf2", 1e-6))
        self._dsed_stiffness_spin.setValue(
            float(getattr(source, "dsed_stiffness_threshold", 10.0))
        )
        dsed_int = str(getattr(source, "dsed_integrator", "auto") or "auto").lower()
        if dsed_int not in {"auto", "rk45", "bdf2"}:
            dsed_int = "auto"
        dsed_int_idx = self._dsed_integrator_combo.findData(dsed_int)
        self._dsed_integrator_combo.setCurrentIndex(
            dsed_int_idx if dsed_int_idx >= 0 else 0
        )

        # Apply visibility after the engine combo settles + the DSED
        # knobs are populated. ``setCurrentIndex`` already fires the
        # changed signal, but call explicitly so first-paint matches.
        self._apply_engine_visibility()

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
        # New pulsim 1.5 Newton controls.
        self._tol_newton_dx_spin.setValue(
            float(getattr(source, "tol_newton_dx", None) or 0.0)
        )
        self._tol_newton_res_spin.setValue(
            float(getattr(source, "tol_newton_res", None) or 0.0)
        )
        self._line_search_check.setChecked(
            bool(getattr(source, "enable_newton_line_search", True))
        )
        self._newton_lm_check.setChecked(
            bool(getattr(source, "enable_newton_lm", False))
        )
        self._substep_correction_check.setChecked(
            bool(getattr(source, "enable_substep_state_correction", True))
        )
        self._max_event_iterations_spin.setValue(
            max(0, int(getattr(source, "max_event_iterations", 0)))
        )
        # Nonlinear refresh combo: None ⇒ auto.
        nlr = getattr(source, "enable_nonlinear_refresh", None)
        nlr_key = "auto" if nlr is None else ("on" if nlr else "off")
        nlr_idx = self._nonlinear_refresh_combo.findData(nlr_key)
        self._nonlinear_refresh_combo.setCurrentIndex(nlr_idx if nlr_idx >= 0 else 0)
        # Start-from-DC-op (lives on the Solver page).
        self._start_from_dc_op_check.setChecked(
            bool(getattr(source, "start_from_dc_op", False))
        )
        # Legacy fields — still loaded for backwards compat but the
        # widgets are hidden in the UI now.
        self._voltage_limiting_check.setChecked(source.enable_voltage_limiting)
        self._max_voltage_step_spin.setValue(source.max_voltage_step)
        self._transient_robust_mode_check.setChecked(source.transient_robust_mode)
        self._transient_auto_regularize_check.setChecked(source.transient_auto_regularize)
        formulation_mode = normalize_formulation_mode(
            getattr(source, "formulation_mode", "projected_wrapper")
        )
        formulation_idx = self._formulation_mode_combo.findData(formulation_mode)
        self._formulation_mode_combo.setCurrentIndex(formulation_idx if formulation_idx >= 0 else 0)
        self._direct_formulation_fallback_check.setChecked(
            bool(getattr(source, "direct_formulation_fallback", True))
        )
        self._on_formulation_mode_changed(self._formulation_mode_combo.currentIndex())

        # Wave-4 sub-A 1.6 — advanced solver-stack knobs.
        linear_stack = str(getattr(source, "linear_solver_stack", "auto") or "auto")
        linear_idx = self._linear_solver_combo.findData(linear_stack)
        self._linear_solver_combo.setCurrentIndex(linear_idx if linear_idx >= 0 else 0)
        self._iterative_max_iter_spin.setValue(
            int(getattr(source, "iterative_solver_max_iterations", 200))
        )
        self._iterative_restart_spin.setValue(
            int(getattr(source, "iterative_solver_restart", 30))
        )
        self._bdf_max_order_spin.setValue(int(getattr(source, "bdf_max_order", 5)))

        averaged_options = getattr(source, "averaged_options", None)
        averaged_enabled = isinstance(averaged_options, dict)
        self._averaged_enabled_check.setChecked(averaged_enabled)
        averaged_options = averaged_options if isinstance(averaged_options, dict) else {}
        topology_idx = self._averaged_topology_combo.findData(
            str(averaged_options.get("topology", "buck")).strip().lower()
        )
        self._averaged_topology_combo.setCurrentIndex(topology_idx if topology_idx >= 0 else 0)
        mode_idx = self._averaged_mode_combo.findData(
            str(averaged_options.get("mode", "ccm")).strip().lower()
        )
        self._averaged_mode_combo.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
        envelope_idx = self._averaged_envelope_combo.findData(
            str(averaged_options.get("envelope", "strict")).strip().lower()
        )
        self._averaged_envelope_combo.setCurrentIndex(envelope_idx if envelope_idx >= 0 else 0)
        self._sync_averaged_controls(averaged_enabled)

        dc_strategy_map = {"auto": 0, "direct": 1, "gmin": 2, "source": 3, "pseudo": 4}
        self._dc_strategy_combo.setCurrentIndex(dc_strategy_map.get(source.dc_strategy, 0))
        self._gmin_initial_spin.setValue(source.gmin_initial)
        self._gmin_final_spin.setValue(source.gmin_final)
        self._source_steps_spin.setValue(source.dc_source_steps)

        self._output_points_spin.setValue(source.output_points)
        self._enable_events_check.setChecked(bool(getattr(source, "enable_events", True)))
        self._max_step_retries_spin.setValue(max(0, int(getattr(source, "max_step_retries", 8))))
        self._enable_losses_check.setChecked(bool(getattr(source, "enable_losses", True)))
        self._thermal_ambient_spin.setValue(float(getattr(source, "thermal_ambient", 25.0)))
        thermal_network = str(getattr(source, "thermal_network", "foster") or "foster").strip().lower()
        thermal_network_idx = self._thermal_network_combo.findData(thermal_network)
        self._thermal_network_combo.setCurrentIndex(thermal_network_idx if thermal_network_idx >= 0 else 0)
        thermal_policy = normalize_thermal_policy(
            str(
                getattr(
                    source,
                    "thermal_policy",
                    "loss_with_temperature_scaling",
                )
                or "loss_with_temperature_scaling"
            )
        )
        thermal_policy_idx = self._thermal_policy_combo.findData(thermal_policy)
        self._thermal_policy_combo.setCurrentIndex(thermal_policy_idx if thermal_policy_idx >= 0 else 0)
        self._thermal_default_rth_spin.setValue(
            max(0.0, float(getattr(source, "thermal_default_rth", 1.0)))
        )
        self._thermal_default_cth_spin.setValue(
            max(0.0, float(getattr(source, "thermal_default_cth", 0.1)))
        )
        self._thermal_include_conduction_check.setChecked(
            bool(getattr(source, "thermal_include_conduction_losses", True))
        )
        self._thermal_include_switching_check.setChecked(
            bool(getattr(source, "thermal_include_switching_losses", True))
        )
        self._ac_start_freq_spin.setValue(max(1e-12, float(getattr(source, "ac_f_start", 1.0))))
        self._ac_stop_freq_spin.setValue(
            max(
                self._ac_start_freq_spin.value() * (1.0 + 1e-12),
                float(getattr(source, "ac_f_stop", 1e6)),
            )
        )
        self._ac_points_spin.setValue(
            max(1, int(getattr(source, "ac_points_per_decade", 10)))
        )
        ac_anchor_mode = normalize_frequency_anchor_mode(
            str(getattr(source, "ac_anchor_mode", "auto") or "auto")
        )
        ac_anchor_mode_idx = self._ac_anchor_mode_combo.findData(ac_anchor_mode)
        self._ac_anchor_mode_combo.setCurrentIndex(ac_anchor_mode_idx if ac_anchor_mode_idx >= 0 else 0)
        ac_sweep_scale = normalize_frequency_sweep_scale(
            str(getattr(source, "ac_sweep_scale", "decade") or "decade")
        )
        ac_sweep_scale_idx = self._ac_sweep_scale_combo.findData(ac_sweep_scale)
        self._ac_sweep_scale_combo.setCurrentIndex(ac_sweep_scale_idx if ac_sweep_scale_idx >= 0 else 0)
        self._ac_injection_node_edit.setText(
            str(getattr(source, "ac_injection_node", "") or "")
        )
        self._ac_measurement_node_edit.setText(
            str(getattr(source, "ac_measurement_node", "") or "")
        )

        self._update_solver_description()
        self._update_dc_strategy_description()
        self._on_dc_strategy_changed(self._dc_strategy_combo.currentIndex())
        self._update_effective_step()
        self._sync_preset_to_values()
        self._apply_capability_gates()

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
        # Keep loaded values untouched: only update visual preset selection.
        self._selected_preset = preset
        for key, card in self._preset_cards.items():
            card.blockSignals(True)
            card.setChecked(key == preset)
            card.blockSignals(False)

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

        # pulsim 1.6 engine + DSED knobs.
        self._settings.engine = str(
            self._engine_combo.currentData() or "pwl"
        )
        self._settings.dsed_rtol = float(self._dsed_rtol_spin.value())
        self._settings.dsed_atol = float(self._dsed_atol_spin.value())
        self._settings.dsed_dt_init = float(self._dsed_dt_init_edit.value)
        self._settings.dsed_h_bdf2 = float(self._dsed_h_bdf2_edit.value)
        self._settings.dsed_stiffness_threshold = float(
            self._dsed_stiffness_spin.value()
        )
        self._settings.dsed_integrator = str(
            self._dsed_integrator_combo.currentData() or "auto"
        )

        self._settings.max_step = self._max_step_edit.value
        self._settings.rel_tol = self._rel_tol_spin.value()
        self._settings.abs_tol = self._abs_tol_spin.value()

        self._settings.max_newton_iterations = self._max_iterations_spin.value()
        # New pulsim 1.5 Newton/Event controls.
        dx = float(self._tol_newton_dx_spin.value())
        self._settings.tol_newton_dx = dx if dx > 0.0 else None
        res = float(self._tol_newton_res_spin.value())
        self._settings.tol_newton_res = res if res > 0.0 else None
        self._settings.enable_newton_line_search = (
            self._line_search_check.isChecked()
        )
        self._settings.enable_newton_lm = self._newton_lm_check.isChecked()
        self._settings.enable_substep_state_correction = (
            self._substep_correction_check.isChecked()
        )
        self._settings.max_event_iterations = (
            self._max_event_iterations_spin.value()
        )
        nlr_key = str(self._nonlinear_refresh_combo.currentData() or "auto")
        if nlr_key == "auto":
            self._settings.enable_nonlinear_refresh = None
        else:
            self._settings.enable_nonlinear_refresh = (nlr_key == "on")
        self._settings.start_from_dc_op = (
            self._start_from_dc_op_check.isChecked()
        )
        # Legacy fields — still written so old projects keep round-trip
        # parity, but no longer forwarded to the kernel.
        self._settings.enable_voltage_limiting = self._voltage_limiting_check.isChecked()
        self._settings.max_voltage_step = self._max_voltage_step_spin.value()
        self._settings.transient_robust_mode = self._transient_robust_mode_check.isChecked()
        self._settings.transient_auto_regularize = (
            self._transient_auto_regularize_check.isChecked()
            and self._transient_robust_mode_check.isChecked()
        )
        self._settings.formulation_mode = normalize_formulation_mode(
            str(self._formulation_mode_combo.currentData() or "projected_wrapper")
        )
        self._settings.direct_formulation_fallback = (
            self._direct_formulation_fallback_check.isChecked()
        )

        # Wave-4 sub-A 1.6 — persist advanced solver-stack knobs.
        self._settings.linear_solver_stack = str(
            self._linear_solver_combo.currentData() or "auto"
        )
        self._settings.iterative_solver_max_iterations = int(
            self._iterative_max_iter_spin.value()
        )
        self._settings.iterative_solver_restart = int(self._iterative_restart_spin.value())
        self._settings.bdf_max_order = int(self._bdf_max_order_spin.value())

        if self._averaged_enabled_check.isChecked() and self._averaged_enabled_check.isEnabled():
            self._settings.averaged_options = {
                "topology": str(self._averaged_topology_combo.currentData() or "buck"),
                "mode": str(self._averaged_mode_combo.currentData() or "ccm"),
                "envelope": str(self._averaged_envelope_combo.currentData() or "strict"),
            }
        else:
            self._settings.averaged_options = None

        dc_strategy_map = {0: "auto", 1: "direct", 2: "gmin", 3: "source", 4: "pseudo"}
        self._settings.dc_strategy = dc_strategy_map.get(self._dc_strategy_combo.currentIndex(), "auto")
        self._settings.gmin_initial = self._gmin_initial_spin.value()
        self._settings.gmin_final = self._gmin_final_spin.value()
        self._settings.dc_source_steps = self._source_steps_spin.value()

        self._settings.output_points = self._output_points_spin.value()
        self._settings.enable_events = self._enable_events_check.isChecked()
        self._settings.max_step_retries = self._max_step_retries_spin.value()
        self._settings.enable_losses = self._enable_losses_check.isChecked()
        self._settings.thermal_ambient = self._thermal_ambient_spin.value()
        self._settings.thermal_network = str(
            self._thermal_network_combo.currentData() or "foster"
        ).strip().lower()
        self._settings.thermal_policy = normalize_thermal_policy(
            str(
                self._thermal_policy_combo.currentData()
                or "loss_with_temperature_scaling"
            )
        )
        self._settings.thermal_default_rth = max(
            0.0,
            float(self._thermal_default_rth_spin.value()),
        )
        self._settings.thermal_default_cth = max(
            0.0,
            float(self._thermal_default_cth_spin.value()),
        )
        self._settings.thermal_include_conduction_losses = (
            self._thermal_include_conduction_check.isChecked()
        )
        self._settings.thermal_include_switching_losses = (
            self._thermal_include_switching_check.isChecked()
        )
        self._settings.ac_f_start = max(1e-12, float(self._ac_start_freq_spin.value()))
        self._settings.ac_f_stop = max(
            self._settings.ac_f_start * (1.0 + 1e-12),
            float(self._ac_stop_freq_spin.value()),
        )
        self._settings.ac_points_per_decade = max(1, int(self._ac_points_spin.value()))
        self._settings.ac_anchor_mode = normalize_frequency_anchor_mode(
            str(self._ac_anchor_mode_combo.currentData() or "auto")
        )
        self._settings.ac_sweep_scale = normalize_frequency_sweep_scale(
            str(self._ac_sweep_scale_combo.currentData() or "decade")
        )
        self._settings.ac_injection_node = str(self._ac_injection_node_edit.text() or "").strip()
        self._settings.ac_measurement_node = str(self._ac_measurement_node_edit.text() or "").strip()

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
        """Update solver description based on engine + method selection."""
        engine = str(self._engine_combo.currentData() or "pwl")

        if engine == "dsed":
            self._solver_desc.setText(
                "DSED — Path-Based Event-Driven scheduler (pulsim 1.6+). "
                "Variable-step, adaptive RK45/BDF2 dispatch, event "
                "prediction. ~24× faster than PWL on buck CCM, geo-"
                "mean 14.5× across 6 SMPS topologies. Ignores the "
                "fixed Step size below — uses rtol/atol + DSED knobs "
                "instead."
            )
            return

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

    def _apply_engine_visibility(self) -> None:
        """Show DSED knobs only when engine='dsed'; hide the
        legacy ``Integration method`` combo since DSED has its own.
        Initial call comes from ``_load_settings`` after the engine
        combo is populated."""
        engine = str(self._engine_combo.currentData() or "pwl")
        is_dsed = engine == "dsed"
        for widget in self._dsed_widgets:
            widget.setVisible(is_dsed)
        # The PWL integration-method combo is meaningless on DSED.
        # Hide it (and its label) without removing — the value still
        # round-trips through .pulsim files via SimulationSettings.
        self._solver_label.setVisible(not is_dsed)
        self._solver_combo.setVisible(not is_dsed)

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

    def _on_formulation_mode_changed(self, _index: int) -> None:
        """Enable direct-mode fallback option only when direct mode is selected."""
        direct_mode = str(self._formulation_mode_combo.currentData() or "") == "direct"
        self._direct_formulation_fallback_check.setEnabled(direct_mode)

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
            success = c.success
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
            success = "mediumseagreen"
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

        nav_hover = (
            f"rgba({primary_q.red()}, {primary_q.green()}, {primary_q.blue()}, 18)"
        )
        nav_active = (
            f"rgba({primary_q.red()}, {primary_q.green()}, {primary_q.blue()}, 32)"
        )

        self._nav_icon_colors = (muted, primary)
        self.setStyleSheet(
            f"""
QDialog#simulationSettingsDialog {{
    background-color: {bg};
}}

/* ── Navigation sidebar ── */
QFrame#simSettingsNav {{
    background-color: {bg};
    border: none;
}}

QLabel#simNavTitle {{
    color: {text};
    font-size: 12px;
    font-weight: 700;
    line-height: 1.35;
}}

QPushButton#simNavBtn {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {muted};
    font-size: 12px;
    font-weight: 550;
    text-align: left;
    padding: 8px 12px 8px 11px;
    min-height: 32px;
    border-radius: 0px;
}}

QPushButton#simNavBtn:hover {{
    background-color: {nav_hover};
    color: {text};
}}

QPushButton#simNavBtn:checked {{
    background-color: {nav_active};
    border-left: 3px solid {primary};
    color: {text};
    font-weight: 650;
}}

QFrame#simNavSeparator {{
    border: none;
    background-color: {border};
    min-width: 1px;
    max-width: 1px;
}}

/* ── Content area ── */
QStackedWidget#simSettingsContent,
QScrollArea,
QWidget#simSettingsMain {{
    background-color: {panel};
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: {panel};
}}

QLabel#simPageTitle {{
    color: {text};
    font-size: 15px;
    font-weight: 700;
}}

QLabel#simSectionLabel {{
    color: {muted};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
}}

QFrame#formSeparator {{
    border: none;
    min-height: 1px;
    max-height: 1px;
    background-color: {border};
    margin-top: 2px;
    margin-bottom: 2px;
}}

/* ── Footer ── */
QWidget#simSettingsFooter {{
    background-color: {panel};
    border-top: 1px solid {border};
}}

/* ── Legacy section label (keep for compat) ── */
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

QTabWidget#advancedTabs::pane {{
    border: 1px solid {border};
    border-top: none;
    background-color: {card_bg};
}}

QTabWidget#advancedTabs QTabBar::tab {{
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    margin-right: 4px;
    color: {muted};
    font-size: 11px;
    font-weight: 600;
}}

QTabWidget#advancedTabs QTabBar::tab:selected {{
    color: {text};
    border-bottom: 2px solid {primary};
    font-weight: 700;
}}

QTabWidget#advancedTabs QTabBar::tab:hover {{
    color: {text};
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
    border-radius: 7px;
    background-clip: padding;
    color: {text};
    min-height: 24px;
    max-height: 28px;
    min-width: 64px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 12px;
}}

QPushButton#cancelButton:hover,
QPushButton#applyButton:hover {{
    border-color: {focus};
}}

QPushButton#runButton {{
    background-color: {primary};
    border: 1px solid {primary};
    border-radius: 7px;
    background-clip: padding;
    color: {primary_fg};
    min-height: 24px;
    max-height: 28px;
    min-width: 80px;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 16px;
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

/* ── Nav section header (ADVANCED) ── */
QLabel#simNavSection {{
    color: {muted};
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 1px;
}}

/* ── Engine segmented control ── */
QWidget#simEngineSegment {{
    background: {input_bg};
    border: 1px solid {input_border};
    border-radius: 8px;
}}

QPushButton#simEngineSegmentItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {muted};
    font-size: 12px;
    font-weight: 500;
    padding: 5px 14px;
}}

QPushButton#simEngineSegmentItem:hover {{ color: {text}; }}

QPushButton#simEngineSegmentItem:checked {{
    background: {checked_bg};
    border-color: {focus};
    color: {text};
    font-weight: 600;
}}

/* ── Run-size estimate chip ── */
QLabel#simRunEstimate {{
    color: {muted};
    font-family: "IBM Plex Mono", "Menlo", "Consolas", monospace;
    font-size: 11px;
}}

/* ── dt-aliasing warning banner ── */
QFrame#simAliasWarning {{
    background: rgba(224, 162, 58, 0.10);
    border: 1px solid rgba(224, 162, 58, 0.45);
    border-radius: 8px;
}}

QLabel#simAliasText {{
    color: {warning};
    font-size: 11px;
}}

QPushButton#aliasApplyBtn {{
    background: rgba(224, 162, 58, 0.14);
    border: 1px solid rgba(224, 162, 58, 0.5);
    border-radius: 6px;
    color: {warning};
    font-family: "IBM Plex Mono", "Menlo", "Consolas", monospace;
    font-size: 10.5px;
    font-weight: 600;
    padding: 4px 10px;
}}

QPushButton#aliasApplyBtn:hover {{
    background: rgba(224, 162, 58, 0.24);
}}

/* ── Footer: Save (secondary) / Save & Run (success primary) ── */
QPushButton#saveButton {{
    background-color: {chip_bg};
    border: 1px solid {border};
    border-radius: 8px;
    color: {text};
    font-weight: 600;
    padding: 6px 16px;
}}

QPushButton#saveButton:hover {{ border-color: {focus}; }}

QPushButton#runButton {{
    background-color: {success};
    border: none;
    border-radius: 8px;
    color: {primary_fg};
    font-weight: 700;
    padding: 6px 18px;
}}

QPushButton#runButton:hover {{
    background-color: {primary_hover};
}}
"""
        )
        run_btn = getattr(self, "_run_btn", None)
        if run_btn is not None:
            run_btn.setIcon(IconService.get_icon("play", primary_fg))
        self._refresh_nav_icons()
