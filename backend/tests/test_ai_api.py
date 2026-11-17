import pytest

from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.dependencies import get_db
from backend.app.main import app

from backend.app.models.job import Job
from backend.app.models.skill import Skill
from backend.app.models.job_skill import JobSkill
from backend.app.models.job_analysis import JobAnalysis


@pytest.fixture
def db_session():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(test_engine)

    try:
        with Session(test_engine) as session:
            yield session
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def create_job(
    db,
    external_id="job-1",
    title="Python Developer",
    is_active=True,
):
    job = Job(
        source="greenhouse",
        board_token="test-company",
        external_id=external_id,
        title=title,
        company="Test Company",
        location="Remote",
        description="Python and Git experience required.",
        url="https://example.com/job",
        departments=["Engineering"],
        offices=["Remote"],
        is_active=is_active,
    )

    db.add(job)
    db.flush()

    return job


def create_skill(
    db,
    name="Git",
    normalized_name="git",
    category="tool",
):
    skill = Skill(
        name=name,
        normalized_name=normalized_name,
        category=category,
    )

    db.add(skill)
    db.flush()

    return skill


def test_get_job_analysis_returns_analysis_and_skills(client, db_session):
    job = create_job(db_session)

    skill = create_skill(db_session)

    db_session.add(
        JobSkill(
            job_id=job.id,
            skill_id=skill.id,
            requirement="required",
            evidence="Experience with Git.",
        )
    )

    db_session.add(
        JobAnalysis(
            job_id=job.id,
            content_hash="test-hash",
            model_name="gemini-test",
            status="success",
            category="software_engineering",
            seniority="mid",
            summary="Python developer with Git experience.",
            result_json={
                "role_category": "software_engineering",
                "seniority": "mid",
                "skills": [],
            },
        )
    )

    db_session.commit()

    response = client.get(
        f"/api/v1/jobs/{job.id}/analysis"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["job_id"] == job.id
    assert data["status"] == "success"
    assert data["category"] == "software_engineering"
    assert data["seniority"] == "mid"
    assert data["model_name"] == "gemini-test"

    assert len(data["skills"]) == 1
    assert data["skills"][0]["name"] == "Git"
    assert data["skills"][0]["requirement"] == "required"


def test_get_job_analysis_returns_404_for_missing_job(client):
    response = client.get(
        "/api/v1/jobs/999999/analysis"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found."


def test_get_job_analysis_returns_404_when_analysis_missing(
    client,
    db_session,
):
    job = create_job(db_session)

    db_session.commit()

    response = client.get(
        f"/api/v1/jobs/{job.id}/analysis"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "AI analysis not found for this job."
    )


def test_list_skills_returns_job_counts_and_filters(
    client,
    db_session,
):
    git = create_skill(db_session)

    python_skill = create_skill(
        db_session,
        name="Python",
        normalized_name="python",
        category="programming_language",
    )

    job1 = create_job(
        db_session,
        external_id="job-1",
    )

    job2 = create_job(
        db_session,
        external_id="job-2",
        title="Backend Developer",
    )

    db_session.add_all([
        JobSkill(
            job_id=job1.id,
            skill_id=git.id,
            requirement="required",
            evidence="Experience with Git.",
        ),
        JobSkill(
            job_id=job2.id,
            skill_id=git.id,
            requirement="preferred",
            evidence="Git knowledge is preferred.",
        ),
        JobSkill(
            job_id=job1.id,
            skill_id=python_skill.id,
            requirement="required",
            evidence="Experience with Python.",
        ),
    ])

    db_session.commit()

    response = client.get(
        "/api/v1/skills?q=git"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Git"
    assert data["items"][0]["job_count"] == 2

    category_response = client.get(
        "/api/v1/skills?category=programming_language"
    )

    assert category_response.status_code == 200
    assert category_response.json()["total"] == 1
    assert category_response.json()["items"][0]["name"] == "Python"


def test_list_jobs_for_skill_returns_only_active_by_default(
    client,
    db_session,
):
    git = create_skill(db_session)

    active_job = create_job(
        db_session,
        external_id="active-job",
        title="Active Python Developer",
        is_active=True,
    )

    inactive_job = create_job(
        db_session,
        external_id="inactive-job",
        title="Inactive Python Developer",
        is_active=False,
    )

    db_session.add_all([
        JobSkill(
            job_id=active_job.id,
            skill_id=git.id,
            requirement="required",
            evidence="Experience with Git.",
        ),
        JobSkill(
            job_id=inactive_job.id,
            skill_id=git.id,
            requirement="mentioned",
            evidence="Git is mentioned.",
        ),
    ])

    db_session.commit()

    response = client.get(
        f"/api/v1/skills/{git.id}/jobs"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["skill"]["name"] == "Git"
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["job_id"] == active_job.id
    assert data["items"][0]["is_active"] is True

    all_response = client.get(
        f"/api/v1/skills/{git.id}/jobs?active_only=false"
    )

    assert all_response.status_code == 200
    assert all_response.json()["total"] == 2


def test_list_jobs_for_missing_skill_returns_404(client):
    response = client.get(
        "/api/v1/skills/999999/jobs"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found."
