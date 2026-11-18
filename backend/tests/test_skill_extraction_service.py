from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.models.job import Job
from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_skill import JobSkill
from backend.app.models.skill import Skill
from backend.app.schemas.ai import ExtractedSkill, JobAnalysisResult
from backend.app.services import skill_extraction_service as service


class PostgresSessionView:
    """Use SQLite for tests while exposing PostgreSQL transaction checks."""

    def __init__(self, session):
        self.session = session
        self.statements = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        self.statements.append(sql)
        if sql == "SET TRANSACTION READ ONLY":
            return None
        return self.session.execute(statement, *args, **kwargs)

    def commit(self):
        self.commit_calls += 1
        return self.session.commit()

    def rollback(self):
        self.rollback_calls += 1
        return self.session.rollback()

    def __getattr__(self, name):
        return getattr(self.session, name)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_job(session, *, active=True, description="Role requirements for a developer."):
    job = Job(
        source="test",
        board_token="test",
        external_id="job-1",
        title="Developer",
        company="Test Co",
        description=description,
        is_active=active,
    )
    session.add(job)
    session.commit()
    return job


def saved_result(*skills):
    return {
        "role_category": "software_engineering",
        "seniority": "unknown",
        "summary": "A software development position.",
        "skills": [
            {
                "name": name,
                "category": "programming_language",
                "requirement": requirement,
                "evidence": evidence,
            }
            for name, requirement, evidence in skills
        ],
    }


def add_existing_analysis(session, job, result, *, model="test-model"):
    analysis = JobAnalysis(
        job_id=job.id,
        content_hash=service.calculate_content_hash(job, model),
        model_name=model,
        status="success",
        result_json=result,
    )
    session.add(analysis)
    session.commit()
    return analysis


def add_skill_association(session, job, name, requirement, evidence):
    skill = Skill(
        name=name,
        normalized_name=service.normalize_skill_name(name),
        category="programming_language",
    )
    session.add(skill)
    session.flush()
    session.add(
        JobSkill(
            job_id=job.id,
            skill_id=skill.id,
            requirement=requirement,
            evidence=evidence,
        )
    )
    session.commit()


@pytest.mark.parametrize("name", ["OIDC", "OpenID Connect", "openid-connect"])
def test_oidc_names_share_openid_connect_catalog_name(name):
    assert service.canonicalize_skill(name, "") == "OpenID Connect"
    assert service.normalize_skill_name(
        service.canonicalize_skill(name, "")
    ) == service.normalize_skill_name("OpenID Connect")


@pytest.mark.parametrize(
    "name",
    ["Git", "GitLab", "Ruby on Rails", "Java", "Python"],
)
def test_oidc_canonicalization_does_not_change_other_skill_names(name):
    assert service.canonicalize_skill(name, "") == name


def test_get_or_create_skill_reuses_oidc_canonical_identity(db_session, monkeypatch):
    monkeypatch.setattr(service, "pg_insert", sqlite_insert)
    first = service.get_or_create_skill(db_session, "OIDC", "concept")
    second = service.get_or_create_skill(db_session, "OpenID Connect", "concept")

    assert first == second
    assert db_session.scalars(select(Skill)).all()[0].name == "OpenID Connect"


def test_get_or_create_reuses_historical_oidc_row_without_rewriting_it(
    db_session, monkeypatch
):
    monkeypatch.setattr(service, "pg_insert", sqlite_insert)
    historical = Skill(
        name="OIDC",
        normalized_name="oidc",
        category="concept",
    )
    db_session.add(historical)
    db_session.commit()
    historical_id = historical.id

    reused_id = service.get_or_create_skill(
        db_session,
        "OpenID Connect",
        "concept",
    )

    skills = db_session.scalars(select(Skill)).all()
    assert reused_id == historical_id
    assert [(skill.id, skill.name) for skill in skills] == [(historical_id, "OIDC")]


