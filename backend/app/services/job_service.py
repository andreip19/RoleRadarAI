from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.job import Job


def upsert_jobs(
    db: Session,
    jobs: list[dict[str, Any]],
) -> dict[str, int]:

    inserted = 0
    updated = 0

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

                for key, value in values.items():
                    setattr(existing, key, value)

                existing.last_seen_at = datetime.now(timezone.utc)

                updated += 1

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
        "total_processed": len(jobs),
    }