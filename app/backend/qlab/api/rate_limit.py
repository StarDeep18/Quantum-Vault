"""Lightweight in-memory rate limiting for public API endpoints (TRD §18).

  * per-client general request budget (protects the single-process MVP)
  * no external services; resets on restart, which is fine for the MVP
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response

from .errors import ApiError

GENERAL_LIMIT = 240          # requests
GENERAL_WINDOW = 60.0        # seconds


class RateLimiter:
    def __init__(self, limit: int = GENERAL_LIMIT, window: float = GENERAL_WINDOW) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = self.window - (now - bucket[0])
            raise ApiError(
                429,
                "RATE_LIMITED",
                "Too many requests from this client.",
                "Slow down — the lab is a single-server prototype.",
                retry_after=max(1.0, retry_after),
            )
        bucket.append(now)


async def rate_limit_middleware(request: Request, call_next):
    limiter: RateLimiter = request.app.state.rate_limiter
    client = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/api/"):
        limiter.check(client)
    response: Response = await call_next(request)
    return response
