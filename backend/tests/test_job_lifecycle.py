from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.models.job import Job

from backend.app.services.job_service import (
    deactivate_missing_jobs,
    upsert_jobs,
)


def make_job(external_id: str, title: str) -> dict:

    return {
        "source": "greenhouse",
        "board_token": "demo",
        "external_id": external_id,
        "title": title,
        "company": "Demo Company",
        "location": "Remote",
        "description": "Python and FastAPI",
        "url": f"https://example.com/jobs/{external_id}",
        "updated_at": None,
        "departments": ["Engineering"],
        "offices": ["Remote"],
    }


def test_job_deactivation_and_reactivation():

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    try:

        with Session(engine) as db:

            jobs = [
                make_job("job-1", "Python Developer"),
                make_job("job-2", "Backend Engineer"),
            ]

            first = upsert_jobs(db, jobs)

            assert first["inserted"] == 2

            # First successful collection without job-2.
            first_missing = deactivate_missing_jobs(
                db=db,
                source="greenhouse",
                board_token="demo",
                observed_external_ids=["job-1"],
            )

            assert first_missing == 0

            job = db.scalar(
                select(Job).where(
                    Job.external_id == "job-2"
                )
            )

            assert job.is_active is True
            assert job.missing_runs == 1
            assert job.inactive_at is None

            # Second consecutive successful collection.
            second_missing = deactivate_missing_jobs(
                db=db,
                source="greenhouse",
                board_token="demo",
                observed_external_ids=["job-1"],
            )

            assert second_missing == 1

            job = db.scalar(
                select(Job).where(
                    Job.external_id == "job-2"
                )
            )

            assert job.is_active is False
            assert job.missing_runs == 2
            assert job.inactive_at is not None

            # The job appears again.
            restored = upsert_jobs(
                db,
                [make_job("job-2", "Backend Engineer")],
            )

            assert restored["inserted"] == 0
            assert restored["updated"] == 1
            assert restored["reactivated"] == 1

            job = db.scalar(
                select(Job).where(
                    Job.external_id == "job-2"
                )
            )

            assert job.is_active is True
            assert job.missing_runs == 0
            assert job.inactive_at is None

            # An empty collection must never deactivate all jobs.
            protected = deactivate_missing_jobs(
                db=db,
                source="greenhouse",
                board_token="demo",
                observed_external_ids=[],
            )

            assert protected == 0

    finally:
        engine.dispose()
