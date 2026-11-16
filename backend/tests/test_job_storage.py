from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.models.job import Job
from backend.app.services.job_service import upsert_jobs


def test_insert_and_update_job():

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    try:

        with Session(engine) as db:

            job = {
                "source": "greenhouse",
                "board_token": "gitlab",
                "external_id": "12345",
                "title": "Python Developer",
                "company": "GitLab",
                "location": "Remote",
                "description": "Python and FastAPI",
                "url": "https://example.com/job/12345",
                "updated_at": None,
                "departments": ["Engineering"],
                "offices": ["Remote"],
            }

            first = upsert_jobs(db, [job])

            assert first["inserted"] == 1
            assert first["updated"] == 0

            updated_job = {
                **job,
                "title": "Senior Python Developer",
            }

            second = upsert_jobs(db, [updated_job])

            assert second["inserted"] == 0
            assert second["updated"] == 1

            saved_jobs = db.scalars(
                select(Job)
            ).all()

            assert len(saved_jobs) == 1

            assert (
                saved_jobs[0].title
                == "Senior Python Developer"
            )

    finally:

        Base.metadata.drop_all(engine)
        engine.dispose()