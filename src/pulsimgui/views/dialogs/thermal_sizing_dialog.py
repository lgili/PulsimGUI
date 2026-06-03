"""Thermal sizing helper dialog (pulsim 1.7).

Three calculators, one dialog. The user opens this from
``Simulation → Thermal Sizing…`` BEFORE running a transient — none of
this touches the schematic; it's a sketchpad for "what R_th_case_to_sink
should I plug in?" and "what R_th_sink_to_amb should my heatsink
have?".

  * **TIM (thermal interface material).** Pick a catalog material (or
    enter ``k`` directly), enter the bond-line thickness and contact
    area; the dialog computes ``R_th = thickness / (k · area)`` via
    :func:`pulsim.thermal.tim_resistance`. That's the
    ``R_th_case_to_sink_K_per_W`` field on every device under a
    HEATSINK.
  * **Convection.** Pick airflow (or enter ``h`` directly), enter the
    heatsink's effective surface area; the dialog computes
    ``R_th = 1 / (h · area)`` via
    :func:`pulsim.thermal.convection_resistance`. That's the
    ``R_th_sink_to_amb_K_per_W`` field on the HEATSINK component.
  * **Look-up.** A read-only table of the bundled TIM catalog with
    typical thermal conductivities — useful even outside the
    calculators ("oh right, ceramic grease is ≈ 5 W/m·K").

Both calculators show a live readout (recomputed on every value
change), a "Copy R_th" button, and an explanatory range tip ("typical
0.05 – 1.0 K/W"). The dialog is non-modal — the user can keep it open
while editing the schematic.

Numerical ergonomics: the user thinks in cm² and mm, but pulsim takes
SI (m² and m). We convert at the boundary so the input fields are
labelled in datasheet units and the API call sees correct SI.

Robustness: each calculator's pulsim call is wrapped — invalid inputs
(zero area, negative thickness, unknown material) surface a friendly
error message in the readout instead of an exception.
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# Callback signature for the "Apply to selected HEATSINK" buttons.
# The widget passes its current R_th [K/W] to the callback. The
# callback returns a status message:
#   * "" → success (typically prefixed with a check + the sink name)
#   * non-empty string → human-readable error (e.g. "Select a HEATSINK first")
# Widgets show the returned message in a small status label below
# the buttons. Returning None is treated the same as "" (success
# without text).
ApplyCallback = Callable[[float], str]


# ---------------------------------------------------------------------------
# Pure-Python wrappers around pulsim 1.7 helpers
# ---------------------------------------------------------------------------


def compute_tim_resistance(
    *,
    area_cm2: float,
    thickness_mm: float,
    material: str | None,
    k_W_per_mK: float | None,
) -> float:
    """Wrapper around :func:`pulsim.thermal.tim_resistance` with
    GUI-friendly units (cm² + mm) and pulsim's SI (m² + m). Returns
    R_th in K/W. Raises ``ValueError`` on garbage input so the caller
    can surface a friendly error."""
    if area_cm2 <= 0:
        raise ValueError("area must be > 0 cm²")
    if thickness_mm <= 0:
        raise ValueError("thickness must be > 0 mm")
    area_m2 = area_cm2 * 1e-4
    thickness_m = thickness_mm * 1e-3
    try:
        import pulsim.thermal as pt
    except ImportError as exc:  # pragma: no cover - defensive
        raise RuntimeError("pulsim.thermal is unavailable") from exc
    kwargs: dict[str, Any] = {}
    if material:
        kwargs["material"] = material
    if k_W_per_mK is not None:
        kwargs["k_W_per_mK"] = float(k_W_per_mK)
    return float(pt.tim_resistance(area_m2, thickness_m, **kwargs))


def compute_convection_resistance(
    *,
    area_cm2: float,
    airflow_m_per_s: float,
    h_W_per_m2K: float | None,
) -> float:
    """Wrapper around :func:`pulsim.thermal.convection_resistance`.
    Returns R_th in K/W."""
    if area_cm2 <= 0:
        raise ValueError("area must be > 0 cm²")
    if airflow_m_per_s < 0:
        raise ValueError("airflow must be ≥ 0 m/s")
    area_m2 = area_cm2 * 1e-4
    try:
        import pulsim.thermal as pt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pulsim.thermal is unavailable") from exc
    kwargs: dict[str, Any] = {"airflow_m_per_s": float(airflow_m_per_s)}
    if h_W_per_m2K is not None:
        kwargs["h_W_per_m2K"] = float(h_W_per_m2K)
    return float(pt.convection_resistance(area_m2, **kwargs))


def get_tim_catalog() -> dict[str, float]:
    """Return ``pulsim.thermal.TIM_CATALOG`` as a plain dict. Empty on
    older kernels."""
    try:
        import pulsim.thermal as pt
    except ImportError:  # pragma: no cover
        return {}
    catalog = getattr(pt, "TIM_CATALOG", None)
    if not isinstance(catalog, dict):
        return {}
    return {str(k): float(v) for k, v in catalog.items()}


# ---------------------------------------------------------------------------
# Sub-widgets (one per calculator) — kept as separate QWidgets so each
# can be tested in isolation without instantiating the full dialog.
# ---------------------------------------------------------------------------


class TIMSizerWidget(QWidget):
    """Calculator for the case-to-sink R_th via a thermal-interface
    material. Live-updates as values change."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        apply_callback: ApplyCallback | None = None,
    ) -> None:
        super().__init__(parent)
        self._apply_callback = apply_callback
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._catalog = get_tim_catalog()
        self._material_combo = QComboBox()
        self._material_combo.addItem("(custom k…)", userData=None)
        for name, k in sorted(self._catalog.items()):
            self._material_combo.addItem(
                f"{name} ({k:g} W/m·K)", userData=name,
            )
        self._material_combo.currentIndexChanged.connect(
            self._on_material_changed
        )
        layout.addRow("Material", self._material_combo)

        self._k_spin = QDoubleSpinBox()
        self._k_spin.setRange(0.01, 500.0)
        self._k_spin.setDecimals(3)
        self._k_spin.setSingleStep(0.1)
        self._k_spin.setValue(3.0)  # thermal grease ballpark
        self._k_spin.setSuffix(" W/(m·K)")
        self._k_spin.valueChanged.connect(self._recompute)
        layout.addRow("k", self._k_spin)

        self._thickness_spin = QDoubleSpinBox()
        self._thickness_spin.setRange(0.01, 10.0)
        self._thickness_spin.setDecimals(3)
        self._thickness_spin.setSingleStep(0.05)
        self._thickness_spin.setValue(0.10)  # 0.1 mm typical grease
        self._thickness_spin.setSuffix(" mm")
        self._thickness_spin.valueChanged.connect(self._recompute)
        layout.addRow("Thickness", self._thickness_spin)

        self._area_spin = QDoubleSpinBox()
        self._area_spin.setRange(0.01, 1000.0)
        self._area_spin.setDecimals(2)
        self._area_spin.setSingleStep(0.5)
        self._area_spin.setValue(1.00)  # 1 cm² typical TO-220 footprint
        self._area_spin.setSuffix(" cm²")
        self._area_spin.valueChanged.connect(self._recompute)
        layout.addRow("Contact area", self._area_spin)

        # Result row — bold + monospaced for readability, with copy
        # button to the right.
        result_row = QHBoxLayout()
        self._result_label = QLabel("R_th = … K/W")
        self._result_label.setObjectName("thermalSizingResult")
        self._result_label.setStyleSheet(
            "QLabel#thermalSizingResult { font-weight: bold; "
            "font-family: monospace; padding: 4px 0; }"
        )
        self._result_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        self._copy_button = QPushButton("Copy")
        self._copy_button.setFixedWidth(72)
        self._copy_button.clicked.connect(self._copy_result)
        result_row.addWidget(self._result_label, 1)
        result_row.addWidget(self._copy_button)
        # "Apply to selected HEATSINK (slot 1)" button — appears only
        # when the dialog wires the apply_callback. The result of the
        # TIM calculator is the R_th_case_to_sink of ONE device on the
        # heatsink; the HEATSINK component stores per-slot values in
        # a CSV (positionally aligned with DEV_k pins). We write to
        # the first slot — the common case is one MOSFET on one
        # heatsink. Multi-slot edits stay manual.
        if self._apply_callback is not None:
            self._apply_button = QPushButton("Apply to HS")
            self._apply_button.setFixedWidth(96)
            self._apply_button.setToolTip(
                "Write this R_th into slot 1 of the selected HEATSINK's "
                "case_to_sink_R_th_csv field. Preserves any existing "
                "slot 2+ entries. Requires a HEATSINK to be selected "
                "on the schematic."
            )
            self._apply_button.clicked.connect(self._on_apply_clicked)
            result_row.addWidget(self._apply_button)
        else:
            self._apply_button = None
        layout.addRow("→ R_th_case_to_sink", result_row)

        # Status label for the Apply button — shows success/error text
        # after a click. Empty by default.
        self._apply_status = QLabel("")
        self._apply_status.setWordWrap(True)
        self._apply_status.setStyleSheet(
            "color: #4a5568; font-size: 11px; padding-top: 2px;"
        )
        if self._apply_button is not None:
            layout.addRow("", self._apply_status)

        tip = QLabel(
            "Typical values: TO-220 + grease ≈ 0.5 K/W; TO-247 + pad ≈ "
            "0.3 K/W; bare metal ≈ 0.05 K/W."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", tip)

        # Initialise display.
        self._recompute()

    def _on_apply_clicked(self) -> None:
        """Invoke the dialog-supplied callback with the current R_th
        and surface the returned status in the small label below the
        buttons. Callback is None-safe so the button can be wired up
        in tests without driving the full main_window."""
        value = getattr(self, "_last_value", None)
        if value is None or self._apply_callback is None:
            return
        try:
            status = self._apply_callback(float(value))
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            status = f"Error: {exc}"
        self._apply_status.setText(status or "")
        # Red-ish for error messages, neutral for success.
        if status and status.lower().startswith(("error", "select")):
            self._apply_status.setStyleSheet(
                "color: #c53030; font-size: 11px; padding-top: 2px;"
            )
        else:
            self._apply_status.setStyleSheet(
                "color: #2f855a; font-size: 11px; padding-top: 2px;"
            )

    # The "(custom k…)" option keeps the k_spin editable; selecting a
    # catalog entry locks k_spin to the catalog value.
    def _on_material_changed(self) -> None:
        material = self._material_combo.currentData()
        if material is None:
            self._k_spin.setEnabled(True)
        else:
            k = self._catalog.get(material)
            if k is not None:
                self._k_spin.setValue(float(k))
            self._k_spin.setEnabled(False)
        self._recompute()

    def _recompute(self) -> None:
        material = self._material_combo.currentData()
        try:
            r_th = compute_tim_resistance(
                area_cm2=self._area_spin.value(),
                thickness_mm=self._thickness_spin.value(),
                material=material,
                # When a catalog material is selected, we let pulsim
                # look up k. When custom, pass the spin value.
                k_W_per_mK=(
                    self._k_spin.value() if material is None else None
                ),
            )
        except (ValueError, RuntimeError) as exc:
            self._result_label.setText(f"R_th = ?  ({exc})")
            self._copy_button.setEnabled(False)
            self._last_value: float | None = None
            return
        self._result_label.setText(f"R_th = {r_th:.4g} K/W")
        self._copy_button.setEnabled(True)
        self._last_value = r_th

    def _copy_result(self) -> None:
        value = getattr(self, "_last_value", None)
        if value is None:
            return
        QGuiApplication.clipboard().setText(f"{value:.4g}")

    # Test hook
    def current_R_th(self) -> float | None:
        return getattr(self, "_last_value", None)


class ConvectionSizerWidget(QWidget):
    """Calculator for the sink-to-ambient R_th via natural / forced
    convection. Live-updates as values change."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        apply_callback: ApplyCallback | None = None,
    ) -> None:
        super().__init__(parent)
        self._apply_callback = apply_callback
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._area_spin = QDoubleSpinBox()
        self._area_spin.setRange(1.0, 10000.0)
        self._area_spin.setDecimals(1)
        self._area_spin.setSingleStep(10.0)
        self._area_spin.setValue(200.0)  # 200 cm² typical TO-220 sink
        self._area_spin.setSuffix(" cm²")
        self._area_spin.valueChanged.connect(self._recompute)
        layout.addRow("Surface area", self._area_spin)

        self._airflow_spin = QDoubleSpinBox()
        self._airflow_spin.setRange(0.0, 20.0)
        self._airflow_spin.setDecimals(2)
        self._airflow_spin.setSingleStep(0.5)
        self._airflow_spin.setValue(0.0)  # natural convection default
        self._airflow_spin.setSuffix(" m/s")
        self._airflow_spin.valueChanged.connect(self._on_airflow_changed)
        layout.addRow("Airflow", self._airflow_spin)

        # When the user types ``h`` directly, the airflow value becomes
        # irrelevant. The spin is enabled but ignored — we still show
        # it so users have the "let pulsim estimate" affordance.
        self._h_spin = QDoubleSpinBox()
        self._h_spin.setRange(0.0, 1000.0)
        self._h_spin.setDecimals(2)
        self._h_spin.setSingleStep(1.0)
        self._h_spin.setValue(0.0)  # 0 = use the airflow estimate
        self._h_spin.setSuffix(" W/(m²·K)  (0 → use airflow)")
        self._h_spin.valueChanged.connect(self._recompute)
        layout.addRow("h (override)", self._h_spin)

        result_row = QHBoxLayout()
        self._result_label = QLabel("R_th = … K/W")
        self._result_label.setObjectName("thermalSizingResult")
        self._result_label.setStyleSheet(
            "QLabel#thermalSizingResult { font-weight: bold; "
            "font-family: monospace; padding: 4px 0; }"
        )
        self._result_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        self._copy_button = QPushButton("Copy")
        self._copy_button.setFixedWidth(72)
        self._copy_button.clicked.connect(self._copy_result)
        result_row.addWidget(self._result_label, 1)
        result_row.addWidget(self._copy_button)
        # "Apply to selected HEATSINK" — same pattern as the TIM tab.
        # Writes directly to ``R_th_sink_to_amb_K_per_W`` (single
        # scalar field, not per-slot CSV).
        if self._apply_callback is not None:
            self._apply_button = QPushButton("Apply to HS")
            self._apply_button.setFixedWidth(96)
            self._apply_button.setToolTip(
                "Write this R_th into R_th_sink_to_amb_K_per_W of the "
                "selected HEATSINK component. Requires a HEATSINK to be "
                "selected on the schematic."
            )
            self._apply_button.clicked.connect(self._on_apply_clicked)
            result_row.addWidget(self._apply_button)
        else:
            self._apply_button = None
        layout.addRow("→ R_th_sink_to_amb", result_row)

        self._apply_status = QLabel("")
        self._apply_status.setWordWrap(True)
        self._apply_status.setStyleSheet(
            "color: #4a5568; font-size: 11px; padding-top: 2px;"
        )
        if self._apply_button is not None:
            layout.addRow("", self._apply_status)

        tip = QLabel(
            "Natural convection: 5 – 20 K/W. Forced (1 – 5 m/s): "
            "1 – 5 K/W. Prefer the heatsink datasheet's R_th-vs-airflow "
            "curve when available — this is a first-cut estimate."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", tip)

        self._recompute()

    def _on_apply_clicked(self) -> None:
        """Mirror of ``TIMSizerWidget._on_apply_clicked``. See there
        for the contract — same callback signature, same surface
        behaviour, different target param."""
        value = getattr(self, "_last_value", None)
        if value is None or self._apply_callback is None:
            return
        try:
            status = self._apply_callback(float(value))
        except Exception as exc:  # noqa: BLE001
            status = f"Error: {exc}"
        self._apply_status.setText(status or "")
        if status and status.lower().startswith(("error", "select")):
            self._apply_status.setStyleSheet(
                "color: #c53030; font-size: 11px; padding-top: 2px;"
            )
        else:
            self._apply_status.setStyleSheet(
                "color: #2f855a; font-size: 11px; padding-top: 2px;"
            )

    def _on_airflow_changed(self) -> None:
        # No special UI gating — h_spin = 0 means "let airflow drive
        # the estimate", non-zero h_spin overrides. We just recompute.
        self._recompute()

    def _recompute(self) -> None:
        h_override = self._h_spin.value()
        try:
            r_th = compute_convection_resistance(
                area_cm2=self._area_spin.value(),
                airflow_m_per_s=self._airflow_spin.value(),
                h_W_per_m2K=h_override if h_override > 0 else None,
            )
        except (ValueError, RuntimeError) as exc:
            self._result_label.setText(f"R_th = ?  ({exc})")
            self._copy_button.setEnabled(False)
            self._last_value: float | None = None
            return
        self._result_label.setText(f"R_th = {r_th:.4g} K/W")
        self._copy_button.setEnabled(True)
        self._last_value = r_th

    def _copy_result(self) -> None:
        value = getattr(self, "_last_value", None)
        if value is None:
            return
        QGuiApplication.clipboard().setText(f"{value:.4g}")

    def current_R_th(self) -> float | None:
        return getattr(self, "_last_value", None)


class TIMCatalogWidget(QWidget):
    """Read-only ``pulsim.thermal.TIM_CATALOG`` lookup table — useful
    "remind me what ceramic grease's k is" reference outside the
    calculators."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        caption = QLabel(
            "Conductivity ``k`` of common thermal-interface materials. "
            "Use this as a starting point — datasheet values vary "
            "considerably with bond-line thickness and application "
            "pressure."
        )
        caption.setWordWrap(True)
        layout.addWidget(caption)

        catalog = get_tim_catalog()
        self._table = QTableWidget(len(catalog), 2)
        self._table.setHorizontalHeaderLabels(["Material", "k [W/(m·K)]"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        for row, (name, k) in enumerate(sorted(catalog.items())):
            self._table.setItem(row, 0, QTableWidgetItem(name))
            k_item = QTableWidgetItem(f"{k:g}")
            k_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 1, k_item)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch,
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents,
        )
        layout.addWidget(self._table, 1)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------


