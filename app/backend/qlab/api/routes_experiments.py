"""Experiment history + comparison routes (TRD §11, §12)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..models import JobState
from ..services import prng_service
from .errors import ApiError

router = APIRouter(prefix="/api", tags=["experiments"])


@router.get("/experiments")
def list_experiments(request: Request, limit: int = 60, kind: Optional[str] = None) -> dict:
    runtime = request.app.state.runtime
    limit = max(1, min(limit, 200))
    experiments = runtime.store.list(limit=limit, kind=kind)
    return {"experiments": [e.summary_dict() for e in experiments]}


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, request: Request) -> dict:
    runtime = request.app.state.runtime
    experiment = runtime.store.get(experiment_id)
    if experiment is None:
        raise ApiError(404, "EXPERIMENT_NOT_FOUND", f"No experiment '{experiment_id}'.",
                       "List available experiments via GET /api/experiments.")
    return experiment.result_dict()


class CompareRequest(BaseModel):
    bits: int = Field(..., ge=1, description="PRNG bit count (QRNG side uses its own shots)")
    seed: object = Field(..., description="Any text or integer seed")
    qrng_experiment_id: Optional[str] = Field(
        None, description="A completed QRNG experiment to compare against; "
                          "defaults to the latest completed hardware run"
    )


@router.post("/compare")
def compare(body: CompareRequest, request: Request) -> dict:
    """Orchestrate a comparison WITHOUT hiding provenance: the PRNG side is
    generated live; the QRNG side must be an existing completed experiment
    (we never silently submit a new QPU job on the user's behalf)."""
    runtime = request.app.state.runtime
    if body.bits > runtime.limits.max_bits:
        raise ApiError(400, "INVALID_BITS",
                       f"bits must be at most {runtime.limits.max_bits}.",
                       f"Pick a bit count in [1, {runtime.limits.max_bits}].")

    if body.qrng_experiment_id:
        qrng = runtime.store.get(body.qrng_experiment_id)
        if qrng is None or qrng.kind != "qrng":
            raise ApiError(404, "EXPERIMENT_NOT_FOUND",
                           f"No QRNG experiment '{body.qrng_experiment_id}'.",
                           "List experiments via GET /api/experiments?kind=qrng.")
    else:
        qrng = runtime.store.latest_completed(kind="qrng", source="quantum_hardware") \
            or runtime.store.latest_completed(kind="qrng")
        if qrng is None:
            raise ApiError(
                409,
                "COMPARE_REQUIRES_QRNG",
                "No completed QRNG experiment available to compare against.",
                "Run a QRNG experiment first (hardware or labelled simulator), then compare.",
            )
    if qrng.status is not JobState.COMPLETED or not qrng.bits:
        raise ApiError(409, "COMPARE_REQUIRES_QRNG",
                       f"QRNG experiment '{qrng.id}' is {qrng.status.value}, not COMPLETED.",
                       "Wait for it to complete or pick another experiment.")

    run = prng_service.generate(body.seed.strip(), body.bits)
    prng_payload = prng_service.result_dict(run)

    store = request.app.state.runtime.store
    prng_experiment = store.create(
        kind="prng", mode=None, source="classical", status=JobState.COMPLETED,
        requested_bits=len(run.bits), seed=run.seed, algorithm=run.algorithm,
        seed_derivation=run.derivation, bits=run.bits,
    )
    prng_experiment.compute_counts()
    prng_experiment.transition(JobState.COMPLETED, "deterministic SplitMix64 generation complete")
    store.persist(prng_experiment.id)
    prng_payload["experiment_id"] = prng_experiment.id

    qrng_view = qrng.result_dict()
    return {
        "prng": prng_payload,
        "qrng": {
            "experiment_id": qrng_view["experiment_id"],
            "mode": qrng_view["mode"],
            "source": qrng_view["source"],
            "provider": qrng_view["provider"],
            "backend": qrng_view["backend"],
            "provider_job_id": qrng_view["provider_job_id"],
            "shots": qrng_view["shots"],
            "bits": qrng_view["bits"],
            "zero_count": qrng_view["zero_count"],
            "one_count": qrng_view["one_count"],
            "observed_zero_pct": qrng_view.get("observed_zero_pct"),
            "observed_one_pct": qrng_view.get("observed_one_pct"),
            "theoretical_zero_pct": 50.0,
            "theoretical_one_pct": 50.0,
            "sigma_pct": qrng_view.get("sigma_pct"),
            "z_score": qrng_view.get("z_score"),
            "created_at": qrng_view["created_at"],
            "completed_at": qrng_view.get("completed_at"),
        },
        "note": (
            "Both distributions can sit near 50/50 — a histogram does not distinguish the "
            "sources. The difference is in provenance and reproducibility: the PRNG side is "
            "a deterministic function of its seed; the QRNG side is a record of physical "
            "quantum measurements that cannot be replayed by re-running."
        ),
    }
