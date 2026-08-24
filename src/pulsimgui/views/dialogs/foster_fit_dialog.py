"""Fit a Foster RC thermal network to a datasheet Z_th(t) curve.

Power-electronics datasheets typically publish a transient thermal
impedance curve ``Z_th(t)`` (junction-to-case or junction-to-ambient).
The simulation parameters that the GUI's thermal pipeline needs —
``thermal_rth_stages`` and ``thermal_cth_stages`` — are a Foster RC
stack that *reproduces* that curve.

Until pulsim 1.7.0 the user had to derive those RC stages by hand
(eyeballing the curve, solving a non-linear least squares, or running
an external fitting tool) and paste comma-separated values into the
component's properties panel. That step is enough friction that most
users either skipped it or guessed.

pulsim 1.7.0 ships :func:`pulsim.thermal.fit_foster_from_zth`, which
solves the same fit numerically. This dialog wraps it:

  1. Paste (or load) the ``t (s), Z_th (K/W)`` samples from the
     datasheet — typically 10-100 points, log-spaced over 6 decades.
  2. Pick how many Foster stages to fit (default 3 — the industry
     sweet spot between accuracy and parameter count).
  3. Hit "Fit". The result is shown both as a table and as an overlay
     plot (raw points + fitted curve) so you can sanity-check.
  4. Copy the resulting ``R_th`` and ``C_th`` CSV strings — they
     paste straight into the component's
     ``thermal_rth_stages`` / ``thermal_cth_stages`` fields.

A small unit test
(``tests/test_views/dialogs/test_foster_fit_dialog.py``) synthesises a
known 3-stage Z_th, runs it through the dialog's fitting helper, and
asserts that the recovered R/τ values are within 5 % of the originals
— guards against silent regressions in either pulsim's fitter or this
dialog's input/output conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services import font_service

# ---------------------------------------------------------------------------
# Pure-Python helpers (no Qt dependencies; trivially unit-testable).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FosterFitResult:
    """A parsed Foster fit ready for the GUI's CSV-strings model.

    Attributes
    ----------
    r_th_K_per_W:
        Per-stage thermal resistances, in K/W. Goes into the
        component's ``thermal_rth_stages`` parameter as a
        comma-separated string.
    tau_s:
        Per-stage thermal time constants, in seconds. Carried for
        diagnostics / display; the GUI stores capacitances rather
        than time constants.
    c_th_J_per_K:
        Per-stage thermal capacitances, in J/K. Derived from
        ``C = τ / R``. Goes into ``thermal_cth_stages``.
    """

    r_th_K_per_W: tuple[float, ...]
    tau_s: tuple[float, ...]
    c_th_J_per_K: tuple[float, ...]

    @property
    def n_stages(self) -> int:
        return len(self.r_th_K_per_W)

    def r_csv(self, *, fmt: str = "{:.6g}") -> str:
        return ", ".join(fmt.format(v) for v in self.r_th_K_per_W)

    def c_csv(self, *, fmt: str = "{:.6g}") -> str:
        return ", ".join(fmt.format(v) for v in self.c_th_J_per_K)


def parse_zth_csv(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse a two-column ``t, Z_th`` text blob into NumPy arrays.

    Accepts comma, tab, semicolon, or whitespace separators on each
    row. Blank rows and ``#``-prefixed comment rows are ignored.
    Designed to be lenient about pasted-from-PDF formatting (extra
    whitespace, mixed delimiters).

    Raises
    ------
    ValueError
        When the parsed data has < 3 samples, mismatched column counts,
        non-monotonic time samples, or values that can't be coerced
        to floats. The error message is user-facing.
    """
    rows: list[tuple[float, float]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Normalise delimiters: any of (',', ';', '\t', whitespace).
        for sep in (",", ";", "\t"):
            if sep in line:
                line = line.replace(sep, " ")
        tokens = [tok for tok in line.split() if tok]
        if len(tokens) < 2:
            raise ValueError(
                f"Line {line_no}: expected two columns (t, Z_th), got {len(tokens)}."
            )
        if len(tokens) > 2:
            # Allow ``t, Z_th, anything`` — many datasheet CSV dumps
            # carry a header column or trailing units; we just take
            # the first two numeric tokens.
            tokens = tokens[:2]
        try:
            t_val = float(tokens[0])
            z_val = float(tokens[1])
        except ValueError as exc:
            raise ValueError(
                f"Line {line_no}: could not parse '{raw_line.strip()}' "
                f"as (t, Z_th)."
            ) from exc
        rows.append((t_val, z_val))

    if len(rows) < 3:
        raise ValueError(
            f"Need at least 3 (t, Z_th) samples to fit a Foster network "
            f"— got {len(rows)}."
        )

    t = np.asarray([r[0] for r in rows], dtype=float)
    z = np.asarray([r[1] for r in rows], dtype=float)
    if not np.all(np.diff(t) > 0):
        raise ValueError(
            "Time samples must be strictly increasing (sort the rows by t)."
        )
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(z)):
        raise ValueError("Z_th data contains NaN or infinite values.")
    if np.any(t <= 0):
        raise ValueError("All time samples must be > 0 seconds.")
    if np.any(z < 0):
        raise ValueError("All Z_th samples must be >= 0 K/W.")
    return t, z


