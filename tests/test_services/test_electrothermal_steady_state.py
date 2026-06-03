"""Tests for the backend ``_compute_electrothermal_steady_state``
helper (pulsim 1.7 ``electrothermal_steady_state`` + ``TempCoLoss``).

What we pin here:

  1. **Skip-when-trivial.** When every device has
     ``loss_a_cond_per_C == loss_a_sw_per_C == 0``, this solver
     reduces *exactly* to ``shared_heatsink_steady_state`` (already
     run by the sibling helper) — so we skip it to keep the result
     list clean.

  2. **Stable solve carries converged powers + feedback gain.** A
     normal positive-tempco MOSFET reaches a higher T_j than the
     T-independent shared-heatsink answer because the conduction loss
     grows with junction temperature. We pin the structure of the
     result, not the exact ºC (those come from pulsim's solver).

  3. **Runaway flagged.** Tempco × R_th cranked up far enough drives
     ρ(M·K) ≥ 1 — no stable equilibrium exists. The record must
     surface ``runaway=True`` and a feedback_gain ≥ 1 so the UI can
     warn the user BEFORE they blow up a real part.

  4. **Reference powers are split conduction vs switching.** The
     ``TempCoLoss`` math anchors ``a_cond`` to ``P_cond_ref`` and
     ``a_sw`` to ``P_sw_ref`` — mixing them would distort the
     closed-form fixed point.

  5. **No descriptors / no pulsim 1.7.** Defensive empty paths.
"""
from __future__ import annotations

import pulsim as p
import pytest

from pulsimgui.services.backend_adapter import PulsimBackend


def _backend() -> PulsimBackend:
    backend = PulsimBackend.__new__(PulsimBackend)
    backend._module = p  # type: ignore[attr-defined]
    return backend


class _StubCircuit:
    def __init__(self, descriptors: list[dict]) -> None:
        self.shared_heatsink_descriptors = descriptors


def _descriptor(devices: list[dict], R_sa: float = 3.0, T_amb: float = 40.0) -> dict:
    return {
        "name": "HS",
        "R_th_sink_to_amb_K_per_W": R_sa,
        "C_th_sink_J_per_K": 0.0,
        "T_amb_C": T_amb,
        "devices": devices,
    }


def _device_spec(
    name: str,
    *,
    R_jc: float = 1.0,
    R_cs: float = 0.5,
) -> dict:
    return {
        "device_name": name, "device_type": "MOSFET_N",
        "R_th_case_to_sink_K_per_W": R_cs,
        "thermal_rth_stages": "", "thermal_cth_stages": "",
        "thermal_rth_K_per_W": R_jc, "thermal_cth_J_per_K": 0.075,
    }


def _component(name: str, *, a_cond: float = 0.0, a_sw: float = 0.0) -> dict:
    return {
        "name": name, "type": "MOSFET_N",
        "parameters": {
            "thermal_enabled": True,
            "thermal_temp_ref": 25.0,
            "loss_a_cond_per_C": a_cond,
            "loss_a_sw_per_C": a_sw,
        },
    }


# ---------------------------------------------------------------------------
# Skip-when-trivial: all tempcos zero → no result (shared steady-state owns it)
# ---------------------------------------------------------------------------


def test_all_zero_tempcos_yields_empty_result() -> None:
    """No tempco on any device → ``electrothermal_steady_state`` would
    give the same answer as ``shared_heatsink_steady_state``. Skip the
    redundant work AND keep the result list clean for the UI."""
    desc = _descriptor([_device_spec("Q1"), _device_spec("Q2")])
    rows = [
        {"component_name": "Q1", "conduction": {"P_avg_W": 5.0}},
        {"component_name": "Q2", "conduction": {"P_avg_W": 10.0}},
    ]
    out = _backend()._compute_electrothermal_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
        component_lookup={"Q1": _component("Q1"), "Q2": _component("Q2")},
    )
    assert out == []


# ---------------------------------------------------------------------------
# Stable solve: hotter than the T-independent answer (positive tempco)
# ---------------------------------------------------------------------------


def test_positive_tempco_drives_T_j_above_T_independent_answer() -> None:
    """A small positive ``a_cond`` (Rds_on rises with T_j) makes the
    converged conduction loss exceed the reference loss — so T_j ends
    up above the T-independent ``shared_heatsink_steady_state`` answer.
    We pin: result records exist, ``converged=True``, ``runaway=False``,
    final_powers > reference_powers, and feedback_gain in (0, 1)."""
    desc = _descriptor([_device_spec("Q1"), _device_spec("Q2")])
    rows = [
        {"component_name": "Q1", "conduction": {"P_avg_W": 5.0}},
        {"component_name": "Q2", "conduction": {"P_avg_W": 10.0}},
    ]
    out = _backend()._compute_electrothermal_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
        component_lookup={
            "Q1": _component("Q1", a_cond=0.006),
            "Q2": _component("Q2", a_cond=0.006),
        },
    )
    assert len(out) == 1
    rec = out[0]
    assert rec["converged"] is True
    assert rec["runaway"] is False
    assert 0.0 < rec["feedback_gain"] < 1.0  # stable margin
    # Converged power > reference power (T_j > 25 °C, positive tempco).
    assert rec["final_powers_W"]["Q1"] > rec["reference_powers_W"]["Q1"]
    assert rec["final_powers_W"]["Q2"] > rec["reference_powers_W"]["Q2"]
    # T_j above the device-isolated answer (Q2 hotter than Q1 because
    # it dissipates more) — sanity check the coupling didn't invert.
    assert rec["devices"]["Q2"] > rec["devices"]["Q1"] > 60.0


