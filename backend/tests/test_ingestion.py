import asyncio

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.models.job import Job
from backend.app.models.ingestion_run import IngestionRun

from backend.app.services import ingestion_service


def test_unified_ingestion_pipeline(monkeypatch):

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    greenhouse_job = {
        "source": "greenhouse",
        "board_token": "gitlab",
        "external_id": "test-gh-001",
        "title": "Python Developer",
        "company": "GitLab",
        "location": "Remote",
        "description": "Python and FastAPI",
        "url": "https://example.com/gh/001",
        "updated_at": None,
        "departments": ["Engineering"],
        "offices": ["Remote"],
    }

    lever_job = {
        "source": "lever",
        "board_token": "veeva",
        "external_id": "test-lever-001",
        "title": "Backend Engineer",
        "company": "Veeva Systems",
        "location": "Remote",
        "description": "Python and PostgreSQL",
        "url": "https://example.com/lever/001",
        "updated_at": None,
        "departments": ["Engineering"],
        "offices": ["Remote"],
    }

    async def fake_greenhouse(board_token):
        assert board_token == "gitlab"
        return [greenhouse_job]

    async def fake_lever(site, company_name, region):
        assert site == "veeva"
        assert company_name == "Veeva Systems"
        assert region == "global"
        return [lever_job]

    monkeypatch.setattr(
        ingestion_service,
        "fetch_greenhouse_jobs",
        fake_greenhouse,
    )

    monkeypatch.setattr(
        ingestion_service,
        "fetch_lever_jobs",
        fake_lever,
    )

    try:

        with Session(engine) as db:

            first = asyncio.run(
                ingestion_service.run_all_ingestion(db)
            )

            assert first["total_sources"] == 2
            assert first["succeeded"] == 2
            assert first["failed"] == 0

            assert sum(
                item["inserted"]
                for item in first["results"]
            ) == 2

            second = asyncio.run(
                ingestion_service.run_all_ingestion(db)
            )

            assert second["succeeded"] == 2

            assert sum(
                item["inserted"]
                for item in second["results"]
            ) == 0

            assert sum(
                item["updated"]
                for item in second["results"]
            ) == 2

            jobs_count = db.scalar(
                select(func.count()).select_from(Job)
            )

            runs_count = db.scalar(
                select(func.count()).select_from(IngestionRun)
            )

            assert jobs_count == 2
            assert runs_count == 4

    finally:
        engine.dispose()
