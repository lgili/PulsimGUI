"""Tests for asynchronous post-processing service."""

from __future__ import annotations

from pulsimgui.services.backend_types import (
    PostProcessingJobResult,
    PostProcessingResult,
    TransientResult,
)
from pulsimgui.services.post_processing_service import PostProcessingService


class _NoPostProcessingBackend:
    """Backend test double without post-processing capability."""

    def has_capability(self, name: str) -> bool:
        return False


class _SuccessPostProcessingBackend:
    """Backend test double returning a successful post-processing payload."""

    def has_capability(self, name: str) -> bool:
        return name == "post_processing"

    def run_post_processing(self, transient_result: TransientResult, jobs: list[dict]) -> PostProcessingResult:
        assert transient_result.is_valid
        assert jobs
        return PostProcessingResult(
            success=True,
            jobs=[
                PostProcessingJobResult(
                    job_id="job1",
                    kind="time_domain",
                    success=True,
                )
            ],
        )


def _valid_transient() -> TransientResult:
    return TransientResult(
        time=[0.0, 1e-6, 2e-6],
        signals={"V(out)": [0.0, 1.0, 0.5]},
    )


def test_service_emits_failed_when_capability_missing(qtbot) -> None:
    """Service should fail fast when backend lacks post-processing feature."""
    service = PostProcessingService(_NoPostProcessingBackend())
    failures: list[str] = []
    service.analysis_failed.connect(failures.append)

    service.run_jobs(_valid_transient(), [{"kind": "time_domain", "signals": ["V(out)"]}])

    qtbot.waitUntil(lambda: len(failures) == 1, timeout=1000)
    assert "not available" in failures[0].lower()


def test_service_emits_completed_for_successful_job(qtbot) -> None:
    """Service should emit completion with mapped PostProcessingResult."""
    service = PostProcessingService(_SuccessPostProcessingBackend())
    completions: list[PostProcessingResult] = []
    failures: list[str] = []
    service.analysis_completed.connect(completions.append)
    service.analysis_failed.connect(failures.append)

    service.run_jobs(_valid_transient(), [{"kind": "time_domain", "signals": ["V(out)"]}])

    qtbot.waitUntil(lambda: len(completions) == 1, timeout=2000)
    assert not failures
    assert completions[0].success
    assert completions[0].jobs[0].job_id == "job1"
