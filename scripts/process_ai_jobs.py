import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text

from backend.app.db.session import SessionLocal, engine
from backend.app.models.job import Job
from backend.app.models.job_skill import JobSkill
from backend.app.services.skill_extraction_service import (
    PIPELINE_VERSION,
    process_job,
)


SAMPLE_JOB_IDS = [
    1124,
    1125,
    1123,
    1114,
    1119,
]
REPORT_FIELDS = [
    "job_id",
    "title",
    "status",
    "skills_count",
    "model",
    "pipeline_version",
    "error",
]


def positive_job_id(value: str) -> int:
    """Parse a positive integer job ID for the CLI."""
    try:
        job_id = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("job ID must be a positive integer") from exc
    if job_id <= 0:
        raise argparse.ArgumentTypeError("job ID must be a positive integer")
    return job_id


def _require_postgresql() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "DATABASE_URL must point to PostgreSQL. SQLite is not used "
            "for AI job processing."
        )


def select_job_targets(
    *,
    job_ids: list[int] | None = None,
    all_active: bool = False,
) -> list[dict]:
    """Read stable job targets and current association counts in read-only mode."""
    _require_postgresql()
    if all_active and job_ids is not None:
        raise ValueError("Specify either job_ids or all_active, not both.")
    if not all_active and job_ids is None:
        raise ValueError("job_ids are required unless all_active is enabled.")

    with SessionLocal() as db:
        if db.in_transaction():
            raise RuntimeError(
                "Target selection requires a fresh session for read-only mode."
            )
        try:
            # Must precede the first SELECT in this transaction.
            db.execute(text("SET TRANSACTION READ ONLY"))
            statement = (
                select(
                    Job.id,
                    Job.title,
                    func.count(JobSkill.skill_id).label("skills_count"),
                )
                .outerjoin(JobSkill, JobSkill.job_id == Job.id)
                .group_by(Job.id, Job.title)
                .order_by(Job.id.asc())
            )
            if all_active:
                statement = statement.where(Job.is_active.is_(True))
            else:
                requested_ids = list(job_ids or [])
                if not requested_ids:
                    return []
                statement = statement.where(Job.id.in_(requested_ids))

            rows = db.execute(statement).all()
            by_id = {
                row.id: {
                    "job_id": row.id,
                    "title": row.title,
                    "skills_count": row.skills_count,
                }
                for row in rows
            }
            if all_active:
                return list(by_id.values())

            # Preserve the user's explicit/default ordering and report missing IDs.
            return [
                by_id.get(
                    job_id,
                    {"job_id": job_id, "title": None, "skills_count": 0},
                )
                for job_id in requested_ids
            ]
        finally:
            db.rollback()


def _safe_title(value: str | None) -> str:
    """Avoid spreadsheet formula execution in CSV exports."""
    title = value or ""
    if title.startswith(("=", "+", "-", "@")):
        return "'" + title
    return title


