from __future__ import annotations

import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import health, documents, query
from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup / shutdown hooks. Slack integration is disabled."""
    logger.info(
        "Starting KnowledgeAssist API (env=%s, model=%s)",
        settings.environment,
        settings.groq_model,
    )
    yield
    logger.info("Shutting down")


# ── App factory ──────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Company Knowledge Assistant API",
        description="RAG-based internal document Q&A — multi-tenant, source-cited answers.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
    )

    # ── CORS ──────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate limiting middleware ───────────────────────────────
    from app.api.routes.query import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Routers ───────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(query.router)

    # ── Global exception handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method, request.url, exc, exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred. Please try again later."},
        )

    return app


app = create_app()
