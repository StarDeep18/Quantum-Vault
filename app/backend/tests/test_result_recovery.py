"""Regression tests for hardware-result recovery after backend restarts.

These tests use a fake provider only; they never submit a real QPU job.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from qlab.api.errors import ApiError
from qlab.api.routes_qrng import job_result, job_status
from qlab.config import Limits
from qlab.models import JobState, Mode
from qlab.providers.base import (
    BackendInfo,
    ProviderError,
    ProviderResult,
    ProviderResultError,
    ProviderStatusInfo,
    ProviderSubmission,
    QuantumProvider,
)
from qlab.services.experiment_service import ExperimentStore
from qlab.services.job_manager import JobManager
from qlab.services.qrng_service import QrngService


BITS = "0101" * 80
PROVIDER_JOB_ID = "00000000-0000-4000-8000-000000000001"


class FakeIQMProvider(QuantumProvider):
    name = "iqm"
    label = "IQM test provider"
    is_simulator = False

    def __init__(self, *, fail_result: bool = False) -> None:
        self.fail_result = fail_result
        self.submit_calls = 0
        self.result_calls = 0

    def configured(self) -> bool:
        return True

    def create_qrng_circuit(self):
        return object()

    def validate_circuit(self, circuit) -> None:
        return None

    def submit_job(self, circuit, shots, backend=None, seed=None):
        self.submit_calls += 1
        return ProviderSubmission(
            provider_job_id=PROVIDER_JOB_ID,
            backend="sirius",
            submitted_at="2026-10-14T00:00:00Z",
        )

    def get_job_status(self, provider_job_id: str) -> ProviderStatusInfo:
        return ProviderStatusInfo(JobState.COMPLETED, "provider says completed")

    def get_job_result(self, provider_job_id: str, shots: int) -> ProviderResult:
        self.result_calls += 1
        if self.fail_result:
            raise ProviderResultError("provider measurements unavailable")
        if shots != 320:
            raise ProviderError("INVALID_SHOTS", "unexpected test shot count")
        return ProviderResult(
            provider_job_id=provider_job_id,
            backend="sirius",
            bits=BITS,
            counts={"0": BITS.count("0"), "1": BITS.count("1")},
            metadata={"measurement_retrieval": "per-shot (get_job_measurements)"},
        )

    def get_backend_metadata(self, name=None) -> list[BackendInfo]:
        return [BackendInfo("sirius", simulator=False, operational=True, qubits=24)]


def make_request(qrng: QrngService, jobs: JobManager):
    runtime = SimpleNamespace(qrng=qrng, jobs=jobs)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))


def create_completed_record(data_dir: Path) -> str:
    store = ExperimentStore(data_dir)
    experiment = store.create(
        kind="qrng",
        mode=Mode.HARDWARE,
        source="quantum_hardware",
        status=JobState.COMPLETED,
        provider="iqm",
        provider_job_id=PROVIDER_JOB_ID,
        backend="sirius",
        requested_shots=320,
        circuit={},
    )
    store.persist(experiment.id)
    return experiment.id


class ResultRecoveryTests(unittest.TestCase):
    def test_worker_persists_fetching_before_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            store = ExperimentStore(data_dir)
            jobs = JobManager(store, Limits())
            provider = FakeIQMProvider()
            experiment = store.create(
                kind="qrng",
                mode=Mode.HARDWARE,
                source="quantum_hardware",
                status=JobState.CREATED,
                provider="iqm",
                requested_shots=320,
                circuit={},
            )

            jobs._execute(experiment.id, provider, 320, "sirius", None)

            completed = store.get(experiment.id)
            self.assertIsNotNone(completed)
            self.assertEqual(completed.status, JobState.COMPLETED)
            self.assertEqual(completed.bits, BITS)
            states = [item["state"] for item in completed.status_history]
            self.assertIn(JobState.FETCHING_RESULT.value, states)
            self.assertEqual(states[-1], JobState.COMPLETED.value)
            last_record = json.loads((data_dir / "experiments.jsonl").read_text().splitlines()[-1])
            self.assertIsNone(last_record["bits"])
            self.assertNotIn(BITS, (data_dir / "experiments.jsonl").read_text())

    def test_legacy_completed_record_recovers_without_submitting_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            experiment_id = create_completed_record(data_dir)
            store = ExperimentStore(data_dir)  # simulate process restart
            jobs = JobManager(store, Limits())
            provider = FakeIQMProvider()
            qrng = QrngService(store, jobs, {"iqm": provider}, Limits())
            request = make_request(qrng, jobs)

            status = job_status(experiment_id, request)
            result = job_result(experiment_id, request)

            self.assertEqual(status["status"], JobState.COMPLETED.value)
            self.assertEqual(result["bits"], BITS)
            self.assertEqual(result["backend"], "sirius")
            self.assertEqual(provider.submit_calls, 0)
            self.assertEqual(provider.result_calls, 1)
            persisted = (data_dir / "experiments.jsonl").read_text()
            self.assertNotIn(BITS, persisted)
            self.assertIsNone(json.loads(persisted.splitlines()[-1])["bits"])

    def test_unrecoverable_result_returns_410_without_bits_or_new_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            experiment_id = create_completed_record(data_dir)
            store = ExperimentStore(data_dir)
            jobs = JobManager(store, Limits())
            provider = FakeIQMProvider(fail_result=True)
            qrng = QrngService(store, jobs, {"iqm": provider}, Limits())
            request = make_request(qrng, jobs)

            with self.assertRaises(ApiError) as caught:
                job_result(experiment_id, request)

            self.assertEqual(caught.exception.status_code, 410)
            self.assertEqual(caught.exception.code, "MEASUREMENTS_NOT_RETAINED")
            self.assertIn("no key", (caught.exception.hint or "").lower())
            self.assertIsNone(store.get(experiment_id).bits)
            self.assertEqual(provider.submit_calls, 0)


if __name__ == "__main__":
    unittest.main()
