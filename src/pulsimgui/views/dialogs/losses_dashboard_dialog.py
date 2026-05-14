"""Loss & efficiency dashboard (wave-4 sub-A 1.4).

Renders the per-device + system-level loss breakdown that's already
computed by Pulsim's thermal pipeline (``ThermalResult.devices[i].losses``)
in a sortable table + system efficiency readout. This is shipped as a
standalone dialog so users can pull it up next to the scope without the
scope workbench needing structural changes; promotion to a permanent
scope tab is queued as a follow-up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pulsimgui.services.backend_types import ThermalDeviceResult, ThermalResult


_COLS = ("Device", "Conduction (W)", "Switching (W)", "Reverse rec. (W)", "Total (W)", "Share")


class LossesDashboardDialog(QDialog):
    """Modal dashboard rendering ``ThermalResult`` loss telemetry.

    The dialog auto-rebuilds its table from the supplied result. Callers
    pass ``None`` (or any result without devices) to render the
    empty-state card, so the dashboard is safe to open before a thermal
    run has populated data.
    """

    def __init__(
        self,
        result: "ThermalResult | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Losses & Efficiency")
        self.setMinimumSize(640, 360)
        self._result: "ThermalResult | None" = result

        self._build_ui()
        self.set_result(result)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._headline = QLabel()
        self._headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._headline.font()
        font.setPointSize(14)
        font.setBold(True)
        self._headline.setFont(font)
        outer.addWidget(self._headline)

        self._subline = QLabel()
        self._subline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._subline)

        self._empty_label = QLabel(
            "No loss telemetry available.\n"
            "Run a thermal-enabled simulation to populate this dashboard."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        outer.addWidget(self._empty_label)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(_COLS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        # Single Close button → connect to both signals for safety.
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_result(self, result: "ThermalResult | None") -> None:
        """Replace the displayed telemetry."""
        self._result = result
        self._populate()

    @property
    def result(self) -> "ThermalResult | None":
        return self._result

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _populate(self) -> None:
        result = self._result
        devices = list(getattr(result, "devices", []) or []) if result is not None else []
        self._table.setRowCount(0)

        if not devices:
            self._headline.setText("No losses available")
            self._subline.setText("")
            self._empty_label.setVisible(True)
            self._table.setVisible(False)
            return

        self._empty_label.setVisible(False)
        self._table.setVisible(True)

        total_loss = float(sum(dev.losses.total for dev in devices))
        switching_total = float(
            sum(dev.losses.switching_total for dev in devices)
        )
        conduction_total = float(sum(dev.losses.conduction for dev in devices))

        # Efficiency is derived only if input power telemetry is present;
        # ThermalResult doesn't carry it today so we mark the readout as
        # "—" until the loss-summary path lands.
        efficiency_text = "—"

        self._headline.setText(f"Total losses: {total_loss:.3g} W")
        self._subline.setText(
            f"Conduction: {conduction_total:.3g} W   "
            f"Switching: {switching_total:.3g} W   "
            f"Efficiency: {efficiency_text}"
        )

        self._table.setSortingEnabled(False)
        for dev in devices:
            row = self._table.rowCount()
            self._table.insertRow(row)
            losses = dev.losses
            share = (losses.total / total_loss) if total_loss > 0 else 0.0
            cells = [
                _text_item(dev.name),
                _num_item(losses.conduction),
                _num_item(losses.switching_total),
                _num_item(losses.reverse_recovery),
                _num_item(losses.total),
                _share_item(share),
            ]
            for col, item in enumerate(cells):
                self._table.setItem(row, col, item)
        self._table.setSortingEnabled(True)
        self._table.sortItems(4, Qt.SortOrder.DescendingOrder)


# ---------------------------------------------------------------------------
# Cell factories
# ---------------------------------------------------------------------------
def _text_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    return item


def _num_item(value: float) -> QTableWidgetItem:
    item = QTableWidgetItem(f"{value:.4g}")
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    item.setData(Qt.ItemDataRole.UserRole, float(value))
    return item


def _share_item(value: float) -> QTableWidgetItem:
    item = QTableWidgetItem(f"{value * 100:.1f} %")
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    item.setData(Qt.ItemDataRole.UserRole, float(value))
    return item
