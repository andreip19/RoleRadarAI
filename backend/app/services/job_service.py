from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.job import Job


MISSING_RUNS_THRESHOLD = 2


def upsert_jobs(
    db: Session,
    jobs: list[dict[str, Any]],
) -> dict[str, int]:

    inserted = 0
    updated = 0
    reactivated = 0

    try:

        for item in jobs:

            source = item["source"]
            board_token = item["board_token"]
            external_id = item["external_id"]

            existing = db.scalar(
                select(Job).where(
                    Job.source == source,
                    Job.board_token == board_token,
                    Job.external_id == external_id,
                )
            )

            values = {
                "title": item["title"],
                "company": item.get("company"),
                "location": item.get("location"),
                "description": item.get("description"),
                "url": item.get("url"),
                "source_updated_at": item.get("updated_at"),
                "departments": item.get("departments") or [],
                "offices": item.get("offices") or [],
            }

            if existing:

                was_inactive = not existing.is_active

                for key, value in values.items():
                    setattr(existing, key, value)

                existing.is_active = True
                existing.inactive_at = None
                existing.missing_runs = 0
                existing.last_seen_at = datetime.now(timezone.utc)

                updated += 1

                if was_inactive:
                    reactivated += 1

            else:

                new_job = Job(
                    source=source,
                    board_token=board_token,
                    external_id=external_id,
                    **values,
                )

                db.add(new_job)
                inserted += 1

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "inserted": inserted,
        "updated": updated,
        "reactivated": reactivated,
        "total_processed": len(jobs),
    }


def deactivate_missing_jobs(
    db: Session,
    source: str,
    board_token: str,
    observed_external_ids: list[str],
) -> int:
    """
    Deactivate a job only after two successful collections
    in which it is missing.
    """

    if not observed_external_ids:
        return 0

    missing_jobs = db.scalars(
        select(Job).where(
            Job.source == source,
            Job.board_token == board_token,
            Job.is_active.is_(True),
            ~Job.external_id.in_(observed_external_ids),
        )
    ).all()

    deactivated = 0
    now = datetime.now(timezone.utc)

    try:

        for job in missing_jobs:

            job.missing_runs += 1

            if job.missing_runs >= MISSING_RUNS_THRESHOLD:

                job.is_active = False
                job.inactive_at = now
                deactivated += 1

        db.commit()

        return deactivated

    except Exception:

        db.rollback()
        raise