class ThermalSizingDialog(QDialog):
    """Bundle TIM + Convection + Catalog tabs into one non-modal dialog.

    Opened from ``Simulation → Thermal Sizing…``.  Has no schematic
    coupling — it's a sketchpad. The user copies the resulting R_th
    values into HEATSINK / device fields manually.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thermal Sizing — TIM + Convection")
        self.setMinimumSize(520, 360)
        # Non-modal so the user can keep it open beside the schematic.
        self.setWindowModality(Qt.WindowModality.NonModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro = QLabel(
            "Sizing helpers for the two key thermal resistances in a "
            "shared-heatsink design. None of this writes to the "
            "schematic — use the Copy buttons to paste the values into "
            "the HEATSINK / device fields."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._tabs = QTabWidget()
        # The Apply callbacks walk up to the parent MainWindow to find
        # the selected HEATSINK and emit an UpdateComponentStateCommand
        # so writes participate in the global undo stack. Only wire
        # them when the parent looks like a MainWindow — keeps the
        # dialog usable from tests + standalone smoke runs (where the
        # parent is None or a bare QWidget).
        parent_looks_like_main_window = (
            parent is not None
            and hasattr(parent, "_schematic_scene")
            and hasattr(parent, "_execute_schematic_command")
            and hasattr(parent, "_current_circuit")
        )
        tim_cb = (
            self._apply_to_selected_heatsink_tim
            if parent_looks_like_main_window
            else None
        )
        conv_cb = (
            self._apply_to_selected_heatsink_convection
            if parent_looks_like_main_window
            else None
        )
        self._tim_sizer = TIMSizerWidget(self, apply_callback=tim_cb)
        self._convection_sizer = ConvectionSizerWidget(self, apply_callback=conv_cb)
        self._catalog_view = TIMCatalogWidget(self)

        self._tabs.addTab(self._tim_sizer, "TIM (case → sink)")
        self._tabs.addTab(self._convection_sizer, "Convection (sink → amb)")
        self._tabs.addTab(self._catalog_view, "TIM catalog")
        layout.addWidget(self._tabs, 1)

        # Close-only button row (non-modal — no Accept/Apply semantics).
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)

        # Visual divider above the buttons; keeps the dialog grounded.
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.insertWidget(layout.count() - 1, sep)

    # Test hooks: expose the sub-widgets so unit tests can poke at
    # the live R_th values without driving the UI.
    @property
    def tim_sizer(self) -> TIMSizerWidget:
        return self._tim_sizer

    @property
    def convection_sizer(self) -> ConvectionSizerWidget:
        return self._convection_sizer

    # ------------------------------------------------------------------
    # Apply-to-selected callbacks. Both follow the same recipe: walk
    # up to MainWindow, find the selected HEATSINK component, build
    # the new-state snapshot, dispatch an UpdateComponentStateCommand
    # via the existing schematic command pipeline (so it participates
    # in undo/redo + dirty-marking).
    #
    # The return value is the status string the widget shows: "" /
    # "Applied …" on success, "Select a HEATSINK first" / "Error: …"
    # on failure. Widgets pick the color based on the prefix.
    # ------------------------------------------------------------------

    def _find_selected_heatsink(self) -> tuple[Any, Any, str] | None:
        """Return ``(main_window, component, sink_display_name)`` for
        the currently-selected HEATSINK, or ``None`` when no valid
        target exists.

        Duck-typed on ``item.component`` rather than
        ``isinstance(item, ComponentItem)`` — keeps the dialog
        decoupled from the graphics-item class hierarchy and makes
        it trivial to test with fake selected-item stand-ins. Items
        that have no ``.component`` attribute (wires, ports, labels,
        decorations) silently fail the filter, same as if the
        isinstance had rejected them."""
        main_window = self.parent()
        if main_window is None:
            return None
        scene = getattr(main_window, "_schematic_scene", None)
        if scene is None:
            return None
        for item in scene.selectedItems():
            comp = getattr(item, "component", None)
            if comp is None:
                continue
            # Compare on str(type) so we don't need to import the enum
            # here (avoids tight coupling for tests that stub out the
            # ComponentType module).
            type_name = getattr(comp.type, "name", str(comp.type))
            if type_name == "HEATSINK":
                return main_window, comp, getattr(comp, "name", "HS")
        return None

    def _dispatch_param_update(
        self,
        main_window: Any,
        component: Any,
        params_patch: dict[str, Any],
    ) -> str:
        """Build an ``UpdateComponentStateCommand`` that merges
        ``params_patch`` into the component's current parameters dict
        and ship it through the schematic command pipeline. Returns a
        status string. Tolerant of import / runtime errors — surfaces
        them as the user-visible status rather than crashing the
        dialog."""
        try:
            from copy import deepcopy

            from pulsimgui.commands.component_commands import (
                UpdateComponentStateCommand,
            )

            circuit = main_window._current_circuit()
            old_state = UpdateComponentStateCommand.snapshot(component)
            new_state = deepcopy(old_state)
            new_state.setdefault("parameters", {}).update(params_patch)
            command = UpdateComponentStateCommand(
                circuit, component.id, new_state, old_state=old_state,
            )
            main_window._execute_schematic_command(
                command, refresh_scene=True, merge=False,
            )
            return ""  # success — caller adds the "Applied …" prefix
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

    def _apply_to_selected_heatsink_convection(self, r_th: float) -> str:
        """Write R_th into ``R_th_sink_to_amb_K_per_W`` on the selected
        HEATSINK (single scalar field)."""
        target = self._find_selected_heatsink()
        if target is None:
            return "Select a HEATSINK on the schematic first."
        main_window, component, sink_name = target
        err = self._dispatch_param_update(
            main_window, component,
            {"R_th_sink_to_amb_K_per_W": float(r_th)},
        )
        if err:
            return err
        return f"Applied {r_th:.4g} K/W to {sink_name} (R_th_sink_to_amb)."

    def _apply_to_selected_heatsink_tim(self, r_th: float) -> str:
        """Write R_th into slot 1 of the HEATSINK's
        ``case_to_sink_R_th_csv`` field, preserving any existing
        slot-2+ entries. The CSV is positional: slot k aligns with
        DEV_k pin → device on that pin gets ``csv[k-1]`` as its
        case-to-sink R_th in the backend."""
        target = self._find_selected_heatsink()
        if target is None:
            return "Select a HEATSINK on the schematic first."
        main_window, component, sink_name = target

        # Patch slot 1 in the CSV; keep slots 2+ untouched.
        current_csv = ""
        try:
            params = getattr(component, "parameters", None) or {}
            current_csv = str(params.get("case_to_sink_R_th_csv") or "")
        except Exception:  # noqa: BLE001
            current_csv = ""
        # Split on , or ;. Empty/whitespace tokens are preserved as ""
        # so user's spacing survives a slot-1 edit.
        tokens = [
            t.strip() for t in current_csv.replace(";", ",").split(",")
        ]
        if not tokens or (len(tokens) == 1 and not tokens[0]):
            new_tokens = [f"{r_th:.4g}"]
        else:
            new_tokens = list(tokens)
            new_tokens[0] = f"{r_th:.4g}"
        new_csv = ", ".join(new_tokens)

        err = self._dispatch_param_update(
            main_window, component, {"case_to_sink_R_th_csv": new_csv},
        )
        if err:
            return err
        return (
            f"Applied {r_th:.4g} K/W to {sink_name} slot 1 "
            f"(case_to_sink_R_th_csv)."
        )
