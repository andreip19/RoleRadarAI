from datetime import datetime, timezone

import httpx

from sqlalchemy.orm import Session

from backend.app.models.ingestion_run import IngestionRun

from backend.app.services.job_service import (
    deactivate_missing_jobs,
    upsert_jobs,
)

from scraper.greenhouse import fetch_greenhouse_jobs
from scraper.lever import fetch_lever_jobs


SOURCES = [
    {
        "source": "greenhouse",
        "board_token": "gitlab",
        "company_name": None,
        "region": None,
    },
    {
        "source": "lever",
        "board_token": "veeva",
        "company_name": "Veeva Systems",
        "region": "global",
    },
]


async def fetch_source_jobs(config: dict):

    source = config["source"]
    board_token = config["board_token"]

    if source == "greenhouse":

        return await fetch_greenhouse_jobs(board_token)

    if source == "lever":

        return await fetch_lever_jobs(
            site=board_token,
            company_name=config["company_name"],
            region=config["region"],
        )

    raise ValueError(f"Unsupported source: {source}")


async def run_all_ingestion(db: Session) -> dict:
    """Synchronize configured sources and track job lifecycle."""

    results = []

    for config in SOURCES:

        source = config["source"]
        board_token = config["board_token"]

        run = IngestionRun(
            source=source,
            board_token=board_token,
            status="running",
        )

        db.add(run)
        db.commit()
        db.refresh(run)

        run_id = run.id

        try:

            # 1. Collect source data.
            jobs = await fetch_source_jobs(config)

            # 2. Insert new jobs and update existing jobs.
            stats = upsert_jobs(db, jobs)

            # 3. Reconcile missing jobs only after a successful
            # non-empty collection.
            observed_ids = list({
                item["external_id"]
                for item in jobs
            })

            deactivated = 0
            empty_fetch_protected = not jobs

            if jobs:

                deactivated = deactivate_missing_jobs(
                    db=db,
                    source=source,
                    board_token=board_token,
                    observed_external_ids=observed_ids,
                )

            # 4. Save execution history.
            run = db.get(IngestionRun, run_id)

            run.status = "success"
            run.fetched = len(jobs)
            run.inserted = stats["inserted"]
            run.updated = stats["updated"]
            run.reactivated = stats["reactivated"]
            run.deactivated = deactivated
            run.finished_at = datetime.now(timezone.utc)

            db.commit()

            results.append({
                "source": source,
                "board_token": board_token,
                "status": "success",
                "fetched": len(jobs),
                "inserted": stats["inserted"],
                "updated": stats["updated"],
                "reactivated": stats["reactivated"],
                "deactivated": deactivated,
                "empty_fetch_protected": empty_fetch_protected,
                "total_processed": stats["total_processed"],
            })

        except Exception as exc:

            db.rollback()

            failed_run = db.get(IngestionRun, run_id)

            if failed_run is not None:

                failed_run.status = "error"
                failed_run.error_message = str(exc)[:2000]
                failed_run.finished_at = datetime.now(timezone.utc)

                db.commit()

            results.append({
                "source": source,
                "board_token": board_token,
                "status": "error",
                "error": str(exc),
            })

    succeeded = sum(
        item["status"] == "success"
        for item in results
    )

    failed = len(results) - succeeded

    return {
        "total_sources": len(SOURCES),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
