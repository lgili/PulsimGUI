"""Tests for LossesDashboardDialog (wave-4 sub-A 1.4)."""

from __future__ import annotations

from pulsimgui.services.backend_types import (
    LossBreakdown,
    ThermalDeviceResult,
    ThermalResult,
)
from pulsimgui.views.dialogs.losses_dashboard_dialog import LossesDashboardDialog


def _device(name: str, *, cond: float, sw_on: float, sw_off: float, rr: float = 0.0):
    return ThermalDeviceResult(
        name=name,
        losses=LossBreakdown(
            conduction=cond,
            switching_on=sw_on,
            switching_off=sw_off,
            reverse_recovery=rr,
        ),
    )


def _result(*devices: ThermalDeviceResult) -> ThermalResult:
    return ThermalResult(devices=list(devices), ambient_temperature=25.0)


def test_empty_state_when_no_result(qapp):
    dlg = LossesDashboardDialog(None)
    try:
        assert not dlg._empty_label.isHidden()
        assert dlg._table.isHidden() is True
        assert dlg._headline.text() == "No losses available"
    finally:
        dlg.deleteLater()


def test_empty_state_when_result_has_no_devices(qapp):
    dlg = LossesDashboardDialog(ThermalResult())
    try:
        assert not dlg._empty_label.isHidden()
        assert dlg._table.rowCount() == 0
    finally:
        dlg.deleteLater()


def test_populates_one_row_per_device(qapp):
    res = _result(
        _device("M1", cond=2.5, sw_on=0.5, sw_off=0.5),
        _device("D1", cond=1.0, sw_on=0.0, sw_off=0.0, rr=0.2),
    )
    dlg = LossesDashboardDialog(res)
    try:
        assert dlg._table.rowCount() == 2
        assert dlg._empty_label.isHidden() is True
        # Total losses headline.
        assert "Total losses" in dlg._headline.text()
        # 2.5 + 0.5 + 0.5 + 1.0 + 0.2 = 4.7
        assert "4.7" in dlg._headline.text()
    finally:
        dlg.deleteLater()


def test_share_column_sums_to_100_percent(qapp):
    res = _result(
        _device("A", cond=1.0, sw_on=0.0, sw_off=0.0),
        _device("B", cond=3.0, sw_on=0.0, sw_off=0.0),
    )
    dlg = LossesDashboardDialog(res)
    try:
        rows = dlg._table.rowCount()
        # Get user-role floats for the share column (col 5).
        from PySide6.QtCore import Qt as _Qt

        shares = []
        for row in range(rows):
            item = dlg._table.item(row, 5)
            assert item is not None
            shares.append(float(item.data(_Qt.ItemDataRole.UserRole)))
        assert sum(shares) == 1.0  # exact since both inputs are exact
    finally:
        dlg.deleteLater()


def test_set_result_repopulates_table(qapp):
    res_a = _result(_device("A", cond=1.0, sw_on=0.0, sw_off=0.0))
    res_b = _result(
        _device("B1", cond=2.0, sw_on=0.0, sw_off=0.0),
        _device("B2", cond=1.0, sw_on=0.0, sw_off=0.0),
    )
    dlg = LossesDashboardDialog(res_a)
    try:
        assert dlg._table.rowCount() == 1
        dlg.set_result(res_b)
        assert dlg._table.rowCount() == 2
        dlg.set_result(None)
        assert dlg._table.rowCount() == 0
        assert not dlg._empty_label.isHidden()
    finally:
        dlg.deleteLater()


def test_sorts_by_total_loss_descending_by_default(qapp):
    res = _result(
        _device("low", cond=0.1, sw_on=0.0, sw_off=0.0),
        _device("high", cond=10.0, sw_on=0.0, sw_off=0.0),
        _device("mid", cond=1.0, sw_on=0.0, sw_off=0.0),
    )
    dlg = LossesDashboardDialog(res)
    try:
        names = [dlg._table.item(row, 0).text() for row in range(dlg._table.rowCount())]
        assert names == ["high", "mid", "low"]
    finally:
        dlg.deleteLater()
