from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.jobs import router as jobs_router
from backend.app.api.ingestion import router as ingestion_router

from backend.app.db.base import Base
from backend.app.db.session import engine

from backend.app.models.job import Job  # noqa: F401
from backend.app.models.ingestion_run import IngestionRun  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Create missing tables without modifying existing records.
    Base.metadata.create_all(bind=engine)

    yield


app = FastAPI(
    title="RoleRadar AI",
    description="Intelligent Job Discovery and Career Matching Platform",
    version="0.4.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():

    return {
        "project": "RoleRadar AI",
        "status": "running",
        "version": "0.4.0",
    }


@app.get("/health")
async def health():

    return {
        "status": "healthy",
        "service": "backend",
    }


app.include_router(jobs_router)
app.include_router(ingestion_router)
