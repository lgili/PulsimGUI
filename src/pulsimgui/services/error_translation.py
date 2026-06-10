"""Translate raw simulation-kernel errors into actionable user messages.

The pulsim kernel reports failures in solver vocabulary ("PwlStateSpaceCache:
numerically singular for mask 0b000000100 N=9") that tells a circuit designer
nothing about WHAT to fix. PSIM/PLECS owe much of their reputation to the user
never having to debug convergence — this layer is the GUI-side half of that
promise: every known failure signature gets a plain-language explanation plus
concrete next steps, with the raw kernel text kept underneath for
support/debugging.

Pure Python (no Qt) so it unit-tests in isolation.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorExplanation:
    """A user-facing explanation of a backend failure."""

    title: str            # short headline, e.g. "Circuit has no DC path to ground"
    what: str             # one-paragraph plain-language cause
    actions: list[str]    # concrete, ordered things the user can try


# Each rule: (compiled regex over the raw message, builder(match) -> ErrorExplanation).
# First match wins — order from most to least specific.
_RULES: list[tuple[re.Pattern, Callable[[re.Match], ErrorExplanation]]] = []


def _rule(pattern: str):
    def register(fn):
        _RULES.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn
    return register


@_rule(r"PwlStateSpaceCache:\s*numerically singular for mask\s*(?P<mask>0b[01]+)")
def _singular_mask(match: re.Match) -> ErrorExplanation:
    mask = match.group("mask")
    all_off = set(mask[2:]) <= {"0"}
    cause = (
        "While preparing the switching model, the solver found a switch "
        f"combination ({mask}{' — all switches OFF' if all_off else ''}) for "
        "which some part of the circuit has no defined voltage: a node or "
        "subcircuit is left floating (no DC path to ground) when those "
        "switches open. This combination is often one the modulation never "
        "actually uses — the solver still has to build it."
    )
    return ErrorExplanation(
        title="A switch combination leaves part of the circuit floating",
        what=cause,
        actions=[
            "Check that every part of the circuit has a path to a GROUND "
            "symbol that does not depend on a switch being closed (loads, "
            "filters and source neutrals are the usual suspects).",
            "Add a large resistor (e.g. 1 MΩ–1 GΩ) from the floating node to "
            "ground, or an RC snubber across the switches — it does not "
            "disturb the result.",
            "If this circuit is a matrix converter or an MMC, update to the "
            "latest version: the converter now regularises these masks "
            "automatically.",
        ],
    )


@_rule(r"numerically singular|singular matrix|matrix is singular")
def _singular_generic(_match: re.Match) -> ErrorExplanation:
    return ErrorExplanation(
        title="Circuit matrix is singular (floating node or source loop)",
        what=(
            "The circuit equations have no unique solution. The two classic "
            "causes are a node with no DC path to ground (e.g. two "
            "capacitors in series, transformer secondary left floating) or "
            "a loop of ideal voltage sources/switches with no resistance."
        ),
        actions=[
            "Make sure the circuit contains a GROUND symbol and every "
            "subnet can reach it through components (not only through "
            "switches).",
            "Add a large resistor (1 MΩ–1 GΩ) from isolated/floating nets "
            "to ground.",
            "Break ideal loops: add a small series resistance to voltage "
            "sources that are short-circuited by switches or inductors.",
        ],
    )


@_rule(r"newton.*(did not|failed to|couldn'?t)\s*converge|did not converge|"
       r"convergence (failure|failed)|max(imum)? iterations (reached|exceeded)")
def _convergence(_match: re.Match) -> ErrorExplanation:
    return ErrorExplanation(
        title="Solver could not converge",
        what=(
            "The nonlinear solver (Newton iteration) failed to settle on a "
            "solution. This usually means very stiff switching transitions, "
            "an unrealistic operating point, or a time step too large for "
            "the fastest dynamics in the circuit."
        ),
        actions=[
            "Reduce the simulation time step (Simulation → Settings → dt) — "
            "a good starting point is 1/100 of the fastest switching period.",
            "Add RC snubbers across fast switches and diodes to soften the "
            "transitions.",
            "Check device parameters for extreme values (zero resistances, "
            "huge gains); give sources a small series resistance.",
            "Enable the robust transient mode in Simulation Settings (it "
            "retries with progressive regularisation).",
        ],
    )


@_rule(r"C-Block control requires backend|compile.*c.block|c.block.*compil")
def _cblock(_match: re.Match) -> ErrorExplanation:
    return ErrorExplanation(
        title="C-Block could not be used",
        what=(
            "The C-Block (custom C control code) could not be compiled or "
            "the installed pulsim backend is too old to run it."
        ),
        actions=[
            "Check the C code for syntax errors (the compiler output is in "
            "the technical detail below).",
            "Update the pulsim backend to the latest version (pip install "
            "-U pulsim).",
        ],
    )


@_rule(r"timestep|time step.*(too large|unstable)|dt.*(too large|exceeds)")
def _timestep(_match: re.Match) -> ErrorExplanation:
    return ErrorExplanation(
        title="Time step too large for this circuit",
        what=(
            "The fixed time step cannot resolve the fastest dynamics in the "
            "circuit (switching edges, small L/C time constants), making "
            "the integration unstable."
        ),
        actions=[
            "Reduce dt in Simulation → Settings (rule of thumb: at least "
            "20 points per switching period; 100 for multilevel "
            "converters).",
            "If runtime becomes too long, consider an averaged (L0) model "
            "for the converter while designing the control loop.",
        ],
    )


@_rule(r"cancell?ed")
def _cancelled(_match: re.Match) -> ErrorExplanation:
    return ErrorExplanation(
        title="Simulation cancelled",
        what="The run was stopped before completion.",
        actions=[],
    )


def explain_backend_error(raw_message: str) -> ErrorExplanation | None:
    """Return the explanation for the first matching failure signature, or
    ``None`` when the message is unknown (caller shows it as-is)."""
    if not raw_message:
        return None
    for pattern, builder in _RULES:
        match = pattern.search(raw_message)
        if match:
            return builder(match)
    return None


def format_user_error(raw_message: str, *, context: str = "Simulation") -> str:
    """Build the full dialog text: friendly explanation first (when the
    signature is known), raw kernel text underneath for support."""
    explanation = explain_backend_error(raw_message)
    if explanation is None:
        return f"{context} failed:\n{raw_message}"
    lines = [explanation.title, "", explanation.what]
    if explanation.actions:
        lines += ["", "How to fix:"]
        lines += [f"  •  {action}" for action in explanation.actions]
    lines += ["", f"Technical detail: {raw_message}"]
    return "\n".join(lines)
