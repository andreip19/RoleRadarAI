from datetime import datetime, timezone

import httpx

from sqlalchemy.orm import Session

from backend.app.models.ingestion_run import IngestionRun
from backend.app.services.job_service import upsert_jobs

from scraper.greenhouse import fetch_greenhouse_jobs
from scraper.lever import fetch_lever_jobs


# Public job boards configured for RoleRadar AI.
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
    """Dispatch job collection to the appropriate connector."""

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
    """Synchronize all configured job boards independently."""

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

            # Step 1: Fetch source data.
            jobs = await fetch_source_jobs(config)

            # Step 2: Normalize and persist records.
            stats = upsert_jobs(db, jobs)

            # Step 3: Record successful execution.
            run = db.get(IngestionRun, run_id)

            run.status = "success"
            run.fetched = len(jobs)
            run.inserted = stats["inserted"]
            run.updated = stats["updated"]
            run.finished_at = datetime.now(timezone.utc)

            db.commit()

            results.append({
                "source": source,
                "board_token": board_token,
                "status": "success",
                "fetched": len(jobs),
                "inserted": stats["inserted"],
                "updated": stats["updated"],
                "total_processed": stats["total_processed"],
            })

        except Exception as exc:

            # A source failure must not stop other connectors.
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
        result["status"] == "success"
        for result in results
    )

    failed = len(results) - succeeded

    return {
        "total_sources": len(SOURCES),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
