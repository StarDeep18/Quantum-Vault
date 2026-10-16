"""JobManager — runs provider job lifecycles in worker threads.

Design (architecture.md §6, §8):
  * POST /jobs returns immediately with an internal id; a worker thread
    submits + polls the provider and records every real state change.
  * Polling: fast at first, exponential backoff while queued, bounded,
    stops immediately on terminal states. Polling never creates new
    provider jobs.
  * Local timeout marks the experiment TIMED_OUT but keeps the provider
    job id; a later status refresh (GET, possibly after a server
    restart) re-attaches to the same provider job and can still
    complete the experiment.
  * Every recorded state is either a locally-true pipeline state or a
    normalized provider state — nothing is fabricated.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from ..config import Limits, redact
from ..models import Experiment, JobState, Mode, TERMINAL_STATES
from ..providers import QuantumProvider
from ..providers.base import ProviderError, ProviderRateLimited
from .experiment_service import ExperimentStore

logger = logging.getLogger("qlab.jobs")


class JobManager:
    def __init__(self, store: ExperimentStore, limits: Limits) -> None:
        self._store = store
        self._limits = limits
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ lifecycle

    def start(self, experiment: Experiment, provider: QuantumProvider, shots: int,
              backend: Optional[str] = None, seed: Optional[str] = None) -> None:
        thread = threading.Thread(
            target=self._run,
            args=(experiment.id, provider, shots, backend, seed),
            name=f"qrng-{experiment.id}",
            daemon=True,
        )
        with self._lock:
            self._threads[experiment.id] = thread
        thread.start()

    def is_alive(self, experiment_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(experiment_id)
        return bool(thread and thread.is_alive())

    # ------------------------------------------------------------ worker

    def _run(self, experiment_id: str, provider: QuantumProvider, shots: int,
             backend: Optional[str], seed: Optional[str]) -> None:
        try:
            self._execute(experiment_id, provider, shots, backend, seed)
        except ProviderRateLimited as exc:
            self._store.mutate(
                experiment_id,
                lambda e: self._rate_limited(e, exc),
            )
        except ProviderError as exc:
            self._store.mutate(
                experiment_id,
                lambda e: e.fail(exc.code, redact(exc.message), exc.hint),
            )
        except Exception as exc:  # last-resort guard — never crash silently
            logger.exception("job worker crashed for %s", experiment_id)
            self._store.mutate(
                experiment_id,
                lambda e: e.fail(
                    "INTERNAL_ERROR",
                    redact(f"Internal error while running the experiment: {exc}"),
                    "Check the server logs. No bits were generated.",
                ),
            )

    @staticmethod
    def _rate_limited(e: Experiment, exc: "ProviderRateLimited") -> None:
        e.error_code = exc.code
        e.error_message = exc.message
        e.error_hint = exc.hint
        e.transition(JobState.RATE_LIMITED, exc.message)

    def _execute(self, experiment_id: str, provider: QuantumProvider, shots: int,
                 backend: Optional[str], seed: Optional[str]) -> None:
        store = self._store

        # 1) local validation of circuit + configuration
        circuit = provider.create_qrng_circuit()
        provider.validate_circuit(circuit)
        if not provider.configured():
            from ..providers.base import ProviderNotConfigured

            raise ProviderNotConfigured(
                f"{provider.label} is not configured on this server.",
                "Add credentials to app/backend/.env — see the configuration panel.",
            )
        store.mutate(
            experiment_id,
            lambda e: e.transition(JobState.VALIDATING, "fixed QRNG circuit validated locally"),
        )

        # 2) submit to the provider (blocking network call)
        store.mutate(
            experiment_id,
            lambda e: e.transition(JobState.SUBMITTING, f"submitting to {provider.label}"),
        )
        submission = provider.submit_job(circuit, shots=shots, backend=backend, seed=seed)

        def _accepted(e: Experiment) -> None:
            e.provider_job_id = submission.provider_job_id
            e.backend = submission.backend
            if submission.transpiled_ops:
                e.transpiled_ops = submission.transpiled_ops
            e.transition(JobState.SUBMITTED, f"accepted by {provider.label} as job {submission.provider_job_id}")

        store.mutate(experiment_id, _accepted)

        # 3) poll with backoff until terminal or timeout
        deadline = time.monotonic() + self._limits.job_timeout_s
        interval = self._limits.poll_initial_s
        while True:
            info = provider.get_job_status(submission.provider_job_id)
            # Do not persist COMPLETED before the measurements are actually
            # fetched. If the server restarts in this gap, FETCHING_RESULT is
            # non-terminal and the next status request can reattach by the
            # persisted provider job ID and retrieve the result.
            recorded_state = (
                JobState.FETCHING_RESULT if info.status is JobState.COMPLETED else info.status
            )
            recorded_detail = (
                "provider job completed; retrieving measurement outcomes"
                if info.status is JobState.COMPLETED else info.detail
            )
            store.mutate(
                experiment_id,
                lambda e, state=recorded_state, detail=recorded_detail: (
                    e.transition(state, detail) if e.status is not state
                    else setattr(e, "status_detail", detail)
                ),
            )
            if info.status in TERMINAL_STATES:
                break
            if time.monotonic() >= deadline:
                store.mutate(
                    experiment_id,
                    lambda e: e.transition(
                        JobState.TIMED_OUT,
                        f"local polling timed out after {self._limits.job_timeout_s}s — "
                        f"provider job {submission.provider_job_id} may still complete; "
                        "its job id is retained and the status can be refreshed",
                    ),
                )
                return
            time.sleep(interval)
            interval = min(interval * 1.4, self._limits.poll_max_s)

        # 4) terminal state
        final = self._store.get(experiment_id)
        if final is None or final.status is not JobState.FETCHING_RESULT:
            return                                    # FAILED / CANCELLED already recorded

        result = provider.get_job_result(submission.provider_job_id, shots)

        def _complete(e: Experiment) -> None:
            e.bits = result.bits
            e.compute_counts()
            # Prefer the backend accepted at submission over a provider fallback.
            e.backend = e.backend or result.backend
            metadata = dict(result.metadata or {})
            metadata.pop("transpiled_ops", None)       # already on the record
            e.provider_metadata = metadata
            e.transition(
                JobState.COMPLETED,
                f"{len(result.bits)} measurement outcomes received from {e.backend}",
            )

        completed = store.mutate(experiment_id, _complete)
        logger.info(
            "experiment %s completed on %s (%s shots, job %s)",
            experiment_id, completed.backend if completed else result.backend,
            shots, submission.provider_job_id,
        )

    # ------------------------------------------------------------ refresh

    def refresh(self, experiment_id: str, provider: QuantumProvider) -> bool:
        """Re-attach to a provider job for an experiment whose worker is no
        longer running (server restart, timeout, crash). TIMED_OUT jobs are
        included so late provider completions can still be recovered.
        Returns True when the experiment state changed."""
        experiment = self._store.get(experiment_id)
        if experiment is None:
            return False
        recoverable_completed_result = (
            experiment.status is JobState.COMPLETED
            and experiment.mode is Mode.HARDWARE
            and not experiment.bits
            and bool(experiment.provider_job_id)
        )
        if (
            experiment.status in TERMINAL_STATES
            and experiment.status is not JobState.TIMED_OUT
            and not recoverable_completed_result
        ):
            return False
        if not experiment.provider_job_id or self.is_alive(experiment_id):
            return False
        try:
            info = provider.get_job_status(experiment.provider_job_id)
        except ProviderError as exc:
            logger.warning("refresh failed for %s: %s", experiment_id, redact(exc.message))
            return False
        except Exception as exc:
            logger.warning("refresh failed for %s: %s", experiment_id, redact(str(exc)))
            return False

        if info.status in TERMINAL_STATES and info.status is JobState.COMPLETED:
            try:
                result = provider.get_job_result(
                    experiment.provider_job_id, experiment.requested_shots or 0
                )

                def _complete(e: Experiment) -> None:
                    e.bits = result.bits
                    e.compute_counts()
                    # Keep the persisted submission backend when reattaching after restart.
                    e.backend = e.backend or result.backend
                    metadata = dict(result.metadata or {})
                    metadata.pop("transpiled_ops", None)
                    e.provider_metadata = metadata
                    e.transition(JobState.COMPLETED, "result recovered by status refresh")

                self._store.mutate(experiment_id, _complete)
                return True
            except ProviderError as exc:
                if recoverable_completed_result:
                    # Keep the provider's COMPLETED state, but fail closed at
                    # the result endpoint if IQM no longer serves the shots.
                    # A transient retrieval failure must not turn an actually
                    # completed hardware job into a fabricated result.
                    logger.warning(
                        "measurement recovery failed for completed job %s: %s",
                        experiment_id, redact(exc.message),
                    )
                    return False
                self._store.mutate(
                    experiment_id,
                    lambda e: e.transition(JobState.FAILED, redact(exc.message)),
                )
                return True
            except Exception as exc:
                if recoverable_completed_result:
                    logger.warning(
                        "measurement recovery failed for completed job %s: %s",
                        experiment_id, redact(str(exc)),
                    )
                    return False
                self._store.mutate(
                    experiment_id,
                    lambda e: e.fail(
                        "RESULT_RECOVERY_FAILED",
                        redact(f"Unable to recover the provider result: {exc}"),
                        "No measurement result was returned; no quantum key was created.",
                    ),
                )
                return True

        def _note(e: Experiment) -> None:
            if e.status is not info.status:
                e.transition(info.status, info.detail or "state recovered by status refresh")
            else:
                e.status_detail = info.detail or e.status_detail

        self._store.mutate(experiment_id, _note)
        return True


# identity lookup used by the polling loop's change check
TERMINAL_LOOKUP: dict[JobState, JobState] = {state: state for state in JobState}
