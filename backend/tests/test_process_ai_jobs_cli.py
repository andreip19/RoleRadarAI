from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import process_ai_jobs


class FakeSessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return False


def configure_cli_mocks(monkeypatch, process_spy):
    monkeypatch.setattr(
        process_ai_jobs,
        "engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(process_ai_jobs, "SessionLocal", FakeSessionContext)
    monkeypatch.setattr(process_ai_jobs, "process_job", process_spy)
    monkeypatch.setattr(
        process_ai_jobs,
        "_write_report",
        lambda *_args, **_kwargs: Path("test-report.csv"),
    )

    def select_spy(*, job_ids=None, all_active=False):
        selected = [100, 200] if all_active else list(job_ids or [])
        return [
            {"job_id": job_id, "title": f"Job {job_id}", "skills_count": 0}
            for job_id in selected
        ]

    monkeypatch.setattr(process_ai_jobs, "select_job_targets", select_spy)


def test_default_dry_run_keeps_existing_sample_ids(monkeypatch, capsys):
    calls = []

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append((job_id, apply))
        return {"status": "would_process"}

    configure_cli_mocks(monkeypatch, process_spy)

    assert process_ai_jobs.main([]) == 0
    assert calls == [(job_id, False) for job_id in process_ai_jobs.SAMPLE_JOB_IDS]
    assert "Selected jobs: 5" in capsys.readouterr().out


def test_job_id_selects_only_one_job_for_dry_run(monkeypatch, capsys):
    calls = []

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append((job_id, apply))
        return {"status": "would_process"}

    configure_cli_mocks(monkeypatch, process_spy)

    assert process_ai_jobs.main(["--job-id", "1119"]) == 0
    assert calls == [(1119, False)]
    assert "Selected jobs: 1" in capsys.readouterr().out


def test_apply_with_explicit_id_processes_only_that_job(monkeypatch, capsys):
    calls = []

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append((job_id, apply))
        on_gemini_request()
        return {"status": "saved"}

    configure_cli_mocks(monkeypatch, process_spy)

    assert process_ai_jobs.main(["--apply", "--job-id", "1119"]) == 0
    assert calls == [(1119, True)]
    output = capsys.readouterr().out
    assert "Saved successfully: 1" in output
    assert "Gemini requests initiated: 1" in output


def test_apply_without_job_id_stops_before_database_or_processing(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("database or processing was reached")

    monkeypatch.setattr(process_ai_jobs, "engine", property(forbidden), raising=False)
    monkeypatch.setattr(process_ai_jobs, "SessionLocal", forbidden)
    monkeypatch.setattr(process_ai_jobs, "process_job", forbidden)

    with pytest.raises(SystemExit) as exc:
        process_ai_jobs.main(["--apply"])

    assert exc.value.code == 2
    assert calls == []


@pytest.mark.parametrize("value", ["abc", "0", "-1119"])
def test_invalid_job_id_is_rejected_before_database_access(monkeypatch, value):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("database or processing was reached")

    monkeypatch.setattr(process_ai_jobs, "SessionLocal", forbidden)
    monkeypatch.setattr(process_ai_jobs, "process_job", forbidden)

    with pytest.raises(SystemExit) as exc:
        process_ai_jobs.main(["--job-id", value])

    assert exc.value.code == 2
    assert calls == []


def test_dry_run_cli_does_not_call_gemini(monkeypatch):
    process_calls = []
    gemini_calls = []

    def process_spy(*, db, job_id, apply, on_gemini_request):
        process_calls.append((job_id, apply))
        return {"status": "would_process"}

    def gemini_spy(*_args, **_kwargs):
        gemini_calls.append("called")
        raise AssertionError("Gemini must not be called by dry-run")

    configure_cli_mocks(monkeypatch, process_spy)
    monkeypatch.setattr(
        "backend.app.services.skill_extraction_service.extract_job_analysis",
        gemini_spy,
    )

    process_ai_jobs.main(["--job-id", "1119"])

    assert process_calls == [(1119, False)]
    assert gemini_calls == []


def test_all_active_cli_selects_the_bulk_mode(monkeypatch):
    calls = []
    targets = []

    def select_spy(*, job_ids=None, all_active=False):
        targets.append((job_ids, all_active))
        return [
            {"job_id": 7, "title": "Job 7", "skills_count": 0},
            {"job_id": 9, "title": "Job 9", "skills_count": 0},
        ]

    def process_spy(*, db, job_id, apply, on_gemini_request):
        calls.append((job_id, apply))
        return {"status": "would_process"}

    configure_cli_mocks(monkeypatch, process_spy)
    monkeypatch.setattr(process_ai_jobs, "select_job_targets", select_spy)

    assert process_ai_jobs.main(["--all-active"]) == 0
    assert targets == [(None, True)]
    assert calls == [(7, False), (9, False)]


def test_job_id_and_all_active_are_mutually_exclusive(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("selection or processing should not start")

    monkeypatch.setattr(process_ai_jobs, "select_job_targets", forbidden)
    monkeypatch.setattr(process_ai_jobs, "process_job", forbidden)

    with pytest.raises(SystemExit) as exc:
        process_ai_jobs.main(["--job-id", "1119", "--all-active"])

    assert exc.value.code == 2
    assert calls == []
