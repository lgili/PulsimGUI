"""Tests for FastBlockService — the GUI bridge to pulsim 1.5's
``fast_block`` Numba "C block" workalike.

numba may or may not be installed in CI (it's the ``pulsim[fast]``
extra). These tests pin behaviour on BOTH paths: the pure-Python
fallback always works; the JIT path is exercised only when numba is
present (and even then we force pure-Python in most tests via
``prefer_numba=False`` so results are deterministic and fast).
"""
from __future__ import annotations

import numpy as np
import pytest

from pulsimgui.services.fast_block_service import (
    CompiledControlLaw,
    FastBlockCompileError,
    FastBlockService,
    is_numba_available,
)


_PI_SOURCE = (
    "def control(error, dt, Kp, Ki, state):\n"
    "    state[0] += Ki * dt * error\n"
    "    return Kp * error + state[0]\n"
)


@pytest.fixture
def svc() -> FastBlockService:
    return FastBlockService()


# ---------------------------------------------------------------------------
# Happy path — pure-Python compile (deterministic, numba-independent).
# ---------------------------------------------------------------------------
def test_compiles_pi_control_law(svc: FastBlockService) -> None:
    law = svc.compile_control_law(_PI_SOURCE, n_states=1, prefer_numba=False)
    assert isinstance(law, CompiledControlLaw)
    assert law.func_name == "control"
    assert law.arg_count == 4         # error, dt, Kp, Ki
    assert law.n_states == 1
    assert law.is_jit is False        # forced pure-Python


def test_compiled_law_integrates_state(svc: FastBlockService) -> None:
    """The integrator state must persist + accumulate across calls."""
    law = svc.compile_control_law(_PI_SOURCE, n_states=1, prefer_numba=False)
    state = law.make_state()
    assert isinstance(state, np.ndarray)
    assert state.shape == (1,)
    assert state[0] == 0.0

    # error=2, dt=1ms, Kp=0.5, Ki=10  → integrator += 10*1e-3*2 = 0.02
    out1 = law(2.0, 1e-3, 0.5, 10.0, state)
    assert out1 == pytest.approx(0.5 * 2.0 + 0.02)
    out2 = law(2.0, 1e-3, 0.5, 10.0, state)
    assert out2 == pytest.approx(0.5 * 2.0 + 0.04)
    assert state[0] == pytest.approx(0.04)


def test_make_state_sizes_to_n_states(svc: FastBlockService) -> None:
    law = svc.compile_control_law(
        "def control(x, state):\n    return state[2] + x\n",
        n_states=3, prefer_numba=False,
    )
    st = law.make_state()
    assert st.shape == (3,)
    assert not st.any()


def test_resolves_single_def_without_explicit_name(svc: FastBlockService) -> None:
    law = svc.compile_control_law(
        "def my_law(x, state):\n    return 2 * x\n", prefer_numba=False,
    )
    assert law.func_name == "my_law"
    assert law(3.0, law.make_state()) == 6.0


def test_resolves_named_entry_point_among_helpers(svc: FastBlockService) -> None:
    src = (
        "def helper(z):\n    return z * z\n"
        "def control(x, state):\n    return helper(x)\n"
    )
    law = svc.compile_control_law(src, prefer_numba=False)
    assert law.func_name == "control"
    assert law(4.0, law.make_state()) == 16.0


def test_explicit_func_name_selects_target(svc: FastBlockService) -> None:
    src = (
        "def a(x, state):\n    return x + 1\n"
        "def b(x, state):\n    return x + 2\n"
    )
    law = svc.compile_control_law(src, func_name="b", prefer_numba=False)
    assert law.func_name == "b"
    assert law(10.0, law.make_state()) == 12.0


def test_uses_numpy_and_math_in_body(svc: FastBlockService) -> None:
    src = (
        "def control(x, state):\n"
        "    return math.sqrt(abs(x)) + np.float64(1.0)\n"
    )
    law = svc.compile_control_law(src, prefer_numba=False)
    assert law(9.0, law.make_state()) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Error paths — must raise FastBlockCompileError with a clear message.
# ---------------------------------------------------------------------------
def test_empty_source_raises(svc: FastBlockService) -> None:
    with pytest.raises(FastBlockCompileError, match="empty"):
        svc.compile_control_law("   ", prefer_numba=False)


def test_syntax_error_raises(svc: FastBlockService) -> None:
    with pytest.raises(FastBlockCompileError, match="[Ss]yntax"):
        svc.compile_control_law("def control(x, state)\n return x", prefer_numba=False)


def test_missing_state_param_raises(svc: FastBlockService) -> None:
    with pytest.raises(FastBlockCompileError, match="state"):
        svc.compile_control_law("def control(x):\n    return x\n", prefer_numba=False)


def test_no_function_defined_raises(svc: FastBlockService) -> None:
    with pytest.raises(FastBlockCompileError, match="no function"):
        svc.compile_control_law("y = 5\n", prefer_numba=False)


def test_ambiguous_functions_raise(svc: FastBlockService) -> None:
    src = (
        "def alpha(x, state):\n    return x\n"
        "def beta(x, state):\n    return x\n"
    )
    with pytest.raises(FastBlockCompileError, match="multiple functions"):
        svc.compile_control_law(src, prefer_numba=False)


def test_var_args_rejected(svc: FastBlockService) -> None:
    with pytest.raises(FastBlockCompileError, match="positional"):
        svc.compile_control_law(
            "def control(*args, state):\n    return 0.0\n", prefer_numba=False,
        )


def test_body_error_surfaces_at_compile_time(svc: FastBlockService) -> None:
    """A NameError in the body (typo'd variable) must be caught during
    warm-up, not left to blow up mid-simulation."""
    src = "def control(x, state):\n    return undefined_var + x\n"
    with pytest.raises(FastBlockCompileError, match="warm-up|NameError"):
        svc.compile_control_law(src, prefer_numba=False)


def test_sandbox_blocks_import(svc: FastBlockService) -> None:
    """The restricted builtins must prevent ``import`` / ``open`` in
    the user body (defence-in-depth; the pure-Python path runs the
    body directly)."""
    src = "def control(x, state):\n    return open('/etc/passwd')\n"
    with pytest.raises(FastBlockCompileError):
        svc.compile_control_law(src, prefer_numba=False)


# ---------------------------------------------------------------------------
# Numba path — only when the extra is installed.
# ---------------------------------------------------------------------------
def test_is_numba_available_is_boolean(svc: FastBlockService) -> None:
    assert isinstance(svc.is_numba_available(), bool)
    assert isinstance(is_numba_available(), bool)


@pytest.mark.skipif(not is_numba_available(),
                    reason="numba not installed (pulsim[fast])")
def test_numba_jit_path_compiles_and_matches_python() -> None:
    """When numba is present, the JIT path must produce the same
    numeric result as pure-Python for the same inputs."""
    svc = FastBlockService()
    jit = svc.compile_control_law(_PI_SOURCE, n_states=1, prefer_numba=True)
    py = svc.compile_control_law(_PI_SOURCE, n_states=1, prefer_numba=False)
    assert jit.is_jit is True

    s_jit, s_py = jit.make_state(), py.make_state()
    for _ in range(5):
        o_jit = jit(1.5, 1e-4, 0.8, 25.0, s_jit)
        o_py = py(1.5, 1e-4, 0.8, 25.0, s_py)
        assert o_jit == pytest.approx(o_py, rel=1e-9)


def test_prefer_numba_false_forces_python_even_if_available(svc: FastBlockService) -> None:
    law = svc.compile_control_law(_PI_SOURCE, prefer_numba=False)
    assert law.is_jit is False
