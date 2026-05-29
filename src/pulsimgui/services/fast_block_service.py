"""Compile a user-authored control law into a runnable callable.

This is the GUI-side bridge to pulsim 1.5's ``pulsim.fast_block``
Numba-JIT "C block" workalike. The user writes a small Python control
function in a C_BLOCK component (the PSIM "Custom C Block" / PLECS
"C-Script Block" analogue); this service compiles it and hands back a
uniform :class:`CompiledControlLaw` the rest of the app can call.

Two compile paths, picked automatically:

* **Numba JIT** (when ``pip install pulsim[fast]`` provided numba) —
  ``pulsim.fast_block`` turns the function into LLVM-compiled machine
  code. Matches hand-written C for the 10–50-flop loops control
  engineers write; first call pays a ~0.3–1 s JIT cost.
* **Pure-Python fallback** (no numba) — the same source runs as an
  ordinary Python function. Correct, just not accelerated. Keeps the
  feature usable out of the box; users opt into the speed-up by
  installing the extra.

Authoring contract (mirrors ``pulsim.fast_block``):

    def control(*scalar_inputs, state):
        # state: 1-D float64 array, persists across calls; mutate
        #        in place. Return the scalar output.
        state[0] += Ki * dt * error
        return Kp * error + state[0]

The last parameter MUST be named ``state``. Everything before it is a
scalar input supplied each step (error, dt, gains, measured signals).
"""
from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


class FastBlockCompileError(Exception):
    """Raised when a user control law fails to compile or violates the
    authoring contract. The message is safe to show in the GUI."""


# Names we accept as the entry-point function when the source defines
# exactly one, or when the user didn't pass an explicit ``func_name``.
_ENTRY_POINT_NAMES = ("control", "block", "step", "compute", "f")


@dataclass
class CompiledControlLaw:
    """A compiled control law, uniform across the Numba and
    pure-Python paths.

    Attributes
    ----------
    func
        The callable. Signature ``(*scalar_args, state)`` → float.
    n_states
        Length of the persistent state vector.
    is_jit
        True when the Numba-compiled path is active.
    func_name
        Name of the entry-point function in the user source.
    arg_count
        Number of scalar arguments (everything before ``state``).
    """

    func: Callable[..., Any]
    n_states: int
    is_jit: bool
    func_name: str
    arg_count: int

    def __call__(self, *args: Any) -> float:
        return float(self.func(*args))

    def make_state(self) -> "np.ndarray":
        """Fresh zero-initialised state vector (float64)."""
        return np.zeros(self.n_states, dtype=np.float64)

    def warm_up(self) -> None:
        """Trigger JIT compilation (no-op on the pure-Python path) by
        calling the function once with zero scalar args + a fresh
        state. Raises :class:`FastBlockCompileError` if the body
        throws so authoring errors surface at build time, not mid-run.
        """
        sample = [0.0] * self.arg_count + [self.make_state()]
        try:
            self.func(*sample)
        except FastBlockCompileError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface body errors
            raise FastBlockCompileError(
                f"Control law '{self.func_name}' raised during warm-up "
                f"with zero inputs: {type(exc).__name__}: {exc}"
            ) from exc


def is_numba_available() -> bool:
    """True iff the Numba JIT path is usable (``pulsim[fast]`` installed).

    Prefers pulsim's own probe so we agree with the kernel about
    whether the fast path exists; falls back to importing numba
    directly if that helper is missing on an older pulsim.
    """
    try:
        from pulsim.fast_block import is_available
        return bool(is_available())
    except Exception:  # noqa: BLE001
        try:
            import numba  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False


