"""IBMQuantumProvider — the REAL HARDWARE path (Slice 2 / Milestone 2).

Executes the fixed QRNG circuit on a real IBM Quantum processor via
QiskitRuntimeService + SamplerV2 (the current IBM Quantum Platform SDK).

Non-negotiable rules implemented here:
  * Bits returned by get_job_result() come ONLY from the provider's
    returned measurement data — never from any local random source.
  * Simulator backends are excluded when selecting hardware
    (service.backends(simulator=False) + defensive local filtering).
  * Credentials are read server-side from config only; every message
    that could echo provider errors is passed through redact().
  * No silent fallback of any kind: failures raise, they never pretend.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from qiskit import QuantumCircuit, transpile

from .. import circuits as qrng_circuits
from ..config import IBMConfig, load_ibm_config, redact
from ..models import JobState
from .base import (
    BackendInfo,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderResult,
    ProviderResultError,
    ProviderStatusInfo,
    ProviderSubmission,
    QuantumProvider,
    normalize_status,
)

CREDENTIALS_HINT = (
    "Create a free IBM Quantum account at https://quantum.cloud.ibm.com, generate an "
    "API token, and set IBM_QUANTUM_API_KEY in app/backend/.env (see .env.example). "
    "The server picks it up on the next submission — no restart needed. Simulator "
    "mode remains available and is always labelled as simulation."
)


class IBMQuantumProvider(QuantumProvider):
    name = "ibm_quantum"
    label = "IBM Quantum — real QPU hardware"
    is_simulator = False

    BACKEND_CACHE_TTL = 60.0          # seconds

    def __init__(self, config_loader=load_ibm_config) -> None:
        self._config_loader = config_loader
        self._service: Any = None
        self._service_key: Optional[str] = None      # token the service was built for
        self._service_lock = threading.Lock()
        self._job_handles: dict[str, Any] = {}
        self._submit_meta: dict[str, dict[str, Any]] = {}
        self._backends_cache: Optional[tuple[float, list[BackendInfo]]] = None

    # ------------------------------------------------------------------ config

    def configured(self) -> bool:
        """Re-read config each call so tokens added to .env later are detected."""
        return self._config_loader().configured

    def _require_config(self) -> IBMConfig:
        cfg = self._config_loader()
        if not cfg.configured:
            raise ProviderNotConfigured(
                "IBM Quantum credentials are not configured on this server.",
                CREDENTIALS_HINT,
            )
        return cfg

    def _get_service(self) -> Any:
        cfg = self._require_config()
        if self._service is not None and self._service_key == cfg.api_key:
            return self._service
        with self._service_lock:
            if self._service is None or self._service_key != cfg.api_key:
                try:
                    from qiskit_ibm_runtime import QiskitRuntimeService
                except ImportError as exc:  # pragma: no cover - sdk is a hard dep
                    raise ProviderError(
                        "SDK_MISSING",
                        "qiskit-ibm-runtime is not installed on the server.",
                        "Install backend dependencies: pip install -r requirements.txt",
                    ) from exc
                kwargs: dict[str, Any] = {"channel": cfg.channel, "token": cfg.api_key}
                if cfg.instance:
                    kwargs["instance"] = cfg.instance
                try:
                    self._service = QiskitRuntimeService(**kwargs)
                except Exception as exc:
                    raise self._translate(exc, "connecting to IBM Quantum") from exc
                self._service_key = cfg.api_key
        return self._service

    # ------------------------------------------------------------------ circuit

    def create_qrng_circuit(self) -> QuantumCircuit:
        return qrng_circuits.build_qrng_circuit()

    def validate_circuit(self, circuit: QuantumCircuit) -> None:
        qrng_circuits.validate_qrng_circuit(circuit)

    # ------------------------------------------------------------------ backends

    def get_backend_metadata(self, name: Optional[str] = None) -> list[BackendInfo]:
        if name:
            return [self._backend_info(self._service_backend(name))]
        now = time.monotonic()
        if self._backends_cache and now - self._backends_cache[0] < self.BACKEND_CACHE_TTL:
            return self._backends_cache[1]
        service = self._get_service()
        try:
            backends = service.backends(simulator=False, operational=True)
        except Exception as exc:
            raise self._translate(exc, "listing IBM Quantum backends") from exc
        infos: list[BackendInfo] = []
        for backend in backends:
            try:
                infos.append(self._backend_info(backend))
            except Exception:
                continue                     # skip backends we cannot describe
        infos.sort(key=lambda b: (b.pending_jobs is None, b.pending_jobs or 0))
        self._backends_cache = (now, infos)
        return infos

    def _service_backend(self, name: str) -> Any:
        service = self._get_service()
        try:
            backend = service.backend(name)
        except Exception as exc:
            raise self._translate(exc, f"resolving backend '{name}'") from exc
        if getattr(backend.configuration(), "simulator", False):
            raise ProviderError(
                "SIMULATOR_BACKEND_REJECTED",
                f"'{name}' is a simulator backend — hardware mode requires a real QPU.",
                "Pick a non-simulator backend or use AUTO selection.",
            )
        return backend

    def _backend_info(self, backend: Any) -> BackendInfo:
        config = backend.configuration()
        simulator = bool(getattr(config, "simulator", False))
        status = backend.status()
        return BackendInfo(
            name=backend.name,
            simulator=simulator,
            operational=bool(getattr(status, "operational", False)),
            pending_jobs=getattr(status, "pending_jobs", None),
            qubits=getattr(config, "n_qubits", None),
            status_message=getattr(status, "status_msg", None),
        )

    def _select_backend(self, requested: Optional[str]) -> Any:
        cfg = self._config_loader()
        # precedence: explicit request > pinned config > AUTO (least pending jobs)
        choice = requested or cfg.pinned_backend
        if choice and choice != "auto":
            return self._service_backend(choice)
        candidates = [
            info for info in self.get_backend_metadata()
            if info.operational and not info.simulator
        ]
        if not candidates:
            raise ProviderError(
                "NO_BACKEND_AVAILABLE",
                "No operational, non-simulator IBM Quantum backend is currently available.",
                "Retry shortly or pin a specific backend in .env (IBM_QUANTUM_BACKEND).",
            )
        return self._service_backend(candidates[0].name)

    # ------------------------------------------------------------------ submit

    def submit_job(
        self,
        circuit: QuantumCircuit,
        shots: int,
        backend: Optional[str] = None,
        seed: Optional[str] = None,
    ) -> ProviderSubmission:
        if seed is not None:
            raise ProviderError(
                "INVALID_REQUEST",
                "Seeding is not supported in hardware mode — hardware outcomes cannot be seeded.",
                "Use simulator mode if you need reproducible runs for development.",
            )
        self.validate_circuit(circuit)
        service = self._get_service()
        target = self._select_backend(backend)

        try:
            from qiskit_ibm_runtime import SamplerV2
            transpiled = transpile(circuit, backend=target, optimization_level=1)
            sampler = SamplerV2(mode=target)
            job = sampler.run([transpiled], shots=shots)
            provider_job_id = job.job_id()
        except Exception as exc:
            raise self._translate(exc, f"submitting to IBM Quantum backend '{target.name}'") from exc

        with self._service_lock:
            self._job_handles[provider_job_id] = job
            self._submit_meta[provider_job_id] = {
                "transpiled_ops": qrng_circuits.transpiled_ops(transpiled),
                "backend": target.name,
                "shots": shots,
                "submitted_at": time.time(),
            }
        return ProviderSubmission(
            provider_job_id=provider_job_id,
            backend=target.name,
            submitted_at=str(getattr(job, "creation_date", "") or ""),
            transpiled_ops=qrng_circuits.transpiled_ops(transpiled),
        )

    # ------------------------------------------------------------------ status

    def _job(self, provider_job_id: str) -> Any:
        job = self._job_handles.get(provider_job_id)
        if job is not None:
            return job
        service = self._get_service()
        try:
            job = service.job(provider_job_id)
        except Exception as exc:
            raise self._translate(exc, f"fetching job '{provider_job_id}'") from exc
        with self._service_lock:
            self._job_handles[provider_job_id] = job
        return job

    def get_job_status(self, provider_job_id: str) -> ProviderStatusInfo:
        job = self._job(provider_job_id)
        try:
            raw_status = job.status()
        except Exception as exc:
            raise self._translate(exc, f"fetching status of job '{provider_job_id}'") from exc

        state = normalize_status(raw_status)
        if state is None:
            # Unrecognized provider state: never guess — surface it as detail.
            return ProviderStatusInfo(
                JobState.RUNNING,
                detail=f"unrecognized provider status reported: {redact(str(raw_status))}",
            )
        detail: Optional[str] = None
        if state is JobState.FAILED:
            try:
                detail = redact(str(job.error_message() or "provider reported job failure"))
            except Exception:
                detail = "provider reported job failure"
        return ProviderStatusInfo(state, detail)

    # ------------------------------------------------------------------ result

    def get_job_result(self, provider_job_id: str, shots: int) -> ProviderResult:
        job = self._job(provider_job_id)
        try:
            primitive_result = job.result()
        except Exception as exc:
            raise self._translate(exc, f"retrieving result of job '{provider_job_id}'") from exc

        bits, counts = self._extract_bits(primitive_result, shots)

        metadata: dict[str, Any] = {"job_id": provider_job_id}
        try:
            metrics = job.metrics() or {}
            timestamps = metrics.get("timestamps") or {}
            if timestamps:
                metadata["provider_timestamps"] = timestamps
        except Exception:
            pass
        try:
            creation = job.creation_date()
            if creation:
                metadata["provider_created"] = str(creation)
        except Exception:
            pass
        submit_meta = self._submit_meta.get(provider_job_id, {})
        if submit_meta:
            metadata["transpiled_ops"] = submit_meta.get("transpiled_ops")

        backend_name = submit_meta.get("backend") or str(
            getattr(getattr(job, "backend", None), "name", "") or ""
        )
        return ProviderResult(
            provider_job_id=provider_job_id,
            backend=backend_name,
            bits=bits,
            counts=counts,
            metadata=metadata,
        )

    @staticmethod
    def _extract_bits(primitive_result: Any, shots: int) -> tuple[str, dict[str, int]]:
        """Extract shot-ordered bits from a SamplerV2 PrimitiveResult.

        The measurement register is the fixed single-bit register 'c'.
        Strict validation: shot count must match and only 0/1 may appear —
        anything else is an honest provider-result error, never faked.
        """
        try:
            pub = primitive_result[0]
            data = pub.data
            creg = getattr(data, "c", None)
            if creg is None:
                raise ProviderResultError(
                    "Provider result did not contain the 'c' measurement register.",
                    "The backend returned an unexpected data layout.",
                )
            bitstrings = creg.get_bitstrings()
        except ProviderResultError:
            raise
        except Exception as exc:
            raise ProviderResultError(
                f"Could not read measurement data from the provider result: {redact(str(exc))}",
                "The job may not have produced a usable payload.",
            ) from exc

        bits = "".join(str(b) for b in bitstrings)
        if len(bits) != shots:
            raise ProviderResultError(
                f"Provider returned {len(bits)} measurement outcomes, expected {shots}.",
                "Refusing to display bits that do not match the requested shot count.",
            )
        if bits and not set(bits) <= {"0", "1"}:
            raise ProviderResultError(
                "Provider returned a measurement outcome outside {0, 1}.",
                "Unexpected qubit outcome — this circuit should measure exactly one bit.",
            )
        counts = {"0": bits.count("0"), "1": bits.count("1")}
        return bits, counts

    # ------------------------------------------------------------------ errors

    @staticmethod
    def _translate(exc: Exception, action: str) -> ProviderError:
        """Normalize provider/SDK exceptions into ProviderError, redacted."""
        status_code = getattr(exc, "status_code", None)
        name = type(exc).__name__
        message = redact(f"{name}: {exc}") if str(exc) else redact(name)

        if status_code == 429 or "429" in str(status_code or ""):
            return ProviderRateLimited(
                f"IBM Quantum rate limit hit while {action}.",
                retry_after=60.0,
                hint="IBM allows about 5 job submissions per minute. Wait for the cooldown and retry.",
            )
        if status_code == 401 or status_code == 403:
            return ProviderError(
                "PROVIDER_AUTH_FAILED",
                f"IBM Quantum rejected the credentials while {action} ({message}).",
                "Check IBM_QUANTUM_API_KEY (and IBM_QUANTUM_INSTANCE) in app/backend/.env — "
                "the token may be expired or revoked.",
            )
        if status_code == 404:
            return ProviderError(
                "PROVIDER_NOT_FOUND",
                f"IBM Quantum returned 'not found' while {action} ({message}).",
                "The job or backend may not exist for this account/instance.",
            )
        if "Account" in name or "account" in str(exc).lower():
            return ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                f"IBM Quantum account issue while {action} ({message}).",
                CREDENTIALS_HINT,
            )
        if status_code and int(status_code) >= 500:
            return ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"IBM Quantum service error while {action} ({message}).",
                "This is on IBM's side — retry in a moment; provider status: "
                "https://status.quantum.ibm.com",
            )
        return ProviderError(
            "PROVIDER_ERROR",
            f"IBM Quantum failure while {action} ({message}).",
            "Check the backend log for details, then retry. No bits were fabricated.",
        )
