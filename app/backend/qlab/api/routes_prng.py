"""PRNG routes (TRD §10).

POST /api/prng/generate {seed, bits} → deterministic SplitMix64 stream.
"""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..models import JobState
from ..services import prng_service
from ..services.experiment_service import ExperimentStore
from .errors import ApiError

router = APIRouter(prefix="/api/prng", tags=["prng"])


class PrngGenerateRequest(BaseModel):
    seed: Union[int, str] = Field(..., description="Any text or integer seed (TRD §10)")
    bits: int = Field(..., ge=1, description="How many bits to generate")


class PrngGenerateResponse(BaseModel):
    experiment_id: str
    seed: str
    algorithm: str
    seed_derivation: str
    initial_state_hex: str
    bits: str
    zero_count: int
    one_count: int
    observed_zero_pct: float
    observed_one_pct: float
    theoretical_zero_pct: float
    theoretical_one_pct: float
    sigma_pct: float
    z_score: float
    created_at: str


@router.post("/generate", response_model=PrngGenerateResponse)
def generate(body: PrngGenerateRequest, request: Request) -> dict:
    limits = request.app.state.runtime.limits
    if body.bits > limits.max_bits:
        raise ApiError(
            400,
            "INVALID_BITS",
            f"bits must be at most {limits.max_bits} (requested {body.bits}).",
            f"Pick a bit count in [1, {limits.max_bits}].",
        )
    seed = str(body.seed).strip()
    if not seed:
        raise ApiError(400, "INVALID_SEED", "The seed cannot be empty.", "Enter any text or number.")
    if len(seed) > limits.max_seed_length:
        raise ApiError(400, "INVALID_SEED",
                       f"Seed too long (max {limits.max_seed_length} characters).",
                       "Use a shorter seed.")

    run = prng_service.generate(seed, body.bits)
    store: ExperimentStore = request.app.state.runtime.store
    experiment = store.create(
        kind="prng",
        mode=None,
        source="classical",
        status=JobState.COMPLETED,
        requested_bits=len(run.bits),
        seed=run.seed,
        algorithm=run.algorithm,
        seed_derivation=run.derivation,
        bits=run.bits,
    )
    experiment.compute_counts()
    experiment.transition(JobState.COMPLETED, "deterministic SplitMix64 generation complete")
    store.persist(experiment.id)
    payload = prng_service.result_dict(run)
    payload["experiment_id"] = experiment.id
    payload["created_at"] = experiment.created_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    return payload
