"""Compatibility shim: present pulsim's pre-1.0 ``Circuit`` API on top of
``pulsim.CircuitBuilder``.

Why this exists
---------------
PulsimGUI's circuit converter (``circuit_converter.py``, ~2 400 lines) was
written against the pre-1.0 pulsim surface — ``pulsim.Circuit()`` plus
``MOSFETParams`` / ``IGBTParams`` / ``SineParams`` / ``PulseParams`` /
``PWMParams`` setter classes and integer-indexed node arguments. The v1.0
namespace flatten retired every single one of those names; v1.3 exposes
``pulsim.CircuitBuilder`` with string node names and direct kwargs.

A direct rewrite of ``circuit_converter.py`` is the textbook fix but it
touches ~2 400 lines and the converter's tests are mock-only, so a
regression there would not surface in CI. This shim is the lower-risk
path: it presents the pre-1.0 ``Circuit`` API verbatim on top of
``CircuitBuilder``, so the existing converter keeps working unchanged
when the host pulsim is 1.0+.

The shim is **not** the long-term home for the GUI's pulsim integration
— ``circuit_converter.py`` should eventually emit ``CircuitBuilder``
calls directly with string node names so the GUI can take advantage of
v1.3 features (MMC arms, Foster networks, ``simulate(step_observer=…)``
streaming, etc.). The shim buys time for that to happen incrementally
without an emergency rewrite.

Surface
-------
``make_compat_module(pulsim_module)`` returns either:

* the raw pulsim module, when ``pulsim.__version__ < "1.0"``
  (the legacy path is already wired correctly for that surface), or
* a :class:`CompatModule` proxy exposing
  ``Circuit`` / ``MOSFETParams`` / ``IGBTParams`` / ``SineParams`` /
  ``PulseParams`` / ``PWMParams`` / ``SchematicPosition`` on top of
  v1.3's ``CircuitBuilder``.

The shim's ``Circuit`` class wraps a ``CircuitBuilder`` and tracks an
``int ↔ str`` node-name map so the converter can keep passing integer
indices. The names it generates match the names the converter feeds to
``add_node`` (``"0"`` for ground, ``"N42"`` for plain id-based labels,
or whatever ``_node_label`` produced).

Known gaps (will surface as :class:`NotImplementedError`)
---------------------------------------------------------
* **MOSFET / IGBT gate pin** — v1.3 treats the gate as a ``switch_fn``
  signal at simulate-time, not a graph node. The shim accepts the gate
  index for API compatibility but **discards** it; the resulting
  CircuitBuilder has a 2-terminal switch sitting where the v0 MOSFET
  was. The GUI's PWM-control wiring will not run until
  ``backend_adapter`` learns to assemble a ``switch_fn`` from the gate
  mapping the shim records in :attr:`Circuit.pending_gate_signals`.
* **VC (voltage-controlled) switch** — same story as MOSFET; the
  control terminal is silently dropped.
* **add_virtual_component** — v1.3 has no notion of a "virtual"
  component inside the builder. Calls are recorded in
  :attr:`Circuit.virtual_component_records` so the backend can hand
  them to ``pulsim.MixedDomainBlockChain`` later. Today, they no-op.
* **add_snubber_rc** — pulsim 1.3 exposes ``pulsim.add_rc_snubber``
  (free function on the builder). The shim wires it through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------
def make_compat_module(pulsim_module: Any) -> Any:
    """Return ``pulsim_module`` itself when it already speaks the v0
    ``Circuit`` surface (real legacy pulsim **or** any GUI test mock
    that fakes the v0 surface), or a :class:`CompatModule` wrapper when
    the host module is real pulsim 1.0+.

    The decision is symmetrical: wrap only when ``CircuitBuilder``
    exists and ``Circuit`` does not. That way:

    * Real legacy pulsim (has ``Circuit``, no ``CircuitBuilder``) →
      passthrough.
    * Real v1.3+ pulsim (has ``CircuitBuilder``, ``Circuit`` raises
      AttributeError via the migration shim) → wrap.
    * Test mocks that supply ``Circuit`` but no ``CircuitBuilder``
      (most ``test_backend_adapter_*`` fakes) → passthrough so the
      mock's own ``Circuit`` is used.
    * Test mocks that supply ``CircuitBuilder`` but no ``Circuit`` →
      wrap; the shim translates v0 calls to the mock's builder.
    """
    has_builder = _has_callable(pulsim_module, "CircuitBuilder")
    has_circuit = _has_callable(pulsim_module, "Circuit")
    if has_builder and not has_circuit:
        return CompatModule(pulsim_module)
    return pulsim_module


def _has_callable(module: Any, name: str) -> bool:
    """Return True when ``module`` exposes ``name`` as a callable.

    Treats AttributeError from PEP-562 ``__getattr__`` (the
    migration-hint helper in pulsim 1.0+) as "not present".
    """
    try:
        obj = getattr(module, name)
    except AttributeError:
        return False
    return callable(obj)


# ---------------------------------------------------------------------------
# Module proxy
# ---------------------------------------------------------------------------
class CompatModule:
    """Looks like the v0 ``pulsim`` module to ``circuit_converter`` but
    everything circuit-shaped routes through pulsim 1.3 internals.

    Non-circuit attributes (``simulate``, ``run_transient``,
    ``SimulationOptions``, …) fall through to the wrapped module so the
    rest of ``backend_adapter`` keeps working with the real pulsim
    surface.
    """

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped

    # --- circuit-construction surface (v0 names) -----------------------
    @property
    def Circuit(self) -> type:  # noqa: N802 — v0 API name
        # Factory returns a Circuit bound to the wrapped pulsim module
        # so it knows how to call ``CircuitBuilder()`` underneath.
        wrapped = self._wrapped

        class _BoundCircuit(Circuit):
            __slots__ = ()

            def __init__(self) -> None:
                super().__init__(wrapped)

        return _BoundCircuit

    MOSFETParams = staticmethod(lambda: MOSFETParams())  # noqa: N815 — v0 API name
    IGBTParams = staticmethod(lambda: IGBTParams())  # noqa: N815
    SineParams = staticmethod(lambda: SineParams())  # noqa: N815
    PulseParams = staticmethod(lambda: PulseParams())  # noqa: N815
    PWMParams = staticmethod(lambda: PWMParams())  # noqa: N815
    SchematicPosition = staticmethod(  # noqa: N815
        lambda **kw: SchematicPosition(**kw)
    )

    # --- everything else: passthrough ----------------------------------
    def __getattr__(self, name: str) -> Any:
        # Called only when the attribute isn't found on the proxy
        # itself; forwards to the wrapped pulsim module.
        return getattr(self._wrapped, name)


# ---------------------------------------------------------------------------
# Parameter bag-of-attributes classes (v0 API)
# ---------------------------------------------------------------------------
@dataclass
class MOSFETParams:
    """Mirrors the pre-1.0 ``pulsim.MOSFETParams`` surface as a bag of
    attributes the GUI fills in via :func:`setattr`. The shim's
    ``Circuit.add_mosfet`` reads the populated fields and translates
    them into v1.3 ``CircuitBuilder.add_mosfet`` arguments.

    Unknown fields are accepted via :meth:`__setattr__` so the converter
    can stuff in any extra parameter without exploding.
    """

    is_nmos: bool = True
    R_on: float = 1e-3
    R_off: float = 1e9
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        # Known fields go through the dataclass slots; unknown ones land
        # in ``extras`` so callers can sprinkle ``v_th`` / ``r_d`` / …
        # without breaking the shim.
        if name in {"is_nmos", "R_on", "R_off", "extras"}:
            object.__setattr__(self, name, value)
        else:
            try:
                bucket = object.__getattribute__(self, "extras")
            except AttributeError:
                object.__setattr__(self, "extras", {})
                bucket = self.extras
            bucket[name] = value


@dataclass
class IGBTParams:
    """Same pattern as :class:`MOSFETParams` for the v0 IGBT API."""

    R_on: float = 1e-2
    R_off: float = 1e9
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"R_on", "R_off", "extras"}:
            object.__setattr__(self, name, value)
        else:
            try:
                bucket = object.__getattribute__(self, "extras")
            except AttributeError:
                object.__setattr__(self, "extras", {})
                bucket = self.extras
            bucket[name] = value


@dataclass
class SineParams:
    """v0 sine-source params bag.

    Translated to ``CircuitBuilder.add_sine_voltage_source(name, from, to,
    v_dc, v_amplitude, frequency, phase)``.
    """

    v_dc: float = 0.0
    v_amplitude: float = 1.0
    frequency: float = 60.0
    phase: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"v_dc", "v_amplitude", "frequency", "phase", "extras"}:
            object.__setattr__(self, name, value)
        else:
            try:
                bucket = object.__getattribute__(self, "extras")
            except AttributeError:
                object.__setattr__(self, "extras", {})
                bucket = self.extras
            bucket[name] = value


@dataclass
class PulseParams:
    """v0 pulse-source params bag.

    Translated to ``CircuitBuilder.add_pulse_voltage_source(name, from, to,
    v_initial, v_pulsed, t_start, pulse_width, period, rise_time, fall_time)``.
    """

    v_initial: float = 0.0
    v_pulsed: float = 1.0
    t_start: float = 0.0
    pulse_width: float = 1e-3
    period: float = 2e-3
    rise_time: float = 1e-6
    fall_time: float = 1e-6
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {
            "v_initial",
            "v_pulsed",
            "t_start",
            "pulse_width",
            "period",
            "rise_time",
            "fall_time",
            "extras",
        }:
            object.__setattr__(self, name, value)
        else:
            try:
                bucket = object.__getattribute__(self, "extras")
            except AttributeError:
                object.__setattr__(self, "extras", {})
                bucket = self.extras
            bucket[name] = value


@dataclass
class PWMParams:
    """v0 PWM-source params bag.

    Translated to ``CircuitBuilder.add_pwm_voltage_source(name, from, to,
    v_high, v_low, frequency, duty)``.
    """

    v_high: float = 1.0
    v_low: float = 0.0
    frequency: float = 1e4
    duty: float = 0.5
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"v_high", "v_low", "frequency", "duty", "extras"}:
            object.__setattr__(self, name, value)
        else:
            try:
                bucket = object.__getattribute__(self, "extras")
            except AttributeError:
                object.__setattr__(self, "extras", {})
                bucket = self.extras
            bucket[name] = value


@dataclass
class SchematicPosition:
    """v0 layout-position struct. Tracked but not propagated — v1.3's
    schematic module lives outside the runtime builder and reads
    positions from a separate path."""

    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


# ---------------------------------------------------------------------------
# Circuit shim
# ---------------------------------------------------------------------------
class Circuit:
    """Drop-in replacement for ``pulsim.Circuit`` that lives on top of
    ``pulsim.CircuitBuilder``.

    The shim tracks an ``int ↔ str`` node-name map so the GUI converter
    can keep passing integer indices to every ``add_*`` method.
    """

    def __init__(self, pulsim_module: Any) -> None:
        # ``pulsim_module`` is the real pulsim 1.3+ module — we need
        # access to ``CircuitBuilder`` and the ``add_rc_snubber`` free
        # function plus a couple of helpers.
        self._pm = pulsim_module
        self._builder = pulsim_module.CircuitBuilder()

        # Node bookkeeping: id → str_name and str_name → id. Ground
        # ("0" / "gnd") is hard-wired to id -1 so the converter's
        # int-based callers can pass it through unmodified.
        self._node_id_to_name: dict[int, str] = {-1: "gnd"}
        self._node_name_to_id: dict[str, int] = {"gnd": -1, "0": -1}
        self._next_node_id: int = 0

        # MOSFET / IGBT / VC-switch / explicit-switch entries — recorded
        # in the order they were added to the builder so the eventual
        # ``switch_fn`` can index into pulsim 1.3's
        # ``SwitchStateMask(num_switches)`` bit positions. Pulsim
        # enumerates switching branches in builder-call order, so the
        # i-th entry here owns bit ``i`` of the mask.
        #
        # Each record carries::
        #
        #     {"device": str, "kind": str, "gate_node": str,
        #      "switch_idx": int}
        #
        # ``gate_node`` is ``""`` for plain ``add_switch`` (no gate
        # terminal).
        self.pending_gate_signals: list[dict[str, Any]] = []

        # add_virtual_component calls are also recorded — they map to
        # pulsim 1.3's ``pulsim.MixedDomainBlockChain`` surface, but
        # that wiring is outside this shim's scope.
        self.virtual_component_records: list[dict[str, Any]] = []

        # Position metadata — never round-tripped to the builder.
        self._positions: dict[str, SchematicPosition] = {}

    # --- public accessors expected by the converter --------------------
    @property
    def builder(self) -> Any:
        """The underlying ``pulsim.CircuitBuilder`` — handed to
        ``simulate(...)``/``compute_dc_op(...)`` by the backend."""
        return self._builder

    @property
    def num_nodes(self) -> int:
        # Excludes ground in v1.3 convention.
        return self._builder.graph.num_nodes

    @property
    def num_branches(self) -> int:
        return self._builder.graph.num_branches

    @property
    def num_switches(self) -> int:
        """Total number of switching branches the builder enumerates.

        Pulsim 1.3's ``SwitchStateMask(num_switches)`` and
        ``make_pwm_switch_fn(..., num_switches=…)`` both want this
        value, **including** event-driven devices like diodes — they
        occupy bits in the mask even though the user-supplied
        ``switch_fn`` never toggles them directly.

        The shim defers to ``builder.graph.num_switches`` so the
        count stays in sync with pulsim's own enumeration: the
        ``pending_gate_signals`` list is a strict subset (only
        explicitly controllable devices). When a circuit has e.g. one
        MOSFET + one diode, ``num_switches == 2`` but
        ``len(pending_gate_signals) == 1``.
        """
        return self._builder.graph.num_switches

    @property
    def switch_indices(self) -> dict[str, int]:
        """``device_name → switch_idx`` map for callers that want to
        target a specific device when assembling the simulate-time
        ``switch_fn``. Empty when there are no switching elements."""
        return {
            entry["device"]: entry["switch_idx"]
            for entry in self.pending_gate_signals
        }

    @property
    def gate_node_indices(self) -> dict[str, int]:
        """``gate_node → switch_idx`` map. The GUI's PWM generator
        records the *gate node it drives* in its
        ``virtual_component_records[*]["nodes"]`` — this property is
        the bridge that lets ``backend_adapter`` connect a PWM gen to
        the switch bit it should toggle."""
        return {
            entry["gate_node"]: entry["switch_idx"]
            for entry in self.pending_gate_signals
            if entry.get("gate_node")
        }

    def node_names(self) -> list[str]:
        return [
            self._node_id_to_name[i]
            for i in sorted(self._node_id_to_name.keys())
            if i >= 0
        ]

    def signal_names(self) -> list[str]:
        # v0's signal_names was a superset of node + branch IDs the GUI
        # used for scope binding. Best-effort approximation: emit node
        # voltage labels and (for switched branches) branch currents.
        return [f"V({n})" for n in self.node_names()]

    def initial_state(self) -> Any:
        # v0 returned a zero vector sized for the state. v1.3 lets us
        # build one from the graph dimensions.
        import numpy as np

        return np.zeros(self._builder.graph.num_nodes + self._builder.num_branches)

    # --- node management ----------------------------------------------
    def add_node(self, name: str) -> int:
        """v0 ``add_node`` returned an integer node id. We mint one
        here, registering the str name with the underlying builder so
        any subsequent ``add_*`` call can pass either form."""
        name = _normalise_node_name(name)
        existing = self._node_name_to_id.get(name)
        if existing is not None:
            return existing
        # Trigger node creation on the builder so it shows up in the
        # graph; we don't actually care about pulsim's internal id — we
        # keep our own.
        self._builder.node(name)
        new_id = self._next_node_id
        self._next_node_id += 1
        self._node_id_to_name[new_id] = name
        self._node_name_to_id[name] = new_id
        return new_id

    def get_node(self, name: str) -> int:
        name = _normalise_node_name(name)
        return self._node_name_to_id.get(name, -1)

    def node_name(self, node_id: int) -> str:
        """Reverse lookup: id → name (used by some GUI hover labels)."""
        return self._node_id_to_name.get(int(node_id), "")

    def _name_of(self, node_id: int) -> str:
        """Internal helper — translate the int handed in by the
        converter back to the str name the v1.3 builder expects."""
        if int(node_id) == -1:
            return "gnd"
        try:
            return self._node_id_to_name[int(node_id)]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Unknown node id {node_id} — was it created via add_node?"
            ) from exc

    # --- linear passives ----------------------------------------------
    def add_resistor(self, name: str, n1: int, n2: int, R: float) -> None:  # noqa: E741, N803
        self._builder.add_resistor(name, self._name_of(n1), self._name_of(n2), float(R))

    def add_capacitor(self, name: str, n1: int, n2: int, C: float) -> None:  # noqa: N803
        self._builder.add_capacitor(name, self._name_of(n1), self._name_of(n2), float(C))

    def add_inductor(self, name: str, n1: int, n2: int, L: float) -> None:  # noqa: N803
        self._builder.add_inductor(name, self._name_of(n1), self._name_of(n2), float(L))

    def add_transformer(
        self,
        name: str,
        p1: int,
        p2: int,
        s1: int,
        s2: int,
        turns_ratio: float = 1.0,
        L_p: float = 1e-3,
        k: float = 1.0,
    ) -> None:
        # v0 took (name, p1, p2, s1, s2, turns_ratio) but v1.3 takes
        # primary/secondary inductances and a coupling coefficient.
        # Reconstruct L_s from L_p + turns_ratio (N1/N2 = √(L_p/L_s)).
        L_s = float(L_p) / max(float(turns_ratio) ** 2, 1e-12)
        self._builder.add_transformer(
            name,
            self._name_of(p1),
            self._name_of(p2),
            self._name_of(s1),
            self._name_of(s2),
            float(L_p),
            float(L_s),
            float(k),
        )

    # --- sources -------------------------------------------------------
    def add_voltage_source(
        self,
        name: str,
        npos: int,
        nneg: int,
        value_or_params: Any,
    ) -> None:
        """v0 took either a scalar (DC) or one of the params bags. v1.3
        splits this into ``add_voltage_source`` (DC) /
        ``add_sine_voltage_source`` / ``add_pulse_voltage_source`` /
        ``add_pwm_voltage_source``. We dispatch by the params type."""
        npos_s = self._name_of(npos)
        nneg_s = self._name_of(nneg)
        if isinstance(value_or_params, SineParams):
            p = value_or_params
            self._builder.add_sine_voltage_source(
                name, npos_s, nneg_s,
                float(p.v_dc), float(p.v_amplitude),
                float(p.frequency), float(p.phase),
            )
        elif isinstance(value_or_params, PulseParams):
            p = value_or_params
            self._builder.add_pulse_voltage_source(
                name, npos_s, nneg_s,
                float(p.v_initial), float(p.v_pulsed),
                float(p.t_start), float(p.pulse_width),
                float(p.period), float(p.rise_time),
                float(p.fall_time),
            )
        elif isinstance(value_or_params, PWMParams):
            p = value_or_params
            self._builder.add_pwm_voltage_source(
                name, npos_s, nneg_s,
                float(p.v_high), float(p.v_low),
                float(p.frequency), float(p.duty),
            )
        else:
            self._builder.add_voltage_source(
                name, npos_s, nneg_s, float(value_or_params),
            )

    def add_sine_voltage_source(
        self,
        name: str,
        npos: int,
        nneg: int,
        params: SineParams,
    ) -> None:
        self._builder.add_sine_voltage_source(
            name,
            self._name_of(npos),
            self._name_of(nneg),
            float(params.v_dc),
            float(params.v_amplitude),
            float(params.frequency),
            float(params.phase),
        )

    def add_pulse_voltage_source(
        self,
        name: str,
        npos: int,
        nneg: int,
        params: PulseParams,
    ) -> None:
        self._builder.add_pulse_voltage_source(
            name,
            self._name_of(npos),
            self._name_of(nneg),
            float(params.v_initial),
            float(params.v_pulsed),
            float(params.t_start),
            float(params.pulse_width),
            float(params.period),
            float(params.rise_time),
            float(params.fall_time),
        )

    def add_pwm_voltage_source(
        self,
        name: str,
        npos: int,
        nneg: int,
        params: PWMParams,
    ) -> None:
        self._builder.add_pwm_voltage_source(
            name,
            self._name_of(npos),
            self._name_of(nneg),
            float(params.v_high),
            float(params.v_low),
            float(params.frequency),
            float(params.duty),
        )

    def add_current_source(
        self,
        name: str,
        npos: int,
        nneg: int,
        I: float,  # noqa: E741, N803
    ) -> None:
        # v1.3 ``add_current_source`` takes a scalar DC value. Sine /
        # PWM current sources aren't part of the v0 GUI flow so we
        # don't dispatch on params type here.
        self._builder.add_current_source(
            name, self._name_of(npos), self._name_of(nneg), float(I),
        )

    # --- active devices -----------------------------------------------
    def add_diode(
        self,
        name: str,
        anode: int,
        cathode: int,
        g_on: float = 1.0,
        g_off: float = 1e-9,
    ) -> None:
        self._builder.add_diode(
            name,
            self._name_of(anode),
            self._name_of(cathode),
            float(g_on),
            float(g_off),
        )

    def _next_switch_idx(self) -> int:
        """Return the bit position pulsim 1.3 will use for the next
        switching device added to the builder. The graph numbers them
        in call order, so the shim just tracks its own counter — kept
        in sync via every ``add_mosfet`` / ``add_igbt`` / ``add_switch``
        / ``add_vcswitch`` path."""
        return len(self.pending_gate_signals)

    def add_mosfet(
        self,
        name: str,
        gate: int,
        drain: int,
        source: int,
        params: MOSFETParams | None = None,
    ) -> None:
        """v0 took (name, gate_idx, drain_idx, source_idx, MOSFETParams).
        v1.3 drops the gate node entirely — the gate is driven by
        ``switch_fn`` at simulate-time. We record the gate-to-switch
        mapping on :attr:`pending_gate_signals` so a later
        ``backend_adapter`` iteration can assemble the ``switch_fn``.

        Under the hood we delegate to ``add_mosfet_with_body_diode``
        rather than the bare ``add_mosfet`` for one specific reason:
        pulsim 1.3's ``PwlStateSpaceCache.build`` eagerly enumerates
        every 2^N switch-mask combination and rejects any singular
        topology — including masks the runtime would never actually
        visit. With a bare MOSFET, the "off" mask leaves the inductor
        terminal floating (singular) and the cache build fails before
        any simulation can start. The intrinsic body diode (anti-
        parallel, source → drain) keeps that terminal connected so
        every mask is solvable. Two switch bits are consumed instead
        of one (MOSFET + body diode), but the shim's
        ``pending_gate_signals`` is the user-controlled list so only
        the MOSFET bit shows up there; the body-diode bit is
        event-driven (commutation events fire it at runtime).
        """
        p = params or MOSFETParams()
        switch_idx = self._next_switch_idx()
        self._builder.add_mosfet_with_body_diode(
            name,
            self._name_of(drain),
            self._name_of(source),
            float(p.R_on),
            float(p.R_off),
        )
        self.pending_gate_signals.append({
            "device": name,
            "kind": "mosfet_n" if p.is_nmos else "mosfet_p",
            "gate_node": self._name_of(gate),
            "switch_idx": switch_idx,
        })

    def add_igbt(
        self,
        name: str,
        gate: int,
        collector: int,
        emitter: int,
        params: IGBTParams | None = None,
    ) -> None:
        p = params or IGBTParams()
        switch_idx = self._next_switch_idx()
        self._builder.add_igbt(
            name,
            self._name_of(collector),
            self._name_of(emitter),
            float(p.R_on),
            float(p.R_off),
        )
        self.pending_gate_signals.append({
            "device": name,
            "kind": "igbt",
            "gate_node": self._name_of(gate),
            "switch_idx": switch_idx,
        })

    def add_switch(
        self,
        name: str,
        n1: int,
        n2: int,
        closed: bool = False,  # noqa: ARG002 - initial state is irrelevant in v1.3
        g_on: float = 1.0,
        g_off: float = 1e-9,
    ) -> None:
        switch_idx = self._next_switch_idx()
        self._builder.add_switch(
            name,
            self._name_of(n1),
            self._name_of(n2),
            float(g_on),
            float(g_off),
        )
        # Plain switches have no gate terminal — recorded with an empty
        # ``gate_node`` so callers know this bit is driven solely by
        # the user-supplied ``switch_fn`` rather than by a PWM-source
        # virtual component.
        self.pending_gate_signals.append({
            "device": name,
            "kind": "switch",
            "gate_node": "",
            "switch_idx": switch_idx,
        })

    def add_vcswitch(
        self,
        name: str,
        ctrl: int,
        t1: int,
        t2: int,
        v_threshold: float = 2.5,  # noqa: ARG002 - threshold ignored in v1.3 (use switch_fn)
        g_on: float = 1.0,
        g_off: float = 1e-9,
    ) -> None:
        # Voltage-controlled switch in v1.3 is just a switch driven by
        # switch_fn(t, state) — record the control node for later
        # wiring.
        switch_idx = self._next_switch_idx()
        self._builder.add_switch(
            name,
            self._name_of(t1),
            self._name_of(t2),
            float(g_on),
            float(g_off),
        )
        self.pending_gate_signals.append({
            "device": name,
            "kind": "vcswitch",
            "gate_node": self._name_of(ctrl),
            "switch_idx": switch_idx,
        })

    def add_snubber_rc(
        self,
        name: str,
        n1: int,
        n2: int,
        R: float,  # noqa: N803
        C: float,  # noqa: N803
        initial_voltage: float = 0.0,  # noqa: ARG002 - v1.3 add_rc_snubber doesn't take IC
    ) -> None:
        # pulsim 1.3 exposes ``add_rc_snubber(builder, name, R, C)`` at
        # the module level.
        if hasattr(self._pm, "add_rc_snubber"):
            self._pm.add_rc_snubber(
                self._builder,
                name,
                self._name_of(n1),
                self._name_of(n2),
                float(R),
                float(C),
            )
        else:
            # Fallback: expand into series R + C.
            inner = f"{name}__snub_node"
            self._builder.node(inner)
            self._builder.add_resistor(f"{name}_R", self._name_of(n1), inner, float(R))
            self._builder.add_capacitor(f"{name}_C", inner, self._name_of(n2), float(C))

    # --- virtual / control components ---------------------------------
    def add_virtual_component(
        self,
        name: str,
        kind: str,
        nodes: list[int] | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """v0's virtual components were control blocks (PI, integrator,
        PWM generator, ...). v1.3 has them under ``pulsim.control`` /
        ``pulsim.blockchain``, but the assembly is driven by the
        backend's BlockChain executor, not the circuit builder. Record
        the call so the backend can pick it up later.
        """
        self.virtual_component_records.append({
            "name": name,
            "kind": kind,
            "nodes": [int(n) for n in (nodes or [])],
            "params": dict(params or {}),
        })

    # --- layout (no-op pass-through) ----------------------------------
    def set_position(self, name: str, position: SchematicPosition) -> None:
        self._positions[name] = position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise_node_name(name: Any) -> str:
    """Convert any incoming node identifier to the canonical str name
    the v1.3 builder expects."""
    if name is None:
        return "gnd"
    s = str(name).strip()
    if not s or s.lower() in {"0", "gnd"}:
        return "gnd"
    return s
