"""Tests for the Monte-Carlo sweep helpers (wave-4 sub-A 1.3)."""

from __future__ import annotations

import math

import pytest

from pulsimgui.services.monte_carlo_sweep import (
    MonteCarloMetric,
    MonteCarloParameter,
    MonteCarloSweepResult,
    MonteCarloSweepSettings,
    adapt_runtime_result,
    build_runtime_metric,
    build_runtime_parameter,
    make_log_uniform_distribution,
    make_normal_distribution,
    make_uniform_distribution,
    synthesize_uniform_samples,
)


# ---------------------------------------------------------------------------
# Distribution factories
# ---------------------------------------------------------------------------
def test_uniform_distribution_maps_zero_one_to_bounds():
    dist = make_uniform_distribution(0.0, 10.0)
    out = dist.inverse_cdf([0.0, 0.5, 1.0])
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(5.0)
    assert out[2] == pytest.approx(10.0)


def test_uniform_distribution_rejects_inverted_bounds():
    with pytest.raises(ValueError):
        make_uniform_distribution(5.0, 1.0)


def test_log_uniform_distribution_geometric_midpoint():
    dist = make_log_uniform_distribution(1.0, 100.0)
    out = dist.inverse_cdf([0.5])
    assert out[0] == pytest.approx(10.0)


def test_log_uniform_rejects_non_positive_bounds():
    with pytest.raises(ValueError):
        make_log_uniform_distribution(0.0, 1.0)
    with pytest.raises(ValueError):
        make_log_uniform_distribution(-1.0, 1.0)


def test_normal_distribution_centred_on_mu_at_50pc():
    dist = make_normal_distribution(2.0, 0.5)
    out = dist.inverse_cdf([0.5])
    assert out[0] == pytest.approx(2.0, abs=1e-3)


def test_normal_distribution_one_sigma_quantile_close_to_known_value():
    dist = make_normal_distribution(0.0, 1.0)
    out = dist.inverse_cdf([0.8413447])  # ≈ 1σ
    assert out[0] == pytest.approx(1.0, abs=5e-3)


def test_normal_rejects_zero_sigma():
    with pytest.raises(ValueError):
        make_normal_distribution(0.0, 0.0)


# ---------------------------------------------------------------------------
# build_runtime_parameter dispatch
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kind,params,probe,expected",
    [
        ("uniform", {"low": 0, "high": 4}, 0.25, 1.0),
        ("log_uniform", {"low": 1, "high": 1000}, 0.5, 10.0 ** 1.5),
        ("normal", {"mu": 5, "sigma": 1}, 0.5, 5.0),
    ],
)
def test_build_runtime_parameter_dispatch(kind, params, probe, expected):
    row = MonteCarloParameter("c1", "C1", "value", kind, params)
    dist = build_runtime_parameter(row)
    out = dist.inverse_cdf([probe])
    assert out[0] == pytest.approx(expected, rel=1e-2, abs=1e-3)


def test_build_runtime_parameter_unknown_distribution():
    row = MonteCarloParameter("c1", "C1", "v", "weibull", {})
    with pytest.raises(ValueError):
        build_runtime_parameter(row)


def test_build_runtime_parameter_cartesian():
    row = MonteCarloParameter(
        "c1", "C1", "value", "cartesian", {"values": [1, 2, 3]}
    )
    spec = build_runtime_parameter(row)
    assert tuple(spec.values) == (1.0, 2.0, 3.0)


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------
def test_settings_runnable_requires_parameters_and_metrics():
    s = MonteCarloSweepSettings()
    ok, reason = s.is_runnable()
    assert ok is False and "parameter" in reason.lower()

    s.parameters = [MonteCarloParameter("c1", "C1", "v", "uniform", {"low": 0, "high": 1})]
    ok, reason = s.is_runnable()
    assert ok is False and "metric" in reason.lower()

    s.metrics = [MonteCarloMetric("rms", "V(out)")]
    ok, reason = s.is_runnable()
    assert ok is True


