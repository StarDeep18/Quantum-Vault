"""Server-side configuration.

Rules enforced here (TRD §6, §18 and docs/architecture.md §15):
  * IBM and IQM credentials are read only from the server environment or
    server-side .env files and are NEVER returned by any API response.
  * A secret-redaction helper is applied to all backend logging so tokens
    cannot end up in log output.
  * Provider configuration is re-checked at submission time, so settings
    added to .env while the server is running are picked up without a
    restart (still server-side only).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

# .../app/backend/qlab/config.py
#   parents[1] = app/backend   (where .env and ./data live by default)
#   parents[3] = repo root     (where .env.example lives)
_BACKEND_DIR = Path(__file__).resolve().parents[1]          # .../app/backend
_REPO_ROOT = Path(__file__).resolve().parents[3]            # repo root
_ENV_FILES = (                                              # later files win
    _REPO_ROOT / ".env",
    _BACKEND_DIR / ".env",
)

logger = logging.getLogger("qlab.config")


# ---------------------------------------------------------------------------
# .env file reading (process environment always takes precedence)
# ---------------------------------------------------------------------------

_file_cache: dict[str, tuple[float, dict[str, str]]] = {}


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a .env file with a mtime-based cache. Returns non-empty values."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cached = _file_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    values = {k: v for k, v in dotenv_values(path).items() if v not in (None, "")}
    _file_cache[str(path)] = (mtime, values)
    return values


def _file_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in _ENV_FILES:
        merged.update(_read_env_file(path))
    return merged


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Effective setting: process environment first, then .env files."""
    value = os.environ.get(name)
    if value:
        return value
    return _file_env().get(name, default)


def review_demo_enabled() -> bool:
    """Explicit, opt-in presentation mode. Defaults OFF and never submits a QPU job."""
    raw = (get_setting("QUANTUM_REVIEW_DEMO", "false") or "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, lo: int, hi: int) -> int:
    raw = get_setting(name, str(default))
    try:
        val = int(str(raw))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# IBM Quantum provider configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IBMConfig:
    api_key: Optional[str]
    instance: Optional[str]          # optional CRN — account default used when empty
    channel: str                     # "ibm_quantum_platform" (current IBM Quantum Platform)
    pinned_backend: Optional[str]    # optional fixed backend name; None = AUTO (least busy)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_ibm_config() -> IBMConfig:
    """Fresh read on every call (cheap, mtime-cached) so tokens added to
    .env while the server runs are detected at the next submission."""
    channel = (get_setting("IBM_QUANTUM_CHANNEL") or "ibm_quantum_platform").strip()
    if channel not in ("ibm_quantum_platform", "ibm_cloud", "ibm_quantum"):
        channel = "ibm_quantum_platform"
    return IBMConfig(
        api_key=(get_setting("IBM_QUANTUM_API_KEY") or "").strip() or None,
        instance=(get_setting("IBM_QUANTUM_INSTANCE") or "").strip() or None,
        channel=channel,
        pinned_backend=(get_setting("IBM_QUANTUM_BACKEND") or "").strip() or None,
    )


# ---------------------------------------------------------------------------
# IQM Quantum (real hardware provider when configured)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IQMConfig:
    """IQM Resonance / on-prem server configuration (all server-side only).

    The access token may be either a long-lived Resonance dashboard token
    (no refresh) or a short-lived access token paired with a refresh token
    (Cortex CLI / IQM user-management OAuth world).
    """

    server_url: Optional[str]           # e.g. https://resonance.iqm.tech (QCs discovered live)
    access_token: Optional[str]
    refresh_token: Optional[str]        # optional — enables automatic refresh
    quantum_computer: Optional[str]     # optional QC id/alias when the server controls several
    qubit: Optional[str]                # optional explicit qubit name (must exist in the live architecture)
    auth_token_url: Optional[str]       # explicit OAuth token endpoint (api.iqm.com style)
    auth_server_url: Optional[str]      # Keycloak base URL (Cortex CLI style)
    auth_realm: str = "cortex"
    auth_client_id: str = "iqm_client"
    auth_client_secret: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.server_url and self.access_token)

    @property
    def refresh_configured(self) -> bool:
        """True when we have a refresh token AND an endpoint to use it against."""
        return bool(self.refresh_token and (self.auth_token_url or self.auth_server_url))


