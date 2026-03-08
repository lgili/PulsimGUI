"""Post-processing service: run analysis jobs on transient results."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from pulsimgui.services.backend_types import PostProcessingResult, TransientResult

if TYPE_CHECKING:  # pragma: no cover
    from pulsimgui.services.backend_adapter import SimulationBackend

logger = logging.getLogger(__name__)


class _PPWorker(QRunnable):
    """Runnable that executes post-processing in a thread pool."""

    def __init__(
        self,
        backend: SimulationBackend,
        transient_result: TransientResult,
        jobs: list[dict],
        on_done: object,  # callable(PostProcessingResult)
        on_error: object,  # callable(str)
    ) -> None:
        super().__init__()
        self._backend = backend
        self._transient_result = transient_result
        self._jobs = jobs
        self._on_done = on_done
        self._on_error = on_error
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self._backend.run_post_processing(self._transient_result, self._jobs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("PostProcessingWorker error")
            self._on_error(str(exc))
            return
        if result.is_valid:
            self._on_done(result)
        else:
            self._on_error(result.error_message or "Post-processing returned invalid result")


class PostProcessingService(QObject):
    """Service that runs post-processing jobs asynchronously.

    Signals:
        analysis_completed: Emitted with the PostProcessingResult on success.
        analysis_failed: Emitted with an error message string on failure.
        analysis_started: Emitted when a job batch starts.
    """

    analysis_completed = Signal(object)  # PostProcessingResult
    analysis_failed = Signal(str)
    analysis_started = Signal()

    def __init__(self, backend: SimulationBackend, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._backend = backend

    def set_backend(self, backend: SimulationBackend) -> None:
        """Update the backend (called when the active backend changes)."""
        self._backend = backend

    def run_jobs(self, transient_result: TransientResult, jobs: list[dict]) -> None:
        """Submit post-processing jobs for asynchronous execution.

        Args:
            transient_result: The transient result to post-process.
            jobs: List of job spec dicts, each with at minimum a ``kind`` key
                  and optionally ``job_id``, ``signals``, and window parameters.
        """
        if not self._backend.has_capability("post_processing"):
            self.analysis_failed.emit(
                "Post-processing is not available — backend ≥ 0.7.0 required."
            )
            return

        if not transient_result.is_valid:
            self.analysis_failed.emit("No valid transient result to post-process.")
            return

        self.analysis_started.emit()

        worker = _PPWorker(
            backend=self._backend,
            transient_result=transient_result,
            jobs=jobs,
            on_done=self._on_done,
            on_error=self._on_error,
        )
        QThreadPool.globalInstance().start(worker)

    def _on_done(self, result: PostProcessingResult) -> None:
        self.analysis_completed.emit(result)

    def _on_error(self, message: str) -> None:
        self.analysis_failed.emit(message)
