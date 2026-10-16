"""IQMProvider — real hardware path via the IQM Quantum API (iqm-client).

Executes the fixed QRNG circuit (|0⟩ → H → measure) on a real IQM QPU
using the *native* IQM circuit format (``iqm.pulse.Circuit``), because the
``qiskit-iqm`` adapter's qiskit pin conflicts with this project's qiskit
version. The math is exact:

    H = R_y(π/2) · Z  and  Z|0⟩ = |0⟩
    ⇒  prx(angle=π/2, phase=π/2) ≡ R_y(π/2) on |0⟩ prepares |+⟩ = H|0⟩

so ``prx(π/2, π/2)`` followed by a Z-basis ``measure`` is *exactly* the
approved QRNG circuit — no approximation, no adapter needed.

Quantum-computer handling (verified against IQM Resonance, iqm-client 36):
  * ``IQM_SERVER_URL`` points at the server (e.g. https://resonance.iqm.tech).
  * The server reports the quantum computers it controls (real QPUs and
    ``:mock`` simulators). We discover them LIVE and expose every REAL QPU
    as a backend choice; ``:mock`` aliases are rejected in hardware mode
    (they are simulators — hardware mode must never silently use one).
  * Selection order: explicit request (API backend parameter) > pinned
    ``IQM_QUANTUM_COMPUTER`` > deterministic default (first real QPU in
    server order). Names are never invented.

Non-negotiable rules implemented here (mirrors ibm_provider.py):
  * Bits returned by get_job_result() come ONLY from the provider's
    per-shot measurement data (``get_job_measurements``) — never from
    counts, never from any local random source.
  * Qubit names are taken from the LIVE dynamic quantum architecture —
    never invented.
  * Credentials are read server-side from config only; every message
    that could echo provider data goes through redact().
  * Token refresh happens server-side (Cortex Keycloak or OAuth token
    endpoint). Tokens are never logged and never returned to the client.
  * Auth retries never duplicate a quantum job: a 401 means the request
    was REJECTED (no job created), so a single retry after refresh is
    safe; ambiguous failures (timeouts) are never blindly retried.
"""

from __future__ import annotations

import base64
import json
import math
import threading
import time
import uuid as uuid_mod
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..config import IQMConfig, load_iqm_config, redact
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
)

IQM_CREDENTIALS_HINT = (
    "IQM hardware mode needs IQM_SERVER_URL and IQM_ACCESS_TOKEN in app/backend/.env "
    "(see .env.example). Get them from the IQM Resonance dashboard (long-lived token) "
    "or your IQM/Cortex tokens. For a short-lived access/refresh-token pair, also "
    "configure the matching IQM_AUTH_SERVER_URL or IQM_AUTH_TOKEN_URL. The server "
    "picks up settings on the next submission — no restart needed. Simulator mode "
    "remains separate and is always labelled as simulation."
)

# deterministic register key for the single measured bit
IQM_REGISTER_KEY = "qrng_bit"

# proactive refresh margin: refresh when the access token has less than this left
_REFRESH_MARGIN_S = 120.0
# TTLs for live server state (qubit names / QC lists only change with new
# calibrations or maintenance — short caches are honest and cheap)
_ARCH_CACHE_TTL = 300.0
_QC_LIST_CACHE_TTL = 60.0
_BACKENDS_CACHE_TTL = 120.0
_AUTH_REQUEST_TIMEOUT_S = 20.0


def _jwt_seconds_left(token: Optional[str]) -> float:
    """Seconds until JWT expiry, or +inf for non-JWT (long-lived) tokens.

    Mirrors iqm.station_control.client.authentication.TokenManager.time_left_seconds
    without importing the private helper.
    """
    if not token or token.count(".") != 2:
        return float("inf")            # opaque long-lived token — no expiry info
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)          # fix base64 padding
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = float(data.get("exp", 0))
        return exp - time.time() if exp else float("inf")
    except Exception:
        return float("inf")            # cannot parse — assume it stays valid


@dataclass(frozen=True)
class _QC:
    """A quantum computer reported by the IQM server (never invented)."""

    alias: str                        # API selector, e.g. "garnet"
    display_name: str                 # UI name from the server, e.g. "IQM Garnet"

    @property
    def is_mock(self) -> bool:
        return self.alias.endswith(":mock")


