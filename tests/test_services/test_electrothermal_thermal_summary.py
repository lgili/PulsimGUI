"""Tests for the pulsim 1.5 ``device_thermal_summary`` migration in
``BackendAdapter._compute_per_device_electrothermal``.

The Phase-4 upgrade swaps the legacy ``device_loss_summary`` +
constant-``P_avg`` Foster loop for a single ``device_thermal_summary``
call that reconstructs the real per-step conduction power. These
tests pin:
  1. the primary path produces correct row shapes from a real buck;
  2. the conduction power is the *real* dissipation (resistor heats,
     ideal switches barely do);
  3. the fallback path fires when ``device_thermal_summary`` is
     unavailable, producing the legacy constant-power rows;
  4. row shape stays compatible with what ``thermal_service``
     consumes.
"""
from __future__ import annotations

import pulsim as p

from pulsimgui.services.backend_adapter import PulsimBackend


def _buck_builder():
    """24V→12V synchronous buck, 100 kHz, ideal switches."""
    b = p.CircuitBuilder()
    b.add_voltage_source("Vin", "vin", "gnd", 24.0)
    b.add_switch("M_HS", "vin", "sw", g_on=1e3, g_off=1e-9)
    b.add_switch("M_LS", "sw", "gnd", g_on=1e3, g_off=1e-9)
    b.add_inductor("L", "sw", "vout", 10e-6)
    b.add_capacitor("Cout", "vout", "gnd", 10e-6)
    b.add_resistor("Rload", "vout", "gnd", 2.4)
    return b


def _sync_switch_fn():
    mhs = p.SwitchStateMask(2)
    mhs.set(0, True)
    mls = p.SwitchStateMask(2)
    mls.set(1, True)
    return p.NativeMultiMaskPwm(10e-6, [0.5, 1.0], [mhs, mls])


def _adapter() -> PulsimBackend:
    """A BackendAdapter with the real pulsim module attached.

    BackendAdapter.__init__ may require args in some builds; we
    construct minimally and force ``_module`` to the real pulsim so
    the electrothermal helpers resolve ``FosterStage`` etc.
    """
    adapter = PulsimBackend.__new__(PulsimBackend)
    adapter._module = p  # type: ignore[attr-defined]
    return adapter


def _run(builder, switch_fn, t_end=1e-3):
    return p.simulate(builder, t_end=t_end, dt=1e-7, switch_fn=switch_fn)


# ---------------------------------------------------------------------------
# Primary path — device_thermal_summary.
# ---------------------------------------------------------------------------
def test_primary_path_returns_rows_for_loss_carrying_devices() -> None:
    b = _buck_builder()
    sf = _sync_switch_fn()
    res = _run(b, sf)

    adapter = _adapter()
    rows = adapter._electrothermal_via_thermal_summary(
        b, res, sf, t_amb_celsius=25.0,
    )
    assert rows is not None, "Primary path should be available on pulsim 1.6"
    names = {r["component_name"] for r in rows}
    # Only loss-carrying kinds — no Vin / Cout.
    assert "Rload" in names
    assert "Vin" not in names
    assert "Cout" not in names


def test_primary_path_resistor_heats_switches_barely() -> None:
    """The whole point of the migration: real P_cond(t). The load
    resistor dissipates real power and heats; the ideal switches
    (g_on=1e3) barely do."""
    b = _buck_builder()
    sf = _sync_switch_fn()
    res = _run(b, sf)

    adapter = _adapter()
    rows = adapter._electrothermal_via_thermal_summary(
        b, res, sf, t_amb_celsius=25.0,
    )
    by_name = {r["component_name"]: r for r in rows}

    rload = by_name["Rload"]
    assert rload["conduction"] > 1.0, (
        f"Rload should dissipate real power; got {rload['conduction']} W"
    )
    # T_j must rise above ambient given real dissipation × 1.5 K/W.
    assert rload["final_temperature"] > 25.0
    assert rload["peak_temperature"] >= rload["final_temperature"] - 1e-6

    # Ideal switches: tiny conduction loss, T_j basically ambient.
    for sw in ("M_HS", "M_LS"):
        assert by_name[sw]["conduction"] < 1.0
        assert by_name[sw]["final_temperature"] < 26.0


