"""Domain models: the normalized experiment record + job lifecycle.

The lifecycle is the one from TRD §8 / architecture.md §7, extended with
SUBMITTING (a locally-true state while the submission HTTP call is in
flight — matches the TRD §14 frontend state machine). Provider-specific
states are always mapped into these before reaching the UI.
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


class JobState(str, enum.Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FETCHING_RESULT = "FETCHING_RESULT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    RATE_LIMITED = "RATE_LIMITED"


TERMINAL_STATES = frozenset(
    {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.TIMED_OUT,
        JobState.RATE_LIMITED,
    }
)

STATE_EXPLANATIONS: dict[JobState, str] = {
    JobState.CREATED: "Experiment record created — the QRNG circuit has not been submitted yet.",
    JobState.VALIDATING: "Validating the fixed QRNG circuit (|0⟩ → H → measure) and provider configuration locally.",
    JobState.SUBMITTING: "Submitting the job to the quantum provider over the network.",
    JobState.SUBMITTED: "The quantum provider accepted the job.",
    JobState.QUEUED: "The job is queued at the provider, waiting for an available quantum processor.",
    JobState.RUNNING: "The circuit is executing on the quantum processor right now.",
    JobState.FETCHING_RESULT: "The provider job is complete; retrieving the returned measurement outcomes.",
    JobState.COMPLETED: "Measurements returned and bits extracted from the provider result.",
    JobState.FAILED: "The job or the provider interaction failed — see the error details.",
    JobState.CANCELLED: "The job was cancelled before completion.",
    JobState.TIMED_OUT: "Local polling timed out while waiting for the provider. The provider job may still complete — its job ID is retained.",
    JobState.RATE_LIMITED: "Submission rejected by a rate limit (provider or local cooldown). Wait and retry.",
}


class Mode(str, enum.Enum):
    HARDWARE = "hardware"
    SIMULATOR = "simulator"


SOURCE_FOR_MODE = {
    Mode.HARDWARE: "quantum_hardware",
    Mode.SIMULATOR: "quantum_simulator",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Experiment record
# ---------------------------------------------------------------------------


@dataclass
class Experiment:
    """One generation run with full provenance (TRD §12 data model)."""

    # identity
    id: str
    kind: str                                   # "prng" | "qrng"
    mode: Optional[Mode] = None                 # qrng only
    source: str = "classical"                   # classical | quantum_hardware | quantum_simulator

    # lifecycle
    status: JobState = JobState.CREATED
    status_detail: Optional[str] = None
    status_history: list[dict[str, Any]] = field(default_factory=list)

    # provenance
    provider: Optional[str] = None              # e.g. "ibm_quantum", "local_statevector"
    provider_job_id: Optional[str] = None
    backend: Optional[str] = None

    # request parameters
    requested_shots: Optional[int] = None
    requested_bits: Optional[int] = None
    seed: Optional[str] = None                  # prng + optional simulator seed
    algorithm: Optional[str] = None             # prng algorithm name
    seed_derivation: Optional[str] = None

    # result
    bits: Optional[str] = None
    zero_count: Optional[int] = None
    one_count: Optional[int] = None

    # circuit (qrng)
    circuit: Optional[dict[str, Any]] = None
    transpiled_ops: Optional[list[str]] = None

    # provider telemetry (safe, non-secret subset)
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    # error state
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_hint: Optional[str] = None

    # timestamps
    created_at: datetime = field(default_factory=utcnow)
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=utcnow)

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    # -- lifecycle ----------------------------------------------------------

    def transition(self, state: JobState, detail: Optional[str] = None) -> None:
        with self._lock:
            if state is self.status:
                # same state, new detail → update in place, no duplicate history
                if detail is not None:
                    self.status_detail = detail
                    self.updated_at = utcnow()
                return
            self.status = state
            self.status_detail = detail
            self.updated_at = utcnow()
            if state is not JobState.CREATED and self.submitted_at is None and state not in (
                JobState.VALIDATING,
                JobState.SUBMITTING,
            ):
                self.submitted_at = utcnow()
            if state in TERMINAL_STATES and self.completed_at is None:
                self.completed_at = utcnow()
            self.status_history.append(
                {"state": state.value, "at": iso(self.updated_at), "detail": detail}
            )

    def fail(self, code: str, message: str, hint: Optional[str] = None) -> None:
        with self._lock:
            self.error_code = code
            self.error_message = message
            self.error_hint = hint
        self.transition(JobState.FAILED, message)

    # -- statistics ---------------------------------------------------------

    def compute_counts(self) -> None:
        if self.bits is None:
            return
        self.zero_count = self.bits.count("0")
        self.one_count = self.bits.count("1")

    # -- API views ----------------------------------------------------------

    def summary_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.id,
            "kind": self.kind,
            "mode": self.mode.value if self.mode else None,
            "source": self.source,
            "status": self.status.value,
            "provider": self.provider,
            "backend": self.backend,
            "shots": self.requested_shots,
            "bits_requested": self.requested_bits,
            "bit_count": len(self.bits) if self.bits else 0,
            "zero_count": self.zero_count,
            "one_count": self.one_count,
            "error_code": self.error_code,
            "created_at": iso(self.created_at),
        }

    def _stats(self) -> dict[str, Any]:
        total = (self.zero_count or 0) + (self.one_count or 0)
        if not total:
            return {}
        zero_pct = 100.0 * (self.zero_count or 0) / total
        sigma_pct = (0.25 / total) ** 0.5 * 100.0
        observed_one_pct = 100.0 - zero_pct
        z = (observed_one_pct - 50.0) / sigma_pct if sigma_pct else 0.0
        return {
            "zero_count": self.zero_count,
            "one_count": self.one_count,
            "observed_zero_pct": round(zero_pct, 2),
            "observed_one_pct": round(observed_one_pct, 2),
            "theoretical_zero_pct": 50.0,
            "theoretical_one_pct": 50.0,
            "sigma_pct": round(sigma_pct, 2),
            "z_score": round(z, 2),
        }

    def status_dict(self) -> dict[str, Any]:
        error = None
        if self.error_code:
            error = {
                "code": self.error_code,
                "message": self.error_message,
                "hint": self.error_hint,
            }
        return {
            "experiment_id": self.id,
            "kind": self.kind,
            "job_id": self.id,                       # internal job id (TRD contract)
            "status": self.status.value,
            "status_detail": self.status_detail,
            "status_explanation": STATE_EXPLANATIONS.get(self.status),
            "mode": self.mode.value if self.mode else None,
            "source": self.source,
            "provider": self.provider,
            "provider_job_id": self.provider_job_id,
            "backend": self.backend,
            "shots": self.requested_shots,
            "bits_requested": self.requested_bits,
            "completed_shots": None,                 # providers do not report partial shot counts — never fabricated
            "error": error,
            "circuit": self.circuit,
            "created_at": iso(self.created_at),
            "submitted_at": iso(self.submitted_at),
            "updated_at": iso(self.updated_at),
            "status_history": list(self.status_history),
        }

    def result_dict(self) -> dict[str, Any]:
        view = self.status_dict()
        view.update(
            {
                "bits": self.bits,
                "transpiled_ops": self.transpiled_ops,
                "provider_metadata": dict(self.provider_metadata),
                "seed": self.seed,
                "algorithm": self.algorithm,
                "seed_derivation": self.seed_derivation,
                "completed_at": iso(self.completed_at),
            }
        )
        view.update(self._stats())
        return view

    def to_persist_dict(self) -> dict[str, Any]:
        """Full record for JSONL persistence (still contains no secrets)."""
        return self.result_dict()

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Optional["Experiment"]:
        """Rebuild an Experiment from a persisted record (JSONL round-trip)."""
        try:
            from datetime import datetime as _dt

            def _parse_ts(value):
                if not value:
                    return None
                try:
                    parsed = _dt.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    return None
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

            error = record.get("error") or {}
            return cls(
                id=record["experiment_id"],
                kind=record.get("kind", "qrng"),
                mode=Mode(record["mode"]) if record.get("mode") else None,
                source=record.get("source", "classical"),
                status=JobState(record.get("status", "CREATED")),
                status_detail=record.get("status_detail"),
                status_history=list(record.get("status_history") or []),
                provider=record.get("provider"),
                provider_job_id=record.get("provider_job_id"),
                backend=record.get("backend"),
                requested_shots=record.get("shots"),
                requested_bits=record.get("bits_requested")
                or (len(record["bits"]) if record.get("bits") else None),
                seed=record.get("seed"),
                algorithm=record.get("algorithm"),
                seed_derivation=record.get("seed_derivation"),
                bits=record.get("bits"),
                zero_count=record.get("zero_count"),
                one_count=record.get("one_count"),
                circuit=record.get("circuit"),
                transpiled_ops=record.get("transpiled_ops"),
                provider_metadata=dict(record.get("provider_metadata") or {}),
                error_code=error.get("code"),
                error_message=error.get("message"),
                error_hint=error.get("hint"),
                created_at=_parse_ts(record.get("created_at")) or utcnow(),
                submitted_at=_parse_ts(record.get("submitted_at")),
                completed_at=_parse_ts(record.get("completed_at")),
                updated_at=_parse_ts(record.get("updated_at")) or utcnow(),
            )
        except (KeyError, ValueError):
            return None
