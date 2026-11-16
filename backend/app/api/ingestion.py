from fastapi import APIRouter, Depends, Query

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.dependencies import get_db
from backend.app.models.ingestion_run import IngestionRun

from backend.app.services.ingestion_service import (
    run_all_ingestion,
)


router = APIRouter(
    prefix="/api/v1/ingestion",
    tags=["ingestion"],
)


@router.post("/run-all")
async def run_all(
    db: Session = Depends(get_db),
):
    """Execute all configured ingestion connectors."""

    return await run_all_ingestion(db)


@router.get("/runs")
def list_ingestion_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve ingestion execution history."""

    total = db.scalar(
        select(func.count()).select_from(IngestionRun)
    ) or 0

    runs = db.scalars(
        select(IngestionRun)
        .order_by(IngestionRun.started_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": run.id,
                "source": run.source,
                "board_token": run.board_token,
                "status": run.status,
                "fetched": run.fetched,
                "inserted": run.inserted,
                "updated": run.updated,
                "reactivated": run.reactivated,
                "deactivated": run.deactivated,
                "error_message": run.error_message,
                "started_at": (
                    run.started_at.isoformat()
                    if run.started_at else None
                ),
                "finished_at": (
                    run.finished_at.isoformat()
                    if run.finished_at else None
                ),
            }
            for run in runs
        ],
    }
