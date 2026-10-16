"""Composition root — builds and wires the runtime graph."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .circuits import circuit_spec
from .config import Limits, data_dir, install_logging, load_limits
from .models import JobState
from .providers import QuantumProvider, build_default_providers
from .services.experiment_service import ExperimentStore
from .services.job_manager import JobManager
from .services.qrng_service import QrngService

logger = logging.getLogger("qlab.runtime")


@dataclass
class Runtime:
    store: ExperimentStore
    providers: dict[str, QuantumProvider]
    limits: Limits
    jobs: JobManager
    qrng: QrngService
    circuit: dict = field(default_factory=circuit_spec)

    def log_startup_summary(self) -> None:
        from .models import Mode
        from .providers import provider_for_mode

        hw = provider_for_mode(self.providers, Mode.HARDWARE)
        logger.info(
            "Quantum Randomness Lab backend ready — hardware provider %s (configured=%s), "
            "simulator available, data dir %s",
            hw.name, hw.configured(), self.store._file.parent,
        )


def build_runtime(limits: Optional[Limits] = None,
                  data_path: Optional[Path] = None) -> Runtime:
    limits = limits or load_limits()
    path = data_path or data_dir()
    store = ExperimentStore(path)
    providers = build_default_providers()
    jobs = JobManager(store, limits)
    qrng = QrngService(store, jobs, providers, limits)
    runtime = Runtime(store=store, providers=providers, limits=limits, jobs=jobs, qrng=qrng)
    _reattach_orphans(runtime)
    return runtime


def _reattach_orphans(runtime: Runtime) -> None:
    """After a restart, note provider jobs that may still be recoverable.
    (Lazy: actual refresh happens on the next GET /jobs/{id} — no eager
    provider calls at boot.)"""
    recovered = 0
    for exp in runtime.store.list(limit=1000):
        if exp.kind == "qrng" and exp.provider_job_id and exp.status not in (
            JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED,
        ):
            recovered += 1
    if recovered:
        logger.info("%d in-flight QRNG job(s) reattached from persistence", recovered)
