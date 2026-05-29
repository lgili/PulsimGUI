"""Monte-Carlo sweep helpers (wave-4 sub-A 1.3).

Lets the GUI drive multi-parameter Monte-Carlo sweeps with non-uniform
distributions without leaking backend runtime types into the dialog
layer.

Backend note (pulsim 1.6.x): ``pulsim.sweep`` used to be a *package*
exposing ``Distribution`` / ``Cartesian`` / a ``metrics`` submodule. In
1.6.x it became a single grid-sweep **function**
(``pulsim.sweep(builder_factory, *, params={name: [values]}, kpi_fn,
...)``) that takes explicit per-parameter value lists and a KPI
callback. Monte-Carlo *sampling* (drawing paired samples from a
distribution) and *metric* computation are therefore now the GUI's
responsibility — this module owns them with pure-Python objects:

  * :class:`Distribution` — a named continuous distribution carrying a
    closed-form inverse CDF (maps the uniform ``[0, 1]`` quantile to a
    value); ``.sample(n, rng)`` draws paired Monte-Carlo samples.
  * :class:`CartesianSpec` — a discrete list of values.
  * :class:`MetricSpec` — a named KPI with a ``compute(trace)`` callable.

A future runner can feed the sampled value lists straight into
``pulsim.sweep(params=...)`` and compose the ``MetricSpec.compute``
callables into its ``kpi_fn``. None of this needs the (removed) old
``pulsim.sweep`` package API.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence


# ---------------------------------------------------------------------------
# Dialog-layer settings
# ---------------------------------------------------------------------------
@dataclass
class MonteCarloParameter:
    """One sweep row.

    ``distribution`` is the canonical name shown in the UI ("uniform",
    "log_uniform", "normal", "cartesian"). ``params`` carries the
    distribution-specific keys (``low``/``high``, ``mu``/``sigma``,
    ``values``). The combination is canonicalised by
    :func:`build_runtime_parameter` before the runtime call.
    """

    component_id: str
    component_name: str
    parameter_name: str
    distribution: str
    params: dict[str, Any]


@dataclass
class MonteCarloMetric:
    """Metric the runtime should compute per sample.

    ``kind`` is one of ``"steady_state"``, ``"peak"``, ``"rms"``,
    ``"settling_time"``, ``"custom"``. ``channel`` is the signal/probe
    name. ``options`` is a free-form dict forwarded to the metric
    factory (e.g. ``target``/``tolerance`` for ``settling_time``, or the
    ``compute`` callable for ``custom``).
    """

    kind: str
    channel: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonteCarloSweepSettings:
    """All inputs to a Monte-Carlo sweep run."""

    parameters: list[MonteCarloParameter] = field(default_factory=list)
    metrics: list[MonteCarloMetric] = field(default_factory=list)
    n_samples: int = 64
    seed: int | None = None
    n_workers: int = 0  # 0 → serial executor

    def is_runnable(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` so the dialog can disable Run gracefully."""
        if not self.parameters:
            return False, "Add at least one parameter row before running."
        if not self.metrics:
            return False, "Pick at least one metric to compute."
        if self.n_samples < 1:
            return False, "Sample count must be at least 1."
        return True, ""


# ---------------------------------------------------------------------------
# GUI-side parameter specs
#
# A :class:`Distribution` is a name + an ``inverse_cdf`` closure mapping the
# uniform ``[0, 1]`` quantile to the distribution's value (so Monte-Carlo
# sampling is just ``inverse_cdf(uniform_draws)``). ``inverse_cdf`` accepts
# any iterable so the helpers can be unit-tested without NumPy, and returns a
# NumPy array when handed one.
# ---------------------------------------------------------------------------
@dataclass
class Distribution:
    """A named continuous distribution defined by its inverse CDF."""

    name: str
    inverse_cdf: Callable[[Iterable[float]], Any]

    def sample(self, n: int, rng: random.Random | None = None) -> list[float]:
        """Draw ``n`` paired Monte-Carlo samples via inverse-transform."""
        r = rng or random.Random()
        draws = [r.random() for _ in range(max(0, int(n)))]
        out = self.inverse_cdf(draws)
        return [float(v) for v in out]