def test_primary_path_row_shape_matches_thermal_service_contract() -> None:
    """Every row must carry the keys ``thermal_service`` reads."""
    b = _buck_builder()
    sf = _sync_switch_fn()
    res = _run(b, sf)
    adapter = _adapter()
    rows = adapter._electrothermal_via_thermal_summary(
        b, res, sf, t_amb_celsius=25.0,
    )
    required = {
        "component_name", "kind", "final_temperature",
        "peak_temperature", "conduction", "turn_on", "turn_off",
        "temperature_trace",
    }
    for r in rows:
        assert required <= set(r.keys()), (
            f"row {r['component_name']} missing keys: {required - set(r.keys())}"
        )
        assert isinstance(r["temperature_trace"], list)
        assert len(r["temperature_trace"]) > 0


def test_primary_path_no_thermal_specs_returns_empty_not_none() -> None:
    """A circuit with only sources + caps (no loss-carrying device)
    yields an empty row list — and crucially NOT ``None`` (which
    would trigger the legacy fallback for no reason)."""
    b = p.CircuitBuilder()
    b.add_voltage_source("Vin", "a", "gnd", 5.0)
    b.add_capacitor("C1", "a", "gnd", 1e-6)
    res = p.simulate(b, t_end=1e-4, dt=1e-7)

    adapter = _adapter()
    rows = adapter._electrothermal_via_thermal_summary(
        b, res, None, t_amb_celsius=25.0,
    )
    assert rows == []


# ---------------------------------------------------------------------------
# Fallback path — legacy constant-power loop.
# ---------------------------------------------------------------------------
def test_fallback_path_produces_constant_power_rows() -> None:
    """The legacy path still works standalone (used when pulsim < 1.5
    or device_thermal_summary raises)."""
    b = _buck_builder()
    sf = _sync_switch_fn()
    res = _run(b, sf)

    adapter = _adapter()
    rows = adapter._electrothermal_legacy_constant_power(
        b, res, sf, t_amb_celsius=25.0,
    )
    by_name = {r["component_name"]: r for r in rows}
    # Rload dissipates → appears with real conduction power.
    assert "Rload" in by_name
    assert by_name["Rload"]["conduction"] > 1.0
    # Legacy path always reports zero switching split.
    assert by_name["Rload"]["turn_on"] == 0.0
    assert by_name["Rload"]["turn_off"] == 0.0


def test_dispatcher_falls_back_when_thermal_summary_unavailable(monkeypatch) -> None:
    """When ``device_thermal_summary`` import fails, the top-level
    ``_compute_per_device_electrothermal`` must transparently route
    to the legacy path and still return rows."""
    import builtins

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        # Force the ``from pulsim import device_thermal_summary`` line
        # in the primary path to fail, simulating pulsim < 1.5.
        if name == "pulsim" and args and args[3] and (
            "device_thermal_summary" in args[3]
        ):
            raise ImportError("simulated pulsim < 1.5")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    b = _buck_builder()
    sf = _sync_switch_fn()
    res = _run(b, sf)
    adapter = _adapter()
    rows = adapter._compute_per_device_electrothermal(
        builder=b, sim_result=res, switch_fn=sf, t_amb_celsius=25.0,
    )
    # Legacy path still finds the dissipating load resistor.
    names = {r["component_name"] for r in rows}
    assert "Rload" in names


def test_dispatcher_prefers_primary_path() -> None:
    """On pulsim 1.6 the dispatcher should use the primary path,
    which (unlike the legacy constant-power path) reconstructs the
    real conduction trace. We can't easily diff the traces here, but
    we CAN assert the dispatcher returns the same device set the
    primary path returns directly."""
    b = _buck_builder()
    sf = _sync_switch_fn()
    res = _run(b, sf)
    adapter = _adapter()

    primary = adapter._electrothermal_via_thermal_summary(
        b, res, sf, t_amb_celsius=25.0,
    )
    dispatched = adapter._compute_per_device_electrothermal(
        builder=b, sim_result=res, switch_fn=sf, t_amb_celsius=25.0,
    )
    assert primary is not None
    assert {r["component_name"] for r in dispatched} == {
        r["component_name"] for r in primary
    }