def test_settings_rejects_zero_samples():
    s = MonteCarloSweepSettings(
        parameters=[MonteCarloParameter("c1", "C1", "v", "uniform", {"low": 0, "high": 1})],
        metrics=[MonteCarloMetric("rms", "V(out)")],
        n_samples=0,
    )
    ok, reason = s.is_runnable()
    assert ok is False and "sample" in reason.lower()


# ---------------------------------------------------------------------------
# Offline synthesizer (placeholder backend / preview)
# ---------------------------------------------------------------------------
def test_synthesize_uniform_samples_shape_and_repeatability():
    settings = MonteCarloSweepSettings(
        parameters=[
            MonteCarloParameter("r1", "R1", "resistance", "uniform", {"low": 1, "high": 10}),
            MonteCarloParameter("l1", "L1", "inductance", "log_uniform", {"low": 1e-6, "high": 1e-3}),
        ],
        metrics=[MonteCarloMetric("rms", "V(out)")],
        n_samples=12,
        seed=7,
    )
    a = synthesize_uniform_samples(settings)
    b = synthesize_uniform_samples(settings)
    assert a.n_samples == 12
    assert len(a.parameter_samples) == 2
    assert a.parameter_samples == b.parameter_samples


def test_synthesize_uniform_samples_per_sample_pivot():
    settings = MonteCarloSweepSettings(
        parameters=[
            MonteCarloParameter("r1", "R1", "resistance", "uniform", {"low": 0, "high": 1}),
        ],
        metrics=[MonteCarloMetric("rms", "V(out)")],
        n_samples=4,
        seed=1,
    )
    result = synthesize_uniform_samples(settings)
    rows = result.per_sample()
    assert len(rows) == 4
    assert "R1.resistance" in rows[0]
    assert "rms(V(out))" in rows[0]


# ---------------------------------------------------------------------------
# Result adapter
# ---------------------------------------------------------------------------
def test_adapt_runtime_result_translates_minimal_fields():
    class _Fake:
        parameters = {"r1": [1.0, 2.0]}
        metrics = {"rms": [0.1, 0.2]}
        failed = 0
        strategy = "monte_carlo"
        n_samples = 2
        seed = 99
        wall_seconds = 0.05

    out = adapt_runtime_result(_Fake())
    assert out.n_samples == 2
    assert out.strategy == "monte_carlo"
    assert out.seed == 99
    assert out.parameter_samples == {"r1": [1.0, 2.0]}
    assert out.metric_samples == {"rms": [0.1, 0.2]}


# ---------------------------------------------------------------------------
# Runtime metric builder
# ---------------------------------------------------------------------------
def test_build_runtime_metric_dispatch():
    rms = build_runtime_metric(MonteCarloMetric("rms", "V(out)"))
    peak = build_runtime_metric(MonteCarloMetric("peak", "I(R1)"))
    ss = build_runtime_metric(MonteCarloMetric("steady_state", "V(out)"))
    # settling_time requires extra kwargs (target, tolerance).
    settling = build_runtime_metric(
        MonteCarloMetric(
            "settling_time",
            "V(out)",
            options={"target": 1.0, "tolerance": 0.05},
        )
    )
    # We don't assert internal shape — just that each branch produces a
    # truthy object and doesn't raise.
    assert rms and peak and ss and settling


def test_build_runtime_metric_requires_channel():
    with pytest.raises(ValueError):
        build_runtime_metric(MonteCarloMetric("rms", ""))


def test_build_runtime_metric_custom_requires_callable():
    with pytest.raises(ValueError):
        build_runtime_metric(MonteCarloMetric("custom", "V(out)", options={}))


def test_build_runtime_metric_rejects_unknown_kind():
    with pytest.raises(ValueError):
        build_runtime_metric(MonteCarloMetric("variance", "V(out)"))
