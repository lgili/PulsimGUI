"""Tests for ``PulsimBackend._normalize_signal_name`` — the prefix
recognition that decides whether a raw kernel signal name needs to be
wrapped in ``V(...)``.

Background
----------

The earlier state-vector → signal-name pairing fix (7b6569c) made the
backend use ``circuit.builder.state_var_names()`` as the authoritative
ordering. Pulsim's state_var_names emits TYPE-PREFIXED names like
``V(N2)``, ``I(L_boost)``, ``Is(I_L)``, ``Is(M1_E_a)``. The wrapper
must recognise ALL of these as already-prefixed and leave them alone.

The fix passed for ``V(...)`` / ``I(...)`` / ``P(...)`` / ``T(...)``
but MISSED ``Is(...)`` — the result was double-wrapped keys like
``"V(Is(I_L))"``, which:

  * Polluted the scope's available-signals list with phantom voltages
    that were really inductor currents.
  * Broke probe lookup for users wiring a current probe through the
    voltage-domain path.

These tests pin every kernel-emitted prefix so a future regression
catches the missing prefix immediately.
"""
from __future__ import annotations

import pytest

from pulsimgui.services.backend_adapter import PulsimBackend


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        # V() — node voltages, the most common kernel signal kind.
        ("V(N2)", "V(N2)"),
        ("V(BUS_P)", "V(BUS_P)"),
        ("V(gnd)", "V(gnd)"),
        # I() — branch currents through dedicated state entries.
        ("I(L_boost)", "I(L_boost)"),
        ("I(M1_Ls_a)", "I(M1_Ls_a)"),
        # Is() — branch currents via voltage-source equivalent. The
        # bug we're guarding against here: this used to fall through
        # to ``V(Is(...))`` because the prefix tuple only included
        # ``I(`` and that doesn't match ``Is(``.
        ("Is(I_L)", "Is(I_L)"),
        ("Is(M1_E_a)", "Is(M1_E_a)"),
        ("Is(V1)", "Is(V1)"),
        # P() — power.
        ("P(R_load)", "P(R_load)"),
        # T() — thermal trace.
        ("T(Q_boost)", "T(Q_boost)"),
        ("T(BR1_D1)", "T(BR1_D1)"),
    ],
)
def test_already_prefixed_names_are_left_alone(raw_name: str, expected: str) -> None:
    """Every recognised kernel prefix returns the name unchanged.
    Pre-fix bug: ``"Is(I_L)"`` returned ``"V(Is(I_L))"`` — the
    parametric ``Is(...)`` rows ABOVE pin this regression."""
    assert PulsimBackend._normalize_signal_name(raw_name) == expected


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        # Unprefixed names that the kernel emits as bare node labels —
        # legitimate use for the default ``V(name)`` wrap.
        ("N2", "V(N2)"),
        ("BUS_P", "V(BUS_P)"),
        ("ac_neg", "V(ac_neg)"),
        # Empty / falsy inputs fall back to the canonical ``V(?)``
        # rather than producing a malformed key.
        ("", "V(?)"),
        ("   ", "V(?)"),
    ],
)
def test_unprefixed_names_get_voltage_wrapper(raw_name: str, expected: str) -> None:
    """The default assumption for a raw kernel key without a recognised
    prefix is that it's a node-voltage label. This is the behaviour
    the GUI's probe enrichment relies on for legacy schematics that
    pass node ids straight through."""
    assert PulsimBackend._normalize_signal_name(raw_name) == expected


def test_case_insensitive_prefix_match_for_uppercase_keys() -> None:
    """Defensive: a kernel build that uppercases prefixes (``V(...)``
    vs ``v(...)``) should still be recognised. We don't drop case for
    the body — only for the prefix sniff."""
    # Lowercase v( — recognised via the case-insensitive sweep.
    assert PulsimBackend._normalize_signal_name("v(node)") == "v(node)"


def test_double_wrap_prevented_for_isolated_legacy_case() -> None:
    """Headline regression — ``Is(I_L)`` must NEVER come back as
    ``V(Is(I_L))``. The previous pipeline would silently produce that
    key, and downstream scope channels labelled ``"I_L"`` would either
    miss (signal lookup tries ``I(I_L)`` first, finds nothing) or
    pick up the wrong signal."""
    out = PulsimBackend._normalize_signal_name("Is(I_L)")
    assert out == "Is(I_L)"
    assert not out.startswith("V(Is")