@pytest.fixture
def prepared_unchanged_job(db_session, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    job = add_job(db_session)
    result = saved_result(("Python", "required", "Strong experience with Python."))
    add_existing_analysis(db_session, job, result)
    add_skill_association(
        db_session,
        job,
        "Python",
        "required",
        "Strong experience with Python.",
    )
    job_id = job.id
    db_session.expire_all()
    return job_id


def test_complete_analysis_and_associations_are_unchanged(
    db_session, prepared_unchanged_job, monkeypatch
):
    view = PostgresSessionView(db_session)
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record_sql)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))

    result = service.process_job(view, prepared_unchanged_job)
    event.remove(db_session.bind, "before_cursor_execute", record_sql)

    assert result["status"] == "unchanged"
    assert statements[0].upper().startswith("SELECT")
    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for sql in statements
    )
    assert view.commit_calls == 0
    assert view.rollback_calls == 1


@pytest.mark.parametrize("association_mode", ["none", "partial"])
def test_incomplete_associations_report_inconsistent_without_gemini(
    db_session, monkeypatch, association_mode
):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    job = add_job(db_session)
    evidence = "Python and Java experience are required."
    result_json = saved_result(
        ("Python", "required", evidence),
        ("Java", "required", evidence),
    )
    add_existing_analysis(db_session, job, result_json)
    if association_mode == "partial":
        add_skill_association(db_session, job, "Python", "required", evidence)
    job_id = job.id
    db_session.expire_all()

    view = PostgresSessionView(db_session)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))
    result = service.process_job(view, job_id)

    assert result["status"] == "inconsistent"
    assert "Java" in result["reason"]
    assert view.commit_calls == 0
    assert view.rollback_calls == 1


def test_oidc_alias_duplicates_in_analysis_match_single_canonical_association(
    db_session, monkeypatch
):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    job = add_job(db_session)
    result_json = saved_result(
        ("OIDC", "mentioned", "OIDC is used."),
        ("OpenID Connect", "required", "OpenID Connect experience is required."),
    )
    add_existing_analysis(db_session, job, result_json)
    add_skill_association(
        db_session,
        job,
        "OpenID Connect",
        "required",
        "OpenID Connect experience is required.",
    )
    job_id = job.id
    db_session.expire_all()

    view = PostgresSessionView(db_session)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))
    assert service.process_job(view, job_id)["status"] == "unchanged"


def test_duplicate_historical_oidc_associations_report_inconsistent(
    db_session, monkeypatch
):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    job = add_job(db_session)
    result_json = saved_result(("OIDC", "required", "OIDC experience is required."))
    add_existing_analysis(db_session, job, result_json)
    add_skill_association(
        db_session, job, "OIDC", "required", "OIDC experience is required."
    )
    add_skill_association(
        db_session,
        job,
        "OpenID Connect",
        "required",
        "OIDC experience is required.",
    )
    job_id = job.id
    db_session.expire_all()

    view = PostgresSessionView(db_session)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))
    result = service.process_job(view, job_id)

    assert result["status"] == "inconsistent"
    assert "asocieri duplicate" in result["reason"]


@pytest.mark.parametrize(
    ("job_options", "analysis_mode", "expected"),
    [
        ({}, "none", "would_process"),
        ({"active": False}, "none", "inactive"),
        ({"description": "  "}, "none", "empty_description"),
    ],
)
def test_dry_run_statuses_are_read_only(
    db_session, monkeypatch, job_options, analysis_mode, expected
):
    job = add_job(db_session, **job_options)
    if analysis_mode == "complete":
        result = saved_result(("Python", "required", "Python is required."))
        add_existing_analysis(db_session, job, result)
        add_skill_association(db_session, job, "Python", "required", "Python is required.")

    view = PostgresSessionView(db_session)
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record_sql)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))
    result = service.process_job(view, job.id)
    event.remove(db_session.bind, "before_cursor_execute", record_sql)

    assert result["status"] == expected
    assert view.statements[0] == "SET TRANSACTION READ ONLY"
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )
    assert view.commit_calls == 0
    assert view.rollback_calls == 1


def test_dry_run_unchanged_status_uses_read_only_transaction(
    db_session, prepared_unchanged_job, monkeypatch
):
    view = PostgresSessionView(db_session)
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record_sql)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))
    result = service.process_job(view, prepared_unchanged_job)
    event.remove(db_session.bind, "before_cursor_execute", record_sql)

    assert result["status"] == "unchanged"
    assert view.statements[0] == "SET TRANSACTION READ ONLY"
    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for sql in statements
    )
    assert view.commit_calls == 0
    assert view.rollback_calls == 1


