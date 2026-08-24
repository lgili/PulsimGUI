"""The dt-aliasing guard's frequency harvest reads real projects.

Two attribute bugs made ``_project_switching_frequencies`` return []
on every real project (so the Solver page's aliasing banner never
fired): it read ``project.circuit`` (Projects store ``circuits`` +
``get_active_circuit()``) and ``comp.component_type`` (the model
attribute is ``type``). Pinned against shipped ex20, whose PWM_BOOST
generator switches at 65 kHz.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pulsimgui.models.project import Project
from pulsimgui.views.main_window import MainWindow

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_harvest_finds_ex20_pwm_frequency(qapp):
    proj = Project.load(_EXAMPLES / "20_pfc_drive_compressor.pulsim")
    fake = SimpleNamespace(_project=proj)
    freqs = MainWindow._project_switching_frequencies(fake)
    assert 65000.0 in freqs


def test_harvest_tolerates_empty_project(qapp):
    fake = SimpleNamespace(_project=SimpleNamespace())
    assert MainWindow._project_switching_frequencies(fake) == []
