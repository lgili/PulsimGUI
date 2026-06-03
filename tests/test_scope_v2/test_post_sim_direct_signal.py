"""Post-sim-only channels (direct-signal motor scopes) must render.

Regression: a scope channel that names a result signal directly (no wire,
no live-stream spec) created no curve up front, so ``replace_signal`` —
which only *updated* existing curves — silently rendered nothing. The
canvas now creates the curve on demand, and ``PostSimCapability`` adds the
legend row, so ``M1.speed_rpm`` / ``M1.i_a`` … actually show up.
"""
from __future__ import annotations

import numpy as np

from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope_v2 import BaseScopeWindow, PostSimCapability
from pulsimgui.views.scope_v2.capabilities.post_sim import PostSimSignalSpec
from pulsimgui.views.scope_v2.variants import ElectricalScopeVariant


def _window() -> BaseScopeWindow:
    return BaseScopeWindow(variant=ElectricalScopeVariant(name="Scope: test"))


def test_replace_signal_creates_missing_curve(qapp) -> None:
    win = _window()
    assert not win.plot_canvas.has_signal("foo")
    win.plot_canvas.replace_signal("foo", np.array([0.0, 1.0]), np.array([2.0, 3.0]))
    assert win.plot_canvas.has_signal("foo")


def test_post_only_channel_renders(qapp) -> None:
    win = _window()
    specs = [PostSimSignalSpec(name="i_a", signal_key="M1.i_a")]
    cap = PostSimCapability(None, specs, result_signal=None, result_getter=lambda: None)
    cap.attach(win)
    # Nothing registered the curve up front (no live spec).
    assert not win.plot_canvas.has_signal("i_a")

    t = np.linspace(0.0, 1.0, 50)
    result = SimulationResult(time=t.tolist(), signals={"M1.i_a": np.sin(t).tolist()})
    cap._on_finished(result)

    # Curve created on demand and populated with the result data.
    assert win.plot_canvas.has_signal("i_a")


def test_post_only_missing_signal_stays_empty(qapp) -> None:
    win = _window()
    specs = [PostSimSignalSpec(name="i_a", signal_key="M1.i_a")]
    cap = PostSimCapability(None, specs, result_signal=None, result_getter=lambda: None)
    cap.attach(win)
    # Result without the requested key → no curve fabricated.
    result = SimulationResult(time=[0.0, 1.0], signals={"V(N1)": [1.0, 1.0]})
    cap._on_finished(result)
    assert not win.plot_canvas.has_signal("i_a")