# ---------------------------------------------------------------------------
# Runaway detection
# ---------------------------------------------------------------------------


def test_runaway_is_flagged_when_feedback_gain_exceeds_unity() -> None:
    """Crank R_jc + R_sa and the tempco far enough and the feedback
    gain ρ(M·K) crosses 1 — no stable equilibrium exists. We must
    surface ``runaway=True`` so the UI can warn the user BEFORE they
    blow up a real part. Setup:
      * 1 device, R_jc = 5 K/W, R_sa = 5 K/W, R_cs = 0
      * conduction loss = 50 W
      * a_cond = 0.05 /°C (cartoon-physics: 5%/°C — well past silicon)
    With M = R_sa + R_jc + R_cs = 10 K/W and K = dP/dT = a · P = 2.5
    W/°C, ρ = M·K = 25 — well above 1.
    """
    desc = _descriptor(
        [_device_spec("Q1", R_jc=5.0, R_cs=0.0)],
        R_sa=5.0, T_amb=25.0,
    )
    rows = [{"component_name": "Q1", "conduction": {"P_avg_W": 50.0}}]
    out = _backend()._compute_electrothermal_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
        component_lookup={"Q1": _component("Q1", a_cond=0.05)},
    )
    assert len(out) == 1
    rec = out[0]
    assert rec["runaway"] is True
    assert rec["converged"] is False
    assert rec["feedback_gain"] >= 1.0
    assert "T_amb_C" in rec
    assert "R_th_sink_to_amb_K_per_W" in rec
    # Stable-only fields aren't expected on a runaway record — make
    # sure we don't lie about them.
    assert "T_sink_C" not in rec or rec.get("T_sink_C") is None
    assert "devices" not in rec or not rec.get("devices")


# ---------------------------------------------------------------------------
# Reference powers split — conduction vs switching anchoring
# ---------------------------------------------------------------------------


def test_conduction_and_switching_tempcos_are_independent() -> None:
    """``a_cond`` should anchor to ``P_cond_ref`` (conduction loss
    only) and ``a_sw`` to ``P_sw_ref`` (turn_on + turn_off). A device
    with ZERO a_sw but non-zero a_cond shouldn't see its switching
    losses inflated. We test by making one device sw-loss-dominated
    with a_cond=0, a_sw=0 — gets the T-independent answer — and
    asserting its final P matches its reference P."""
    desc = _descriptor(
        [_device_spec("Q1"), _device_spec("Q2")],
        R_sa=2.0, T_amb=25.0,
    )
    rows = [
        # Q1 is conduction-heavy with a positive a_cond → final > ref.
        {"component_name": "Q1", "conduction": {"P_avg_W": 4.0},
         "turn_on": {"P_avg_W": 0.5}, "turn_off": {"P_avg_W": 0.5}},
        # Q2 is switching-heavy with a_cond=a_sw=0 (no tempcos).
        # We feed Q2 a different LossModel via the descriptor + lookup;
        # but its tempcos are zero so its final = reference.
        {"component_name": "Q2",
         "conduction": {"P_avg_W": 1.0},
         "turn_on": {"P_avg_W": 3.0}, "turn_off": {"P_avg_W": 3.0}},
    ]
    out = _backend()._compute_electrothermal_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
        component_lookup={
            "Q1": _component("Q1", a_cond=0.006),
            "Q2": _component("Q2"),  # all-zero tempcos — but still in the sink
        },
    )
    assert len(out) == 1
    rec = out[0]
    # Q1 (with a_cond > 0) saw its conduction loss grow.
    assert rec["final_powers_W"]["Q1"] > rec["reference_powers_W"]["Q1"]
    # Q2 (with all-zero tempcos) is anchored — final = reference. This
    # validates that a_cond=0 + a_sw=0 yields a true no-op for that
    # device's loss model even when the sink is coupled to a tempco-active
    # peer.
    assert rec["final_powers_W"]["Q2"] == pytest.approx(
        rec["reference_powers_W"]["Q2"], rel=1e-9,
    )


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_no_descriptors_returns_empty() -> None:
    """No HEATSINK → no electrothermal records — the legacy isolated
    path owns the answer."""
    out = _backend()._compute_electrothermal_steady_state(
        circuit=_StubCircuit([]),
        electrothermal_rows=[
            {"component_name": "Q1", "conduction": {"P_avg_W": 5.0}},
        ],
        component_lookup={"Q1": _component("Q1", a_cond=0.006)},
    )
    assert out == []


def test_devices_without_power_rows_are_dropped() -> None:
    """Same defensive contract as ``shared_heatsink``: a device whose
    name isn't in ``electrothermal_rows`` (no recorded loss model) is
    excluded from the solve so it doesn't get folded in as 0 W."""
    desc = _descriptor(
        [_device_spec("Q1"), _device_spec("Q_passive")],
        R_sa=2.0, T_amb=25.0,
    )
    rows = [{"component_name": "Q1", "conduction": {"P_avg_W": 5.0}}]
    out = _backend()._compute_electrothermal_steady_state(
        circuit=_StubCircuit([desc]),
        electrothermal_rows=rows,
        component_lookup={
            "Q1": _component("Q1", a_cond=0.006),
            "Q_passive": _component("Q_passive", a_cond=0.006),
        },
    )
    # Only Q1 appears in the result; Q_passive is silently dropped.
    assert len(out) == 1
    assert "Q1" in out[0]["devices"]
    assert "Q_passive" not in out[0].get("devices", {})
