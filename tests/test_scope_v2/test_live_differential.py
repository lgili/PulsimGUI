"""Live streaming must plot a differential VOLTAGE_PROBE as V(+) − V(−).

The kernel ring buffer pushes the full node-voltage state vector, but it
permutes nodes internally — a node's column is only knowable from the
stream's own ``state_index_for(name)``. ``LiveStreamCapability`` resolves
each spec's "+"/"−" node names to columns at stream-ready time and, for a
differential probe, subtracts the "−" column on every tick.

Mirror of the post-sim fix in ``MainWindow._result_with_probe_signals`` so
the live trace and the finalised trace agree.
"""
from __future__ import annotations

import numpy as np

from pulsimgui.views.scope_v2.capabilities.live_stream import (
    LiveSignalSpec,
    LiveStreamCapability,
)


class _FakeStream:
    """Minimal NativeLiveStream stand-in: name→column + one sample chunk."""

    def __init__(self, names: list[str], x: np.ndarray, *, with_index: bool = True):
        self._names = names
        self._x = x
        self._read = False
        if not with_index:
            # Emulate an older backend that lacks the lookup: shadow the
            # method with a non-callable so getattr(...)/callable(...) skips it.
            self.state_index_for = None  # type: ignore[assignment]

    def state_index_for(self, name: str):
        return self._names.index(name) if name in self._names else None

    def get_new_samples(self):
        if self._read:
            return np.empty(0), np.empty((0, self._x.shape[1]))
        self._read = True
        return np.arange(self._x.shape[0], dtype=float), self._x


class _FakeCanvas:
    def __init__(self):
        self.appended: list[tuple[str, np.ndarray, np.ndarray]] = []

    def append_signal(self, name, t, y):
        self.appended.append((name, np.asarray(t), np.asarray(y)))

    def add_signal(self, *a, **k):
        pass

    def set_empty_message(self, *a, **k):
        pass


class _FakeShell:
    def __init__(self):
        self.plot_canvas = _FakeCanvas()

    def set_drawer_status(self, *a, **k):
        pass


def _drive(spec: LiveSignalSpec, stream: _FakeStream) -> np.ndarray:
    """Run one resolve+tick cycle and return the y-chunk plotted for ``spec``."""
    cap = LiveStreamCapability(simulation_service=object(), signal_specs=[spec])
    shell = _FakeShell()
    cap._shell = shell  # bypass attach() (no Qt / no service signals needed)
    cap._stream = stream
    cap._active = True
    cap._resolved_cols = [cap._resolve_columns(stream, spec)]
    cap._tick()
    assert shell.plot_canvas.appended, "nothing was plotted"
    return shell.plot_canvas.appended[-1][2]


def test_live_differential_subtracts_minus_terminal() -> None:
    # col 0 = V(+), col 1 = V(-); both real (non-ground) nodes.
    x = np.array([[10.0, 3.0], [12.0, -4.0], [0.0, -5.0]])
    stream = _FakeStream(["V(VBUS_POS)", "V(VBUS_NEG)"], x)
    spec = LiveSignalSpec(
        name="V_bus",
        state_idx=0,
        pos_keys=("V(VBUS_POS)",),
        neg_keys=("V(VBUS_NEG)",),
    )
    y = _drive(spec, stream)
    # V(+) - V(-): 10-3, 12-(-4), 0-(-5)
    assert np.allclose(y, [7.0, 16.0, 5.0])


def test_live_single_ended_without_neg_keys() -> None:
    x = np.array([[10.0, 3.0], [12.0, -4.0]])
    stream = _FakeStream(["V(VOUT)", "V(other)"], x)
    spec = LiveSignalSpec(name="Vout", state_idx=99, pos_keys=("V(VOUT)",), neg_keys=())
    y = _drive(spec, stream)
    assert np.allclose(y, [10.0, 12.0])  # plain V(+), no subtraction


def test_live_ground_referenced_neg_unresolved_stays_single_ended() -> None:
    # The "-" key names a node the stream doesn't expose (ground) → single-ended.
    x = np.array([[7.5, 1.0], [8.0, 1.0]])
    stream = _FakeStream(["V(P)", "V(Q)"], x)
    spec = LiveSignalSpec(name="Vg", state_idx=0, pos_keys=("V(P)",), neg_keys=("V(0)",))
    y = _drive(spec, stream)
    assert np.allclose(y, [7.5, 8.0])


def test_live_falls_back_to_state_idx_without_stream_index() -> None:
    # Older backend with no state_index_for → use the pre-resolved channel idx.
    x = np.array([[10.0, 3.0], [12.0, -4.0]])
    stream = _FakeStream(["V(P)"], x, with_index=False)
    spec = LiveSignalSpec(name="x", state_idx=1, pos_keys=("V(P)",), neg_keys=())
    y = _drive(spec, stream)
    assert np.allclose(y, [3.0, -4.0])  # column 1 (state_idx fallback)
