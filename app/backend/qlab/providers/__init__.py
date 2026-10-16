"""Provider registry — the only place providers are constructed.

Hardware-mode selection: IQM when configured, otherwise IBM Quantum.
Both stay registered; switching providers later (or per deployment) is a
pure configuration change.
"""

from __future__ import annotations

from ..models import Mode
from .base import (
    BackendInfo,
    ProviderError,
    ProviderJobFailed,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderResult,
    ProviderResultError,
    ProviderStatusInfo,
    ProviderSubmission,
    QuantumProvider,
    normalize_status,
)
from .ibm_provider import CREDENTIALS_HINT, IBMQuantumProvider
from .iqm_provider import IQM_CREDENTIALS_HINT, IQMProvider
from .simulator_provider import SIMULATOR_BACKEND_NAME, SimulatorProvider

# preference order for hardware mode: first configured provider wins
HARDWARE_PROVIDER_ORDER = ("iqm", "ibm_quantum")


def build_default_providers() -> dict[str, QuantumProvider]:
    return {
        "iqm": IQMProvider(),
        "ibm_quantum": IBMQuantumProvider(),
        "local_statevector": SimulatorProvider(),
    }


def provider_for_mode(providers: dict[str, QuantumProvider], mode: Mode) -> QuantumProvider:
    if mode is Mode.HARDWARE:
        for key in HARDWARE_PROVIDER_ORDER:
            provider = providers.get(key)
            if provider is not None and provider.configured():
                return provider
        # none configured — return the first registered hardware provider so
        # error messages and /config hints stay provider-specific and honest
        for key in HARDWARE_PROVIDER_ORDER:
            provider = providers.get(key)
            if provider is not None:
                return provider
        raise KeyError("no hardware provider registered")
    return providers["local_statevector"]


__all__ = [
    "BackendInfo",
    "ProviderError",
    "ProviderJobFailed",
    "ProviderNotConfigured",
    "ProviderRateLimited",
    "ProviderResult",
    "ProviderResultError",
    "ProviderStatusInfo",
    "ProviderSubmission",
    "QuantumProvider",
    "normalize_status",
    "IBMQuantumProvider",
    "IQMProvider",
    "SimulatorProvider",
    "SIMULATOR_BACKEND_NAME",
    "CREDENTIALS_HINT",
    "IQM_CREDENTIALS_HINT",
    "HARDWARE_PROVIDER_ORDER",
    "build_default_providers",
    "provider_for_mode",
]
