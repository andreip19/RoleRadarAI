from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.jobs import router as jobs_router
from backend.app.api.ingestion import router as ingestion_router

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.db.migrations import migrate_sqlite_schema

from backend.app.models.job import Job
from backend.app.models.ingestion_run import IngestionRun


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Create missing tables first.
    Base.metadata.create_all(bind=engine)

    # Apply additive migrations to existing SQLite tables.
    migrate_sqlite_schema()

    yield


app = FastAPI(
    title="RoleRadar AI",
    description="Intelligent Job Discovery and Career Matching Platform",
    version="0.5.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():

    return {
        "project": "RoleRadar AI",
        "status": "running",
        "version": "0.5.0",
    }


@app.get("/health")
async def health():

    return {
        "status": "healthy",
        "service": "backend",
    }


app.include_router(jobs_router)
app.include_router(ingestion_router)