def _write_report(
    records: list[dict],
    report_format: str,
    report_path: str | None,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = (
        Path(report_path)
        if report_path
        else Path("reports") / f"ai_processing_{timestamp}.{report_format}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    if report_format == "json":
        path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        with path.open("w", newline="", encoding="utf-8-sig") as report_file:
            writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            for record in records:
                row = dict(record)
                row["title"] = _safe_title(row.get("title"))
                writer.writerow(row)
    return path


def run_targets(
    targets: list[dict],
    *,
    apply: bool,
    report_format: str = "csv",
    report_path: str | None = None,
    all_active: bool = False,
) -> dict:
    """Run sequentially, opening and closing one database session per job."""
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    counts = {
        "saved": 0,
        "unchanged": 0,
        "would_process": 0,
        "inactive": 0,
        "empty_description": 0,
        "inconsistent": 0,
        "not_found": 0,
        "errors": 0,
        "interrupted": 0,
        "gemini_requests": 0,
        "skills_count": sum(target["skills_count"] for target in targets),
    }
    records = []
    total = len(targets)
    interrupted = False

    for index, target in enumerate(targets, start=1):
        job_id = target["job_id"]
        title = target.get("title") or ""
        print(f"[{index}/{total}] Job {job_id}: {title or '(titlu indisponibil)'}")

        def on_gemini_request():
            counts["gemini_requests"] += 1

        try:
            with SessionLocal() as db:
                try:
                    result = process_job(
                        db=db,
                        job_id=job_id,
                        apply=apply,
                        on_gemini_request=on_gemini_request,
                    )
                except KeyboardInterrupt:
                    db.rollback()
                    raise
                except Exception:
                    # process_job also rolls back apply failures; this protects
                    # the per-job boundary if an exception occurs outside it.
                    db.rollback()
                    raise
        except KeyboardInterrupt:
            interrupted = True
            counts["interrupted"] += 1
            records.append(
                {
                    "job_id": job_id,
                    "title": title,
                    "status": "interrupted",
                    "skills_count": target["skills_count"],
                    "model": model_name,
                    "pipeline_version": PIPELINE_VERSION,
                    "error": "KeyboardInterrupt",
                }
            )
            print("Întrerupere solicitată; tranzacția curentă a fost închisă.")
            break
        except Exception as exc:
            counts["errors"] += 1
            records.append(
                {
                    "job_id": job_id,
                    "title": title,
                    "status": "error",
                    "skills_count": target["skills_count"],
                    "model": model_name,
                    "pipeline_version": PIPELINE_VERSION,
                    # Do not export exception messages that might contain data.
                    "error": type(exc).__name__,
                }
            )
            print(f"[{index}/{total}] Status: error; error={type(exc).__name__}; errors={counts['errors']}")
            continue

        status = result.get("status", "unknown")
        skill_count = result.get("skills_count", target["skills_count"])
        if status == "saved":
            counts["saved"] += 1
            counts["skills_count"] += skill_count - target["skills_count"]
        elif status == "not_found":
            counts["not_found"] += 1
            counts["errors"] += 1
        elif status in counts:
            counts[status] += 1
        else:
            counts["errors"] += 1

        records.append(
            {
                "job_id": job_id,
                "title": result.get("title") or title,
                "status": status,
                "skills_count": skill_count,
                "model": model_name,
                "pipeline_version": PIPELINE_VERSION,
                "error": "",
            }
        )
        print(
            f"[{index}/{total}] Status: {status}; skills={skill_count}; "
            f"errors={counts['errors']}"
        )

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Total active jobs selected: {total if all_active else 'n/a'}")
    print(f"Total jobs selected: {total}")
    print(f"Saved successfully: {counts['saved']}")
    print(f"Unchanged: {counts['unchanged']}")
    print(f"Would process: {counts['would_process']}")
    print(f"Inactive: {counts['inactive']}")
    print(f"Without useful description: {counts['empty_description']}")
    print(f"Inconsistent: {counts['inconsistent']}")
    print(f"Not found: {counts['not_found']}")
    print(f"Errors: {counts['errors']}")
    print(f"Interrupted: {counts['interrupted']}")
    print(f"Total skill associations: {counts['skills_count']}")
    print(f"Gemini requests initiated: {counts['gemini_requests']}")

    try:
        output_path = _write_report(records, report_format, report_path)
        print(f"Local report: {output_path}")
    except OSError as exc:
        counts["report_error"] = type(exc).__name__
        print(f"Report could not be written: {type(exc).__name__}")

    counts["total_jobs"] = total
    counts["records"] = records
    counts["interrupted_run"] = interrupted
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="RoleRadar AI - controlled job analysis"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call Gemini and save results in PostgreSQL.",
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--job-id",
        type=positive_job_id,
        help="Process only this job ID.",
    )
    selector.add_argument(
        "--all-active",
        action="store_true",
        help="Select all active PostgreSQL jobs in ascending ID order.",
    )
    parser.add_argument(
        "--report-format",
        choices=("csv", "json"),
        default="csv",
        help="Local report format (default: csv).",
    )
    parser.add_argument(
        "--report-path",
        help="Optional local report path; a timestamped path is used by default.",
    )
    args = parser.parse_args(argv)

    if args.apply and args.job_id is None and not args.all_active:
        parser.error("--apply requires either --job-id or --all-active.")

    if engine.dialect.name != "postgresql":
        raise SystemExit(
            "ERROR: DATABASE_URL must point to PostgreSQL. "
            "SQLite is not used for AI job processing."
        )

    if args.all_active:
        targets = select_job_targets(all_active=True)
    else:
        job_ids = [args.job_id] if args.job_id is not None else SAMPLE_JOB_IDS
        targets = select_job_targets(job_ids=job_ids)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"MODE: {mode}; pipeline V{PIPELINE_VERSION}; database: PostgreSQL")
    print(f"Selected jobs: {len(targets)}")
    summary = run_targets(
        targets,
        apply=args.apply,
        report_format=args.report_format,
        report_path=args.report_path,
        all_active=args.all_active,
    )
    if summary["interrupted_run"]:
        return 130
    if summary["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
