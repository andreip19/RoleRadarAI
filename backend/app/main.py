import logging
import time

from contextlib import asynccontextmanager

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.jobs import router as jobs_router
from backend.app.api.ingestion import router as ingestion_router
from backend.app.api.ai import router as ai_router

from backend.app.core.logging_config import configure_logging
from backend.app.core.security import app_environment, validate_production_config

from backend.app.core.metrics import (
    HTTP_REQUESTS,
    HTTP_REQUEST_DURATION,
)

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.db.migrations import migrate_sqlite_schema

from backend.app.models.job import Job
from backend.app.models.ingestion_run import IngestionRun


configure_logging()

logger = logging.getLogger("roleradar.http")


@asynccontextmanager
async def lifespan(app: FastAPI):

    validate_production_config()

    Base.metadata.create_all(bind=engine)

    migrate_sqlite_schema()

    logger.info("application_started")

    yield

    logger.info("application_stopped")


app = FastAPI(
    title="RoleRadar AI",
    description="Intelligent Job Discovery and Career Matching Platform",
    version="0.6.0",
    lifespan=lifespan,
)


def configured_cors_origins() -> list[str]:
    origins = [
        origin.strip().rstrip("/")
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if app_environment() == "development":
        origins.extend(("http://localhost:5173", "http://127.0.0.1:5173"))
    origins = list(dict.fromkeys(origins))
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS cannot contain a wildcard.")
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)


@app.middleware("http")
async def monitor_http_requests(
    request: Request,
    call_next,
):
    """Measure HTTP request count and processing duration."""

    started = time.perf_counter()

    status_code = 500

    try:

        response = await call_next(request)

        status_code = response.status_code

        return response

    except Exception:

        logger.exception("http_request_failed")

        raise

    finally:

        duration = time.perf_counter() - started

        route = request.scope.get("route")

        route_path = getattr(
            route,
            "path",
            "unmatched",
        )

        method = request.method

        HTTP_REQUESTS.labels(
            method=method,
            route=route_path,
            status=str(status_code),
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=method,
            route=route_path,
        ).observe(duration)

        logger.info(
            "http_request",
            extra={
                "method": method,
                "route": route_path,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 3),
            },
        )


@app.get("/")
async def root():

    return {
        "project": "RoleRadar AI",
        "status": "running",
        "version": "0.6.0",
    }


@app.get("/health")
async def health():

    return {
        "status": "healthy",
        "service": "backend",
    }


@app.get("/ready")
async def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning(
            "readiness_database_unavailable",
            extra={"error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "backend"},
        )

    return {"status": "ready", "service": "backend"}


@app.get(
    "/metrics",
    include_in_schema=False,
)
def prometheus_metrics():

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


app.include_router(jobs_router)
app.include_router(ingestion_router)
app.include_router(ai_router)