class FastBlockService:
    """Compiles C_BLOCK Python control-law source into a
    :class:`CompiledControlLaw`."""

    # Builtins exposed to the user source. Deliberately small — enough
    # for numeric control laws, nothing that touches the filesystem,
    # imports, or process. (Numba's nopython mode rejects most of the
    # dangerous surface anyway, but the pure-Python fallback runs the
    # body directly, so we keep the namespace tight.)
    _SAFE_BUILTINS = {
        "abs": abs, "min": min, "max": max, "round": round,
        "len": len, "range": range, "float": float, "int": int,
        "bool": bool, "enumerate": enumerate, "sum": sum, "pow": pow,
    }

    def is_numba_available(self) -> bool:
        return is_numba_available()

    def compile_control_law(
        self,
        source: str,
        *,
        func_name: str | None = None,
        n_states: int = 1,
        prefer_numba: bool = True,
    ) -> CompiledControlLaw:
        """Compile ``source`` into a :class:`CompiledControlLaw`.

        Parameters
        ----------
        source
            Python source defining the control-law function. May
            contain helper defs / module-level constants; the
            entry-point is resolved via ``func_name`` or the
            single-def / known-name heuristic.
        func_name
            Explicit entry-point name. When ``None``, the resolver
            uses the only top-level def, or the first matching one of
            ``control/block/step/compute/f``.
        n_states
            Persistent state-vector length (≥ 0).
        prefer_numba
            When True (default) and numba is available, JIT-compile
            via ``pulsim.fast_block``. When False, force the
            pure-Python path (used by tests + as the no-numba
            fallback).

        Raises
        ------
        FastBlockCompileError
            On syntax errors, a missing / ambiguous entry point, a
            bad signature (no trailing ``state`` parameter), or a
            body error caught during warm-up.
        """
        if not source or not source.strip():
            raise FastBlockCompileError("Control law source is empty.")

        n_states = max(0, int(n_states))

        raw_func = self._extract_function(source, func_name)
        arg_count = self._validate_signature(raw_func)

        compiled, is_jit = self._maybe_jit(raw_func, n_states, prefer_numba)

        law = CompiledControlLaw(
            func=compiled,
            n_states=n_states,
            is_jit=is_jit,
            func_name=raw_func.__name__,
            arg_count=arg_count,
        )
        # Validate the body actually runs with zero inputs — catches
        # NameErrors / shape bugs at compile time instead of mid-sim.
        law.warm_up()
        return law

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _extract_function(
        self, source: str, func_name: str | None
    ) -> Callable[..., Any]:
        namespace: dict[str, Any] = {
            "__builtins__": dict(self._SAFE_BUILTINS),
            "np": np,
            "numpy": np,
            "math": math,
        }
        try:
            code = compile(source, "<c_block>", "exec")
        except SyntaxError as exc:
            raise FastBlockCompileError(
                f"Syntax error in control law (line {exc.lineno}): {exc.msg}"
            ) from exc
        try:
            exec(code, namespace)  # noqa: S102 - sandboxed builtins
        except Exception as exc:  # noqa: BLE001
            raise FastBlockCompileError(
                f"Error executing control-law module body: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        # Keep only functions actually defined in the user source
        # (exclude np / math / builtins that are callable).
        defined = {
            name: obj for name, obj in namespace.items()
            if inspect.isfunction(obj)
        }

        if func_name:
            fn = defined.get(func_name)
            if fn is None:
                raise FastBlockCompileError(
                    f"Control law function '{func_name}' not found. "
                    f"Defined functions: {sorted(defined) or '(none)'}."
                )
            return fn

        if len(defined) == 1:
            return next(iter(defined.values()))

        for candidate in _ENTRY_POINT_NAMES:
            if candidate in defined:
                return defined[candidate]

        if not defined:
            raise FastBlockCompileError(
                "Control law defines no function. Define one, e.g.:\n"
                "    def control(error, dt, state):\n"
                "        state[0] += dt * error\n"
                "        return state[0]"
            )
        raise FastBlockCompileError(
            f"Control law defines multiple functions "
            f"({sorted(defined)}) and none is named one of "
            f"{_ENTRY_POINT_NAMES}. Name your entry point 'control' "
            f"or pass an explicit function name."
        )

    @staticmethod
    def _validate_signature(func: Callable[..., Any]) -> int:
        """Verify the trailing parameter is ``state`` and return the
        number of scalar arguments before it."""
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError) as exc:
            raise FastBlockCompileError(
                f"Cannot inspect control-law signature: {exc}"
            ) from exc
        params = list(sig.parameters.values())
        if not params:
            raise FastBlockCompileError(
                f"Control law '{func.__name__}' takes no arguments — it "
                f"must accept at least a trailing 'state' parameter."
            )
        # Reject *args / **kwargs — the per-step caller passes fixed
        # positional scalars + state.
        for p in params:
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                raise FastBlockCompileError(
                    f"Control law '{func.__name__}' must use fixed "
                    f"positional parameters (no *args / **kwargs)."
                )
        if params[-1].name != "state":
            raise FastBlockCompileError(
                f"Control law '{func.__name__}' last parameter must be "
                f"named 'state' (got '{params[-1].name}'). It receives "
                f"the persistent float64 state vector."
            )
        return len(params) - 1

    def _maybe_jit(
        self,
        func: Callable[..., Any],
        n_states: int,
        prefer_numba: bool,
    ) -> tuple[Callable[..., Any], bool]:
        """Return ``(callable, is_jit)``. Tries ``pulsim.fast_block``
        when numba is available + requested; otherwise returns the raw
        Python function. A JIT failure degrades to pure-Python rather
        than aborting — a correct-but-slow block beats no block."""
        if not prefer_numba or not is_numba_available():
            return func, False
        try:
            from pulsim import fast_block
            compiled = fast_block(func, n_states=n_states)
            # pulsim's FastBlock is callable; unwrap to a plain callable
            # so our uniform __call__ doesn't double-wrap.
            return compiled, True
        except Exception:  # noqa: BLE001 - degrade, don't abort
            return func, False
