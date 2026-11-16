
import httpx

from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
)

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.db.dependencies import get_db
from backend.app.models.job import Job
from backend.app.schemas.job import JobListResponse
from backend.app.services.job_service import upsert_jobs

from scraper.greenhouse import fetch_greenhouse_jobs
from scraper.lever import fetch_lever_jobs


router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
)


# ============================================================
# GREENHOUSE - FETCH JOBS
# ============================================================

@router.get("/greenhouse/{board_token}")
async def get_greenhouse_jobs(
    board_token: str = Path(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
):
    """Retrieve published jobs from a public Greenhouse board."""

    try:
        jobs = await fetch_greenhouse_jobs(board_token)

        items = jobs[:limit]

        return {
            "source": "greenhouse",
            "board_token": board_token,
            "total": len(jobs),
            "returned": len(items),
            "items": items,
        }

    except httpx.HTTPStatusError as exc:

        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Greenhouse job board not found.",
            )

        raise HTTPException(
            status_code=502,
            detail="Greenhouse API returned an error.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Greenhouse API.",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# GREENHOUSE - SYNCHRONIZE JOBS WITH DATABASE
# ============================================================

@router.post("/greenhouse/{board_token}/sync")
async def sync_greenhouse_jobs(
    board_token: str = Path(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    db: Session = Depends(get_db),
):
    """Fetch and save Greenhouse jobs into SQLite."""

    try:
        jobs = await fetch_greenhouse_jobs(board_token)

        result = upsert_jobs(db, jobs)

        return {
            "source": "greenhouse",
            "board_token": board_token,
            "fetched": len(jobs),
            **result,
        }

    except httpx.HTTPStatusError as exc:

        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Greenhouse job board not found.",
            )

        raise HTTPException(
            status_code=502,
            detail="Greenhouse API error.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Greenhouse connection failed.",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# LEVER - FETCH JOBS
# ============================================================

@router.get("/lever/{site}")
async def get_lever_jobs(
    site: str = Path(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    company_name: str | None = Query(
        default=None,
        max_length=200,
    ),
    region: Literal["global", "eu"] = Query(
        default="global",
    ),
):
    """Retrieve published jobs from a public Lever board."""

    try:
        jobs = await fetch_lever_jobs(
            site=site,
            company_name=company_name,
            region=region,
        )

        items = jobs[:limit]

        return {
            "source": "lever",
            "board_token": site,
            "total": len(jobs),
            "returned": len(items),
            "items": items,
        }

    except httpx.HTTPStatusError as exc:

        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Lever job board not found.",
            )

        raise HTTPException(
            status_code=502,
            detail="Lever API returned an error.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Lever API.",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


# ============================================================
# LEVER - SYNCHRONIZE JOBS WITH DATABASE
# ============================================================

@router.post("/lever/{site}/sync")
async def sync_lever_jobs(
    site: str = Path(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    company_name: str | None = Query(
        default=None,
        max_length=200,
    ),
    region: Literal["global", "eu"] = Query(
        default="global",
    ),
    db: Session = Depends(get_db),
):
    """Fetch and save Lever jobs into SQLite."""

    try:
        jobs = await fetch_lever_jobs(
            site=site,
            company_name=company_name,
            region=region,
        )

        result = upsert_jobs(db, jobs)

        return {
            "source": "lever",
            "board_token": site,
            "fetched": len(jobs),
            **result,
        }

    except httpx.HTTPStatusError as exc:

        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Lever job board not found.",
            )

        raise HTTPException(
            status_code=502,
            detail="Lever API returned an error.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Lever connection failed.",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


# ============================================================
# DATABASE - LIST, SEARCH AND FILTER JOBS
# ============================================================

@router.get(
    "",
    response_model=JobListResponse,
)
def list_jobs(
    q: str | None = Query(
        default=None,
        max_length=200,
    ),
    company: str | None = Query(
        default=None,
        max_length=200,
    ),
    location: str | None = Query(
        default=None,
        max_length=200,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    """List stored jobs with search, filters and pagination."""

    statement = select(Job)

    # Search in job title and description
    if q and q.strip():

        pattern = f"%{q.strip()}%"

        statement = statement.where(
            or_(
                Job.title.ilike(pattern),
                Job.description.ilike(pattern),
            )
        )

    # Filter by company
    if company and company.strip():

        statement = statement.where(
            Job.company.ilike(
                f"%{company.strip()}%"
            )
        )

    # Filter by location
    if location and location.strip():

        statement = statement.where(
            Job.location.ilike(
                f"%{location.strip()}%"
            )
        )

    # Calculate total number of matching jobs
    count_statement = (
        select(func.count())
        .select_from(statement.subquery())
    )

    total = db.scalar(count_statement) or 0

    # Retrieve current page
    jobs = db.scalars(
        statement
        .order_by(Job.last_seen_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": jobs,
    }


# ============================================================
# JOB LIFECYCLE - ACTIVE / INACTIVE / STATISTICS
# ============================================================

def _list_jobs_by_status(
    is_active: bool,
    db: Session,
    limit: int,
    offset: int,
):

    statement = select(Job).where(
        Job.is_active.is_(is_active)
    )

    total = db.scalar(
        select(func.count()).select_from(
            statement.subquery()
        )
    ) or 0

    jobs = db.scalars(
        statement
        .order_by(Job.last_seen_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": jobs,
    }


@router.get(
    "/active",
    response_model=JobListResponse,
)
def list_active_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve currently active job postings."""

    return _list_jobs_by_status(
        is_active=True,
        db=db,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/inactive",
    response_model=JobListResponse,
)
def list_inactive_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve inactive job postings."""

    return _list_jobs_by_status(
        is_active=False,
        db=db,
        limit=limit,
        offset=offset,
    )


@router.get("/statistics")
def get_job_statistics(
    db: Session = Depends(get_db),
):
    """Return job lifecycle statistics."""

    total = db.scalar(
        select(func.count()).select_from(Job)
    ) or 0

    active = db.scalar(
        select(func.count()).select_from(Job).where(
            Job.is_active.is_(True)
        )
    ) or 0

    inactive = db.scalar(
        select(func.count()).select_from(Job).where(
            Job.is_active.is_(False)
        )
    ) or 0

    source_rows = db.execute(
        select(
            Job.source,
            func.count(),
        ).where(
            Job.is_active.is_(True)
        ).group_by(Job.source)
    ).all()

    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "by_source": {
            source: count
            for source, count in source_rows
        },
    }