class IQMProvider(QuantumProvider):
    name = "iqm"
    label = "IQM Quantum — real QPU hardware"
    is_simulator = False

    NOT_CONFIGURED_REASON = "IQM_SERVER_URL / IQM_ACCESS_TOKEN are not set on the server"
    SETUP_HINT = IQM_CREDENTIALS_HINT
    SETUP_STEPS = [
        "Create an IQM Resonance account at resonance.iqm.tech (or use your "
        "on-prem IQM server) and obtain an access token — from the dashboard, or "
        "from `cortex auth login` if you have a Cortex tokens file",
        "Copy your server URL (e.g. https://resonance.iqm.tech) and the access token",
        "Put them in app/backend/.env: IQM_SERVER_URL=… and IQM_ACCESS_TOKEN=…. "
        "For an OAuth access/refresh pair, also set IQM_REFRESH_TOKEN and the "
        "matching IQM_AUTH_SERVER_URL or IQM_AUTH_TOKEN_URL. The server picks up "
        "settings on the next submission — no restart needed",
    ]

    def __init__(self, config_loader: Callable[[], IQMConfig] = load_iqm_config,
                 client_factory: Optional[Callable[..., Any]] = None,
                 refresh_client: Optional[Any] = None) -> None:
        """``client_factory`` / ``refresh_client`` are injection points for
        tests (no network in unit tests). Production uses iqm-client."""
        self._config_loader = config_loader
        self._client_factory = client_factory          # tests: fake IQMClient
        self._refresh_client = refresh_client          # tests: fake requests-like
        self._lock = threading.RLock()
        # in-memory token state (never logged, never returned)
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_source: Optional[str] = None       # config access token the state came from
        # per-quantum-computer client cache, invalidated when the token changes
        self._clients: dict[Optional[str], Any] = {}
        self._clients_key: Optional[tuple] = None      # (server_url, access_token)
        # live server state caches
        self._qc_cache: Optional[tuple[float, list[_QC]]] = None
        self._arch_cache: dict[Optional[str], tuple[float, Any]] = {}
        self._backends_cache: Optional[tuple[float, list[BackendInfo]]] = None
        self._trackers: dict[str, Any] = {}            # provider_job_id -> CircuitJobTracker
        self._submit_meta: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ config

    def configured(self) -> bool:
        """Re-read config each call so tokens added to .env later are detected."""
        return self._config_loader().configured

    def _require_config(self) -> IQMConfig:
        cfg = self._config_loader()
        if not cfg.configured:
            raise ProviderNotConfigured(
                "IQM Quantum credentials are not configured on this server.",
                IQM_CREDENTIALS_HINT,
            )
        return cfg

    # ------------------------------------------------------------------ clients

    def _construct_client(self, cfg: IQMConfig, qc: Optional[str]) -> Any:
        """Build a raw IQMClient. May raise the SDK's ClientConfigurationError
        (e.g. when the server controls several QPUs and none was chosen) —
        callers decide how to translate/parse it."""
        if self._client_factory is not None:
            return self._client_factory(url=cfg.server_url, quantum_computer=qc,
                                        token=self._access_token)
        from iqm.iqm_client import IQMClient

        return IQMClient.from_url(cfg.server_url, quantum_computer=qc,
                                  token=self._access_token)

    def _get_client(self, cfg: Optional[IQMConfig] = None,
                    qc: Optional[str] = None) -> Any:
        """Build (or reuse) an IQMClient for the CURRENT in-memory token state
        and the given quantum computer. Rebuilt whenever the config's token
        changes (operator edited .env) or we refreshed the access token."""
        cfg = cfg or self._require_config()
        with self._lock:
            self._sync_tokens(cfg)
            key = (cfg.server_url, self._access_token)
            if self._clients_key != key:
                self._clients = {}
                self._clients_key = key
                self._qc_cache = None
                self._arch_cache = {}
                self._backends_cache = None
            if qc in self._clients:
                return self._clients[qc]
            try:
                client = self._construct_client(cfg, qc)
            except Exception as exc:
                raise self._translate(exc, "connecting to the IQM server") from exc
            self._clients[qc] = client
            return client

    def _sync_tokens(self, cfg: IQMConfig) -> None:
        """Adopt config tokens when the config identity changes (keeps our
        refreshed tokens otherwise)."""
        if self._token_source != cfg.access_token:
            self._access_token = cfg.access_token
            self._refresh_token = cfg.refresh_token
            self._token_source = cfg.access_token
            self._clients = {}                # force rebuild for the new token
            self._clients_key = None

    # ------------------------------------------------------------------ refresh

    def _refresh_endpoint(self, cfg: IQMConfig) -> Optional[tuple[str, dict[str, str], Optional[tuple[str, str]]]]:
        """(url, form_data, basic_auth) for the configured refresh flow, or None."""
        if cfg.auth_token_url:
            url = cfg.auth_token_url
        elif cfg.auth_server_url:
            url = (
                f"{cfg.auth_server_url.rstrip('/')}/realms/{cfg.auth_realm}"
                "/protocol/openid-connect/token"
            )
        else:
            return None
        data = {
            "client_id": cfg.auth_client_id,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token or "",
        }
        basic = (
            (cfg.auth_client_id, cfg.auth_client_secret)
            if cfg.auth_token_url and cfg.auth_client_secret
            else None
        )
        return url, data, basic

    def _maybe_refresh(self, cfg: IQMConfig, *, force: bool = False) -> bool:
        """Refresh the access token when it is about to expire.

        Returns True when a refresh was attempted and succeeded, False when
        no refresh was needed. Raises ProviderError when a refresh is
        REQUIRED but fails — before any quantum job is created (so retries
        never duplicate jobs).
        """
        with self._lock:
            self._sync_tokens(cfg)
            if not cfg.refresh_token:
                return False                  # long-lived token — nothing to do
            if not force and _jwt_seconds_left(self._access_token) > _REFRESH_MARGIN_S:
                return False
            endpoint = self._refresh_endpoint(cfg)
            if endpoint is None:
                raise ProviderError(
                    "PROVIDER_AUTH_REFRESH_FAILED",
                    "The IQM access token has expired and no refresh endpoint is configured.",
                    "Set IQM_AUTH_SERVER_URL (Cortex CLI flow) or IQM_AUTH_TOKEN_URL "
                    "(api.iqm.com OAuth flow) in app/backend/.env to enable automatic "
                    "refresh, or update IQM_ACCESS_TOKEN with a fresh token.",
                )
            url, data, basic = endpoint
            try:
                if self._refresh_client is not None:
                    response = self._refresh_client.post(url, data=data, auth=basic,
                                                         timeout=_AUTH_REQUEST_TIMEOUT_S)
                else:
                    import requests

                    response = requests.post(
                        url, data=data, auth=basic, timeout=_AUTH_REQUEST_TIMEOUT_S
                    )
            except Exception as exc:
                raise ProviderError(
                    "PROVIDER_AUTH_REFRESH_FAILED",
                    f"Could not reach the IQM authentication server while refreshing the "
                    f"access token ({redact(type(exc).__name__)}).",
                    "Check IQM_AUTH_SERVER_URL / IQM_AUTH_TOKEN_URL and network access. "
                    "No quantum job was submitted.",
                ) from exc
            if response.status_code != 200:
                raise ProviderError(
                    "PROVIDER_AUTH_REFRESH_FAILED",
                    "IQM refused to refresh the access token "
                    f"(HTTP {response.status_code}). The refresh token may be expired or revoked.",
                    "Re-authenticate (e.g. `cortex auth login`) and update IQM_ACCESS_TOKEN / "
                    "IQM_REFRESH_TOKEN in app/backend/.env. No quantum job was submitted.",
                )
            try:
                payload = response.json()
                new_access = payload.get("access_token")
                if not new_access:
                    raise ValueError("no access_token in response")
            except Exception as exc:
                raise ProviderError(
                    "PROVIDER_AUTH_REFRESH_FAILED",
                    "The IQM authentication server returned an unexpected refresh response.",
                    "No quantum job was submitted.",
                ) from exc
            self._access_token = new_access
            if payload.get("refresh_token"):
                self._refresh_token = payload["refresh_token"]
            self._clients = {}                # rebuild clients with the new token
            self._clients_key = None
            self._qc_cache = None
            self._arch_cache = {}
            self._backends_cache = None
            return True

    def _is_auth_error(self, exc: Exception) -> bool:
        """401/403-class failures: the request was REJECTED, never executed."""
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return True
        name = type(exc).__name__.lower()
        return "auth" in name and "error" in name

    def _call(self, action: str, fn: Callable[[Any], Any], *,
              allow_refresh_retry: bool = True, qc: Optional[str] = None) -> Any:
        """Run ``fn(client)`` with proactive + reactive token refresh.

        A 401-class rejection means the request was NOT executed (no job
        created), so one retry after a forced refresh is safe. Network
        timeouts / connection errors are never retried here — the caller
        decides what is safe to repeat.
        """
        cfg = self._require_config()
        if qc is None:
            qc = self._resolve_qc(cfg)
        self._maybe_refresh(cfg)
        try:
            return fn(self._get_client(cfg, qc))
        except ProviderError as exc:
            # Client construction can itself fail with a translated auth
            # ProviderError. Preserve its classification and still honor the
            # existing one-time refresh path for a rejected credential.
            if allow_refresh_retry and cfg.refresh_token and exc.code == "PROVIDER_AUTH_FAILED":
                refreshed = self._maybe_refresh(cfg, force=True)
                if refreshed:
                    try:
                        return fn(self._get_client(cfg, qc))
                    except ProviderError:
                        raise
                    except Exception as exc2:
                        raise self._translate(exc2, action) from exc2
            raise
        except Exception as exc:
            if allow_refresh_retry and cfg.refresh_token and self._is_auth_error(exc):
                refreshed = self._maybe_refresh(cfg, force=True)
                if refreshed:
                    try:
                        return fn(self._get_client(cfg, qc))
                    except ProviderError:
                        raise
                    except Exception as exc2:
                        raise self._translate(exc2, action) from exc2
            raise self._translate(exc, action) from exc

    # ------------------------------------------------------------------ quantum computers

    def _discover_qcs(self, cfg: IQMConfig) -> list[_QC]:
        """LIVE quantum-computer list from the server (aliases + display names).

        Discovery path for multi-QPU servers (e.g. IQM Resonance): building a
        client without a quantum_computer raises ClientConfigurationError
        whose message lists the available aliases — we parse it, then ask a
        real client for the full list (display names, ids).
        """
        now = time.monotonic()
        with self._lock:
            if self._qc_cache is not None and now - self._qc_cache[0] < _QC_LIST_CACHE_TTL:
                return self._qc_cache[1]
            self._sync_tokens(cfg)

        qcs: list[_QC] = []
        try:
            client = self._construct_client(cfg, None)   # single-QPU server: works
        except Exception as exc:
            message = str(exc)
            marker = "Available quantum computers are:"
            if marker not in message:
                raise self._translate(exc, "connecting to the IQM server") from exc
            aliases = [a.strip() for a in message.split(marker, 1)[1].split(",") if a.strip()]
            qcs = [_QC(alias=a, display_name=a) for a in aliases]
            first_real = next((a for a in aliases if not a.endswith(":mock")), None)
            if first_real is None:
                raise ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "The IQM server reports no real quantum computers (only mocks).",
                    "Hardware mode requires a real QPU — mocks are simulators.",
                )
            try:
                client = self._construct_client(cfg, first_real)
            except Exception:
                # the parsed aliases alone are enough to operate
                with self._lock:
                    self._qc_cache = (now, qcs)
                return qcs
            else:
                upgraded = self._qcs_from_client(client)     # full list: ids + display names
                if upgraded:
                    qcs = upgraded
        else:
            if not qcs:
                qcs = self._qcs_from_client(client)

        with self._lock:
            self._qc_cache = (now, qcs)
        return qcs

    @staticmethod
    def _qcs_from_client(client: Any) -> list[_QC]:
        """Quantum-computer list from a constructed client (real SDK or fake)."""
        listed = getattr(client, "quantum_computers", None)     # test fakes
        if listed is not None:
            return [
                _QC(alias=qc.alias, display_name=getattr(qc, "display_name", qc.alias))
                for qc in listed
            ]
        try:                                                     # real SDK v36
            inner = getattr(getattr(client, "_executor", None), "client", None)
            if inner is not None:
                return [
                    _QC(alias=qc.alias, display_name=qc.display_name)
                    for qc in inner._get_quantum_computers()
                ]
        except Exception:
            pass
        return []

    def _resolve_qc(self, cfg: IQMConfig, requested: Optional[str] = None) -> Optional[str]:
        """Effective quantum computer alias for a call.

        Precedence: explicit request > pinned config (IQM_QUANTUM_COMPUTER) >
        deterministic default (first REAL QPU in server order). ``None`` means
        "let the server decide" (single-QPU servers). Mocks are always
        rejected — hardware mode must never run on a simulator.
        """
        qcs = self._discover_qcs(cfg)
        aliases = {qc.alias for qc in qcs}
        real = [qc for qc in qcs if not qc.is_mock]

        choice = requested or cfg.quantum_computer
        if choice and choice != "auto":
            if aliases and choice not in aliases:
                raise ProviderError(
                    "INVALID_BACKEND",
                    f"Quantum computer '{choice}' does not exist on this IQM server.",
                    f"Real quantum computers available: {', '.join(qc.alias for qc in real) or 'none'}."
                    if real else "No real quantum computer is currently available.",
                )
            if choice.endswith(":mock"):
                raise ProviderError(
                    "SIMULATOR_BACKEND_REJECTED",
                    f"'{choice}' is a mock quantum computer — hardware mode requires a real QPU.",
                    "Pick a real quantum computer (no ':mock' suffix) or use AUTO selection.",
                )
            return choice
        if not qcs:
            return None                     # server not asked yet / single-QPU server
        if not real:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                "The IQM server reports no real quantum computers (only mocks).",
                "Hardware mode requires a real QPU. Check your IQM Resonance subscription.",
            )
        return real[0].alias

    # ------------------------------------------------------------------ circuit

    def create_qrng_circuit(self) -> Any:
        """Build the fixed QRNG circuit in IQM native form.

        The qubit name is taken from the LIVE dynamic quantum architecture
        (cached briefly) — never invented. Returns an ``iqm.pulse.Circuit``.
        """
        qubit, _arch, _qc = self._select_qubit()
        return self._build_circuit(qubit)

    @staticmethod
    def _build_circuit(qubit: str) -> Any:
        from iqm.pulse.circuit_operations import Circuit, CircuitOperation

        return Circuit(
            name="qrng_h_measure",
            instructions=(
                # prx(π/2, π/2) = R_y(π/2): exactly H·Z on |0⟩ ⇒ prepares |+⟩ = H|0⟩
                CircuitOperation(
                    "prx", locus=(qubit,),
                    args={"angle": math.pi / 2, "phase": math.pi / 2},
                ),
                CircuitOperation(
                    "measure", locus=(qubit,),
                    args={"key": IQM_REGISTER_KEY, "feedback_key": IQM_REGISTER_KEY},
                ),
            ),
        )

    def validate_circuit(self, circuit: Any) -> None:
        """Validate the fixed QRNG circuit against the LIVE architecture
        (client-side, no job submitted) + enforce the exact QRNG shape."""
        from iqm.iqm_client.validation import CircuitValidationError, validate_circuit_instructions

        instructions = list(getattr(circuit, "instructions", ()) or ())
        problems: list[str] = []
        if len(instructions) != 2:
            problems.append(f"expected exactly 2 instructions (prx, measure), found {len(instructions)}")
        else:
            prx, measure = instructions
            if prx.name != "prx" or measure.name != "measure":
                problems.append(
                    f"expected (prx, measure), found ({prx.name}, {measure.name})"
                )
            if prx.name == "prx":
                angle = float(prx.args.get("angle", 0.0))
                phase = float(prx.args.get("phase", 0.0))
                if abs(angle - math.pi / 2) > 1e-9 or abs(phase - math.pi / 2) > 1e-9:
                    problems.append("prx must be exactly (angle=π/2, phase=π/2)")
            if measure.name == "measure" and measure.args.get("key") != IQM_REGISTER_KEY:
                problems.append(f"measure key must be '{IQM_REGISTER_KEY}'")
        if problems:
            raise ProviderError(
                "CIRCUIT_REJECTED",
                "circuit rejected by fixed QRNG spec: " + "; ".join(problems),
                "Every hardware run uses the approved |0⟩ → H → measure circuit only.",
            )

        _ts, arch, _qc = self._architecture()
        try:
            validate_circuit_instructions(arch, [circuit])
        except CircuitValidationError as exc:
            raise ProviderError(
                "CIRCUIT_REJECTED",
                f"IQM rejected the QRNG circuit against the live architecture: {redact(str(exc))}",
                "The QPU calibration may have changed — retrying re-reads the architecture.",
            ) from exc

    # ------------------------------------------------------------------ architecture / backends

    def _architecture(self, qc: Optional[str] = None) -> tuple[float, Any, Optional[str]]:
        """Live dynamic quantum architecture (qubit names + native ops), cached
        per quantum computer."""
        cfg = self._require_config()
        if qc is None:
            qc = self._resolve_qc(cfg)
        now = time.monotonic()
        with self._lock:
            cached = self._arch_cache.get(qc)
            if cached is not None and now - cached[0] < _ARCH_CACHE_TTL:
                return cached[0], cached[1], qc
        arch = self._call(
            "fetching the IQM quantum architecture",
            lambda client: client.get_dynamic_quantum_architecture(),
            qc=qc,
        )
        with self._lock:
            self._arch_cache[qc] = (now, arch)
        return now, arch, qc

    def _select_qubit(self) -> tuple[str, Any, Optional[str]]:
        """Deterministic qubit choice: configured qubit if it exists live,
        else the FIRST qubit of the live architecture (server order)."""
        cfg = self._require_config()
        qc = self._resolve_qc(cfg)
        _ts, arch, qc = self._architecture(qc)
        qubits = list(getattr(arch, "qubits", ()) or [])
        if not qubits:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"The IQM server reported a quantum architecture with no qubits for '{qc}'.",
                "The QPU may be under maintenance — check IQM Resonance status.",
            )
        if cfg.qubit:
            if cfg.qubit not in qubits:
                raise ProviderError(
                    "INVALID_BACKEND",
                    f"Configured IQM_QUBIT '{cfg.qubit}' does not exist on '{qc}' "
                    f"(live qubits: {', '.join(qubits[:8])}…).",
                    "Remove IQM_QUBIT from .env to use automatic selection, or set a "
                    "real qubit name from the live architecture.",
                )
            return cfg.qubit, arch, qc
        return qubits[0], arch, qc

    def get_backend_metadata(self, name: Optional[str] = None) -> list[BackendInfo]:
        """REAL quantum computers this server controls, with live metadata.

        Every entry's name is the server-reported alias, qubit count and
        health come from live calls, and ``:mock`` (simulator) quantum
        computers are excluded — hardware mode must never offer them.
        """
        cfg = self._require_config()
        now = time.monotonic()
        with self._lock:
            if self._backends_cache is not None and now - self._backends_cache[0] < _BACKENDS_CACHE_TTL:
                infos = self._backends_cache[1]
                return [i for i in infos if name in (None, i.name)]
        qcs = [qc for qc in self._discover_qcs(cfg) if not qc.is_mock]
        infos: list[BackendInfo] = []
        for qc in qcs:
            try:
                _ts, arch, _ = self._architecture(qc.alias)
                qubits = len(getattr(arch, "qubits", ()) or [])
                healthy, message = True, f"{qc.display_name} — live architecture verified"
                try:
                    health = self._call(
                        f"checking health of quantum computer '{qc.alias}'",
                        lambda client: client.get_health(), qc=qc.alias,
                    )
                    if isinstance(health, dict):
                        status = health.get("operational_status")
                        nested = health.get("health") or {}
                        if status and str(status).lower() not in ("online", "ok"):
                            healthy, message = False, f"{qc.display_name} — status: {status}"
                        elif "healthy" in nested and not nested["healthy"]:
                            healthy = False
                            message = f"{qc.display_name} — server reports unhealthy"
                except ProviderError as exc:
                    healthy, message = False, f"{qc.display_name} — {redact(exc.message)}"
                infos.append(BackendInfo(
                    name=qc.alias,
                    simulator=False,
                    operational=healthy,
                    pending_jobs=None,        # IQM does not expose queue depth — never fabricated
                    qubits=qubits,
                    status_message=message,
                ))
            except ProviderError as exc:
                infos.append(BackendInfo(
                    name=qc.alias,
                    simulator=False,
                    operational=False,
                    pending_jobs=None,
                    qubits=None,
                    status_message=f"{qc.display_name} — {redact(exc.message)}",
                ))
        with self._lock:
            self._backends_cache = (now, infos)
        return [i for i in infos if name in (None, i.name)]

    # ------------------------------------------------------------------ submit

    def submit_job(
        self,
        circuit: Any,
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
        cfg = self._require_config()

        # resolve the quantum computer: explicit request > pinned config > default
        requested = backend if backend not in (None, "auto") else None
        if requested and cfg.quantum_computer and requested != cfg.quantum_computer:
            raise ProviderError(
                "INVALID_BACKEND",
                f"Backend '{requested}' conflicts with the pinned IQM_QUANTUM_COMPUTER "
                f"'{cfg.quantum_computer}'.",
                "Remove the pin from .env to allow choosing a quantum computer per job.",
            )
        qc = self._resolve_qc(cfg, requested)
        qubit = circuit.instructions[0].locus[0]

        # refresh BEFORE submitting: a rejected submission never creates a job,
        # so this proactive refresh also guarantees the retry below is safe
        self._maybe_refresh(cfg)

        def _do_submit(client: Any) -> Any:
            return client.submit_circuits([circuit], shots=shots)

        try:
            tracker = self._call(
                f"submitting to IQM quantum computer '{qc or 'default'}'", _do_submit, qc=qc
            )
            provider_job_id = str(tracker.job_id)
        except ProviderRateLimited:
            raise
        except ProviderError:
            raise                          # already translated (incl. auth retry inside _call)

        backend_name = qc or self._url_tail(cfg)
        with self._lock:
            self._trackers[provider_job_id] = tracker
            self._submit_meta[provider_job_id] = {
                "backend": backend_name,
                "qc": qc,
                "shots": shots,
                "submitted_at": time.time(),
            }
        return ProviderSubmission(
            provider_job_id=provider_job_id,
            backend=backend_name,
            submitted_at=str(tracker.job_id),
            transpiled_ops=[
                f"prx(π/2, π/2) @ {qubit}",
                f"measure → '{IQM_REGISTER_KEY}' @ {qubit}",
            ],
            raw={"provider": "iqm"},
        )

    @staticmethod
    def _url_tail(cfg: IQMConfig) -> str:
        # honest fallback display name derived from the server URL
        return (cfg.server_url or "").rstrip("/").rsplit("/", 1)[-1] or "iqm-server"

    # ------------------------------------------------------------------ status

    def _tracker(self, provider_job_id: str) -> Any:
        with self._lock:
            tracker = self._trackers.get(provider_job_id)
        if tracker is not None:
            return tracker
        # re-attach after a restart: ask the server for the job (on the quantum
        # computer it was submitted to, when we know it)
        cfg = self._require_config()
        with self._lock:
            qc = (self._submit_meta.get(provider_job_id) or {}).get("qc")
        if qc is None:
            qc = self._resolve_qc(cfg)

        def _fetch(client: Any) -> Any:
            return client.get_job(uuid_mod.UUID(provider_job_id))

        tracker = self._call(f"fetching IQM job '{provider_job_id}'", _fetch, qc=qc)
        with self._lock:
            self._trackers[provider_job_id] = tracker
        return tracker

    _IQM_STATUS_MAP = {
        "WAITING": (JobState.QUEUED, "job is waiting in the IQM queue"),
        "PROCESSING": (JobState.RUNNING, "circuit is executing on the IQM QPU"),
        "COMPLETED": (JobState.COMPLETED, "measurements returned by the IQM QPU"),
        "FAILED": (JobState.FAILED, None),
        "CANCELLED": (JobState.CANCELLED, "job was cancelled"),
    }

    def get_job_status(self, provider_job_id: str) -> ProviderStatusInfo:
        tracker = self._tracker(provider_job_id)

        def _update(client: Any) -> Any:
            tracker.update()
            return tracker.status

        raw = self._call(f"updating IQM job status '{provider_job_id}'", _update)
        name = str(getattr(raw, "name", raw)).upper()
        mapped = self._IQM_STATUS_MAP.get(name)
        if mapped is None:
            return ProviderStatusInfo(
                JobState.RUNNING,
                detail=f"unrecognized IQM job status reported: {redact(str(raw))}",
            )
        state, detail = mapped
        if state is JobState.FAILED:
            errors = getattr(tracker, "errors", None)
            detail = redact(str(errors)) if errors else "IQM reported a job failure"
        return ProviderStatusInfo(state, detail)

    # ------------------------------------------------------------------ result

    def get_job_result(self, provider_job_id: str, shots: int) -> ProviderResult:
        """PER-SHOT measurement retrieval — the number is never derived
        from aggregate counts."""
        def _measurements(client: Any) -> Any:
            return client.get_job_measurements(uuid_mod.UUID(provider_job_id))

        results = self._call(f"retrieving IQM measurements for job '{provider_job_id}'", _measurements)
        bits, counts = self._extract_bits(results, shots)

        with self._lock:
            meta = dict(self._submit_meta.get(provider_job_id) or {})
        cfg = self._config_loader()
        metadata: dict[str, Any] = {
            "job_id": provider_job_id,
            "register": IQM_REGISTER_KEY,
            "measurement_retrieval": "per-shot (get_job_measurements)",
            "bit_order": "shot order, first shot = first bit",
        }
        qc = meta.get("qc")
        if qc:
            cached = self._arch_cache.get(qc)
            calibration = getattr(cached[1], "calibration_set_id", None) if cached else None
            if calibration:
                metadata["calibration_set_id"] = str(calibration)
            display = next(
                (q.display_name for q in (self._qc_cache[1] if self._qc_cache else []) if q.alias == qc),
                None,
            )
            if display:
                metadata["quantum_computer"] = display
        backend_name = meta.get("backend") or (qc or self._url_tail(cfg))
        return ProviderResult(
            provider_job_id=provider_job_id,
            backend=backend_name,
            bits=bits,
            counts=counts,
            metadata=metadata,
        )

    @staticmethod
    def _extract_bits(results: Any, shots: int) -> tuple[str, dict[str, int]]:
        """Strict extraction from CircuitMeasurementResults.

        Shape: list (per circuit) of {register_key: [shot][bit]}.
        We submitted ONE circuit with ONE single-qubit register, so we expect
        exactly one result dict and one register; every shot must carry
        exactly one 0/1 outcome. Anything else is an honest error.
        """
        try:
            if not isinstance(results, list) or len(results) != 1:
                raise ProviderResultError(
                    f"IQM returned {len(results) if isinstance(results, list) else 'non-list'} "
                    f"circuit result(s), expected exactly 1.",
                    "The job payload does not match the single-circuit QRNG submission.",
                )
            registers = dict(results[0] or {})
            if IQM_REGISTER_KEY in registers:
                rows = registers[IQM_REGISTER_KEY]
            elif len(registers) == 1:
                rows = next(iter(registers.values()))  # defensive: server renamed the register
            else:
                raise ProviderResultError(
                    f"IQM result registers {sorted(registers)} do not contain "
                    f"'{IQM_REGISTER_KEY}'.",
                    "Unexpected measurement register layout.",
                )
            bits = ""
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) != 1:
                    raise ProviderResultError(
                        "IQM returned a multi-bit measurement row for a single-qubit circuit.",
                        "Expected exactly one measured bit per shot.",
                    )
                value = row[0]
                if value not in (0, 1):
                    raise ProviderResultError(
                        f"IQM returned a measurement outcome outside {{0, 1}}: {value!r}.",
                        "Refusing to use unexpected qubit outcomes.",
                    )
                bits += str(int(value))
        except ProviderResultError:
            raise
        except Exception as exc:
            raise ProviderResultError(
                f"Could not read per-shot measurement data from the IQM result: {redact(str(exc))}",
                "The job may not have produced a usable payload.",
            ) from exc
        if len(bits) != shots:
            raise ProviderResultError(
                f"IQM returned {len(bits)} measurement outcomes, expected {shots}.",
                "Refusing to display bits that do not match the requested shot count.",
            )
        counts = {"0": bits.count("0"), "1": bits.count("1")}
        return bits, counts

    # ------------------------------------------------------------------ errors

    def _redact_tokens(self, text: str) -> str:
        """Defense in depth: strip the provider's CURRENT in-memory tokens
        (including refreshed ones that env-based redact() cannot know)."""
        for token in (self._access_token, self._refresh_token):
            if token and len(token) >= 4 and token in text:
                text = text.replace(token, "[REDACTED]")
        return text

    def _translate(self, exc: Exception, action: str) -> ProviderError:
        """Normalize iqm-client / network exceptions into ProviderError, redacted."""
        status_code = getattr(exc, "status_code", None)
        name = type(exc).__name__
        raw = f"{name}: {exc}" if str(exc) else name
        message = self._redact_tokens(redact(raw))

        if status_code == 429 or "429" in str(status_code or ""):
            return ProviderRateLimited(
                f"IQM rate limit hit while {action}.",
                retry_after=60.0,
                hint="IQM Resonance limits submission frequency. Wait for the cooldown and retry.",
            )
        if status_code in (401, 403) or "auth" in name.lower():
            return ProviderError(
                "PROVIDER_AUTH_FAILED",
                f"IQM rejected the credentials while {action} ({message}).",
                "Check IQM_ACCESS_TOKEN (and IQM_REFRESH_TOKEN) in app/backend/.env — "
                "the token may be expired or revoked.",
            )
        if "CircuitValidation" in name:
            return ProviderError(
                "CIRCUIT_REJECTED",
                f"IQM rejected the circuit while {action} ({message}).",
                "The QPU calibration may not support this circuit right now.",
            )
        if status_code == 404 or "NotFound" in name:
            return ProviderError(
                "PROVIDER_NOT_FOUND",
                f"IQM returned 'not found' while {action} ({message}).",
                "The job, quantum computer, or server URL may be wrong.",
            )
        if "GatewayTimeout" in name or "OperationTimeout" in name or "Timeout" in name:
            return ProviderError(
                "PROVIDER_TIMEOUT",
                f"IQM timed out while {action} ({message}).",
                "The QPU may be busy. The job status is retained — refresh before "
                "resubmitting to avoid duplicate quantum jobs.",
            )
        if status_code and int(status_code) >= 500:
            return ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"IQM service error while {action} ({message}).",
                "This is on IQM's side — retry in a moment.",
            )
        if "Connection" in name or "requests.exceptions" in str(type(exc)):
            return ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"Could not reach the IQM server while {action} ({message}).",
                "Check IQM_SERVER_URL and network access.",
            )
        return ProviderError(
            "PROVIDER_ERROR",
            f"IQM failure while {action} ({message}).",
            "Check the backend log for details, then retry. No bits were fabricated.",
        )
