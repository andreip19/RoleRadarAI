from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.dependencies import get_db

from backend.app.models.job import Job
from backend.app.models.skill import Skill
from backend.app.models.job_skill import JobSkill
from backend.app.models.job_analysis import JobAnalysis

from backend.app.schemas.ai_api import (
    AnalysisSkillRead,
    JobAnalysisRead,
    SkillCatalogItem,
    SkillListResponse,
    SkillSummary,
    SkillJobItem,
    SkillJobsResponse,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["AI"],
)


# ============================================================
# AI ANALYSIS
# ============================================================

@router.get(
    "/jobs/{job_id}/analysis",
    response_model=JobAnalysisRead,
)
def get_job_analysis(
    job_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve the AI analysis and extracted skills for a job."""

    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    analysis = db.scalar(
        select(JobAnalysis).where(
            JobAnalysis.job_id == job_id
        )
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="AI analysis not found for this job.",
        )

    skill_rows = db.execute(
        select(
            Skill.id,
            Skill.name,
            Skill.category,
            JobSkill.requirement,
            JobSkill.evidence,
        )
        .join(
            JobSkill,
            JobSkill.skill_id == Skill.id,
        )
        .where(
            JobSkill.job_id == job_id
        )
        .order_by(Skill.name.asc())
    ).all()

    skills = [
        AnalysisSkillRead(
            id=row.id,
            name=row.name,
            category=row.category,
            requirement=row.requirement,
            evidence=row.evidence,
        )
        for row in skill_rows
    ]

    return JobAnalysisRead(
        job_id=analysis.job_id,
        content_hash=analysis.content_hash,
        model_name=analysis.model_name,
        status=analysis.status,
        category=analysis.category,
        seniority=analysis.seniority,
        summary=analysis.summary,
        result_json=analysis.result_json,
        analyzed_at=analysis.analyzed_at,
        skills=skills,
    )


# ============================================================
# SKILL CATALOG
# ============================================================

@router.get(
    "/skills",
    response_model=SkillListResponse,
)
def list_skills(
    q: str | None = Query(
        default=None,
        max_length=100,
    ),
    category: str | None = Query(
        default=None,
        max_length=80,
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
    """List extracted skills with search, category filter and job counts."""

    conditions = []

    if q and q.strip():
        pattern = f"%{q.strip()}%"

        conditions.append(
            Skill.name.ilike(pattern)
        )

    if category and category.strip():
        conditions.append(
            Skill.category == category.strip()
        )

    total = db.scalar(
        select(func.count())
        .select_from(Skill)
        .where(*conditions)
    ) or 0

    job_counts = (
        select(
            JobSkill.skill_id.label("skill_id"),
            func.count(JobSkill.job_id).label("job_count"),
        )
        .group_by(JobSkill.skill_id)
        .subquery()
    )

    job_count_expression = func.coalesce(
        job_counts.c.job_count,
        0,
    )

    statement = (
        select(
            Skill,
            job_count_expression.label("job_count"),
        )
        .outerjoin(
            job_counts,
            job_counts.c.skill_id == Skill.id,
        )
        .where(*conditions)
        .order_by(
            job_count_expression.desc(),
            Skill.name.asc(),
        )
        .offset(offset)
        .limit(limit)
    )

    rows = db.execute(statement).all()

    items = [
        SkillCatalogItem(
            id=row.Skill.id,
            name=row.Skill.name,
            normalized_name=row.Skill.normalized_name,
            category=row.Skill.category,
            job_count=row.job_count,
        )
        for row in rows
    ]

    return SkillListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


# ============================================================
# JOBS ASSOCIATED WITH A SKILL
# ============================================================

@router.get(
    "/skills/{skill_id}/jobs",
    response_model=SkillJobsResponse,
)
def list_jobs_for_skill(
    skill_id: int,
    active_only: bool = Query(default=True),
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
    """Retrieve jobs associated with a specific skill."""

    skill = db.get(Skill, skill_id)

    if skill is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found.",
        )

    conditions = [
        JobSkill.skill_id == skill_id
    ]

    if active_only:
        conditions.append(
            Job.is_active.is_(True)
        )

    total = db.scalar(
        select(func.count())
        .select_from(JobSkill)
        .join(
            Job,
            Job.id == JobSkill.job_id,
        )
        .where(*conditions)
    ) or 0

    rows = db.execute(
        select(
            Job,
            JobSkill.requirement,
            JobSkill.evidence,
        )
        .join(
            JobSkill,
            JobSkill.job_id == Job.id,
        )
        .where(*conditions)
        .order_by(
            Job.last_seen_at.desc()
        )
        .offset(offset)
        .limit(limit)
    ).all()

    items = [
        SkillJobItem(
            job_id=row.Job.id,
            title=row.Job.title,
            company=row.Job.company,
            location=row.Job.location,
            description=row.Job.description,
            source=row.Job.source,
            url=row.Job.url,
            is_active=row.Job.is_active,
            requirement=row.requirement,
            evidence=row.evidence,
        )
        for row in rows
    ]

    return SkillJobsResponse(
        skill=SkillSummary(
            id=skill.id,
            name=skill.name,
            normalized_name=skill.normalized_name,
            category=skill.category,
        ),
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )
