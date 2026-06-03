"""Tests for the backend ``_check_thermal_limits`` helper (pulsim 1.7
``ThermalLimitMonitor`` integration).

What we pin here:

  1. **Detection.** A device whose ``temperature_trace`` exceeds its
     ``thermal_t_max_C`` reports ``tripped=True`` with the first trip
     sample and the peak temperature. Numbers come from pulsim's own
     monitor — we just feed it samples; the test exists to guarantee
     the wiring (param read, trace replay, attribute extraction) is
     correct.
  2. **Opt-out.** ``thermal_t_max_C <= 0`` means "I don't care" — the
     device is silently dropped from the result list, NOT reported as
     ``tripped=False``. (Reporting every device every run would bury
     the actual trips in noise.)
  3. **No trace.** A device that opted in but produced no
     ``temperature_trace`` (e.g. the thermal pipeline skipped it
     because it isn't a loss-carrying kind) is silently skipped — not
     mis-reported as "not tripped".
  4. **Hysteresis.** A non-zero ``hysteresis_C`` is forwarded to
     ``ThermalLimitMonitor`` and reflected on the result record so the
     user can see what was used.
  5. **No rows / no monitor class.** Defensive empty-list paths.
  6. **Empty result list when no row has ``tripped`` AND no rows
     opted in.** Distinguishes from the "got rows, none tripped"
     case which still surfaces the records (for diagnostics).
"""
from __future__ import annotations

import pulsim as p
import pytest

from pulsimgui.services.backend_adapter import PulsimBackend


def _backend() -> PulsimBackend:
    backend = PulsimBackend.__new__(PulsimBackend)
    backend._module = p  # type: ignore[attr-defined]
    return backend


def _device(
    name: str,
    *,
    t_max: float = 0.0,
    hyst: float = 0.0,
) -> dict:
    """Build a minimal component dict carrying the new thermal-limit
    params the model layer adds."""
    return {
        "name": name,
        "type": "MOSFET_N",
        "parameters": {
            "thermal_enabled": True,
            "thermal_t_max_C": t_max,
            "thermal_t_max_hysteresis_C": hyst,
        },
    }


# ---------------------------------------------------------------------------
# Detection (the headline test)
# ---------------------------------------------------------------------------


def test_trip_detected_when_trace_exceeds_t_max() -> None:
    """T_j ramps from 25 °C past 175 °C → monitor trips. The peak we
    record is the trace's max; the trip sample is the first one
    strictly above T_limit_C."""
    trace = [25.0, 50.0, 100.0, 150.0, 176.0, 178.0, 165.0]  # exceeds 175 at idx 4
    rows = [{"component_name": "Q1", "temperature_trace": trace}]
    out = _backend()._check_thermal_limits(
        component_lookup={"Q1": _device("Q1", t_max=175.0)},
        electrothermal_rows=rows,
    )
    assert len(out) == 1
    rec = out[0]
    assert rec["device_name"] == "Q1"
    assert rec["T_limit_C"] == pytest.approx(175.0)
    assert rec["tripped"] is True
    # First sample strictly above 175 is index 4 (176 °C). We feed
    # ``float(sample_idx)`` as ``t`` so trip_time matches the sample
    # index — this is the contract the helper documents.
    assert rec["trip_time_s"] == pytest.approx(4.0)
    assert rec["trip_temperature_C"] == pytest.approx(176.0)
    assert rec["peak_temperature_C"] == pytest.approx(178.0)
    # Convenient "by how much did we cook?" derived field.
    assert rec["trip_margin_C"] == pytest.approx(3.0)


def test_safe_run_under_limit_records_peak_without_tripping() -> None:
    """Sub-limit run still produces a record: tripped=False, peak below
    the limit, trip_margin_C negative. Lets the dashboard show "120 °C
    peak vs 150 °C limit (30 °C margin)" without re-instantiating the
    monitor."""
    trace = [25.0, 60.0, 90.0, 110.0, 120.0, 100.0]
    out = _backend()._check_thermal_limits(
        component_lookup={"Q1": _device("Q1", t_max=150.0)},
        electrothermal_rows=[{"component_name": "Q1", "temperature_trace": trace}],
    )
    rec = out[0]
    assert rec["tripped"] is False
    assert rec["trip_time_s"] is None
    assert rec["trip_temperature_C"] is None
    assert rec["peak_temperature_C"] == pytest.approx(120.0)
    assert rec["trip_margin_C"] == pytest.approx(-30.0)


