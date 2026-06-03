"""``PostSimCapability`` — replaces live data with the full-resolution result.

When the kernel finishes a run, ``SimulationService.simulation_finished``
fires with a ``SimulationResult``. This capability listens for that and
swaps the streaming ring data on each curve for the complete time +
state arrays from the result, so the user sees the entire run in the
same window they were already looking at.

It pairs with :class:`LiveStreamCapability`; if only this capability is
attached, the canvas stays empty until the first run finishes. If both
are attached, the live stream populates the curves first and this
capability finalises them at the end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from pulsimgui.views.scope_v2._auto_palette import next_palette_color

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


# ── Fuzzy-match helpers (used by PostSimCapability._on_finished) ──────


def _extract_body(key: str) -> str:
    """Return the body inside ``V(…)`` / ``I(…)`` / ``T(…)``, else ``""``.

    Examples
    --------
    >>> _extract_body("V(SW)")
    'SW'
    >>> _extract_body("Vsw")
    ''
    """
    if "(" not in key or not key.endswith(")"):
        return ""
    start = key.index("(") + 1
    return key[start:-1]


def _fuzzy_candidates(name: str) -> tuple[str, ...]:
    """Build the fuzzy-lookup keys to try for a spec ``name``.

    Returns the spec name plus the spec name with a leading ``V``,
    ``I`` or ``T`` stripped — covers the case where the kernel emits
    ``V(SW)`` while the GUI's probe is labelled ``Vsw`` (strip V → ``sw``
    → matches ``V(SW)``'s body) AND the case where it emits ``V(VOUT)``
    while the GUI labels ``Vout`` (as-is, case-insensitive → ``vout``
    matches body ``VOUT``).
    """
    if not name:
        return ()
    out: list[str] = [name]
    if name[:1].upper() in {"V", "I", "T"} and len(name) > 1:
        out.append(name[1:])
    return tuple(out)


@dataclass(frozen=True)
class PostSimSignalSpec:
    """Mapping used to look a signal up in the finished ``SimulationResult``.

    Attributes
    ----------
    name
        Display name on the plot canvas (matches the live-stream spec
        so the curve transitions seamlessly).
    signal_key
        Primary key into ``SimulationResult.signals`` — the canonical
        string the scope's channel binding resolved from wires on the
        schematic.
    fallback_keys
        Additional candidate keys tried in order if ``signal_key`` is
        not present in the result. Use this when the same signal might
        be exposed under several names depending on backend version
        or whether it came from probe enrichment (``VP(name)``), the
        raw kernel virtual-channel (``name``), or node-level wiring
        (``V(node)``).
    """

    name: str
    signal_key: str
    fallback_keys: tuple[str, ...] = ()


class PostSimCapability:
    """Finalise the plot canvas with the full simulation result.

    Two channels into the capability:

    * ``result_signal`` — a Qt signal emitting a ``SimulationResult``
      whenever a fresh, *probe-enriched* result is available. When the
      host wires this to a signal the host owns (e.g.
      ``MainWindow.electrical_result_ready``) the capability receives
      the result with synthetic ``VP(name)`` / ``IP(name)`` channels
      already merged. Defaults to ``simulation_service.simulation_finished``
      for hosts that don't enrich.
    * ``result_getter`` — a callable returning the most-recent enriched
      result (or ``None``). Used on ``attach()`` so scopes opened *after*
      a run already shows data instead of an empty canvas. Defaults to
      reading ``simulation_service.last_result``.
    """

    def __init__(
        self,
        simulation_service: Any,
        signal_specs: list[PostSimSignalSpec],
        *,
        result_signal: Any = None,
        result_getter: Callable[[], Any] | None = None,
    ) -> None:
        self._simulation_service = simulation_service
        self._signal_specs = list(signal_specs)
        self._result_signal = result_signal
        self._result_getter = result_getter
        self._shell: BaseScopeWindow | None = None

    def attach(self, shell: BaseScopeWindow) -> None:
        """Subscribe to the result signal + perform the catch-up step.

        If a run has already completed before the scope window opened,
        the result signal will not fire again — we'd sit on an empty
        canvas until the user manually re-runs. The catch-up call pulls
        the most-recent enriched result once on attach so the scope
        opens already populated.
        """
        self._shell = shell

        sig = self._result_signal
        if sig is None:
            sig = getattr(self._simulation_service, "simulation_finished", None)
        if sig is None:
            _LOG.warning(
                "PostSimCapability: %s has no result signal to subscribe to",
                type(self._simulation_service).__name__,
            )
        else:
            sig.connect(self._on_finished)

        # Catch-up path: scope opened after the last run completed.
        if self._result_getter is not None:
            last = self._result_getter()
        else:
            last = getattr(self._simulation_service, "last_result", None)
        if last is not None and getattr(last, "is_valid", True):
            # Defer one event-loop tick so the rest of the capabilities
            # finish attaching (the empty-state overlay, sidebar rows,
            # etc.) before we replace curves.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda r=last: self._on_finished(r))

    def _on_finished(self, result: Any) -> None:
        """Replace each curve with the full-resolution arrays from ``result``."""
        if self._shell is None or result is None:
            return
        t = np.asarray(getattr(result, "time", []), dtype=np.float64)
        signals = getattr(result, "signals", None) or {}
        if t.size == 0 or not signals:
            return

        # Build the fuzzy-lookup index ONCE per finished signal — maps
        # the case-insensitive "body" inside ``V(…)`` / ``I(…)`` /
        # ``T(…)`` to the original key, plus the bare lowercase form.
        # ``V(SW)`` → ``{"sw": "V(SW)", "v(sw)": "V(SW)"}``.
        fuzzy_index: dict[str, str] = {}
        for key in signals.keys():
            fuzzy_index[str(key).lower()] = str(key)
            inner = _extract_body(str(key))
            if inner:
                fuzzy_index.setdefault(inner.lower(), str(key))

        # Each scope channel binding gives us a primary ``signal_key``
        # plus optional fallbacks. We walk the primary then the fallbacks
        # so that whichever name the backend actually emitted under
        # (``VP(name)`` from probe enrichment, ``name`` from raw virtual
        # channels, ``V(node)`` from node-level wiring) matches. As a
        # last resort, fuzzy_index resolves divergences like the kernel
        # emitting ``V(SW)`` for a probe the GUI labelled ``Vsw``.
        matched = 0
        unmatched_specs: list[PostSimSignalSpec] = []
        for spec in self._signal_specs:
            data = None
            hit_key: str | None = None
            for candidate in (spec.signal_key, *spec.fallback_keys):
                if not candidate:
                    continue
                data = signals.get(candidate)
                if data is not None:
                    hit_key = candidate
                    break
            # Fuzzy fallback: walk the spec.name AND every
            # fallback_key, trying each one as-is and with a leading
            # V/I/T stripped, case-insensitive. ``spec.name`` is often
            # noisy (e.g. ``"Vsw (N7)"``) so the resolver's clean
            # ``fallback_keys`` (``"Vsw"``, ``"V(Vsw)"``, ``"N7"``, …)
            # are what actually carries the match here. Strip-V on
            # ``"Vsw"`` → ``"sw"`` → matches the body of ``V(SW)``.
            if data is None:
                all_names: tuple[str, ...] = (spec.name, *spec.fallback_keys)
                for raw_name in all_names:
                    if not raw_name:
                        continue
                    for variant in _fuzzy_candidates(raw_name):
                        backend_key = fuzzy_index.get(variant.lower())
                        if backend_key is None:
                            continue
                        data = signals.get(backend_key)
                        if data is not None:
                            hit_key = backend_key
                            break
                    if data is not None:
                        break
            if data is None:
                unmatched_specs.append(spec)
                continue
            y = np.asarray(data, dtype=np.float64)
            # Some backends return per-step values; trim to ``t`` length
            # to be safe if a stray sample slipped in.
            n = min(t.size, y.size)
            canvas = self._shell.plot_canvas
            # Post-sim-only channels (e.g. a direct-signal motor scope:
            # ``M1.speed_rpm`` / ``M1.i_a``) have no live spec, so no curve or
            # sidebar row was created up front. Make them now so the trace
            # both renders and shows in the legend.
            if not canvas.has_signal(spec.name):
                color = next_palette_color(matched)
                canvas.add_signal(spec.name, color=color, panel="Main")
                sidebar = getattr(self._shell, "sidebar", None)
                if sidebar is not None:
                    try:
                        sidebar.add_signal_row(spec.name, color)
                    except Exception:  # noqa: BLE001 — legend row is best-effort
                        pass
            canvas.replace_signal(spec.name, t[:n], y[:n])
            matched += 1
            if hit_key is not None and hit_key != spec.signal_key:
                _LOG.debug(
                    "PostSimCapability: %r resolved via fallback %r",
                    spec.name, hit_key,
                )

        # When nothing matches, dump everything we have at WARNING level
        # so the user can immediately see what keys ARE in the result —
        # otherwise the "0 of N matched" message gives no clue what
        # name the backend used. Costs nothing in the happy path.
        if matched == 0 and unmatched_specs:
            tried: list[str] = []
            for spec in unmatched_specs:
                tried.append(spec.signal_key)
                tried.extend(spec.fallback_keys)
            _LOG.warning(
                "PostSimCapability: 0 of %d signals matched. "
                "Tried keys: %r. Available keys in result.signals: %r",
                len(self._signal_specs), sorted(set(tried)), sorted(signals.keys()),
            )

        # Reset the empty-state hint now that the canvas has real data.
        self._shell.plot_canvas.set_empty_message(
            "Run completed",
            "Drop more signals from the sidebar to overlay them.",
        )

        # Surface a one-line summary in the drawer. When nothing
        # matched, expand the summary with the available keys so the
        # user can see directly which name the backend used — saves a
        # roundtrip through the log file. Status dot colour reflects
        # the outcome: success (all matched), warning (partial), error
        # (zero) so the user gets a glanceable signal too.
        set_status = getattr(self._shell, "set_drawer_status", None)
        if set_status is not None:
            total = len(self._signal_specs)
            if matched == total and total > 0:
                state = "success"
            elif matched > 0:
                state = "warning"
            else:
                state = "error"
            if matched == 0 and unmatched_specs and signals:
                preview = ", ".join(sorted(signals.keys())[:6])
                more = (
                    f" (+{len(signals) - 6} more)"
                    if len(signals) > 6 else ""
                )
                summary = (
                    f"Run completed — {t.size} points • 0 of "
                    f"{total} matched. Backend keys: {preview}{more}"
                )
            else:
                summary = (
                    f"Run completed — {t.size} points • "
                    f"{matched} of {total} signals matched."
                )
            set_status(state, summary)


__all__ = ["PostSimCapability", "PostSimSignalSpec"]
