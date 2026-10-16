"""QRNG service — orchestration for the quantum pipeline (Slice 2/3).

Enforces, in one place:
  * shot-count bounds (validation with actionable messages)
  * simulator-only seeding (hardware outcomes cannot be seeded)
  * hardware requires a configured provider — never a silent fallback
  * a global hardware submission cooldown under provider rate limits
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from ..circuits import circuit_spec
from ..config import Limits
from ..models import Experiment, JobState, Mode, SOURCE_FOR_MODE
from ..providers import QuantumProvider, provider_for_mode
from ..providers.base import ProviderError, ProviderNotConfigured
from .experiment_service import ExperimentStore
from .job_manager import JobManager


class SubmissionCooldownError(ProviderError):
    def __init__(self, retry_after: float):
        super().__init__(
            "SUBMIT_COOLDOWN",
            f"Hardware submission cooldown active — wait {retry_after:.0f}s between QPU submissions.",
            "Quantum providers limit job submissions per minute; the lab enforces a "
            "local cooldown so you never hit it accidentally.",
        )
        self.retry_after = retry_after


class QrngService:
    def __init__(self, store: ExperimentStore, job_manager: JobManager,
                 providers: dict[str, QuantumProvider], limits: Limits) -> None:
        self._store = store
        self._jobs = job_manager
        self._providers = providers
        self._limits = limits
        self._cooldown_lock = threading.Lock()
        self._last_hw_submit = 0.0

    # ------------------------------------------------------------ validation

    def validate_request(self, shots: int, mode: Mode, backend: Optional[str],
                         seed: Optional[str]) -> None:
        if not (self._limits.min_shots <= shots <= self._limits.max_shots):
            raise ProviderError(
                "INVALID_SHOTS",
                f"shots must be between {self._limits.min_shots} and {self._limits.max_shots} "
                f"(requested {shots}).",
                f"Pick a shot count in [{self._limits.min_shots}, {self._limits.max_shots}].",
            )
        if backend is not None:
            backend = backend.strip()
            if backend and backend != "auto" and not all(
                ch.isalnum() or ch in "-_" for ch in backend
            ):
                raise ProviderError(
                    "INVALID_BACKEND",
                    f"backend '{backend}' contains invalid characters.",
                    "Use 'auto' or a real backend name like 'ibm_brisbane'.",
                )
        if seed is not None:
            if mode is not Mode.SIMULATOR:
                raise ProviderError(
                    "INVALID_REQUEST",
                    "A seed can only be used in simulator mode.",
                    "Hardware outcomes come from a real quantum processor — they cannot be "
                    "seeded, which is exactly the point.",
                )
            if len(seed) > self._limits.max_seed_length:
                raise ProviderError("INVALID_SEED", "Simulator seed is too long (max 256 characters).")

    def cooldown_remaining(self) -> float:
        with self._cooldown_lock:
            elapsed = time.monotonic() - self._last_hw_submit
        remaining = self._limits.submit_cooldown_s - elapsed
        return max(0.0, remaining)

    # ------------------------------------------------------------ create job

    def create_job(self, shots: int, mode: Mode, backend: Optional[str] = None,
                   seed: Optional[str] = None) -> Experiment:
        self.validate_request(shots, mode, backend, seed)

        provider = provider_for_mode(self._providers, mode)
        if mode is Mode.HARDWARE:
            if not provider.configured():
                hint = getattr(provider, "SETUP_HINT", None) or (
                    "Add provider credentials to app/backend/.env — see the configuration panel."
                )
                raise ProviderNotConfigured(
                    f"{getattr(provider, 'label', 'The hardware provider')} is not configured on this server.",
                    hint,
                )
            remaining = self.cooldown_remaining()
            if remaining > 0:
                raise SubmissionCooldownError(remaining)

        experiment = self._store.create(
            kind="qrng",
            mode=mode,
            source=SOURCE_FOR_MODE[mode],
            status=JobState.CREATED,
            provider=provider.name,
            requested_shots=shots,
            seed=seed if mode is Mode.SIMULATOR else None,
            circuit=circuit_spec(),
        )
        experiment.transition(JobState.CREATED, "experiment created, waiting for submission")

        if mode is Mode.HARDWARE:
            with self._cooldown_lock:
                self._last_hw_submit = time.monotonic()

        self._jobs.start(experiment, provider, shots=shots,
                         backend=(backend or None) if backend != "auto" else None, seed=seed)
        return experiment

    # ------------------------------------------------------------ queries

    def get(self, experiment_id: str) -> Optional[Experiment]:
        return self._store.get(experiment_id)

    def refresh_stale(self, experiment: Experiment) -> bool:
        """If the worker is gone but the provider job may exist, refresh."""
        if experiment.kind != "qrng" or experiment.mode is None:
            return False
        provider = provider_for_mode(self._providers, experiment.mode)
        if experiment.mode is Mode.HARDWARE and not provider.configured():
            return False
        return self._jobs.refresh(experiment.id, provider)
