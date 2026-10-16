"""FastAPI application entry point.

Run (development):
    uvicorn qlab.main:app --host 127.0.0.1 --port 8000

Run (single-server demo — serves the built frontend + API on one port):
    cd app/frontend && npm run build      # produces app/frontend/dist
    uvicorn qlab.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.errors import install_error_handlers
from .api.rate_limit import RateLimiter, rate_limit_middleware
from .api.routes_experiments import router as experiments_router
from .api.routes_prng import router as prng_router
from .api.routes_qrng import router as qrng_router
from .config import install_logging
from .runtime import Runtime, build_runtime

install_logging()
logger = logging.getLogger("qlab.main")

_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(runtime: Runtime | None = None) -> FastAPI:
    app = FastAPI(
        title="Quantum Randomness Lab API",
        version=__version__,
        description=(
            "PRNG (deterministic SplitMix64) vs QRNG (real quantum hardware via IQM "
            "when configured, IBM Quantum as alternative, fixed circuit |0⟩ → H → "
            "measure). Every hardware bit originates from returned provider "
            "measurement data."
        ),
    )
    app.state.runtime = runtime or build_runtime()

    install_error_handlers(app)
    app.state.rate_limiter = RateLimiter()
    app.middleware("http")(rate_limit_middleware)

    app.include_router(prng_router)
    app.include_router(qrng_router)
    app.include_router(experiments_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "service": "quantum-randomness-lab"}

    # Serve the built frontend when present (single-server demo mode).
    if _FRONTEND_DIST.is_dir():
        assets = _FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            candidate = (_FRONTEND_DIST / full_path).resolve()
            if (str(candidate).startswith(str(_FRONTEND_DIST.resolve()))
                    and candidate.is_file()):
                return FileResponse(str(candidate))
            return FileResponse(str(_FRONTEND_DIST / "index.html"))
    else:

        @app.get("/", include_in_schema=False)
        def root():
            return JSONResponse(
                {
                    "service": "Quantum Randomness Lab API",
                    "version": __version__,
                    "docs": "/docs",
                    "note": "Frontend not built. Run the Vite dev server or `npm run build`.",
                }
            )

    @app.on_event("startup")
    def _startup() -> None:
        app.state.runtime.log_startup_summary()

    return app


app = create_app()
