import logging
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.app.api.jobs import router as jobs_router
from backend.app.api.ingestion import router as ingestion_router
from backend.app.api.ai import router as ai_router

from backend.app.core.logging_config import configure_logging

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
