import csv
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.models.job import Job
from backend.app.models.job_skill import JobSkill
from backend.app.models.skill import Skill
from scripts import process_ai_jobs


class SQLiteReadOnlyView:
    """Exercise selector queries on SQLite while mocking PostgreSQL READ ONLY."""

    def __init__(self, session):
        self.session = session
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.session.close()

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        if str(statement) == "SET TRANSACTION READ ONLY":
            return None
        return self.session.execute(statement, *args, **kwargs)

    def in_transaction(self):
        return self.session.in_transaction()

    def rollback(self):
        return self.session.rollback()


class FakeSession:
    def __init__(self):
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        process_ai_jobs,
        "engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_job(session, job_id, *, active=True, title=None):
    job = Job(
        id=job_id,
        source="test",
        board_token="bulk-test",
        external_id=str(job_id),
        title=title or f"Job {job_id}",
        description="A sufficiently long job description for tests.",
        is_active=active,
    )
    session.add(job)
    return job


def test_all_active_selection_is_complete_active_only_and_id_sorted(
    sqlite_engine, monkeypatch
):
    with Session(sqlite_engine) as db:
        active_30 = add_job(db, 30)
        add_job(db, 10)
        inactive_20 = add_job(db, 20, active=False)
        skill = Skill(name="Python", normalized_name="python", category="programming_language")
        db.add(skill)
        db.flush()
        db.add(JobSkill(job_id=active_30.id, skill_id=skill.id, requirement="required", evidence="Python required."))
        db.add(JobSkill(job_id=inactive_20.id, skill_id=skill.id, requirement="mentioned", evidence="Python."))
        db.commit()

    views = []

    def readonly_session_factory():
        view = SQLiteReadOnlyView(Session(sqlite_engine))
        views.append(view)
        return view

    monkeypatch.setattr(process_ai_jobs, "SessionLocal", readonly_session_factory)
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(sqlite_engine, "before_cursor_execute", record_sql)
    targets = process_ai_jobs.select_job_targets(all_active=True)
    event.remove(sqlite_engine, "before_cursor_execute", record_sql)

    assert [target["job_id"] for target in targets] == [10, 30]
    assert [target["skills_count"] for target in targets] == [0, 1]
    assert views[0].statements[0] == "SET TRANSACTION READ ONLY"
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def make_targets(*job_ids):
    return [
        {"job_id": job_id, "title": f"Job {job_id}", "skills_count": 2}
        for job_id in job_ids
    ]


