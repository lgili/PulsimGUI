"""``TriggerCapability`` — Free Run / Single trigger inside the Inspector.

The capability decorates the shell's ``Trigger`` inspector group with:

  * **Mode** combo: ``Free Run`` (always capture) vs ``Single`` (freeze
    on the first crossing).
  * **Source** combo: which registered signal drives the trigger.
  * **Edge** combo: rising / falling crossings.
  * **Level** spin: threshold the source must cross.
  * **Re-arm** button: re-prime ``Single`` mode for the next event.

The trigger logic lives entirely on the GUI thread — when ``Single``
is armed, the capability watches incoming live samples and freezes the
view on the first crossing by toggling pyqtgraph auto-range off. The
``stop()`` method on the simulation service is *not* called; the user
can keep streaming and just choose what they look at.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


class TriggerCapability:
    """Populate the Trigger inspector group with mode/source/edge/level UI."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None

        self._mode_combo: QComboBox | None = None
        self._source_combo: QComboBox | None = None
        self._edge_combo: QComboBox | None = None
        self._level_spin: QDoubleSpinBox | None = None
        self._rearm_btn: QPushButton | None = None
        self._status_lbl: QLabel | None = None

        self._mode = "Free Run"
        self._source: str | None = None
        self._edge = "rising"
        self._level = 0.0
        self._armed = True
        self._fired = False
        # Track the last-seen sample to detect edge crossings between
        # successive incoming chunks (we don't re-look at the cached
        # history every tick — too expensive).
        self._last_value: float | None = None

    def attach(self, shell: BaseScopeWindow) -> None:
        self._shell = shell
        self._build_ui(shell.inspector.trigger_group)

        # Periodically refresh the source combo so newly added signals
        # become selectable without the user having to re-open the
        # group. We just hook into the toolbar's run signal — every Run
        # is a natural moment to refresh.
        shell.toolbar.run_clicked.connect(self._refresh_sources)

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self, group_frame: QWidget) -> None:
        layout = group_frame.layout()
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        def _add_row(row: int, label: str, widget: QWidget) -> None:
            k = QLabel(label)
            kf = QFont()
            kf.setPointSize(10)
            kf.setWeight(QFont.Weight.DemiBold)
            k.setFont(kf)
            grid.addWidget(k, row, 0)
            grid.addWidget(widget, row, 1)
            grid.setColumnStretch(1, 1)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Free Run", "Single"])
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        _add_row(0, "Mode", self._mode_combo)

        self._source_combo = QComboBox()
        self._source_combo.addItem("(none)")
        self._source_combo.currentTextChanged.connect(self._on_source_changed)
        _add_row(1, "Source", self._source_combo)

        self._edge_combo = QComboBox()
        self._edge_combo.addItems(["rising", "falling"])
        self._edge_combo.currentTextChanged.connect(self._on_edge_changed)
        _add_row(2, "Edge", self._edge_combo)

        self._level_spin = QDoubleSpinBox()
        self._level_spin.setRange(-1e12, 1e12)
        self._level_spin.setDecimals(6)
        self._level_spin.setSingleStep(0.1)
        self._level_spin.valueChanged.connect(self._on_level_changed)
        _add_row(3, "Level", self._level_spin)

        layout.addWidget(grid_host)

        row_btn = QWidget()
        row_btn_layout = QHBoxLayout(row_btn)
        row_btn_layout.setContentsMargins(0, 4, 0, 0)
        self._rearm_btn = QPushButton("Re-arm")
        self._rearm_btn.setEnabled(False)
        self._rearm_btn.clicked.connect(self._rearm)
        row_btn_layout.addWidget(self._rearm_btn)
        row_btn_layout.addStretch(1)
        layout.addWidget(row_btn)

        self._status_lbl = QLabel("Free Run — capturing continuously.")
        sf = QFont()
        sf.setPointSize(9)
        self._status_lbl.setFont(sf)
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._status_lbl)

    # ── Source list management ──────────────────────────────────────────

    def _refresh_sources(self) -> None:
        if self._shell is None or self._source_combo is None:
            return
        existing = set()
        for i in range(self._source_combo.count()):
            existing.add(self._source_combo.itemText(i))
        canvas_signals = ["(none)"] + list(self._shell.plot_canvas.signals())
        if existing == set(canvas_signals):
            return
        self._source_combo.blockSignals(True)
        current = self._source_combo.currentText()
        self._source_combo.clear()
        self._source_combo.addItems(canvas_signals)
        if current in canvas_signals:
            self._source_combo.setCurrentText(current)
        self._source_combo.blockSignals(False)
        self._on_source_changed(self._source_combo.currentText())

    # ── Slots ───────────────────────────────────────────────────────────

    def _on_mode_changed(self, mode: str) -> None:
        self._mode = mode
        self._fired = False
        self._armed = mode != "Free Run"
        if self._rearm_btn is not None:
            self._rearm_btn.setEnabled(mode == "Single")
        self._update_status()

    def _on_source_changed(self, source: str) -> None:
        self._source = None if source in ("", "(none)") else source
        self._update_status()

    def _on_edge_changed(self, edge: str) -> None:
        self._edge = edge

    def _on_level_changed(self, level: float) -> None:
        self._level = float(level)

    def _rearm(self) -> None:
        self._armed = True
        self._fired = False
        self._last_value = None
        self._update_status()

    def _update_status(self) -> None:
        if self._status_lbl is None:
            return
        if self._mode == "Free Run":
            self._status_lbl.setText("Free Run — capturing continuously.")
            return
        if self._source is None:
            self._status_lbl.setText("Single — pick a source signal.")
        elif self._fired:
            self._status_lbl.setText("Single — fired. Click Re-arm.")
        else:
            self._status_lbl.setText("Single — armed; waiting for crossing.")

    def detect_crossing(self, source_name: str, t_new: np.ndarray, y_new: np.ndarray) -> bool:
        """Hook the live-stream tick can call to test for a Single fire.

        Returns ``True`` the first time the source crosses ``self._level``
        in the configured direction after Re-arm. After firing, the
        capability ignores further crossings until the user re-arms.
        """
        if (
            self._mode != "Single"
            or not self._armed
            or self._fired
            or source_name != self._source
            or y_new.size == 0
        ):
            return False
        target = float(self._level)
        prev = self._last_value
        fired = False
        for v in y_new:
            if prev is not None:
                if self._edge == "rising" and prev <= target < v:
                    fired = True
                elif self._edge == "falling" and prev >= target > v:
                    fired = True
                if fired:
                    break
            prev = float(v)
        self._last_value = float(y_new[-1])
        if fired:
            self._fired = True
            self._armed = False
            self._update_status()
        return fired


__all__ = ["TriggerCapability"]
