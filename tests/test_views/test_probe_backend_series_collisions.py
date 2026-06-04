"""Tests for ``MainWindow._probe_backend_series`` — the helper that
translates a (probe component, wired node) pair into a concrete signal
series from ``result.signals``.

The lookup chain has to tolerate three independent kinds of name
divergence between the schematic and the kernel:

  1. **Wire-alias divergence.** The user labels a wire ``"SW"`` but the
     kernel emits the same node's voltage as ``"V(N7)"`` (numeric
     auto-naming).
  2. **Casing divergence.** Probe is ``"I_L"``, kernel emits ``"i_l"``
     or ``"I(I_L)"``.
  3. **Name-collision divergence.** A user-named probe carries the
     same label as an unrelated kernel-emitted signal — e.g. a
     ``VOLTAGE_PROBE`` named ``"I_L"`` while ``I_L`` is also the
     kernel's current-probe key on an inductor. Bare-name matching
     would silently return the WRONG signal (current instead of
     voltage); the lookup has to prefer the type-prefix-wrapped form
     (``V(N5)``) and reject same-name bare matches whose body also
     appears under the OPPOSITE kernel-prefix.

These tests pin all three by exercising representative scenarios
synthetically (no backend, no Qt event loop) — the helper is a pure
function over the ``result.signals`` dict.
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.main_window import MainWindow


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    """MainWindow's class-level imports require a QApplication to be
    instantiated before they fire. The helper is a staticmethod but
    the import does QObject registrations at import time."""
    return QApplication.instance() or QApplication(sys.argv)


def _result(signals: dict[str, list[float]]) -> SimulationResult:
    """Minimal SimulationResult shim — only ``signals`` is read by the
    helper, but every result needs a non-empty ``time`` for downstream
    callers."""
    sample_count = max((len(s) for s in signals.values()), default=1)
    return SimulationResult(
        time=[float(i) for i in range(sample_count)],
        signals={k: list(v) for k, v in signals.items()},
        statistics={},
        error_message="",
    )


# ---------------------------------------------------------------------------
# Name-collision defense — the main motivation for this file
# ---------------------------------------------------------------------------


def test_voltage_probe_named_like_a_current_key_returns_node_voltage() -> None:
    """A VOLTAGE_PROBE the user (badly) named ``"I_L"`` while
    ``signals`` also contains a current-probe key ``"I_L"`` MUST
    return the voltage at the node it's wired to (``V(N5)``), NOT the
    inductor current that happens to share its name.

    Pre-defense: the probe's ``component_name="I_L"`` was the first
    candidate in the lookup chain and ``signals["I_L"]`` matched
    immediately, returning the current series. The scope channel
    then displayed amps in a volts-scoped widget."""
    result = _result({
        "I_L": [10.0, 20.0, 30.0],       # current series — must NOT win
        "Is(I_L)": [10.0, 20.0, 30.0],   # current's V-source equiv
        "V(N5)": [5.0, 5.0, 5.0],        # the voltage we want
    })
    series = MainWindow._probe_backend_series(
        result, "I_L", "probe-uuid",
        node_label="N5", node_id="5", kernel_prefix="V",
    )
    assert series == [5.0, 5.0, 5.0]


def test_current_probe_named_like_a_voltage_key_returns_branch_current() -> None:
    """Symmetric defense for the I direction. A CURRENT_PROBE named
    ``"Vbus"`` while ``signals`` ALSO contains the voltage key
    ``"Vbus"`` (or a body collision via ``V(Vbus)``) must return the
    current series, NOT the voltage."""
    result = _result({
        "Vbus": [100.0, 100.0, 100.0],    # voltage that happens to share probe name
        "V(Vbus)": [100.0, 100.0, 100.0], # same node, wrapped form
        "I(Vbus)": [1.5, 1.6, 1.7],       # the current we actually want
        "Is(Vbus)": [1.5, 1.6, 1.7],
    })
    series = MainWindow._probe_backend_series(
        result, "Vbus", "probe-uuid",
        node_label="Vbus", node_id="42", kernel_prefix="I",
    )
    # Must be the current series — neither of the voltage entries.
    assert series == [1.5, 1.6, 1.7]


def test_voltage_probe_falls_through_to_node_id_when_label_collides() -> None:
    """Wire alias collides with a current key, but the node_id branch
    still resolves cleanly via ``V(N{node_id})``. Pin that the helper
    walks the WHOLE wrapped-candidate list (label variants + id
    variants) before falling to bare matches."""
    result = _result({
        # "AC_NEG" alias collides with a switching-loss probe key
        # users might place — same body, different domain.
        "AC_NEG": [99.0, 99.0, 99.0],         # WRONG type
        "I(AC_NEG)": [99.0, 99.0, 99.0],      # foreign wrapper of the same body
        "V(N2)": [-311.0, +311.0, 0.0],       # the real V at the wire's kernel node
    })
    series = MainWindow._probe_backend_series(
        result, "Vin", "probe-uuid",
        node_label="AC_NEG", node_id="2", kernel_prefix="V",
    )
    assert series == [-311.0, +311.0, 0.0]


# ---------------------------------------------------------------------------
# Wire-alias and node-id fallbacks (the original purpose of the lookup chain)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label_alias", "node_id"),
    [
        ("SW", "7"),       # wire labelled SW, kernel says N7
        ("BUS_P", "13"),
        ("AC_NEG", "2"),
        ("DC+", "1"),       # punctuation in the alias
    ],
)
def test_voltage_probe_resolves_via_node_id_when_alias_is_unknown(
    label_alias: str, node_id: str,
) -> None:
    """Many ex 20-class schematics carry wire aliases the kernel never
    sees (the converter strips them when stamping the MNA). The
    lookup chain must fall through to ``V(N{node_id})``."""
    expected = [42.0, 43.0, 44.0]
    result = _result({
        # No V(<alias>) key — the kernel only knows the numeric N{}.
        f"V(N{node_id})": expected,
    })
    series = MainWindow._probe_backend_series(
        result, "Xsw", "probe-uuid",
        node_label=label_alias, node_id=node_id, kernel_prefix="V",
    )
    assert series == expected


@pytest.mark.parametrize(
    "alias_variant",
    ["SW", "sw", "Sw"],
)
def test_lookup_is_case_insensitive_on_the_node_label(
    alias_variant: str,
) -> None:
    """User typed ``"SW"`` on the wire but the kernel emitted
    ``"V(sw)"`` (or some other casing). The set-of-variants in the
    candidate builder must produce both case forms so the wrapped
    lookup hits regardless."""
    expected = [1.0, 2.0, 3.0]
    result = _result({
        "V(sw)": expected,  # lowercase wrapping
    })
    series = MainWindow._probe_backend_series(
        result, "Xsw", "probe-uuid",
        node_label=alias_variant, node_id="9", kernel_prefix="V",
    )
    assert series == expected


def test_lookup_picks_v_wrapped_over_bare_when_both_present() -> None:
    """Priority 1 is the type-prefix-wrapped form. When ``signals``
    contains BOTH the bare label and the V-wrapped label for the same
    node, the wrapped form wins."""
    result = _result({
        "AC_POS": [0.0, 0.0, 0.0],    # bare candidate match
        "V(AC_POS)": [311.0, 0.0, -311.0],  # canonical wrapped form
    })
    series = MainWindow._probe_backend_series(
        result, "Vin", "probe-uuid",
        node_label="AC_POS", node_id="27", kernel_prefix="V",
    )
    assert series == [311.0, 0.0, -311.0]


# ---------------------------------------------------------------------------
# Component-name and component-id fallbacks
# ---------------------------------------------------------------------------


def test_component_name_match_when_no_node_lookup_available() -> None:
    """Some kernel-emitted keys are NAMED after the probe component
    (e.g. PMSM motor state ``M1.i_a``). When no wrapped-form lookup
    succeeds, the helper falls through to ``component_name``."""
    result = _result({
        # No V(node_*) hits — just a non-wrapped key named like the probe.
        "M1.i_a": [-1.5, 0.0, 1.5],
    })
    series = MainWindow._probe_backend_series(
        result, "M1.i_a", "probe-uuid",
        node_label=None, node_id=None, kernel_prefix="V",
    )
    assert series == [-1.5, 0.0, 1.5]


def test_component_id_match_when_name_is_missing() -> None:
    """When the kernel registered the probe under its UUID (rare,
    typically a sweep / batch run artefact) the component_id fallback
    catches it."""
    result = _result({
        "abc-123-uuid": [7.0, 8.0, 9.0],
    })
    series = MainWindow._probe_backend_series(
        result, "", "abc-123-uuid",
        node_label=None, node_id=None, kernel_prefix="V",
    )
    assert series == [7.0, 8.0, 9.0]


# ---------------------------------------------------------------------------
# Fuzzy match (priority 3) — still must respect the type-guard
# ---------------------------------------------------------------------------


def test_fuzzy_match_returns_v_wrapped_when_body_matches_probe_name() -> None:
    """When all priority-1/2 candidates miss, the fuzzy match walks
    every key. A ``V(<probe_name>)`` body match is accepted."""
    result = _result({
        # The probe is named "I_load" — neither component_name nor any
        # node variant matches. Only the fuzzy body match should hit.
        "V(I_load)": [12.0, 12.0, 12.0],
    })
    series = MainWindow._probe_backend_series(
        result, "I_load", "probe-uuid",
        node_label="wrong_alias", node_id="999", kernel_prefix="V",
    )
    assert series == [12.0, 12.0, 12.0]


def test_fuzzy_match_rejects_i_wrapped_for_voltage_probe() -> None:
    """The type-guard in the fuzzy fallback: a V probe walking through
    fuzzy candidates must NOT accept ``I(<body>)`` or ``Is(<body>)``
    keys even when their body matches the probe's name. Returns None
    rather than silently picking up the wrong domain."""
    result = _result({
        # Only foreign-wrapper matches — no V() body match.
        "I(I_load)": [100.0, 100.0, 100.0],
        "Is(I_load)": [100.0, 100.0, 100.0],
    })
    series = MainWindow._probe_backend_series(
        result, "I_load", "probe-uuid",
        node_label="wrong_alias", node_id="999", kernel_prefix="V",
    )
    assert series is None


def test_fuzzy_match_accepts_i_wrapped_for_current_probe() -> None:
    """Mirror of the previous test: an I probe SHOULD accept ``I(...)``
    / ``Is(...)`` via fuzzy, and reject ``V(...)``."""
    result = _result({
        "I(I_load)": [100.0, 100.0, 100.0],
        # V(I_load) is foreign for an I probe.
        "V(I_load)": [-99.0, -99.0, -99.0],
    })
    series = MainWindow._probe_backend_series(
        result, "I_load", "probe-uuid",
        node_label="wrong_alias", node_id="999", kernel_prefix="I",
    )
    assert series == [100.0, 100.0, 100.0]


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_no_match_at_all_returns_none() -> None:
    """When nothing in the lookup chain hits, the helper returns None
    so the caller can decide whether to skip enrichment or emit a
    warning. Pin that it doesn't fall through to a wrong-but-similar
    signal."""
    result = _result({
        "completely_unrelated": [42.0, 42.0],
    })
    series = MainWindow._probe_backend_series(
        result, "Vin", "probe-uuid",
        node_label="AC_NEG", node_id="2", kernel_prefix="V",
    )
    assert series is None


def test_empty_signals_dict_returns_none() -> None:
    """No signals at all — typical of a sim that errored before any
    state was emitted. The helper must not crash."""
    result = _result({})
    series = MainWindow._probe_backend_series(
        result, "Vin", "probe-uuid",
        node_label="AC_NEG", node_id="2", kernel_prefix="V",
    )
    assert series is None
