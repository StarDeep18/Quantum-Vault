"""API error envelope — every failure is actionable, never generic.

Shape (PRD §8.5):

    {"error": {"code": "...", "message": "...", "hint": "...", "retry_after": n}}
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..config import redact
from ..providers.base import ProviderError, ProviderNotConfigured, ProviderRateLimited


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 hint: Optional[str] = None, retry_after: Optional[float] = None,
                 details: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint
        self.retry_after = retry_after
        self.details = details

    def to_response(self) -> JSONResponse:
        body: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
            }
        }
        if self.retry_after is not None:
            body["error"]["retry_after"] = round(self.retry_after, 1)
            body["error"]["hint"] = (
                (self.hint or "") + f" Retry in ~{self.retry_after:.0f}s."
            ).strip()
        if self.details is not None:
            body["error"]["details"] = self.details
        headers = {}
        if self.status_code == 429 and self.retry_after is not None:
            headers["Retry-After"] = str(int(self.retry_after) + 1)
        return JSONResponse(status_code=self.status_code, content=body, headers=headers)


def provider_error_to_api(exc: ProviderError) -> ApiError:
    if isinstance(exc, ProviderNotConfigured):
        return ApiError(400, exc.code, exc.message, exc.hint)
    if exc.code in ("INVALID_SHOTS", "INVALID_BACKEND", "INVALID_SEED", "INVALID_REQUEST",
                    "SIMULATOR_BACKEND_REJECTED"):
        return ApiError(400, exc.code, exc.message, exc.hint)
    if exc.code == "JOB_NOT_FOUND":
        return ApiError(404, exc.code, exc.message, exc.hint)
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None or exc.code == "RATE_LIMITED" or exc.code == "SUBMIT_COOLDOWN":
        return ApiError(429, exc.code, exc.message, exc.hint, retry_after=retry_after)
    return ApiError(502, exc.code, exc.message, exc.hint)


def install_error_handlers(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return exc.to_response()

    @app.exception_handler(ProviderError)
    async def _provider_error(_: Request, exc: ProviderError):
        return provider_error_to_api(exc).to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        problems = []
        for item in exc.errors():
            where = ".".join(str(p) for p in item.get("loc", []))
            problems.append(f"{where or 'body'}: {item.get('msg', 'invalid value')}")
        return ApiError(
            422,
            "VALIDATION_ERROR",
            "Request parameters are invalid: " + "; ".join(problems[:5]),
            "Check the request shape — see docs/TRD.md §9–§11 for the API contract.",
            details={"errors": exc.errors()[:10]},
        ).to_response()

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return ApiError(
            500,
            "INTERNAL_ERROR",
            redact(f"Unexpected server error: {type(exc).__name__}"),
            "Check the server log — no bits were generated.",
        ).to_response()
