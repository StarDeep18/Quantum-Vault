"""QuantumProvider abstraction (TRD §4, architecture.md §5).

All quantum execution goes through this boundary. The rest of the app
(UI contract, services, storage) only ever sees normalized data:

    create_qrng_circuit()  -> qiskit circuit for the fixed QRNG spec
    validate_circuit()     -> enforce the fixed spec (no arbitrary circuits)
    submit_job()           -> ProviderSubmission {provider_job_id, backend}
    get_job_status()       -> ProviderStatusInfo {normalized status, detail}
    get_job_result()       -> ProviderResult {shot-ordered bits, counts}
    get_backend_metadata() -> real backend list / metadata

Provider-specific response formats never leak past this module.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Optional

from qiskit import QuantumCircuit

from ..models import JobState


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Base error with a machine-readable code and a user-facing hint."""

    def __init__(self, code: str, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


class ProviderNotConfigured(ProviderError):
    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__("PROVIDER_NOT_CONFIGURED", message, hint)


class ProviderRateLimited(ProviderError):
    def __init__(self, message: str, retry_after: float = 60.0, hint: Optional[str] = None):
        super().__init__("RATE_LIMITED", message, hint)
        self.retry_after = retry_after


class ProviderJobFailed(ProviderError):
    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__("PROVIDER_JOB_FAILED", message, hint)


class ProviderResultError(ProviderError):
    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__("PROVIDER_RESULT_ERROR", message, hint)


# ---------------------------------------------------------------------------
# Normalized value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSubmission:
    provider_job_id: str
    backend: str
    submitted_at: str
    transpiled_ops: Optional[list[str]] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderStatusInfo:
    status: JobState
    detail: Optional[str] = None
    queue_position: Optional[int] = None


@dataclass(frozen=True)
class ProviderResult:
    provider_job_id: str
    backend: str
    bits: str                                   # shot-ordered, exactly `shots` chars of 0/1
    counts: dict[str, int]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BackendInfo:
    name: str
    simulator: bool
    operational: bool
    pending_jobs: Optional[int] = None
    qubits: Optional[int] = None
    status_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Status normalization (TRD §8 / architecture.md §7)
# ---------------------------------------------------------------------------

STATUS_MAP = {
    # qiskit-ibm-runtime JobStatus names
    "INITIALIZING": JobState.VALIDATING,
    "VALIDATING": JobState.VALIDATING,
    "QUEUED": JobState.QUEUED,
    "RUNNING": JobState.RUNNING,
    "DONE": JobState.COMPLETED,
    "COMPLETED": JobState.COMPLETED,
    "ERROR": JobState.FAILED,
    "FAILED": JobState.FAILED,
    "CANCELLED": JobState.CANCELLED,
    "CANCELED": JobState.CANCELLED,
    # REST API state strings (defensive)
    "PENDING": JobState.QUEUED,
    "RATE_LIMITED": JobState.RATE_LIMITED,
    "RATELIMITED": JobState.RATE_LIMITED,
    "RUNNING_BLOCKED": JobState.QUEUED,
}


def normalize_status(value: Any) -> Optional[JobState]:
    """Map a provider status (enum member or string) to the normalized
    lifecycle. Returns None when the value is not recognized — callers
    must then keep the last known state instead of guessing."""
    if value is None:
        return None
    name = getattr(value, "name", None)
    text = str(name if name is not None else value).strip().upper()
    text = text.rsplit(".", 1)[-1]              # tolerate "JobStatus.QUEUED"
    return STATUS_MAP.get(text)


# ---------------------------------------------------------------------------
# The adapter interface
# ---------------------------------------------------------------------------


class QuantumProvider(abc.ABC):
    """Contract every quantum provider must implement."""

    name: str = "unknown"
    label: str = "Unknown provider"
    is_simulator: bool = False

    @abc.abstractmethod
    def configured(self) -> bool:
        """True when this provider can submit hardware/simulated jobs right now."""

    @abc.abstractmethod
    def create_qrng_circuit(self) -> QuantumCircuit:
        """Build the fixed QRNG circuit for this provider."""

    @abc.abstractmethod
    def validate_circuit(self, circuit: QuantumCircuit) -> None:
        """Reject anything that is not the approved QRNG circuit."""

    @abc.abstractmethod
    def submit_job(self, circuit: QuantumCircuit, shots: int, backend: Optional[str] = None,
                   seed: Optional[str] = None) -> ProviderSubmission:
        """Submit and return a normalized submission (blocking network call)."""

    @abc.abstractmethod
    def get_job_status(self, provider_job_id: str) -> ProviderStatusInfo:
        """Fetch the current normalized status of a provider job."""

    @abc.abstractmethod
    def get_job_result(self, provider_job_id: str, shots: int) -> ProviderResult:
        """Fetch measurement data and extract shot-ordered bits."""

    @abc.abstractmethod
    def get_backend_metadata(self, name: Optional[str] = None) -> list[BackendInfo]:
        """List selectable backends (real QPUs unless this is a simulator)."""

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "simulator": self.is_simulator,
            "configured": self.configured(),
        }