def fit_zth_to_foster(
    t: np.ndarray,
    zth: np.ndarray,
    *,
    n_stages: int = 3,
    n_iter: int = 30,
) -> FosterFitResult:
    """Fit ``zth(t)`` to an n-stage Foster network and return the
    resistances + time constants + derived capacitances.

    Thin wrapper around :func:`pulsim.thermal.fit_foster_from_zth` that
    converts the resulting list of ``FosterStage`` (which carries
    ``R_th_K_per_W`` and ``tau_s``) into the dual representation the
    GUI persists (``R`` plus ``C = τ / R``).

    Raises
    ------
    RuntimeError
        When the fitter raises or returns an empty list. Forwarded
        unchanged so the dialog can display the underlying message.
    """
    import pulsim.thermal as pt  # local import — keeps module import cheap

    try:
        stages = pt.fit_foster_from_zth(
            t, zth, n_stages=int(n_stages), n_iter=int(n_iter),
        )
    except Exception as exc:  # noqa: BLE001 - surface the actual error
        raise RuntimeError(
            f"fit_foster_from_zth failed: {type(exc).__name__}: {exc}"
        ) from exc

    if not stages:
        raise RuntimeError("Fitter returned no Foster stages.")

    r_values: list[float] = []
    tau_values: list[float] = []
    c_values: list[float] = []
    for stage in stages:
        r = float(getattr(stage, "R_th_K_per_W"))
        tau = float(getattr(stage, "tau_s"))
        if r <= 0 or tau <= 0:
            raise RuntimeError(
                f"Fitter returned a non-physical stage: R={r:.4g}, tau={tau:.4g}."
            )
        r_values.append(r)
        tau_values.append(tau)
        c_values.append(tau / r)

    return FosterFitResult(
        r_th_K_per_W=tuple(r_values),
        tau_s=tuple(tau_values),
        c_th_J_per_K=tuple(c_values),
    )


def evaluate_foster_zth(
    t: np.ndarray, r_th: tuple[float, ...], tau: tuple[float, ...],
) -> np.ndarray:
    """Compute ``Z_th(t) = Σᵢ Rᵢ · (1 − exp(−t / τᵢ))`` for plotting."""
    t_arr = np.asarray(t, dtype=float)
    z = np.zeros_like(t_arr, dtype=float)
    for r, taui in zip(r_th, tau):
        if taui <= 0:
            continue
        z = z + r * (1.0 - np.exp(-t_arr / taui))
    return z


# ---------------------------------------------------------------------------
# Dialog UI.
# ---------------------------------------------------------------------------


