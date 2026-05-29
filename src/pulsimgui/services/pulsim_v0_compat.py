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
    @property
    def SchematicPosition(self) -> type:  # noqa: N802 — v0 API name
        # Expose the dataclass directly — the GUI converter calls it
        # positionally as ``SchematicPosition(x, y, rotation,
        # mirrored)``, which a kwargs-only lambda silently rejects.
        # A property defers the lookup so the forward reference to the
        # dataclass declared below this class body resolves at call
        # time rather than class-body execution time.
        return SchematicPosition

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

    **Field names track what** :class:`CircuitConverter._add_voltage_source`
    **writes**: ``offset`` (DC bias) and ``amplitude`` (peak). Earlier
    revisions of this shim used the pulsim-1.x positional names
    ``v_dc`` / ``v_amplitude``, but the converter was already speaking
    the v0 ``offset`` / ``amplitude`` vocabulary — the mismatch sent
    every sine source write into ``extras`` and emitted an
    amplitude-0 source, so every diode bridge in the GUI quietly
    produced V_bus ≈ 0 V.
    """

    offset: float = 0.0
    amplitude: float = 1.0
    frequency: float = 60.0
    phase: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"offset", "amplitude", "frequency", "phase", "extras"}:
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

    Field names track what :class:`CircuitConverter._add_voltage_source`
    writes:: ``v_initial``, ``v_pulse``, ``t_delay``, ``t_rise``,
    ``t_fall``, ``t_width``, ``period``. Earlier revisions named these
    ``v_pulsed`` / ``t_start`` / ``pulse_width`` / ``rise_time`` /
    ``fall_time`` (pulsim-1.x positional vocabulary) — the mismatch
    sent every pulse write into ``extras`` so the source defaulted to
    a 1 V → 1 V no-op step.

    Translated to ``CircuitBuilder.add_pulse_voltage_source(name, from, to,
    v_initial, v_pulse, t_delay, t_width, period, t_rise, t_fall)``.
    """

    v_initial: float = 0.0
    v_pulse: float = 1.0
    t_delay: float = 0.0
    t_width: float = 1e-3
    period: float = 2e-3
    t_rise: float = 1e-6
    t_fall: float = 1e-6
    extras: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {
            "v_initial",
            "v_pulse",
            "t_delay",
            "t_width",
            "period",
            "t_rise",
            "t_fall",
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
    positions from a separate path.

    ``CircuitConverter._apply_positions_from_list`` calls this with
    four *positional* args ``(x, y, rotation, mirrored)`` so the
    dataclass order must match — switching to ``staticmethod(lambda
    **kw: …)`` is what broke it on real .pulsim files.
    """

    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    mirrored: bool = False


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

        # Closed-loop descriptors stashed by ``CircuitConverter.build()``
        # after it detects a PI+PWM+MOSFET chain. The backend reads this
        # to wire ``pulsim.bind_pi_to_switch`` at simulate time. Empty
        # list = open-loop circuit; backend uses the legacy static
        # switch_fn path instead.
        self.closed_loop_descriptors: list[dict[str, Any]] = []

        # Nonlinear-device observer handles (pulsim 1.5+ induction
        # motor + Jiles-Atherton hysteretic inductor). Each ``add_*``
        # below appends ``{"kind": str, "name": str, "handle": obj}``;
        # the backend reads this list at simulate time, calls
        # ``make_<kind>_observer(builder, handle)`` for each, and
        # composes the resulting step-observers into the run's
        # observer chain so the device's nonlinear back-EMF / dM/dt
        # contribution is driven every step.
        self.nonlinear_observer_specs: list[dict[str, Any]] = []

        # C_BLOCK control-loop descriptors (pulsim 1.5 fast_block).
        # Populated by ``CircuitConverter`` when it detects a
        # python_numba C_BLOCK regulating a PWM-driven switch from a
        # single-node feedback. Each entry carries the compiled-law
        # source + feedback node + switch + sample time; the backend
        # compiles it via FastBlockService and runs it as a ClosedLoop
        # (measured node → control law → duty → switch) each step.
        self.cblock_loop_descriptors: list[dict[str, Any]] = []

        # Position metadata — never round-tripped to the builder.
        self._positions: dict[str, SchematicPosition] = {}

        # ``device_name → initial_voltage|initial_current`` collected
        # from v0-style ``add_capacitor(…, initial_voltage)`` and
        # ``add_inductor(…, initial_current)`` calls. Pulsim 1.4 has no
        # builder-level IC slot, so these values are kept here for a
        # future caller (e.g. ``backend_adapter`` could later pre-load
        # ``simulate(initial_state=…)`` from the dict). Empty for the
        # common case where the converter passes ICs of zero.
        self._initial_conditions: dict[str, float] = {}

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
        here without poking the underlying builder.

        Why not call ``builder.node(name)``? Because v1.3's
        ``CircuitBuilder`` **auto-creates** any node a subsequent
        ``add_*`` call references, and any node we touch here that
        never ends up wired to a branch becomes a dangling row in
        the MNA matrix (singular topology, cache build rejects it).
        The v0 GUI flow creates several "logical" nodes that v1.3
        doesn't need — most notably the **gate** of a MOSFET / IGBT
        (the gate has no electrical wiring in v1.3, it's a
        ``switch_fn`` signal). Reserving the name on the shim side
        and letting the builder discover only the truly-electrical
        names keeps every mask buildable.
        """
        name = _normalise_node_name(name)
        existing = self._node_name_to_id.get(name)
        if existing is not None:
            return existing
        new_id = self._next_node_id
        self._next_node_id += 1
        self._node_id_to_name[new_id] = name
        self._node_name_to_id[name] = new_id
        return new_id

    def get_node(self, name: str) -> int:
        name = _normalise_node_name(name)
        return self._node_name_to_id.get(name, -1)

    def ground(self) -> int:
        """Return the ground node id (always ``-1`` in the shim).

        v0 ``pulsim.Circuit`` exposed a ``ground()`` method that
        :class:`CircuitConverter` calls whenever it encounters a node
        whose normalised name is ``"0"`` (the v0 ground convention).
        The shim reserves ``-1 ↔ "gnd"`` at construction time
        (:attr:`_node_id_to_name`) so any node id we mint here can be
        translated back to the v1.3 ``"gnd"`` string by ``_name_of``
        without colliding with the user-minted ids that start at 0.
        """
        return -1

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

    def add_capacitor(  # noqa: N803
        self,
        name: str,
        n1: int,
        n2: int,
        C: float,
        initial_voltage: float = 0.0,
    ) -> None:
        # pulsim 1.5 lands native `c0=` kwarg on
        # ``CircuitBuilder.add_capacitor`` — IC propagates through to
        # ``initial_state()`` synthesis without the shim having to
        # warn-and-drop. Pre-1.5 hosts get the legacy 4-arg path with
        # a one-shot warning + shim-side record (handled by the older
        # capability detector if/when this shim ships against a
        # pre-1.5 wheel).
        try:
            self._builder.add_capacitor(
                name, self._name_of(n1), self._name_of(n2), float(C),
                c0=float(initial_voltage) if initial_voltage else None,
            )
        except TypeError:
            # Pre-1.5 binding without c0 kwarg — fall back to the
            # shim-side warn-and-drop the way v1.4 did.
            if initial_voltage:
                _warn_initial_condition("capacitor", name, "V", initial_voltage)
                self._initial_conditions[name] = float(initial_voltage)
            self._builder.add_capacitor(
                name, self._name_of(n1), self._name_of(n2), float(C),
            )

    def add_inductor(  # noqa: N803
        self,
        name: str,
        n1: int,
        n2: int,
        L: float,
        initial_current: float = 0.0,
    ) -> None:
        # See ``add_capacitor`` for the IC handling rationale.
        try:
            self._builder.add_inductor(
                name, self._name_of(n1), self._name_of(n2), float(L),
                i0=float(initial_current) if initial_current else None,
            )
        except TypeError:
            if initial_current:
                _warn_initial_condition("inductor", name, "A", initial_current)
                self._initial_conditions[name] = float(initial_current)
            self._builder.add_inductor(
                name, self._name_of(n1), self._name_of(n2), float(L),
            )

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
                float(p.offset), float(p.amplitude),
                float(p.frequency), float(p.phase),
            )
        elif isinstance(value_or_params, PulseParams):
            p = value_or_params
            self._builder.add_pulse_voltage_source(
                name, npos_s, nneg_s,
                float(p.v_initial), float(p.v_pulse),
                float(p.t_delay), float(p.t_width),
                float(p.period), float(p.t_rise),
                float(p.t_fall),
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
        # Read the same field names the GUI converter writes
        # (``offset`` / ``amplitude``) rather than the old positional
        # names so a 110 V_rms sine source actually emits 110 V_rms.
        self._builder.add_sine_voltage_source(
            name,
            self._name_of(npos),
            self._name_of(nneg),
            float(params.offset),
            float(params.amplitude),
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
            float(params.v_pulse),
            float(params.t_delay),
            float(params.t_width),
            float(params.period),
            float(params.t_rise),
            float(params.t_fall),
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
        g_on: float = 1e3,
        g_off: float = 1e-9,
        V_th: float = 0.7,  # noqa: N803
    ) -> None:
        """v1.3's ``add_diode(name, anode, cathode, g_on, g_off, V_th=0.0)``.

        Three defaults differ from v0 and matter for cache buildability:

        * ``g_on=1e3`` (1 mΩ ON) — pulsim's own buck example uses this
          value. The v0 default of 1.0 (1 Ω) produces a diode forward
          drop large enough to collapse buck/boost output voltages by
          several volts at typical inductor currents.
        * ``V_th=0.7`` — a non-zero forward-voltage threshold is
          required for ``PwlStateSpaceCache.build`` to certify the
          all-off mask as non-singular for topologies that rely on
          diode commutation to keep an inductor terminal grounded
          (buck, boost, half-wave rectifier, …). With ``V_th=0`` the
          eager-cache rejects the topology before any timestep runs.

        ``V_th`` isn't part of the v0 ``Circuit.add_diode(name, anode,
        cathode, g_on, g_off)`` signature, so callers that only pass
        four positional args get the new default automatically.
        """
        self._builder.add_diode(
            name,
            self._name_of(anode),
            self._name_of(cathode),
            float(g_on),
            float(g_off),
            float(V_th),
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

    # --- nonlinear devices needing a simulate-time observer -----------
    def add_induction_motor(
        self,
        name: str,
        a: int,
        b: int,
        c: int,
        n: int,
        params: dict[str, Any],
    ) -> None:
        """Add a 3-phase squirrel-cage induction motor via pulsim
        1.5's ``add_induction_motor`` and stash its handle so the
        backend can wire ``make_induction_motor_observer`` into the
        step-observer chain at simulate time.

        ``a/b/c`` are the stator phase terminal node ids, ``n`` the
        star-point neutral. ``params`` carries the equivalent-circuit
        R/L set + mechanical parameters (see DEFAULT_PARAMETERS).

        Raises ``AttributeError`` if the host pulsim predates 1.5 (no
        ``add_induction_motor``) so the converter can surface a clear
        "runtime does not support" message instead of a silent skip.
        """
        add_im = getattr(self._pm, "add_induction_motor", None)
        if add_im is None:
            raise AttributeError(
                "pulsim runtime has no add_induction_motor "
                "(requires pulsim >= 1.5)"
            )
        motor = add_im(
            self._builder,
            name=name,
            phase_nodes=[self._name_of(a), self._name_of(b), self._name_of(c)],
            neutral_node=self._name_of(n),
            R_s=float(params.get("R_s", 0.5)),
            L_s=float(params.get("L_s", 0.05)),
            R_r=float(params.get("R_r", 0.4)),
            L_r=float(params.get("L_r", 0.05)),
            L_m=float(params.get("L_m", 0.045)),
            pole_pairs=int(params.get("pole_pairs", 2)),
            J=float(params.get("J", 1e-3)),
            B=float(params.get("B", 0.0)),
            T_load=float(params.get("T_load", 0.0)),
        )
        self.nonlinear_observer_specs.append(
            {"kind": "induction_motor", "name": name, "handle": motor}
        )

    def add_hysteretic_inductor(
        self,
        name: str,
        n1: int,
        n2: int,
        params: dict[str, Any],
    ) -> None:
        """Add a Jiles-Atherton hysteretic inductor via pulsim 1.5's
        ``add_hysteretic_inductor`` and stash its handle for the
        backend's observer wiring.

        ``params["material"]`` selects a built-in J-A parameter set
        through ``pulsim.reference_material``; geometry
        (``N_turns`` / ``l_m`` / ``A_core``) sizes the linear
        air-core inductance and the hysteresis contribution.
        """
        add_hl = getattr(self._pm, "add_hysteretic_inductor", None)
        ref_material = getattr(self._pm, "reference_material", None)
        if add_hl is None or ref_material is None:
            raise AttributeError(
                "pulsim runtime has no add_hysteretic_inductor "
                "(requires pulsim >= 1.5)"
            )
        material = str(params.get("material", "si_steel_m19"))
        ja_params = ref_material(material)
        hyst = add_hl(
            self._builder,
            name=name,
            from_node=self._name_of(n1),
            to_node=self._name_of(n2),
            params=ja_params,
            N_turns=int(params.get("N_turns", 100)),
            l_m=float(params.get("l_m", 0.1)),
            A_core=float(params.get("A_core", 1e-4)),
        )
        self.nonlinear_observer_specs.append(
            {"kind": "hysteretic_inductor", "name": name, "handle": hyst}
        )

    # --- virtual / control components ---------------------------------
    def add_virtual_component(
        self,
        kind: str,
        name: str,
        nodes: list[int] | None = None,
        params: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """v0's virtual components were control blocks (PI, integrator,
        PWM generator, ...). v1.3 has them under ``pulsim.control`` /
        ``pulsim.blockchain``, but the assembly is driven by the
        backend's BlockChain executor, not the circuit builder. Record
        the call so the backend can pick it up later.

        Argument order matches what
        :class:`CircuitConverter._add_virtual_component` calls today
        — ``(kind, name, nodes, params, metadata)``. Earlier revisions
        had ``name`` first and silently dropped ``metadata``, which
        caused every ``VOLTAGE_PROBE`` / ``CURRENT_PROBE`` /
        ``PWM_GENERATOR`` write from the GUI to raise a TypeError
        once pulsim 1.4+ landed.
        """
        self.virtual_component_records.append({
            "name": name,
            "kind": kind,
            "nodes": [int(n) for n in (nodes or [])],
            "params": dict(params or {}),
            "metadata": dict(metadata or {}),
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


def _warn_initial_condition(
    device_kind: str,
    device_name: str,
    unit: str,
    value: float,
) -> None:
    """Emit a one-line warning when the v0 converter passes a non-zero
    initial condition that pulsim 1.4 has no builder-level slot for.

    Pulsim 1.4's ``CircuitBuilder.add_capacitor`` and ``add_inductor``
    are 4-arg (name, from, to, value) — initial state is set at run
    time via ``simulate(initial_state=…)`` if needed. The shim records
    the value in :attr:`Circuit._initial_conditions` so a future
    backend pass *could* pre-load it, but today the value would be
    silently lost — a warning makes the gap obvious in the console.

    Warning is rate-limited per device name to avoid spamming the
    output when a .pulsim file declares many ICs.
    """
    import warnings

    warnings.warn(
        f"v0 compat: non-zero {device_kind} IC {value} {unit} on "
        f"'{device_name}' is recorded but not yet propagated to the "
        f"pulsim 1.4 simulator. Set ICs via simulate(initial_state=…) "
        f"if they materially affect your result.",
        RuntimeWarning,
        stacklevel=3,
    )
