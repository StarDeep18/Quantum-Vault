"""SimulatorProvider — development / fallback mode ONLY.

This provider runs the *same fixed QRNG circuit* through an ideal
statevector simulation: the Born-rule probabilities of the circuit are
computed exactly, and per-shot measurement outcomes are sampled from
those probabilities. It is explicitly labelled `quantum_simulator` in
every response and can never masquerade as hardware (architecture.md
invariant 3). Its output is used only when the user explicitly selects
simulator mode.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from .. import circuits as qrng_circuits
from ..models import JobState
from .base import (
    BackendInfo,
    ProviderResult,
    ProviderStatusInfo,
    ProviderSubmission,
    QuantumProvider,
)

SIMULATOR_BACKEND_NAME = "local-statevector-simulator"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SimulatorProvider(QuantumProvider):
    name = "local_statevector"
    label = "Ideal statevector simulator (local, development mode)"
    is_simulator = True

    def __init__(self) -> None:
        # Completed simulator "jobs", kept in memory: job_id -> ProviderResult
        self._results: dict[str, ProviderResult] = {}

    # -- interface ----------------------------------------------------------

    def configured(self) -> bool:
        return True                                        # always available, always labelled

    def create_qrng_circuit(self) -> QuantumCircuit:
        return qrng_circuits.build_qrng_circuit()

    def validate_circuit(self, circuit: QuantumCircuit) -> None:
        qrng_circuits.validate_qrng_circuit(circuit)

    def submit_job(
        self,
        circuit: QuantumCircuit,
        shots: int,
        backend: Optional[str] = None,
        seed: Optional[str] = None,
    ) -> ProviderSubmission:
        if backend not in (None, "auto", SIMULATOR_BACKEND_NAME):
            raise ProviderError(
                "INVALID_BACKEND",
                f"Unknown simulator backend '{backend}'.",
                f"Use '{SIMULATOR_BACKEND_NAME}' or omit the backend in simulator mode.",
            )
        self.validate_circuit(circuit)

        # Born-rule probabilities from the actual (measurement-free) circuit
        bare = circuit.remove_final_measurements(inplace=False)
        probabilities = np.asarray(Statevector.from_instruction(bare).probabilities(), dtype=float)
        probabilities = probabilities / probabilities.sum()

        # Deterministic seed derivation for reproducible simulator runs
        # (development convenience — hardware mode can never be seeded).
        if seed:
            import hashlib

            entropy = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "little")
            rng = np.random.default_rng(entropy)
        else:
            rng = np.random.default_rng()
        outcomes = rng.choice(len(probabilities), size=shots, p=probabilities)
        bits = "".join("1" if int(outcome) == 1 else "0" for outcome in outcomes)
        counts = {"0": bits.count("0"), "1": bits.count("1")}

        job_id = f"sim-{uuid.uuid4().hex[:12]}"
        self._results[job_id] = ProviderResult(
            provider_job_id=job_id,
            backend=SIMULATOR_BACKEND_NAME,
            bits=bits,
            counts=counts,
            metadata={
                "simulator": True,
                "method": "exact statevector, measurement sampled from Born-rule probabilities",
                "seeded": bool(seed),
            },
        )
        return ProviderSubmission(
            provider_job_id=job_id,
            backend=SIMULATOR_BACKEND_NAME,
            submitted_at=_now_iso(),
            transpiled_ops=qrng_circuits.transpiled_ops(circuit),
            raw={"simulator": True},
        )

    def get_job_status(self, provider_job_id: str) -> ProviderStatusInfo:
        if provider_job_id in self._results:
            return ProviderStatusInfo(JobState.COMPLETED, "simulated execution finished (instant, local)")
        raise ProviderError("JOB_NOT_FOUND", f"Simulator job '{provider_job_id}' not found.")

    def get_job_result(self, provider_job_id: str, shots: int) -> ProviderResult:
        result = self._results.get(provider_job_id)
        if result is None:
            raise ProviderError("JOB_NOT_FOUND", f"Simulator job '{provider_job_id}' not found.")
        if len(result.bits) != shots:
            raise ProviderError(
                "PROVIDER_RESULT_ERROR",
                f"Simulator returned {len(result.bits)} bits, expected {shots}.",
            )
        return result

    def get_backend_metadata(self, name: Optional[str] = None) -> list[BackendInfo]:
        return [
            BackendInfo(
                name=SIMULATOR_BACKEND_NAME,
                simulator=True,
                operational=True,
                pending_jobs=0,
                qubits=1,
                status_message="local ideal simulation (no queue)",
            )
        ]


from .base import ProviderError  # noqa: E402  (kept at bottom to avoid clutter above)
