import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.models.job import Job
from backend.app.models.skill import Skill
from backend.app.models.job_skill import JobSkill
from backend.app.models.job_analysis import JobAnalysis
from backend.app.services.gemini_service import extract_job_analysis


logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1"

REQUIREMENT_PRIORITY = {
    "mentioned": 1,
    "preferred": 2,
    "required": 3,
}


def normalize_skill_name(name: str) -> str:
    """Normalize a skill name for catalog deduplication."""
    return re.sub(r"\s+", " ", name.casefold()).strip()


def canonicalize_skill(name: str, evidence: str) -> str:
    """
    Resolve only unambiguous aliases supported by their evidence.

    CSV is expanded only when the evidence explicitly mentions
    Computer Software Validation.
    """
    normalized_name = normalize_skill_name(name)
    normalized_evidence = normalize_skill_name(evidence)

    if (
        normalized_name == "csv"
        and "computer software validation" in normalized_evidence
    ):
        return "Computer Software Validation"

    return name.strip()


def calculate_content_hash(
    job: Job,
    model_name: str,
) -> str:
    """Calculate a hash that also identifies the model and pipeline version."""
    content = {
        "pipeline_version": PIPELINE_VERSION,
        "model_name": model_name,
        "title": job.title or "",
        "company": job.company or "",
        "description": job.description or "",
    }

    serialized = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def get_or_create_skill(
    db: Session,
    name: str,
    category: str,
) -> int:
    """Insert a skill in PostgreSQL or reuse its existing catalog entry."""
    normalized_name = normalize_skill_name(name)

    statement = (
        pg_insert(Skill)
        .values(
            name=name,
            normalized_name=normalized_name,
            category=category,
        )
        .on_conflict_do_nothing(
            index_elements=[Skill.normalized_name]
        )
        .returning(Skill.id)
    )

    skill_id = db.execute(statement).scalar_one_or_none()

    if skill_id is not None:
        return skill_id

    existing_skill = db.scalar(
        select(Skill).where(
            Skill.normalized_name == normalized_name
        )
    )

    if existing_skill is None:
        raise RuntimeError(
            f"Skill could not be inserted or retrieved: {name}"
        )

    if existing_skill.category is None:
        existing_skill.category = category

    return existing_skill.id


def process_job(
    db: Session,
    job_id: int,
    apply: bool = False,
) -> dict:
    """
    Analyze and optionally persist one job.

    apply=False:
        Inspect the job and determine whether analysis is required.
        No Gemini call and no database writes.

    apply=True:
        Call Gemini and persist the validated analysis atomically.
    """

    if db.get_bind().dialect.name != "postgresql":
        raise RuntimeError(
            "AI processing requires PostgreSQL. "
            "SQLite processing is disabled."
        )

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )

    job = db.get(Job, job_id)

    if job is None:
        return {
            "status": "not_found",
            "job_id": job_id,
        }

    if not job.is_active:
        return {
            "status": "inactive",
            "job_id": job_id,
        }

    if not job.description or not job.description.strip():
        return {
            "status": "empty_description",
            "job_id": job_id,
        }

    content_hash = calculate_content_hash(
        job,
        model_name,
    )

    existing_analysis = db.scalar(
        select(JobAnalysis).where(
            JobAnalysis.job_id == job.id
        )
    )

    if (
        existing_analysis is not None
        and existing_analysis.status == "success"
        and existing_analysis.content_hash == content_hash
        and existing_analysis.model_name == model_name
    ):
        return {
            "status": "unchanged",
            "job_id": job.id,
            "title": job.title,
        }

    if not apply:
        return {
            "status": "would_process",
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
        }

    try:
        # Gemini is called before modifying existing associations.
        result = extract_job_analysis(
            title=job.title,
            description=job.description,
            company=job.company,
        )

        # Canonicalize and deduplicate extracted skills.
        canonical_skills = {}

        for extracted_skill in result.skills:
            canonical_name = canonicalize_skill(
                extracted_skill.name,
                extracted_skill.evidence,
            )

            normalized_name = normalize_skill_name(
                canonical_name
            )

            current = canonical_skills.get(normalized_name)

            if (
                current is None
                or REQUIREMENT_PRIORITY[extracted_skill.requirement]
                > REQUIREMENT_PRIORITY[current[0].requirement]
            ):
                canonical_skills[normalized_name] = (
                    extracted_skill,
                    canonical_name,
                )

        # Replace the old job-skill associations only after
        # Gemini has returned a valid result.
        db.execute(
            delete(JobSkill).where(
                JobSkill.job_id == job.id
            )
        )

        for extracted_skill, canonical_name in canonical_skills.values():
            skill_id = get_or_create_skill(
                db=db,
                name=canonical_name,
                category=extracted_skill.category,
            )

            db.add(
                JobSkill(
                    job_id=job.id,
                    skill_id=skill_id,
                    requirement=extracted_skill.requirement,
                    evidence=extracted_skill.evidence,
                )
            )

        if existing_analysis is None:
            existing_analysis = JobAnalysis(
                job_id=job.id,
                content_hash=content_hash,
                model_name=model_name,
            )
            db.add(existing_analysis)

        existing_analysis.content_hash = content_hash
        existing_analysis.model_name = model_name
        existing_analysis.status = "success"
        existing_analysis.category = result.role_category
        existing_analysis.seniority = result.seniority
        existing_analysis.summary = result.summary
        existing_analysis.result_json = result.model_dump(
            mode="json"
        )
        existing_analysis.error_message = None
        existing_analysis.analyzed_at = datetime.now(
            timezone.utc
        )

        # Persist analysis, skills and associations atomically.
        db.commit()

        logger.info(
            "Job %s analyzed successfully. Skills: %s",
            job.id,
            len(canonical_skills),
        )

        return {
            "status": "saved",
            "job_id": job.id,
            "title": job.title,
            "category": result.role_category,
            "seniority": result.seniority,
            "skills_count": len(canonical_skills),
        }

    except Exception:
        db.rollback()
        logger.exception(
            "AI processing failed for job %s",
            job_id,
        )
        raise
