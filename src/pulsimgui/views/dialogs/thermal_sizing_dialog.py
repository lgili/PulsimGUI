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

from typing import Any

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        layout.addRow("→ R_th_case_to_sink", result_row)

        tip = QLabel(
            "Typical values: TO-220 + grease ≈ 0.5 K/W; TO-247 + pad ≈ "
            "0.3 K/W; bare metal ≈ 0.05 K/W."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", tip)

        # Initialise display.
        self._recompute()

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        layout.addRow("→ R_th_sink_to_amb", result_row)

        tip = QLabel(
            "Natural convection: 5 – 20 K/W. Forced (1 – 5 m/s): "
            "1 – 5 K/W. Prefer the heatsink datasheet's R_th-vs-airflow "
            "curve when available — this is a first-cut estimate."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", tip)

        self._recompute()

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
        self._tim_sizer = TIMSizerWidget(self)
        self._convection_sizer = ConvectionSizerWidget(self)
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