def test_dry_run_rejects_an_already_started_transaction(db_session, monkeypatch):
    db_session.execute(select(1))
    view = PostgresSessionView(db_session)
    monkeypatch.setattr(service, "extract_job_analysis", lambda **_: pytest.fail("Gemini called"))

    with pytest.raises(RuntimeError, match="without an active transaction"):
        service.process_job(view, 1)

    assert view.statements == []
    assert view.commit_calls == 0
    assert view.rollback_calls == 0


def result_for_reanalysis():
    return JobAnalysisResult(
        role_category="software_engineering",
        seniority="unknown",
        summary="A developer role requiring Java skills.",
        skills=[
            ExtractedSkill(
                name="Java",
                category="programming_language",
                requirement="required",
                evidence="Java experience is required.",
            )
        ],
    )


@pytest.mark.parametrize("failure", ["gemini", "skill", "association", "analysis"])
def test_reanalysis_failures_roll_back_and_preserve_old_results(
    db_session, monkeypatch, failure
):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setattr(service, "pg_insert", sqlite_insert)
    job = add_job(db_session)
    old_json = saved_result(("Python", "required", "Python is required."))
    analysis = add_existing_analysis(db_session, job, old_json)
    add_skill_association(db_session, job, "Python", "required", "Python is required.")
    job.description = "Changed description requiring Java."
    db_session.commit()
    original_hash = analysis.content_hash

    if failure == "gemini":
        def fail_gemini(**_):
            raise RuntimeError("mock Gemini failure")

        monkeypatch.setattr(service, "extract_job_analysis", fail_gemini)
    else:
        monkeypatch.setattr(service, "extract_job_analysis", lambda **_: result_for_reanalysis())

    if failure == "skill":
        def fail_skill_insert(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("INSERT INTO SKILLS"):
                raise RuntimeError("mock skill save failure")

        event.listen(db_session.bind, "before_cursor_execute", fail_skill_insert)
    elif failure == "association":
        def fail_association_insert(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("INSERT INTO JOB_SKILLS"):
                raise RuntimeError("mock association save failure")

        event.listen(db_session.bind, "before_cursor_execute", fail_association_insert)
    elif failure == "analysis":
        def fail_analysis_update(session, _flush_context, _instances):
            if any(isinstance(item, JobAnalysis) for item in session.dirty):
                raise RuntimeError("mock analysis update failure")

        event.listen(db_session, "before_flush", fail_analysis_update)

    view = PostgresSessionView(db_session)
    with pytest.raises(RuntimeError):
        service.process_job(view, job.id, apply=True)

    event.remove(db_session.bind, "before_cursor_execute", fail_skill_insert) if failure == "skill" else None
    event.remove(db_session.bind, "before_cursor_execute", fail_association_insert) if failure == "association" else None
    event.remove(db_session, "before_flush", fail_analysis_update) if failure == "analysis" else None

    db_session.expire_all()
    saved_analysis = db_session.scalar(
        select(JobAnalysis).where(JobAnalysis.job_id == job.id)
    )
    associations = db_session.execute(
        select(Skill.name, JobSkill.requirement, JobSkill.evidence)
        .join(JobSkill, JobSkill.skill_id == Skill.id)
        .where(JobSkill.job_id == job.id)
    ).all()

    assert saved_analysis.content_hash == original_hash
    assert saved_analysis.result_json == old_json
    assert associations == [("Python", "required", "Python is required.")]
    assert view.rollback_calls == 1
    assert view.commit_calls == (1 if failure in {"association", "analysis"} else 0)


def test_process_job_reports_gemini_request_at_sdk_boundary(
    db_session, monkeypatch
):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setattr(service, "pg_insert", sqlite_insert)
    job = add_job(db_session)
    job_id = job.id
    db_session.commit()
    calls = []

    def fake_extraction(**kwargs):
        kwargs["on_request"]()
        return result_for_reanalysis()

    monkeypatch.setattr(service, "extract_job_analysis", fake_extraction)
    view = PostgresSessionView(db_session)
    result = service.process_job(
        view,
        job_id,
        apply=True,
        on_gemini_request=lambda: calls.append(job_id),
    )

    assert result["status"] == "saved"
    assert calls == [job_id]