# ---------------------------------------------------------------------------
# Opt-out, missing-data, defensive
# ---------------------------------------------------------------------------


def test_opt_out_devices_are_silently_dropped() -> None:
    """``thermal_t_max_C <= 0`` → device omitted entirely (not reported
    as "didn't trip"). One opted-in + one opted-out: only the opted-in
    record makes it through."""
    out = _backend()._check_thermal_limits(
        component_lookup={
            "Q1": _device("Q1", t_max=150.0),
            "Q2": _device("Q2", t_max=0.0),     # opted out
            "Q3": _device("Q3", t_max=-50.0),   # opted out (negative)
        },
        electrothermal_rows=[
            {"component_name": "Q1", "temperature_trace": [25.0, 100.0]},
            {"component_name": "Q2", "temperature_trace": [25.0, 200.0]},  # not in result
            {"component_name": "Q3", "temperature_trace": [25.0, 99.0]},
        ],
    )
    assert {rec["device_name"] for rec in out} == {"Q1"}


def test_opted_in_but_no_trace_is_silently_skipped() -> None:
    """Device opted in but ``temperature_trace`` is missing / empty
    (passive component, observer disabled, etc.). Skip it — reporting
    ``tripped=False`` with no actual measurement would be a lie."""
    out = _backend()._check_thermal_limits(
        component_lookup={
            "Q1": _device("Q1", t_max=150.0),
            "Q2": _device("Q2", t_max=150.0),
        },
        electrothermal_rows=[
            {"component_name": "Q1", "temperature_trace": []},
            {"component_name": "Q2"},  # key absent entirely
        ],
    )
    assert out == []


def test_no_rows_returns_empty() -> None:
    """No electrothermal data → nothing to check. Distinguishes "the
    sim ran with no thermal model" from "the sim ran, nobody opted in"
    (both yield ``[]`` — the UI shows "thermal limits: not configured"
    in either case)."""
    out = _backend()._check_thermal_limits(
        component_lookup={"Q1": _device("Q1", t_max=150.0)},
        electrothermal_rows=[],
    )
    assert out == []


def test_unknown_device_name_is_silently_skipped() -> None:
    """A row referring to a component the converter never registered
    (defensive: shim divergence, renamed during sim) — skip rather
    than KeyError."""
    out = _backend()._check_thermal_limits(
        component_lookup={"Q1": _device("Q1", t_max=150.0)},
        electrothermal_rows=[
            {"component_name": "Q_orphan", "temperature_trace": [25.0, 999.0]},
        ],
    )
    assert out == []


# ---------------------------------------------------------------------------
# Hysteresis surfaced through the contract
# ---------------------------------------------------------------------------


def test_hysteresis_is_forwarded_and_echoed() -> None:
    """A user-set hysteresis ends up on the result record so the UI can
    show "T_max = 150 °C ± 5 °C". The behavioural effect (no chatter
    when T_j hovers right at the limit) is owned by pulsim — we just
    pin the wiring."""
    # 152 °C samples but with 5 °C hysteresis. Monitor still trips on
    # the first sample > 150 (because hysteresis only affects re-arming
    # after recovery — the rising-edge trip semantics are unchanged).
    out = _backend()._check_thermal_limits(
        component_lookup={"Q1": _device("Q1", t_max=150.0, hyst=5.0)},
        electrothermal_rows=[{
            "component_name": "Q1",
            "temperature_trace": [25.0, 152.0, 100.0, 148.0, 100.0],
        }],
    )
    assert out[0]["hysteresis_C"] == pytest.approx(5.0)
    assert out[0]["tripped"] is True
    assert out[0]["trip_temperature_C"] == pytest.approx(152.0)


def test_negative_hysteresis_is_clamped_to_zero() -> None:
    """Defensive: a malformed (negative) hysteresis value is clamped
    to 0 before reaching pulsim — the monitor would reject it
    otherwise and we'd lose the whole record over a UI typo."""
    out = _backend()._check_thermal_limits(
        component_lookup={"Q1": _device("Q1", t_max=150.0, hyst=-5.0)},
        electrothermal_rows=[{
            "component_name": "Q1", "temperature_trace": [25.0, 200.0],
        }],
    )
    assert out[0]["hysteresis_C"] == 0.0
    assert out[0]["tripped"] is True