@dataclass
class CartesianSpec:
    """A discrete list of explicit values (grid / categorical sweep)."""

    values: tuple[float, ...]

    def sample(self, n: int, rng: random.Random | None = None) -> list[float]:
        """Draw ``n`` samples by choosing uniformly among the values."""
        r = rng or random.Random()
        if not self.values:
            return []
        return [float(r.choice(self.values)) for _ in range(max(0, int(n)))]


def _normal_quantile(p: float) -> float:
    """Standard-normal inverse CDF via Beasley–Springer–Moro approximation."""
    # Coefficients for the lower region.
    a = (
        -3.969683028665376e1,
        2.209460984245205e2,
        -2.759285104469687e2,
        1.383577518672690e2,
        -3.066479806614716e1,
        2.506628277459239,
    )
    b = (
        -5.447609879822406e1,
        1.615858368580409e2,
        -1.556989798598866e2,
        6.680131188771972e1,
        -1.328068155288572e1,
    )
    c = (
        -7.784894002430293e-3,
        -3.223964580411365e-1,
        -2.400758277161838,
        -2.549732539343734,
        4.374664141464968,
        2.938163982698783,
    )
    d = (
        7.784695709041462e-3,
        3.224671290700398e-1,
        2.445134137142996,
        3.754408661907416,
    )

    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(
        ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
    ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def _arrayify(values: Iterable[float], func: Callable[[float], float]) -> Any:
    """Apply ``func`` element-wise. Works for NumPy arrays and plain lists."""
    try:
        import numpy as np  # pragma: no cover - optional dep present in pulsim

        if isinstance(values, np.ndarray):
            return np.vectorize(func)(values)
    except ImportError:  # pragma: no cover
        pass
    return [func(v) for v in values]


# ---------------------------------------------------------------------------
# Distribution factories
# ---------------------------------------------------------------------------
def make_uniform_distribution(low: float, high: float) -> Distribution:
    """Build a uniform [low, high] :class:`Distribution`."""
    if high < low:
        raise ValueError("Uniform high must be >= low")
    span = float(high) - float(low)
    return Distribution(
        name=f"uniform({low}, {high})",
        inverse_cdf=lambda u: _arrayify(u, lambda p: float(low) + p * span),
    )


def make_log_uniform_distribution(low: float, high: float) -> Distribution:
    """Build a log-uniform distribution covering [low, high] with low > 0."""
    if low <= 0 or high <= 0:
        raise ValueError("Log-uniform bounds must be strictly positive")
    if high < low:
        raise ValueError("Log-uniform high must be >= low")
    log_low = math.log(low)
    log_high = math.log(high)
    log_span = log_high - log_low
    return Distribution(
        name=f"log_uniform({low}, {high})",
        inverse_cdf=lambda u: _arrayify(u, lambda p: math.exp(log_low + p * log_span)),
    )


def make_normal_distribution(mu: float, sigma: float) -> Distribution:
    """Build a normal(mu, sigma) distribution.

    Uses the Beasley–Springer–Moro quantile so we don't pull SciPy in.
    """
    if sigma <= 0:
        raise ValueError("Normal sigma must be > 0")
    return Distribution(
        name=f"normal({mu}, {sigma})",
        inverse_cdf=lambda u: _arrayify(
            u, lambda p: float(mu) + float(sigma) * _normal_quantile(min(max(p, 1e-9), 1 - 1e-9))
        ),
    )


def make_cartesian(values: Sequence[float]) -> CartesianSpec:
    """Build a Cartesian-product spec from a list of discrete values."""
    if not values:
        raise ValueError("Cartesian spec needs at least one value")
    return CartesianSpec(values=tuple(float(v) for v in values))


def build_runtime_parameter(row: MonteCarloParameter) -> Distribution | CartesianSpec:
    """Translate a :class:`MonteCarloParameter` into a sampling spec.

    Raises ``ValueError`` if the distribution name is unknown or the
    row's ``params`` are missing required keys.
    """
    kind = row.distribution.strip().lower()
    params = row.params or {}
    if kind == "uniform":
        low = float(params["low"])
        high = float(params["high"])
        return make_uniform_distribution(low, high)
    if kind in ("log_uniform", "log-uniform"):
        low = float(params["low"])
        high = float(params["high"])
        return make_log_uniform_distribution(low, high)
    if kind == "normal":
        mu = float(params["mu"])
        sigma = float(params["sigma"])
        return make_normal_distribution(mu, sigma)
    if kind == "cartesian":
        values = params.get("values") or []
        return make_cartesian([float(v) for v in values])
    raise ValueError(f"Unknown distribution kind: {row.distribution!r}")


# ---------------------------------------------------------------------------
# Metric specs
#
# A :class:`MetricSpec` carries a ``compute(trace)`` callable that reduces a
# channel's 1-D sample trace to a single scalar KPI. A future sweep runner
# extracts each metric's channel trace from a result and calls ``compute``;
# the specs are deliberately backend-agnostic (no pulsim import).
# ---------------------------------------------------------------------------
@dataclass
class MetricSpec:
    """A named KPI plus the reduction that computes it from a trace."""

    name: str
    kind: str
    channel: str
    # Reduces a channel trace (or, for a user ``custom`` metric, whatever the
    # caller passes) to a scalar KPI. Loosely typed to accept user callables.
    compute: Callable[..., Any]
    options: dict[str, Any] = field(default_factory=dict)


def _rms(trace: Sequence[float]) -> float:
    vals = [float(v) for v in trace]
    if not vals:
        return 0.0
    return math.sqrt(sum(v * v for v in vals) / len(vals))


def _peak(trace: Sequence[float]) -> float:
    vals = [abs(float(v)) for v in trace]
    return max(vals) if vals else 0.0


def _steady_state(trace: Sequence[float]) -> float:
    vals = [float(v) for v in trace]
    if not vals:
        return 0.0
    tail = max(1, len(vals) // 10)  # mean of the last ~10% of the trace
    return sum(vals[-tail:]) / tail


def _make_settling_time(target: float, tolerance: float) -> Callable[[Sequence[float]], float]:
    band = abs(tolerance)

    def _settling(trace: Sequence[float]) -> float:
        vals = [float(v) for v in trace]
        n = len(vals)
        if n == 0:
            return 0.0
        # Last index where the trace leaves the [target ± band] band; the
        # settling "time" is reported as the normalised fraction of the
        # trace after which it stays settled (a runner can scale by dt).
        last_out = -1
        for i, v in enumerate(vals):
            if abs(v - target) > band:
                last_out = i
        return (last_out + 1) / n

    return _settling


def build_runtime_metric(metric: MonteCarloMetric) -> MetricSpec:
    """Translate :class:`MonteCarloMetric` into a :class:`MetricSpec`.

    Raises ``ValueError`` on a missing channel, an unknown kind, or a
    ``custom`` metric without a ``compute`` callable.
    """
    kind = metric.kind.strip().lower()
    channel = metric.channel
    if not channel:
        raise ValueError("Metric channel is required")

    options = dict(metric.options or {})
    if kind == "steady_state":
        compute: Callable[[Sequence[float]], float] = _steady_state
    elif kind == "peak":
        compute = _peak
    elif kind == "rms":
        compute = _rms
    elif kind == "settling_time":
        target = float(options.get("target", 0.0))
        tolerance = float(options.get("tolerance", 0.05))
        compute = _make_settling_time(target, tolerance)
    elif kind == "custom":
        # ``options['compute']`` must be a callable taking the channel
        # trace and returning a float.
        custom = options.get("compute")
        if not callable(custom):
            raise ValueError("Custom metric requires a 'compute' callable in options")
        name = options.get("name") or f"custom({channel})"
        return MetricSpec(name=name, kind=kind, channel=channel, compute=custom, options=options)
    else:
        raise ValueError(f"Unknown metric kind: {metric.kind!r}")

    return MetricSpec(
        name=f"{kind}({channel})",
        kind=kind,
        channel=channel,
        compute=compute,
        options=options,
    )


# ---------------------------------------------------------------------------
# GUI-side result mirror
# ---------------------------------------------------------------------------
@dataclass
class MonteCarloSweepResult:
    """Aggregated Monte-Carlo result (GUI-side mirror of the runtime's)."""

    n_samples: int
    strategy: str
    seed: int | None
    wall_seconds: float
    failed: int = 0
    # parameter_name -> list of sampled values
    parameter_samples: dict[str, list[float]] = field(default_factory=dict)
    # metric_name -> list of computed values
    metric_samples: dict[str, list[float]] = field(default_factory=dict)

    def per_sample(self) -> list[dict[str, float]]:
        """Pivot into a list of {param_name|metric_name: value} dicts.

        Convenient for CSV export and histogram/scatter plotting.
        """
        n = self.n_samples
        rows: list[dict[str, float]] = []
        for i in range(n):
            row: dict[str, float] = {}
            for k, values in self.parameter_samples.items():
                if i < len(values):
                    row[k] = values[i]
            for k, values in self.metric_samples.items():
                if i < len(values):
                    row[k] = values[i]
            rows.append(row)
        return rows


def adapt_runtime_result(runtime_result: Any) -> MonteCarloSweepResult:
    """Build a GUI-side :class:`MonteCarloSweepResult` from the runtime's."""

    def _as_floats(values: Any) -> list[float]:
        try:
            return [float(v) for v in values]
        except TypeError:  # pragma: no cover - dict-of-arrays edge
            return [float(values)]

    params_dict = getattr(runtime_result, "parameters", {}) or {}
    metrics_dict = getattr(runtime_result, "metrics", {}) or {}

    return MonteCarloSweepResult(
        n_samples=int(getattr(runtime_result, "n_samples", 0) or 0),
        strategy=str(getattr(runtime_result, "strategy", "")),
        seed=getattr(runtime_result, "seed", None),
        wall_seconds=float(getattr(runtime_result, "wall_seconds", 0.0) or 0.0),
        failed=int(getattr(runtime_result, "failed", 0) or 0),
        parameter_samples={k: _as_floats(v) for k, v in params_dict.items()},
        metric_samples={k: _as_floats(v) for k, v in metrics_dict.items()},
    )


# ---------------------------------------------------------------------------
# Random fallback (offline tests / placeholder backend / preview)
# ---------------------------------------------------------------------------
def synthesize_uniform_samples(
    settings: MonteCarloSweepSettings,
    *,
    rng_seed: int | None = None,
) -> MonteCarloSweepResult:
    """Generate a deterministic offline result with the requested shape.

    Used by the placeholder backend so the dialog can still preview
    histograms in demo mode. Each parameter is sampled within its
    declared bounds; metrics get a ``sample_index`` filler.
    """
    rng = random.Random(rng_seed if rng_seed is not None else settings.seed or 0)
    n = max(1, int(settings.n_samples))

    param_samples: dict[str, list[float]] = {}
    for row in settings.parameters:
        key = f"{row.component_name}.{row.parameter_name}"
        kind = row.distribution.strip().lower()
        params = row.params
        low = float(params.get("low", 0.0))
        high = float(params.get("high", 1.0))
        mu = float(params.get("mu", 0.0))
        sigma = float(params.get("sigma", 1.0))
        values: list[float]
        if kind == "uniform":
            values = [rng.uniform(low, high) for _ in range(n)]
        elif kind in ("log_uniform", "log-uniform"):
            if low <= 0:
                low = 1e-9
            if high <= 0:
                high = max(low * 10, 1e-9)
            log_low, log_high = math.log(low), math.log(high)
            values = [math.exp(rng.uniform(log_low, log_high)) for _ in range(n)]
        elif kind == "normal":
            values = [rng.gauss(mu, sigma) for _ in range(n)]
        elif kind == "cartesian":
            choices = list(params.get("values") or [0.0])
            values = [float(rng.choice(choices)) for _ in range(n)]
        else:
            values = [0.0 for _ in range(n)]
        param_samples[key] = values

    metric_samples: dict[str, list[float]] = {}
    for metric in settings.metrics:
        key = f"{metric.kind}({metric.channel})"
        metric_samples[key] = [float(i) for i in range(n)]

    return MonteCarloSweepResult(
        n_samples=n,
        strategy="monte_carlo",
        seed=settings.seed,
        wall_seconds=0.0,
        failed=0,
        parameter_samples=param_samples,
        metric_samples=metric_samples,
    )
