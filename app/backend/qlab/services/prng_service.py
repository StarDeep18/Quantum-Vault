"""PRNG service — classical, deterministic, reproducible (Slice 1 / M1).

Algorithm: SplitMix64 (Steele & Lea), a well-documented 64-bit
deterministic generator. Pure integer arithmetic — identical output on
every platform, every run.

    state_{i+1} = state_i + 0x9E3779B97F4A7C15   (golden gamma)
    z = state_{i+1}
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
    z = (z ^ (z >> 27)) * 0x94D049BB133111EB
    output_i = z ^ (z >> 31)

Bit extraction: each generated bit is the MOST SIGNIFICANT BIT of one
64-bit output. One output → one bit, so the sequence is easy to audit.

Seed derivation (documented + returned in every response):
  * seed parses as an integer  →  used directly as the 64-bit state
  * anything else              →  SHA-256(seed)[:8] little-endian as state

Same seed + same bit count → same sequence, always. No platform, network
or hardware randomness is involved anywhere in this path.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .statistics_service import distribution

ALGORITHM = "splitmix64"

_MASK64 = (1 << 64) - 1
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15
_MIX_1 = 0xBF58476D1CE4E5B9
_MIX_2 = 0x94D049BB133111EB

_INT_RE = re.compile(r"^-?\d+$")


def derive_seed_state(seed: str) -> tuple[int, str]:
    """Map a user seed string to the initial 64-bit state (+ description)."""
    text = seed.strip()
    if _INT_RE.match(text):
        state = int(text) & _MASK64
        derivation = "integer seed → used directly as the initial 64-bit state"
    else:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        state = int.from_bytes(digest[:8], "little")
        derivation = "non-integer seed → SHA-256(seed), first 8 bytes, little-endian → state"
    return state, derivation


def splitmix64_output(state: int) -> tuple[int, int]:
    """Advance the state; return (new_state, 64-bit output)."""
    state = (state + _GOLDEN_GAMMA) & _MASK64
    z = state
    z = ((z ^ (z >> 30)) * _MIX_1) & _MASK64
    z = ((z ^ (z >> 27)) * _MIX_2) & _MASK64
    return state, z ^ (z >> 31)


@dataclass(frozen=True)
class PrngRun:
    bits: str
    seed: str
    initial_state: int
    derivation: str
    algorithm: str = ALGORITHM


def generate(seed: str, bits: int) -> PrngRun:
    """Deterministically generate `bits` bits from `seed`."""
    if bits < 1:
        raise ValueError("bits must be >= 1")
    state, derivation = derive_seed_state(seed)
    out: list[str] = []
    append = out.append
    for _ in range(bits):
        state, output = splitmix64_output(state)
        append("1" if output >> 63 else "0")
    return PrngRun("".join(out), seed, state, derivation)


def result_dict(run: PrngRun) -> dict[str, Any]:
    """API view of a PRNG run: stream + counts + provenance."""
    stats = distribution(run.bits)
    return {
        "algorithm": run.algorithm,
        "seed": run.seed,
        "seed_derivation": run.derivation,
        "initial_state_hex": f"0x{run.initial_state:016x}",
        "bits": run.bits,
        **stats,
    }
