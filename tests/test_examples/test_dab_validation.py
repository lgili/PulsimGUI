"""Dual Active Bridge — kernel validation against the phase-shift power law.

P(φ) = V1·V2'·φ(1−φ/π)/(2πfL). Gate-level (8 real switches) is CHEAP here:
single-phase-shift modulation only ever visits ~4 switch masks, the opposite
of the 2^N matrix-converter blow-up.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validate_dab import run  # noqa: E402


def test_dab_power_matches_phase_shift_law() -> None:
    p_sim, p_th = run(phi=math.pi / 4, t_end=2e-3)
    assert p_th > 0
    assert abs(p_sim - p_th) / p_th < 0.05      # within 5 %


def test_dab_power_scales_with_phase() -> None:
    """φ=π/6 transfers less power than φ=π/4 (monotone below π/2)."""
    p_small, th_small = run(phi=math.pi / 6, t_end=2e-3)
    p_large, th_large = run(phi=math.pi / 4, t_end=2e-3)
    assert p_small < p_large
    assert abs(p_small - th_small) / th_small < 0.07
    assert abs(p_large - th_large) / th_large < 0.05
