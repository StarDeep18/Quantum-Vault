"""QRNG routes (TRD §9) — hardware-first, honest states, provenance preserved."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request

from ..models import JobState, Mode, TERMINAL_STATES
from ..providers import provider_for_mode
from ..providers.base import ProviderError
from ..config import load_iqm_config, redact, review_demo_enabled
from .errors import ApiError
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/qrng", tags=["qrng"])


def _hardware_provider(request: Request):
    """The active hardware provider (IQM when configured, else IBM)."""
    runtime = request.app.state.runtime
    return provider_for_mode(runtime.providers, Mode.HARDWARE)


class QrngJobRequest(BaseModel):
    shots: int = Field(..., ge=1, description="Measurement shots (one bit per shot)")
    mode: Mode = Field(Mode.HARDWARE, description="hardware = real QPU, simulator = labelled local sim")
    backend: Optional[str] = Field("auto", description="'auto' or a specific backend name")
    seed: Optional[str] = Field(None, max_length=256, description="simulator mode only")


# --------------------------------------------------------------------- config

@router.get("/config")
def qrng_config(request: Request) -> dict:
    """Provider/mode availability + limits. Fast (no provider network calls)."""
    runtime = request.app.state.runtime
    hw = _hardware_provider(request)
    limits = runtime.limits
    configured = hw.configured()
    cooldown = runtime.qrng.cooldown_remaining()
    return {
        "review_demo_enabled": review_demo_enabled(),
        "hardware": {
            "available": configured,
            "provider": hw.name,
            "label": hw.label,
            "simulator": False,
            "reason": None if configured else getattr(hw, "NOT_CONFIGURED_REASON", "credentials are not set on the server"),
            "setup_hint": getattr(hw, "SETUP_HINT", ""),
            "setup_steps": list(getattr(hw, "SETUP_STEPS", [])),
        },
        "simulator": {
            "available": True,
            "provider": "local_statevector",
            "label": "Ideal statevector simulator — development mode, always labelled",
            "simulator": True,
        },
        "limits": {
            "min_shots": limits.min_shots,
            "max_shots": limits.max_shots,
            "default_shots": limits.default_shots,
            "max_bits": limits.max_bits,
            "default_bits": limits.default_bits,
            "job_timeout_s": limits.job_timeout_s,
            "submit_cooldown_s": limits.submit_cooldown_s,
        },
        "submit_cooldown_remaining_s": round(cooldown, 1),
        "circuit": runtime.circuit,
    }


@router.get("/backends")
def qrng_backends(request: Request) -> dict:
    """REAL hardware backend list (live from the active provider when configured)."""
    hw = _hardware_provider(request)
    if not hw.configured():
        return {"available": False,
                "reason": getattr(hw, "NOT_CONFIGURED_REASON", "credentials are not set on the server"),
                "backends": []}
    try:
        infos = hw.get_backend_metadata()
    except ProviderError as exc:
        return {"available": False, "reason": redact(exc.message), "backends": []}
    selected_backend = None
    selection_error = None
    if hw.name == "iqm":
        # Match IQMProvider._resolve_qc: honor a configured pin; otherwise
        # report the first live real QPU, which is the provider's AUTO choice.
        pinned = load_iqm_config().quantum_computer
        if pinned and pinned != "auto":
            if any(backend.name == pinned and not backend.simulator for backend in infos):
                selected_backend = pinned
            else:
                selection_error = "IQM_QUANTUM_COMPUTER does not match a discovered real QPU."
        else:
            selected_backend = next((backend.name for backend in infos if not backend.simulator), None)
    return {
        "available": True,
        "reason": None,
        "selected_backend": selected_backend,
        "selection_error": selection_error,
        "backends": [
            {
                "name": b.name,
                "simulator": b.simulator,
                "operational": b.operational,
                "pending_jobs": b.pending_jobs,
                "qubits": b.qubits,
                "status_message": b.status_message,
            }
            for b in infos
        ],
    }


# --------------------------------------------------------------------- jobs

@router.post("/jobs", status_code=202)
def create_job(body: QrngJobRequest, request: Request) -> dict:
    """ProviderErrors (validation, not-configured, cooldown, provider
    failures) are normalized to the API error envelope by the global
    exception handler in qlab.api.errors."""
    runtime = request.app.state.runtime
    experiment = runtime.qrng.create_job(
        shots=body.shots,
        mode=body.mode,
        backend=body.backend,
        seed=(body.seed.strip() if body.seed else None) or None,
    )
    return experiment.status_dict()


@router.get("/jobs/{experiment_id}")
def job_status(experiment_id: str, request: Request) -> dict:
    runtime = request.app.state.runtime
    experiment = runtime.qrng.get(experiment_id)
    if experiment is None or experiment.kind != "qrng":
        raise ApiError(404, "JOB_NOT_FOUND", f"No QRNG experiment '{experiment_id}'.",
                       "Submit a new job via POST /api/qrng/jobs or list /api/experiments.")
    # Honest refresh: if the local worker is gone but the provider job exists,
    # re-attach and report the true provider state (also survives restarts).
    # A completed hardware record with no in-memory shots is the legacy restart
    # race: recover its measurements from the provider using the saved job ID.
    needs_measurement_recovery = (
        experiment.status is JobState.COMPLETED
        and experiment.mode is Mode.HARDWARE
        and not experiment.bits
        and bool(experiment.provider_job_id)
    )
    if (
        experiment.status not in TERMINAL_STATES
        or experiment.status is JobState.TIMED_OUT
        or needs_measurement_recovery
    ):
        try:
            runtime.qrng.refresh_stale(experiment)
        except Exception:
            pass                                     # refresh failures never mask the stored state
    view = experiment.status_dict()
    view["worker_alive"] = runtime.qrng and runtime.jobs.is_alive(experiment.id)
    return view


@router.get("/jobs/{experiment_id}/result")
def job_result(experiment_id: str, request: Request) -> dict:
    runtime = request.app.state.runtime
    experiment = runtime.qrng.get(experiment_id)
    if experiment is None or experiment.kind != "qrng":
        raise ApiError(404, "JOB_NOT_FOUND", f"No QRNG experiment '{experiment_id}'.",
                       "Submit a new job via POST /api/qrng/jobs or list /api/experiments.")
    if experiment.status is JobState.COMPLETED and not experiment.bits and experiment.mode is Mode.HARDWARE:
        # Older records may have been marked COMPLETED just before the server
        # restarted and cleared its in-memory shot data. Retry retrieval by the
        # accepted provider ID before declaring the measurements unrecoverable.
        try:
            runtime.qrng.refresh_stale(experiment)
        except Exception:
            pass
        experiment = runtime.qrng.get(experiment_id) or experiment
    if experiment.status is JobState.COMPLETED and not experiment.bits and experiment.mode is Mode.HARDWARE:
        raise ApiError(
            410,
            "MEASUREMENTS_NOT_RETAINED",
            f"Experiment '{experiment_id}' completed, but its hardware measurements could not be recovered from the provider after a backend restart.",
            "Automatic recovery by the saved provider job ID was attempted. Submit a new IQM hardware job if needed; no key was created from this result.",
        )
    if experiment.status is not JobState.COMPLETED or not experiment.bits:
        raise ApiError(
            409,
            "RESULT_NOT_READY",
            f"Experiment '{experiment_id}' is {experiment.status.value} — no result yet.",
            "Poll GET /api/qrng/jobs/" + experiment_id + " until it reaches COMPLETED.",
        )
    return experiment.result_dict()