def test_batch_dry_run_is_sequential_and_does_not_count_gemini_calls(
    monkeypatch, tmp_path
):
    sessions = []
    calls = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append((job_id, apply))
        assert on_gemini_request is not None
        return {"status": "would_process", "title": f"Job {job_id}"}

    monkeypatch.setattr(process_ai_jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(process_ai_jobs, "process_job", process_spy)

    summary = process_ai_jobs.run_targets(
        make_targets(1, 2, 3),
        apply=False,
        report_path=str(tmp_path / "dry-run.csv"),
        all_active=True,
    )

    assert calls == [(1, False), (2, False), (3, False)]
    assert len({id(session) for session in sessions}) == 3
    assert all(session.closed for session in sessions)
    assert all(session.commit_calls == 0 for session in sessions)
    assert summary["would_process"] == 3
    assert summary["gemini_requests"] == 0


def test_apply_uses_one_session_commit_per_job(monkeypatch, tmp_path):
    sessions = []
    calls = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append(job_id)
        assert apply is True
        on_gemini_request()
        db.commit()
        return {"status": "saved", "skills_count": job_id % 3}

    monkeypatch.setattr(process_ai_jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(process_ai_jobs, "process_job", process_spy)

    summary = process_ai_jobs.run_targets(
        make_targets(1, 2, 3),
        apply=True,
        report_path=str(tmp_path / "apply.csv"),
        all_active=True,
    )

    assert calls == [1, 2, 3]
    assert len(sessions) == 3
    assert [session.commit_calls for session in sessions] == [1, 1, 1]
    assert all(session.closed for session in sessions)
    assert summary["saved"] == 3
    assert summary["gemini_requests"] == 3


def test_failed_job_rolls_back_and_batch_continues(monkeypatch, tmp_path):
    sessions = []
    calls = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append(job_id)
        if job_id == 2:
            raise RuntimeError("sensitive message should not enter report")
        db.commit()
        return {"status": "saved", "skills_count": 1}

    monkeypatch.setattr(process_ai_jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(process_ai_jobs, "process_job", process_spy)
    report_path = tmp_path / "errors.json"

    summary = process_ai_jobs.run_targets(
        make_targets(1, 2, 3),
        apply=True,
        report_format="json",
        report_path=str(report_path),
    )

    assert calls == [1, 2, 3]
    assert [session.rollback_calls for session in sessions] == [0, 1, 0]
    assert [session.commit_calls for session in sessions] == [1, 0, 1]
    assert summary["saved"] == 2
    assert summary["errors"] == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report[1]["error"] == "RuntimeError"
    assert "sensitive" not in report_path.read_text(encoding="utf-8")


def test_interrupted_batch_can_resume_and_unchanged_jobs_are_skipped(
    monkeypatch, tmp_path
):
    sessions = []
    first_run_calls = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    def interrupting_process(*, db, job_id, apply, on_gemini_request):
        first_run_calls.append(job_id)
        if job_id == 2:
            raise KeyboardInterrupt
        db.commit()
        return {"status": "saved", "skills_count": 1}

    monkeypatch.setattr(process_ai_jobs, "SessionLocal", session_factory)
    monkeypatch.setattr(process_ai_jobs, "process_job", interrupting_process)
    first = process_ai_jobs.run_targets(
        make_targets(1, 2, 3),
        apply=True,
        report_path=str(tmp_path / "interrupted.csv"),
    )

    assert first_run_calls == [1, 2]
    assert first["saved"] == 1
    assert first["interrupted_run"] is True
    assert sessions[0].commit_calls == 1
    assert sessions[1].rollback_calls == 1
    assert sessions[1].closed is True

    resume_calls = []

    def resumed_process(*, db, job_id, apply, on_gemini_request):
        resume_calls.append(job_id)
        if job_id == 1:
            return {"status": "unchanged", "skills_count": 1}
        on_gemini_request()
        db.commit()
        return {"status": "saved", "skills_count": 2}

    monkeypatch.setattr(process_ai_jobs, "process_job", resumed_process)
    resumed = process_ai_jobs.run_targets(
        make_targets(1, 2, 3),
        apply=True,
        report_path=str(tmp_path / "resumed.csv"),
    )

    assert resume_calls == [1, 2, 3]
    assert resumed["unchanged"] == 1
    assert resumed["saved"] == 2
    assert resumed["gemini_requests"] == 2


def test_inconsistent_status_is_reported_without_gemini(monkeypatch, tmp_path):
    session = FakeSession()
    monkeypatch.setattr(process_ai_jobs, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        process_ai_jobs,
        "process_job",
        lambda **_: {"status": "inconsistent", "reason": "details"},
    )

    summary = process_ai_jobs.run_targets(
        make_targets(4),
        apply=False,
        report_path=str(tmp_path / "inconsistent.csv"),
    )

    assert summary["inconsistent"] == 1
    assert summary["gemini_requests"] == 0
    with (tmp_path / "inconsistent.csv").open(encoding="utf-8-sig") as report_file:
        row = next(csv.DictReader(report_file))
    assert row["status"] == "inconsistent"
    assert row["pipeline_version"] == "9"


def test_batch_report_has_no_description_and_csv_title_is_safe(tmp_path):
    records = [
        {
            "job_id": 1,
            "title": "=HYPERLINK(\"example\")",
            "status": "saved",
            "skills_count": 2,
            "model": "model",
            "pipeline_version": "9",
            "error": "",
        }
    ]
    path = process_ai_jobs._write_report(
        records,
        "csv",
        str(tmp_path / "safe.csv"),
    )

    with path.open(encoding="utf-8-sig") as report_file:
        row = next(csv.DictReader(report_file))
    assert row["title"].startswith("'=")
    assert "description" not in row