_EXAMPLE_CSV = """\
# Datasheet Z_th(t) for a TO-220 MOSFET (illustrative).
# Columns: t (s), Z_th (K/W). Lines starting with '#' are ignored.
1e-5    0.024
3e-5    0.041
1e-4    0.069
3e-4    0.107
1e-3    0.169
3e-3    0.249
1e-2    0.353
3e-2    0.452
1e-1    0.540
3e-1    0.587
1.0     0.602
"""


class FosterFitDialog(QDialog):
    """Modal dialog: datasheet Z_th(t) → Foster R/C stages.

    Surfaces :func:`pulsim.thermal.fit_foster_from_zth` to the user.
    Output is the comma-separated R / C strings that drop into a
    component's ``thermal_rth_stages`` / ``thermal_cth_stages``
    parameter fields with a single paste.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fit Foster Thermal Network from Datasheet Z_th(t)")
        self.setModal(False)
        self.resize(900, 640)

        self._fit_result: FosterFitResult | None = None

        root = QVBoxLayout(self)

        # --- Step 1: paste / load Z_th data --------------------------------
        input_group = QGroupBox("1. Datasheet Z_th(t) data — paste or load")
        input_layout = QVBoxLayout(input_group)

        hint = QLabel(
            "Two columns: <b>t (s)</b>, <b>Z_th (K/W)</b>. Commas, tabs, "
            "semicolons, or spaces all accepted. Lines starting with "
            "'#' are ignored."
        )
        hint.setWordWrap(True)
        input_layout.addWidget(hint)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText(
            "Paste Z_th(t) samples here, one row per line:\n"
            "    1e-5, 0.024\n"
            "    1e-4, 0.069\n"
            "    1e-3, 0.169\n"
            "    ...\n"
        )
        self._text_edit.setMinimumHeight(140)
        font = self._text_edit.font()
        font.setFamilies(font_service.MONO_FAMILIES)
        font.setPointSize(11)
        self._text_edit.setFont(font)
        input_layout.addWidget(self._text_edit)

        input_buttons = QHBoxLayout()
        self._load_button = QPushButton("Load from file…")
        self._load_button.clicked.connect(self._on_load_file)
        input_buttons.addWidget(self._load_button)
        self._example_button = QPushButton("Insert example")
        self._example_button.setToolTip(
            "Drop in a sample TO-220 MOSFET Z_th(t) so you can try the "
            "fitter without locating a datasheet first."
        )
        self._example_button.clicked.connect(self._on_insert_example)
        input_buttons.addWidget(self._example_button)
        input_buttons.addStretch(1)
        input_layout.addLayout(input_buttons)

        root.addWidget(input_group)

        # --- Step 2: fit settings + button --------------------------------
        settings_group = QGroupBox("2. Fit settings")
        settings_form = QFormLayout(settings_group)
        self._n_stages_spin = QSpinBox()
        self._n_stages_spin.setRange(1, 5)
        self._n_stages_spin.setValue(3)
        self._n_stages_spin.setToolTip(
            "Number of Foster stages in the network. 3 is the industry "
            "default for transient thermal modelling of power devices "
            "(captures fast / medium / slow time constants). Use 4-5 "
            "for higher fidelity on heavily-modulated junctions."
        )
        settings_form.addRow("Foster stages:", self._n_stages_spin)
        self._n_iter_spin = QSpinBox()
        self._n_iter_spin.setRange(10, 200)
        self._n_iter_spin.setValue(30)
        self._n_iter_spin.setToolTip(
            "Inner iterations for the alternating-LS fit. The default "
            "(30) converges on every datasheet curve we've tried; "
            "increase if the residual report looks high."
        )
        settings_form.addRow("Iterations:", self._n_iter_spin)
        settings_form.addRow(QLabel("&nbsp;"))  # spacer
        self._fit_button = QPushButton("Fit Foster network")
        self._fit_button.setMinimumHeight(36)
        self._fit_button.clicked.connect(self._on_fit_clicked)
        settings_form.addRow(self._fit_button)
        root.addWidget(settings_group)

        # --- Step 3: results table + R/C copy buttons ---------------------
        results_group = QGroupBox("3. Fitted stages — paste into the component's thermal-port fields")
        results_layout = QVBoxLayout(results_group)

        self._stages_table = QTableWidget(0, 4)
        self._stages_table.setHorizontalHeaderLabels([
            "Stage", "R_th (K/W)", "τ (s)", "C_th (J/K)",
        ])
        header = self._stages_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._stages_table.verticalHeader().setVisible(False)
        self._stages_table.setMinimumHeight(120)
        results_layout.addWidget(self._stages_table)

        copy_layout = QFormLayout()
        self._r_csv_label = QLabel("—")
        self._r_csv_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        rh_row = QHBoxLayout()
        rh_row.addWidget(self._r_csv_label, 1)
        self._copy_r_button = QPushButton("Copy")
        self._copy_r_button.clicked.connect(self._on_copy_r)
        self._copy_r_button.setEnabled(False)
        rh_row.addWidget(self._copy_r_button)
        rh_wrap = QWidget(); rh_wrap.setLayout(rh_row)
        copy_layout.addRow("thermal_rth_stages:", rh_wrap)

        self._c_csv_label = QLabel("—")
        self._c_csv_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        ch_row = QHBoxLayout()
        ch_row.addWidget(self._c_csv_label, 1)
        self._copy_c_button = QPushButton("Copy")
        self._copy_c_button.clicked.connect(self._on_copy_c)
        self._copy_c_button.setEnabled(False)
        ch_row.addWidget(self._copy_c_button)
        ch_wrap = QWidget(); ch_wrap.setLayout(ch_row)
        copy_layout.addRow("thermal_cth_stages:", ch_wrap)

        results_layout.addLayout(copy_layout)

        # "Apply to selected device" — writes both CSVs into the
        # selected schematic component in one click (+ flips
        # thermal_network to "foster" since the fit produces Foster
        # stages). Only renders when the dialog has a MainWindow-shaped
        # parent — standalone / test instances see just the Copy
        # buttons. Same pattern as the Thermal Sizing dialog.
        parent_looks_like_main_window = (
            parent is not None
            and hasattr(parent, "_schematic_scene")
            and hasattr(parent, "_execute_schematic_command")
            and hasattr(parent, "_current_circuit")
        )
        if parent_looks_like_main_window:
            apply_row = QHBoxLayout()
            self._apply_button = QPushButton("Apply to selected device")
            self._apply_button.setMinimumHeight(32)
            self._apply_button.setToolTip(
                "Write thermal_rth_stages + thermal_cth_stages into the "
                "selected schematic component's parameters in one click "
                "(also flips thermal_network to 'foster' since this is "
                "a Foster fit). The component must have its thermal "
                "port enabled. Goes through the normal undo stack."
            )
            self._apply_button.setEnabled(False)  # enabled after a fit
            self._apply_button.clicked.connect(self._on_apply_clicked)
            apply_row.addWidget(self._apply_button)
            apply_row.addStretch(1)
            results_layout.addLayout(apply_row)
            self._apply_status = QLabel("")
            self._apply_status.setWordWrap(True)
            self._apply_status.setStyleSheet(
                "color: #4a5568; font-size: 11px; padding-top: 2px;"
            )
            results_layout.addWidget(self._apply_status)
        else:
            self._apply_button = None
            self._apply_status = None

        self._residual_label = QLabel("Residual: —")
        results_layout.addWidget(self._residual_label)

        root.addWidget(results_group)

        # --- Preview plot --------------------------------------------------
        plot_group = QGroupBox("4. Preview — raw points vs fitted curve")
        plot_layout = QVBoxLayout(plot_group)
        self._plot = pg.PlotWidget()
        self._plot.setLogMode(x=True, y=False)
        self._plot.setLabel("bottom", "t", units="s")
        self._plot.setLabel("left", "Z_th", units="K/W")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setMinimumHeight(160)
        self._plot.addLegend()
        plot_layout.addWidget(self._plot)
        root.addWidget(plot_group, 1)

        # --- Close ---------------------------------------------------------
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        root.addWidget(button_box)

    # -- Slots --------------------------------------------------------------

    def _on_load_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Z_th(t) data",
            filter="Text / CSV (*.txt *.csv *.dat);;All files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8", errors="replace") as fh:
                self._text_edit.setPlainText(fh.read())
        except OSError as exc:
            QMessageBox.warning(self, "File error", f"Could not read {filename}:\n{exc}")

    def _on_insert_example(self) -> None:
        self._text_edit.setPlainText(_EXAMPLE_CSV)

    def _on_fit_clicked(self) -> None:
        text = self._text_edit.toPlainText()
        try:
            t, zth = parse_zth_csv(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Z_th data", str(exc))
            return

        n_stages = int(self._n_stages_spin.value())
        n_iter = int(self._n_iter_spin.value())
        try:
            result = fit_zth_to_foster(
                t, zth, n_stages=n_stages, n_iter=n_iter,
            )
        except RuntimeError as exc:
            QMessageBox.warning(self, "Fit failed", str(exc))
            return

        self._fit_result = result
        self._populate_results_table(result)
        self._update_csv_labels(result)
        self._draw_plot(t, zth, result)

    def _populate_results_table(self, result: FosterFitResult) -> None:
        self._stages_table.setRowCount(result.n_stages)
        for row in range(result.n_stages):
            for col, value in enumerate((
                str(row + 1),
                f"{result.r_th_K_per_W[row]:.6g}",
                f"{result.tau_s[row]:.6g}",
                f"{result.c_th_J_per_K[row]:.6g}",
            )):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._stages_table.setItem(row, col, item)

    def _update_csv_labels(self, result: FosterFitResult) -> None:
        self._r_csv_label.setText(f"<tt>{result.r_csv()}</tt>")
        self._c_csv_label.setText(f"<tt>{result.c_csv()}</tt>")
        self._copy_r_button.setEnabled(True)
        self._copy_c_button.setEnabled(True)
        # Apply button only renders for MainWindow-shaped parents — gate
        # the enable on its existence so standalone / test runs are
        # unaffected.
        if self._apply_button is not None:
            self._apply_button.setEnabled(True)

    def _draw_plot(
        self, t: np.ndarray, zth: np.ndarray, result: FosterFitResult,
    ) -> None:
        self._plot.clear()
        self._plot.addLegend()

        # Raw points as scatter.
        self._plot.plot(
            t, zth,
            pen=None, symbol="o", symbolSize=6,
            symbolBrush=(60, 175, 200), symbolPen=(60, 175, 200),
            name="Datasheet",
        )
        # Fitted curve over a denser log-grid.
        t_fit = np.logspace(np.log10(t.min()), np.log10(t.max()), 400)
        z_fit = evaluate_foster_zth(t_fit, result.r_th_K_per_W, result.tau_s)
        self._plot.plot(
            t_fit, z_fit,
            pen=pg.mkPen(color=(245, 158, 11), width=2),
            name=f"{result.n_stages}-stage Foster fit",
        )

        # Residual stats inline.
        z_at_t = evaluate_foster_zth(t, result.r_th_K_per_W, result.tau_s)
        residual_max = float(np.max(np.abs(z_at_t - zth)))
        residual_rms = float(np.sqrt(np.mean((z_at_t - zth) ** 2)))
        z_range = float(zth.max() - zth.min()) or 1.0
        self._residual_label.setText(
            f"Residual: max {residual_max:.4g} K/W "
            f"({100.0 * residual_max / z_range:.2f} % of range), "
            f"RMS {residual_rms:.4g} K/W"
        )

    def _on_copy_r(self) -> None:
        if self._fit_result is None:
            return
        QGuiApplication.clipboard().setText(self._fit_result.r_csv())

    def _on_copy_c(self) -> None:
        if self._fit_result is None:
            return
        QGuiApplication.clipboard().setText(self._fit_result.c_csv())

    # -- Apply to selected device --------------------------------------------

    def _on_apply_clicked(self) -> None:
        """Write the fitted CSVs to the selected schematic device.

        Routes through ``UpdateComponentStateCommand`` so the write
        participates in undo/redo + marks the document dirty. Sets
        ``thermal_network`` to "foster" along with the two CSV fields
        — the fit ALWAYS produces Foster-form stages, so this is the
        correct topology flag whether the user previously had it set
        to "single_rc" or "cauer".
        """
        if self._apply_button is None or self._apply_status is None:
            return
        if self._fit_result is None:
            return
        target = self._find_selected_thermal_device()
        if target is None:
            self._set_apply_status(
                "Select a device with its thermal port enabled on the "
                "schematic first.",
                ok=False,
            )
            return
        main_window, component, device_name = target
        try:
            from copy import deepcopy

            from pulsimgui.commands.component_commands import (
                UpdateComponentStateCommand,
            )

            circuit = main_window._current_circuit()
            old_state = UpdateComponentStateCommand.snapshot(component)
            new_state = deepcopy(old_state)
            params = new_state.setdefault("parameters", {})
            params["thermal_rth_stages"] = self._fit_result.r_csv()
            params["thermal_cth_stages"] = self._fit_result.c_csv()
            # Foster fit ⇒ Foster topology. Flip the toggle so the
            # backend builds FosterStage from these CSVs (the Cauer
            # path would re-interpret R / C as physical layer values,
            # which they aren't for a Z_th fit).
            params["thermal_network"] = "foster"
            command = UpdateComponentStateCommand(
                circuit, component.id, new_state, old_state=old_state,
            )
            main_window._execute_schematic_command(
                command, refresh_scene=True, merge=False,
            )
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            self._set_apply_status(f"Error: {exc}", ok=False)
            return
        self._set_apply_status(
            f"Applied {self._fit_result.n_stages}-stage Foster fit to "
            f"{device_name} (thermal_rth_stages + thermal_cth_stages, "
            f"thermal_network = foster).",
            ok=True,
        )

    def _set_apply_status(self, text: str, *, ok: bool) -> None:
        """Update the status label below the Apply button. Green for
        success, red for "select a device first" / "error". Defensive
        no-op when the label isn't present (standalone construction)."""
        if self._apply_status is None:
            return
        self._apply_status.setText(text)
        color = "#2f855a" if ok else "#c53030"
        self._apply_status.setStyleSheet(
            f"color: {color}; font-size: 11px; padding-top: 2px;"
        )

    def _find_selected_thermal_device(self) -> tuple[Any, Any, str] | None:
        """Return ``(main_window, component, display_name)`` for the
        currently-selected schematic component that has its thermal
        port enabled.

        Acceptance: any component with ``enable_thermal_port=True`` —
        not just MOSFETs/diodes — because the Foster Fit dialog
        produces a junction-to-case ladder, which any loss-carrying
        device with a thermal port can consume. We also accept
        ``thermal_enabled=True`` as a fallback (legacy / SharedHeatsink
        path doesn't always set ``enable_thermal_port``).

        ``None`` when:
          * no parent / no scene available;
          * nothing selected;
          * selection has no ``.component``;
          * selected component is a HEATSINK (it has its own R + C
            sink-side fields — Foster fit doesn't belong there);
          * selected component has neither thermal flag set.
        """
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
            type_name = getattr(comp.type, "name", str(comp.type))
            if type_name == "HEATSINK":
                # HEATSINK has its own sink-side R + C fields — refuse
                # so the user doesn't accidentally write the device's
                # junction-to-case ladder there.
                continue
            params = getattr(comp, "parameters", None) or {}
            has_port = bool(
                params.get("enable_thermal_port", False)
            ) or bool(params.get("thermal_enabled", False))
            if not has_port:
                continue
            return main_window, comp, getattr(comp, "name", "device")
        return None
