"""LANDY Creator — FastAPI application.

Entrypoint: uvicorn landy.main:app --host 0.0.0.0 --port $PORT

All configuration is read from environment variables via landy.config.settings.
Never hard-code secrets, ports, or service URLs here.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from landy.config import settings
from landy.logging_setup import configure_logging, logger
from landy.routes import health, auth
from landy.routes import documents, analyses

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("landy_api_start", version="0.2.0")
    # Bootstrap MinIO bucket — logged as warning on failure, not crash
    try:
        from landy.storage import bootstrap_bucket
        bootstrap_bucket()
    except Exception as exc:
        logger.warning(
            "storage_bootstrap_failed",
            error=str(exc),
            note="MinIO not reachable — uploads will fail until storage is available",
        )
    yield
    logger.info("landy_api_stop")


app = FastAPI(
    title="LANDY Creator API",
    description=(
        "Contract review and negotiation coaching for Indonesian content creators. "
        "This API provides legal information, not legal advice."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router,     prefix="/api")
app.include_router(auth.router,       prefix="/api/auth")
app.include_router(documents.router,  prefix="/api/documents",  tags=["documents"])
app.include_router(analyses.router,   prefix="/api/analyses",   tags=["analyses"])
