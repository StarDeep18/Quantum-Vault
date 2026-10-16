"""The fixed, auditable QRNG circuit (PRD §9, TRD §7).

MVP circuit — single qubit, single classical bit:

    q[0]: |0⟩ ── H ── M ──
                   │
    c[0]: ─────────┘

The MVP never accepts user-supplied circuits (TRD §18); every hardware
QRNG execution is built from this module so the circuit is always the
approved, auditable one.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from qiskit import QuantumCircuit, qasm2

CIRCUIT_NAME = "qrng_h_measure"
CLASSICAL_REGISTER = "c"


def build_qrng_circuit() -> QuantumCircuit:
    """|0⟩ → H → measure into classical bit c[0]."""
    qc = QuantumCircuit(1, 1, name=CIRCUIT_NAME)
    qc.h(0)
    qc.measure(0, 0)
    return qc


def validate_qrng_circuit(qc: QuantumCircuit) -> None:
    """Raise ValueError unless qc is exactly the approved QRNG circuit."""
    problems: list[str] = []
    if qc.num_qubits != 1:
        problems.append(f"expected 1 qubit, found {qc.num_qubits}")
    if qc.num_clbits != 1:
        problems.append(f"expected 1 classical bit, found {qc.num_clbits}")
    if len(qc.cregs) != 1 or qc.cregs[0].name != CLASSICAL_REGISTER:
        problems.append(f"expected a single classical register named '{CLASSICAL_REGISTER}'")
    ops = dict(qc.count_ops())
    if ops.get("h", 0) != 1 or ops.get("measure", 0) != 1 or len(ops) != 2:
        problems.append(f"expected exactly one H and one measure, found {ops}")
    if qc.num_qubits >= 1 and qc.num_clbits >= 1:
        data = list(qc.data)
        if len(data) == 2:
            h_inst, m_inst = data
            if h_inst.operation.name != "h" or h_inst.clbits:
                problems.append("first operation must be H on the qubit only")
            if m_inst.operation.name != "measure" or m_inst.qubits != tuple(qc.qubits):
                problems.append("second operation must measure the qubit")
    if problems:
        raise ValueError("circuit rejected by fixed QRNG spec: " + "; ".join(problems))


def circuit_spec() -> dict[str, Any]:
    """Normalized circuit description for the frontend (no provider specifics)."""
    qc = build_qrng_circuit()
    return {
        "name": CIRCUIT_NAME,
        "qubits": 1,
        "classical_bits": 1,
        "gates": [
            {"index": 0, "type": "h", "qubits": [0], "label": "H"},
            {"index": 1, "type": "measure", "qubits": [0], "clbits": [0], "label": "M"},
        ],
        "state_sequence": [
            {"stage": "initial", "state": "|0⟩"},
            {"stage": "after_h", "state": "(|0⟩ + |1⟩)/√2"},
            {"stage": "measured", "state": "0 or 1 (per shot)"},
        ],
        "qasm2": qasm2.dumps(qc),
    }


def _format_param(value: float) -> str:
    """Render common angles as π multiples for readable provenance."""
    for k in (1, 2, 3, 4, 6, 8):
        target = math.pi / k
        if abs(value - target) < 1e-9:
            return f"π/{k}"
        if abs(value + target) < 1e-9:
            return f"-π/{k}"
    if abs(value - math.pi) < 1e-9:
        return "π"
    if abs(value + math.pi) < 1e-9:
        return "-π"
    return f"{value:.4g}"


def transpiled_ops(qc: QuantumCircuit) -> list[str]:
    """Human-readable gate list of a transpiled circuit, for provenance."""
    ops: list[str] = []
    for inst in qc.data:
        name = inst.operation.name
        params = [_format_param(float(p)) for p in inst.operation.params]
        ops.append(f"{name}({', '.join(params)})" if params else name)
    return ops


__all__ = [
    "CIRCUIT_NAME",
    "CLASSICAL_REGISTER",
    "build_qrng_circuit",
    "validate_qrng_circuit",
    "circuit_spec",
    "transpiled_ops",
]
