"""Signal-flow evaluator compatibility layer.

This module first tries to import ``SignalEvaluator`` from the backend package
(``pulsim.signal_evaluator``). When unavailable (for example in older
``pulsim`` builds), it provides a local fallback implementation used by
PulsimGui.
"""

from __future__ import annotations

from collections import deque
import logging
from typing import Any

log = logging.getLogger(__name__)

try:  # Prefer backend-native implementation when available.
    from pulsim.signal_evaluator import (  # type: ignore[import-not-found]
        AlgebraicLoopError,
        SIGNAL_TYPES,
        SignalEvaluator,
    )

except Exception:
    # -----------------------------------------------------------------------
    # Local fallback implementation
    # -----------------------------------------------------------------------

    def _try_import_native() -> dict[str, Any]:
        """Try to import optional native control classes from pulsim bindings."""
        native: dict[str, Any] = {}
        try:
            from pulsim._pulsim import (  # type: ignore[import]
                HysteresisController,
                PIController,
                PIDController,
                RateLimiter,
                SampleHold,
            )

            native["PIController"] = PIController
            native["PIDController"] = PIDController
            native["RateLimiter"] = RateLimiter
            native["HysteresisController"] = HysteresisController
            native["SampleHold"] = SampleHold
        except Exception as exc:  # pragma: no cover - optional backend feature
            log.debug("Native control classes not available: %s", exc)
        return native


    _NATIVE = _try_import_native()

    SIGNAL_TYPES: frozenset[str] = frozenset(
        {
            "CONSTANT",
            "GAIN",
            "SUM",
            "SUBTRACTOR",
            "LIMITER",
            "RATE_LIMITER",
            "PI_CONTROLLER",
            "PID_CONTROLLER",
            "PWM_GENERATOR",
            "VOLTAGE_PROBE",
            "CURRENT_PROBE",
            "POWER_PROBE",
            "INTEGRATOR",
            "DIFFERENTIATOR",
            "HYSTERESIS",
            "SAMPLE_HOLD",
            "MATH_BLOCK",
            "SIGNAL_MUX",
            "SIGNAL_DEMUX",
        }
    )

    _SOURCE_TYPES: frozenset[str] = frozenset(
        {
            "CONSTANT",
            "VOLTAGE_PROBE",
            "CURRENT_PROBE",
            "POWER_PROBE",
        }
    )

    _OUTPUT_PIN_NAMES: dict[str, list[str]] = {
        "CONSTANT": ["OUT"],
        "GAIN": ["OUT"],
        "SUM": ["OUT"],
        "SUBTRACTOR": ["OUT"],
        "LIMITER": ["OUT"],
        "RATE_LIMITER": ["OUT"],
        "PI_CONTROLLER": ["OUT"],
        "PID_CONTROLLER": ["OUT"],
        "INTEGRATOR": ["OUT"],
        "DIFFERENTIATOR": ["OUT"],
        "HYSTERESIS": ["OUT"],
        "SIGNAL_MUX": ["OUT"],
        "SIGNAL_DEMUX": ["OUT1", "OUT2", "OUT3", "OUT4", "OUT5", "OUT6", "OUT7", "OUT8"],
        "VOLTAGE_PROBE": ["OUT"],
        "CURRENT_PROBE": ["MEAS"],
        "POWER_PROBE": ["OUT"],
        "PWM_GENERATOR": ["OUT"],
        "MATH_BLOCK": ["OUT"],
        "SAMPLE_HOLD": ["OUT"],
    }


    class AlgebraicLoopError(RuntimeError):
        """Raised when a cycle is detected in the signal-flow graph."""

        def __init__(self, cycle_ids: list[str]) -> None:
            self.cycle_ids = cycle_ids
            names = ", ".join(cycle_ids)
            super().__init__(
                "Algebraic loop detected in signal network. "
                f"Blocks involved: [{names}]. "
                "Break the loop (e.g. add a unit-delay or restructure the control path)."
            )


    class SignalEvaluator:
        """Evaluate signal-domain blocks in topological order."""

        def __init__(self, circuit_data: dict) -> None:
            self._circuit_data = circuit_data
            self._comps: dict[str, dict] = {}
            self._adj: dict[str, list[tuple[str, str]]] = {}
            self._state: dict[str, float] = {}
            self._controllers: dict[str, Any] = {}
            self._order: list[str] = []
            self._pwm_names: dict[str, str] = {}
            self._probe_nodes: dict[str, str] = {}

        def build(self) -> None:
            """Parse circuit data and prepare the evaluation graph."""
            self._comps.clear()
            self._adj.clear()
            self._state.clear()
            self._controllers.clear()
            self._order.clear()
            self._pwm_names.clear()

            self._collect_signal_components()
            self._build_graph()
            self._order = self._topological_sort()
            self._init_controllers()

            connected_ids: set[str] = {dst_id for edges in self._adj.values() for dst_id, _ in edges}
            self._pwm_names = {cid: name for cid, name in self._pwm_names.items() if cid in connected_ids}

        def has_signal_blocks(self) -> bool:
            """Return whether the circuit has evaluable signal blocks."""
            return bool(self._order)

        def pwm_components(self) -> dict[str, str]:
            """Return ``{component_id: pwm_name}`` for PWMs with DUTY_IN connected."""
            return dict(self._pwm_names)

        def update_probes(self, probe_values: dict[str, float]) -> None:
            """Inject probe measurements into block state."""
            for comp_id, value in probe_values.items():
                if comp_id in self._comps:
                    self._state[comp_id] = float(value)

        def step(self, t: float) -> dict[str, float]:
            """Evaluate all blocks once at time ``t``."""
            for comp_id in self._order:
                comp = self._comps[comp_id]
                ctype = comp.get("type", "")
                params = comp.get("parameters") or {}

                if ctype in _SOURCE_TYPES:
                    if ctype == "CONSTANT":
                        self._state[comp_id] = float(params.get("value", 0.0))
                    continue

                inputs = self._collect_inputs(comp_id, comp)

                if ctype == "GAIN":
                    k = float(params.get("gain", 1.0))
                    self._state[comp_id] = k * (inputs[0] if inputs else 0.0)

                elif ctype in ("SUM", "MATH_BLOCK"):
                    signs = list(params.get("signs") or ["+"] * len(inputs))
                    total = 0.0
                    for idx, val in enumerate(inputs):
                        sign = signs[idx] if idx < len(signs) else "+"
                        total += val if sign == "+" else -val
                    self._state[comp_id] = total

                elif ctype == "SUBTRACTOR":
                    a = inputs[0] if len(inputs) > 0 else 0.0
                    b = inputs[1] if len(inputs) > 1 else 0.0
                    self._state[comp_id] = a - b

                elif ctype == "LIMITER":
                    lo = float(params.get("lower_limit", -1e9))
                    hi = float(params.get("upper_limit", 1e9))
                    value = inputs[0] if inputs else 0.0
                    self._state[comp_id] = max(lo, min(hi, value))

                elif ctype == "RATE_LIMITER":
                    ctl = self._controllers.get(comp_id)
                    if ctl is not None and hasattr(ctl, "update"):
                        self._state[comp_id] = float(ctl.update(inputs[0] if inputs else 0.0, t))
                    else:
                        self._state[comp_id] = inputs[0] if inputs else 0.0

                elif ctype == "INTEGRATOR":
                    ctl = self._controllers.get(comp_id)
                    if isinstance(ctl, dict):
                        t_prev = ctl["t_prev"]
                        dt = (t - t_prev) if t_prev >= 0 else 0.0
                        ctl["t_prev"] = t
                        k = float(params.get("gain", 1.0))
                        ctl["integral"] = ctl.get("integral", 0.0) + k * (inputs[0] if inputs else 0.0) * dt
                        lo = float(params.get("output_min", -1e6))
                        hi = float(params.get("output_max", 1e6))
                        self._state[comp_id] = max(lo, min(hi, ctl["integral"]))

                elif ctype == "PI_CONTROLLER":
                    ctl = self._controllers.get(comp_id)
                    error = inputs[0] if inputs else 0.0
                    if isinstance(ctl, dict):
                        t_prev = ctl["t_prev"]
                        dt = (t - t_prev) if t_prev >= 0.0 else 0.0
                        ctl["t_prev"] = t
                        kp = float(params.get("kp", 1.0))
                        ki = float(params.get("ki", 0.0))
                        ctl["integral"] += error * dt
                        raw = kp * error + ki * ctl["integral"]
                        lo = float(params.get("output_min", -1e9))
                        hi = float(params.get("output_max", 1e9))
                        self._state[comp_id] = max(lo, min(hi, raw))
                    elif ctl is not None and hasattr(ctl, "update"):
                        self._state[comp_id] = float(ctl.update(error, t))
                    else:
                        self._state[comp_id] = 0.0

                elif ctype == "PID_CONTROLLER":
                    ctl = self._controllers.get(comp_id)
                    error = inputs[0] if inputs else 0.0
                    if ctl is not None and not isinstance(ctl, dict) and hasattr(ctl, "update"):
                        self._state[comp_id] = float(ctl.update(error, t))
                    else:
                        self._state[comp_id] = error

                elif ctype == "HYSTERESIS":
                    ctl = self._controllers.get(comp_id)
                    if ctl is not None and not isinstance(ctl, dict) and hasattr(ctl, "update"):
                        self._state[comp_id] = float(ctl.update(inputs[0] if inputs else 0.0))
                    else:
                        self._state[comp_id] = inputs[0] if inputs else 0.0

                elif ctype == "SAMPLE_HOLD":
                    ctl = self._controllers.get(comp_id)
                    if ctl is not None and not isinstance(ctl, dict) and hasattr(ctl, "update"):
                        self._state[comp_id] = float(ctl.update(inputs[0] if inputs else 0.0, t))
                    else:
                        self._state[comp_id] = inputs[0] if inputs else 0.0

                elif ctype in ("SIGNAL_MUX", "SIGNAL_DEMUX"):
                    self._state[comp_id] = inputs[0] if inputs else 0.0

                elif ctype == "PWM_GENERATOR":
                    duty = inputs[0] if inputs else float(params.get("duty_cycle", 0.5))
                    self._state[comp_id] = max(0.0, min(1.0, duty))

                else:
                    self._state[comp_id] = inputs[0] if inputs else 0.0

            return dict(self._state)

        def get_pwm_duty(self, comp_id: str) -> float:
            """Return clamped duty value for a PWM component."""
            return float(self._state.get(comp_id, 0.5))

        def reset(self) -> None:
            """Reset stateful controller internals."""
            for ctl in self._controllers.values():
                if hasattr(ctl, "reset"):
                    ctl.reset()
                elif isinstance(ctl, dict):
                    ctl.update({"integral": 0.0, "t_prev": -1.0})

        def _collect_signal_components(self) -> None:
            for comp in self._circuit_data.get("components", []):
                ctype = comp.get("type", "")
                if ctype in SIGNAL_TYPES:
                    comp_id = str(comp["id"])
                    self._comps[comp_id] = comp
                    self._adj[comp_id] = []
                    self._state[comp_id] = 0.0
                    if ctype == "PWM_GENERATOR":
                        self._pwm_names[comp_id] = str(comp.get("name") or comp_id)
                    if ctype in ("VOLTAGE_PROBE", "CURRENT_PROBE"):
                        nodes = comp.get("pin_nodes") or []
                        self._probe_nodes[comp_id] = nodes[0] if nodes else ""

        def _build_graph(self) -> None:
            comp_pin_set: set[tuple[str, int]] = {
                (cid, int(pin["index"]))
                for cid, comp in self._comps.items()
                for pin in (comp.get("pins") or [])
                if "index" in pin
            }

            for wire in self._circuit_data.get("wires", []):
                sc = wire.get("start_connection") or {}
                ec = wire.get("end_connection") or {}
                if not sc or not ec:
                    continue

                src_id = str(sc.get("component_id", ""))
                dst_id = str(ec.get("component_id", ""))
                try:
                    src_pin = int(sc.get("pin_index", -1))
                    dst_pin = int(ec.get("pin_index", -1))
                except Exception:
                    continue

                if src_id not in self._comps or dst_id not in self._comps:
                    continue
                if (src_id, src_pin) not in comp_pin_set or (dst_id, dst_pin) not in comp_pin_set:
                    continue

                src_comp = self._comps[src_id]
                src_type = src_comp.get("type", "")
                src_outputs = _OUTPUT_PIN_NAMES.get(src_type, ["OUT"])
                src_pin_name = self._pin_name(src_comp, src_pin)

                if src_pin_name not in src_outputs:
                    dst_comp = self._comps[dst_id]
                    dst_type = dst_comp.get("type", "")
                    dst_outputs = _OUTPUT_PIN_NAMES.get(dst_type, ["OUT"])
                    dst_pin_name = self._pin_name(dst_comp, dst_pin)
                    if dst_pin_name in dst_outputs:
                        src_id, dst_id = dst_id, src_id
                        src_pin, dst_pin = dst_pin, src_pin
                        src_comp = dst_comp
                        src_type = dst_type
                        src_pin_name = dst_pin_name
                    else:
                        continue

                dst_pin_name = self._pin_name(self._comps[dst_id], dst_pin)
                self._adj[src_id].append((dst_id, dst_pin_name))

        def _topological_sort(self) -> list[str]:
            in_degree: dict[str, int] = {cid: 0 for cid in self._comps}
            for edges in self._adj.values():
                for dst_id, _ in edges:
                    in_degree[dst_id] = in_degree.get(dst_id, 0) + 1

            queue: deque[str] = deque(cid for cid, deg in in_degree.items() if deg == 0)
            order: list[str] = []
            while queue:
                cid = queue.popleft()
                order.append(cid)
                for dst_id, _ in self._adj.get(cid, []):
                    in_degree[dst_id] -= 1
                    if in_degree[dst_id] == 0:
                        queue.append(dst_id)

            remaining = [cid for cid, deg in in_degree.items() if deg > 0]
            if remaining:
                names = [str(self._comps[cid].get("name") or cid) for cid in remaining]
                raise AlgebraicLoopError(names)
            return order

        def _init_controllers(self) -> None:
            for comp_id in self._order:
                comp = self._comps[comp_id]
                ctype = comp.get("type", "")
                params = comp.get("parameters") or {}

                if ctype == "PI_CONTROLLER":
                    pi_cls = _NATIVE.get("PIController")
                    if pi_cls is not None:
                        try:
                            self._controllers[comp_id] = pi_cls(
                                float(params.get("kp", 1.0)),
                                float(params.get("ki", 0.0)),
                                float(params.get("output_min", -1e9)),
                                float(params.get("output_max", 1e9)),
                            )
                            continue
                        except Exception:
                            pass
                    self._controllers[comp_id] = {"integral": 0.0, "t_prev": -1.0}

                elif ctype == "PID_CONTROLLER":
                    pid_cls = _NATIVE.get("PIDController")
                    if pid_cls is not None:
                        try:
                            self._controllers[comp_id] = pid_cls(
                                float(params.get("kp", 1.0)),
                                float(params.get("ki", 0.0)),
                                float(params.get("kd", 0.01)),
                                float(params.get("output_min", -1e9)),
                                float(params.get("output_max", 1e9)),
                            )
                            continue
                        except Exception:
                            pass

                elif ctype == "RATE_LIMITER":
                    rl_cls = _NATIVE.get("RateLimiter")
                    if rl_cls is not None:
                        try:
                            self._controllers[comp_id] = rl_cls(
                                float(params.get("rising_rate", 1e6)),
                                float(params.get("falling_rate", -1e6)),
                            )
                            continue
                        except Exception:
                            pass

                elif ctype == "HYSTERESIS":
                    hyst_cls = _NATIVE.get("HysteresisController")
                    if hyst_cls is not None:
                        try:
                            upper = float(params.get("upper_threshold", 0.5))
                            lower = float(params.get("lower_threshold", -0.5))
                            self._controllers[comp_id] = hyst_cls(
                                upper,
                                upper - lower,
                                float(params.get("output_high", 1.0)),
                                float(params.get("output_low", 0.0)),
                            )
                            continue
                        except Exception:
                            pass

                elif ctype == "SAMPLE_HOLD":
                    sh_cls = _NATIVE.get("SampleHold")
                    if sh_cls is not None:
                        try:
                            self._controllers[comp_id] = sh_cls(float(params.get("sample_time", 1e-4)))
                            continue
                        except Exception:
                            pass

                elif ctype == "INTEGRATOR":
                    self._controllers[comp_id] = {"integral": 0.0, "t_prev": -1.0}

        def _collect_inputs(self, comp_id: str, comp: dict) -> list[float]:
            pin_values: dict[int, float] = {}
            for src_id, edges in self._adj.items():
                for dst_id, dst_pin_name in edges:
                    if dst_id != comp_id:
                        continue
                    for pin in comp.get("pins") or []:
                        if pin.get("name") == dst_pin_name and "index" in pin:
                            pin_values[int(pin["index"])] = self._state.get(src_id, 0.0)
            if not pin_values:
                return []
            return [val for _, val in sorted(pin_values.items())]

        @staticmethod
        def _pin_name(comp: dict, pin_index: int) -> str:
            for pin in comp.get("pins") or []:
                if int(pin.get("index", -1)) == pin_index:
                    return str(pin.get("name", ""))
            return ""


__all__ = ["SignalEvaluator", "AlgebraicLoopError", "SIGNAL_TYPES"]
