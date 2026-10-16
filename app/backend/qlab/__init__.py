"""Quantum Randomness Lab — backend package.

Two independent generation pipelines:

- PRNG  : classical, deterministic (SplitMix64), reproducible from a seed.
- QRNG  : fixed circuit |0> - H - M executed on a real quantum processor
          through a provider adapter (IBM Quantum first), or on an
          explicitly-labelled local simulator for development.

Architecture invariants (see docs/architecture.md):
  hardware QRNG bits originate from provider measurement data only,
  the provider sits behind an adapter boundary, credentials never
  leave the server, and replay never generates new randomness.
"""

__version__ = "1.0.0"