def load_iqm_config() -> IQMConfig:
    """Fresh read on every call (mtime-cached file env) so tokens added to
    .env while the server runs are detected at the next submission."""
    return IQMConfig(
        server_url=(get_setting("IQM_SERVER_URL") or "").strip() or None,
        access_token=(get_setting("IQM_ACCESS_TOKEN") or "").strip() or None,
        refresh_token=(get_setting("IQM_REFRESH_TOKEN") or "").strip() or None,
        quantum_computer=(get_setting("IQM_QUANTUM_COMPUTER") or "").strip() or None,
        qubit=(get_setting("IQM_QUBIT") or "").strip() or None,
        auth_token_url=(get_setting("IQM_AUTH_TOKEN_URL") or "").strip() or None,
        auth_server_url=(get_setting("IQM_AUTH_SERVER_URL") or "").strip() or None,
        auth_realm=(get_setting("IQM_AUTH_REALM") or "cortex").strip() or "cortex",
        auth_client_id=(get_setting("IQM_AUTH_CLIENT_ID") or "iqm_client").strip() or "iqm_client",
        auth_client_secret=(get_setting("IQM_AUTH_CLIENT_SECRET") or "").strip() or None,
    )


# ---------------------------------------------------------------------------
# Lab limits
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Limits:
    min_shots: int = 8
    max_shots: int = 4096
    default_shots: int = 256
    max_bits: int = 8192
    default_bits: int = 256
    job_timeout_s: int = 3600           # allow real hardware queue time; late status refresh remains supported
    submit_cooldown_s: int = 13         # local guard for IBM's 5 jobs/min limit
    poll_initial_s: float = 2.0
    poll_max_s: float = 15.0
    max_seed_length: int = 256


def load_limits() -> Limits:
    return Limits(
        min_shots=_get_int("QRNG_MIN_SHOTS", 8, 1, 10000),
        max_shots=_get_int("QRNG_MAX_SHOTS", 4096, 1, 100000),
        default_shots=_get_int("QRNG_DEFAULT_SHOTS", 256, 1, 100000),
        max_bits=_get_int("PRNG_MAX_BITS", 8192, 1, 1_000_000),
        default_bits=_get_int("PRNG_DEFAULT_BITS", 256, 1, 1_000_000),
        job_timeout_s=_get_int("QRNG_JOB_TIMEOUT_SECONDS", 3600, 10, 86400),
        submit_cooldown_s=_get_int("QRNG_SUBMIT_COOLDOWN_SECONDS", 13, 0, 3600),
    )


def data_dir() -> Path:
    raw = get_setting("QRLAB_DATA_DIR", "./data")
    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND_DIR / path
    return path


# ---------------------------------------------------------------------------
# Secret hygiene
# ---------------------------------------------------------------------------

SECRET_ENV_KEYS = (
    "IBM_QUANTUM_API_KEY",
    "IQM_ACCESS_TOKEN",
    "IQM_REFRESH_TOKEN",
    "IQM_AUTH_CLIENT_SECRET",
)


def active_secrets() -> list[str]:
    """Current secret *values* (used for redaction only — never logged)."""
    secrets: list[str] = []
    for key in SECRET_ENV_KEYS:
        value = get_setting(key) or ""
        if len(value) >= 4:
            secrets.append(value)
    return secrets


def redact(text: str) -> str:
    """Replace any occurrence of an active secret value with a placeholder."""
    for secret in active_secrets():
        if secret in text:
            text = text.replace(secret, "[REDACTED]")
    return text


class SecretRedactingFilter(logging.Filter):
    """Logging filter that guarantees secrets never reach log output."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:                               # pragma: no cover
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def install_logging() -> None:
    """Attach the redaction filter + sane formatting to the qlab logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    )
    handler.addFilter(SecretRedactingFilter())
    root = logging.getLogger("qlab")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
