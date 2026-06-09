"""Unit tests for the external M3C gate modulator (Etapa 5-6 conversion)."""
from __future__ import annotations

from types import SimpleNamespace

from pulsimgui.services.m3c_gate_modulator import M3CSvmGateModulator

BRANCHES = [f"M_{X}{y}" for X in "ABC" for y in "abc"]


class _Arm:
    def __init__(self, name, v_per_sm, i_b):
        self.name = name
        self.params = SimpleNamespace(n_sm=len(v_per_sm))
        self.v_C_per_sm = list(v_per_sm)
        self.i_b = i_b


class _FakeController:
    """Minimal update()/m_ref() controller for the update() test."""
    def __init__(self):
        self.branches = list(BRANCHES)
        self._m = {n: 0.0 for n in BRANCHES}
        self.calls = 0

    def update(self, t, currents, vcap):
        self.calls += 1
        # echo a simple modulation so we can see it propagate
        for n in self.branches:
            self._m[n] = 0.5

    def m_ref(self, name):
        return self._m.get(name, 0.0)


def _mod(pwm=False):
    return M3CSvmGateModulator(controller=_FakeController(),
                               branches=list(BRANCHES), pwm=pwm)


def test_zero_modulation_all_bypassed() -> None:
    m = _mod()
    arm = _Arm("M_Aa", [4000.0] * 6, i_b=100.0)
    assert m.gates_for(0.0, arm) == [0.0] * 6


def test_full_positive_inserts_all() -> None:
    m = _mod()
    m._m_ref["M_Aa"] = 1.0
    arm = _Arm("M_Aa", [4000.0] * 6, i_b=100.0)
    assert m.gates_for(0.0, arm) == [1.0] * 6


def test_half_modulation_inserts_half() -> None:
    """m=0.5, N=6 ⇒ level 3.0 ⇒ exactly 3 submodules inserted (+1)."""
    m = _mod()
    m._m_ref["M_Aa"] = 0.5
    arm = _Arm("M_Aa", [4000.0] * 6, i_b=100.0)
    s = m.gates_for(0.0, arm)
    assert sum(1 for x in s if x == 1.0) == 3
    assert sum(1 for x in s if x == 0.0) == 3
    assert m.last_n_insert["M_Aa"] == 3


def test_sort_and_select_charges_lowest_when_charging() -> None:
    """Positive insertion + i_b>0 charges the inserted caps, so the EXTERNAL
    sort-and-select must pick the lowest-voltage submodules."""
    m = _mod()
    m._m_ref["M_Aa"] = 0.5                       # 3 of 6 inserted
    v = [4600.0, 4500.0, 4000.0, 3700.0, 3500.0, 3600.0]
    arm = _Arm("M_Aa", v, i_b=120.0)             # charging
    s = m.gates_for(0.0, arm)
    inserted = {k for k, x in enumerate(s) if x == 1.0}
    # the three lowest caps are indices 3,4,5
    assert inserted == {3, 4, 5}


def test_sort_and_select_discharges_highest() -> None:
    """Negative insertion with i_b>0 DISCHARGES the inserted caps, so it must
    pick the highest-voltage submodules to bring them down."""
    m = _mod()
    m._m_ref["M_Aa"] = -0.5                      # 3 of 6 inserted at −1
    v = [4600.0, 4500.0, 4000.0, 3700.0, 3500.0, 3600.0]
    arm = _Arm("M_Aa", v, i_b=120.0)
    s = m.gates_for(0.0, arm)
    inserted = {k for k, x in enumerate(s) if x == -1.0}
    assert all(x in (0.0, -1.0) for x in s)
    assert inserted == {0, 1, 2}                 # three highest caps


def test_pwm_dither_realises_fractional_level() -> None:
    """m chosen so level = 2.5: with PWM the insertion count toggles between 2
    and 3 across the carrier, averaging the fractional level."""
    m = _mod(pwm=True)
    m.f_carrier = 2000.0
    m._m_ref["M_Aa"] = 2.5 / 6.0                 # level = 2.5
    arm = _Arm("M_Aa", [4000.0] * 6, i_b=100.0)
    counts = set()
    for k in range(200):
        t = k * 1.0e-5
        s = m.gates_for(t, arm)
        counts.add(sum(1 for x in s if x == 1.0))
    assert counts == {2, 3}                      # dithers between the two levels


def test_update_propagates_controller_m_ref() -> None:
    m = _mod()
    m.update(0.0, {n: 0.0 for n in BRANCHES}, {n: 24000.0 for n in BRANCHES})
    arm = _Arm("M_Bb", [4000.0] * 6, i_b=100.0)
    # controller echoed 0.5 into the cache; no gates computed yet
    assert "M_Bb" not in m.last_n_insert
    assert m._m_ref["M_Bb"] == 0.5
    s = m.gates_for(0.0, arm)
    assert sum(1 for x in s if x == 1.0) == 3
    assert m.controller.calls == 1
