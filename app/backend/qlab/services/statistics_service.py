"""Statistics service — honest math for both pipelines.

Scientific honesty rules (PRD Principle 5, context.md §5):
  * Theoretical probabilities for the |0⟩→H→M circuit are exactly 50/50.
  * Observed frequencies of finite-shot experiments fluctuate around the
    theoretical value; we surface the 1σ binomial band and a z-score so
    the UI can say this explicitly instead of implying perfection.
  * A near-50/50 histogram alone proves nothing about the SOURCE of the
    bits (PRNG looks identical) — comparison views must say so.
"""

from __future__ import annotations

from typing import Any


def count_bits(bits: str) -> tuple[int, int]:
    if not bits:
        raise ValueError("empty bit stream")
    if any(ch not in "01" for ch in bits):
        raise ValueError("bit stream contains characters other than 0/1")
    return bits.count("0"), bits.count("1")


def binomial_sigma_pct(n: int, p: float = 0.5) -> float:
    """Standard deviation of the observed-1 fraction, in percent."""
    if n <= 0:
        raise ValueError("n must be positive")
    return (p * (1.0 - p) / n) ** 0.5 * 100.0


def distribution(bits: str) -> dict[str, Any]:
    """Full theoretical-vs-observed distribution for a bit stream."""
    zeros, ones = count_bits(bits)
    total = zeros + ones
    if total == 0:
        raise ValueError("empty bit stream")
    zero_pct = 100.0 * zeros / total
    sigma = binomial_sigma_pct(total)
    return {
        "zero_count": zeros,
        "one_count": ones,
        "observed_zero_pct": round(zero_pct, 2),
        "observed_one_pct": round(100.0 - zero_pct, 2),
        "theoretical_zero_pct": 50.0,
        "theoretical_one_pct": 50.0,
        "sigma_pct": round(sigma, 2),
        "z_score": round(((100.0 - zero_pct) - 50.0) / sigma, 2) if sigma else 0.0,
    }
