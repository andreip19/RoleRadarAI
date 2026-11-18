import hashlib
import json
import logging
import os
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.models.job import Job
from backend.app.models.skill import Skill
from backend.app.models.job_skill import JobSkill
from backend.app.models.job_analysis import JobAnalysis
from backend.app.services.gemini_service import extract_job_analysis


logger = logging.getLogger(__name__)

PIPELINE_VERSION = "9"

REQUIREMENT_PRIORITY = {
    "mentioned": 1,
    "preferred": 2,
    "required": 3,
}


def normalize_skill_name(name: str) -> str:
    """Normalize Unicode and formatting variants for skill deduplication."""

    normalized = unicodedata.normalize("NFKC", name).casefold().strip()

    # Treat spacing, dots, slashes and hyphens as formatting differences.
    # Keep meaningful characters such as + and # (C++ and C#).
    return re.sub(r"[\s._/\-\u2010-\u2015]+", "", normalized)


def canonicalize_skill(name: str, evidence: str) -> str:
    """
    Resolve only unambiguous aliases explicitly supported by evidence.

    OpenID Connect is the stable catalog name for both OIDC and its full
    name. CSV and RTSM are canonicalized only when both forms occur in
    the evidence.
    """
    normalized_name = normalize_skill_name(name)
    normalized_evidence = normalize_skill_name(evidence)

    if normalized_name in {"oidc", "openidconnect"}:
        return "OpenID Connect"

    if (
        normalized_name in {"csv", "computersoftwarevalidation"}
        and "computersoftwarevalidation" in normalized_evidence
        and re.search(r"\bcsv\b", evidence, re.IGNORECASE)
    ):
        return "Computer Software Validation"

    if (
        normalized_name in {"rtsm", "randomizationandtrialsupplymanagement"}
        and "rtsm" in normalized_evidence
        and "randomizationandtrialsupplymanagement" in normalized_evidence
    ):
        return "RTSM"

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


def _find_legacy_skill_match(skills, normalized_name: str):
    """Find an existing catalog entry using the current name normalization."""

    return next(
        (
            candidate
            for candidate in skills
            if normalize_skill_name(
                canonicalize_skill(candidate.name, "")
            ) == normalized_name
        ),
        None,
    )


def get_or_create_skill(
    db: Session,
    name: str,
    category: str,
) -> int:
    """Reuse an equivalent existing skill before inserting a new catalog entry."""

    name = canonicalize_skill(name, "")
    normalized_name = normalize_skill_name(name)

    def find_existing():
        exact_match = db.scalar(
            select(Skill).where(
                Skill.normalized_name == normalized_name
            )
        )

        if exact_match is not None:
            return exact_match

        existing_skills = db.scalars(
            select(Skill).order_by(Skill.id)
        ).all()

        return _find_legacy_skill_match(
            existing_skills,
            normalized_name,
        )

    # Check both current and legacy catalog keys before inserting.
    existing_skill = find_existing()

    if existing_skill is not None:
        if existing_skill.category is None:
            existing_skill.category = category

        return existing_skill.id

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

    # Handle a concurrent insert using the same catalog key.
    existing_skill = find_existing()

    if existing_skill is None:
        raise RuntimeError(
            f"Skill could not be inserted or retrieved: {name}"
        )

    if existing_skill.category is None:
        existing_skill.category = category

    return existing_skill.id


def _analysis_association_integrity(
    db: Session,
    job_id: int,
    result_json: dict | None,
) -> tuple[bool, str]:
    """Compare saved analysis skills with the current job-skill rows."""
    if not isinstance(result_json, dict) or not isinstance(result_json.get("skills"), list):
        return False, "Analiza nu conține o listă validă de competențe în result_json."

    expected = {}
    for item in result_json["skills"]:
        if not isinstance(item, dict) or not item.get("name"):
            return False, "Analiza conține o competență fără nume valid."
        evidence = item.get("evidence") or ""
        canonical_name = canonicalize_skill(str(item["name"]), str(evidence))
        key = normalize_skill_name(canonical_name)
        candidate = (canonical_name, item.get("requirement"), evidence)
        current = expected.get(key)
        if current is None or (
            REQUIREMENT_PRIORITY.get(candidate[1], 0)
            > REQUIREMENT_PRIORITY.get(current[1], 0)
            or (
                REQUIREMENT_PRIORITY.get(candidate[1], 0)
                == REQUIREMENT_PRIORITY.get(current[1], 0)
                and len(candidate[2]) < len(current[2])
            )
        ):
            expected[key] = candidate

    rows = db.execute(
        select(Skill.name, JobSkill.requirement, JobSkill.evidence)
        .join(JobSkill, JobSkill.skill_id == Skill.id)
        .where(JobSkill.job_id == job_id)
    ).all()

    actual = {}
    duplicate_associations = []
    for name, requirement, evidence in rows:
        canonical_name = canonicalize_skill(name, evidence)
        key = normalize_skill_name(canonical_name)
        if key in actual:
            duplicate_associations.append(canonical_name)
        actual[key] = (
            canonical_name,
            requirement,
            evidence,
        )

    if expected == actual and not duplicate_associations:
        return True, ""

    missing = [
        details[0]
        for key, details in expected.items()
        if key not in actual
    ]
    extra = [
        details[0]
        for key, details in actual.items()
        if key not in expected
    ]
    mismatched = [
        expected[key][0]
        for key in expected.keys() & actual.keys()
        if expected[key] != actual[key]
    ]
    reasons = []
    if missing:
        reasons.append("lipsesc: " + ", ".join(sorted(missing)))
    if extra:
        reasons.append("în plus: " + ", ".join(sorted(extra)))
    if mismatched:
        reasons.append("nivel/dovadă diferită: " + ", ".join(sorted(mismatched)))
    if duplicate_associations:
        reasons.append(
            "asocieri duplicate după canonicalizare: "
            + ", ".join(sorted(set(duplicate_associations)))
        )
    return False, "; ".join(reasons) or "Numărul sau conținutul competențelor diferă."


def _database_dialect(db: Session) -> str:
    return db.get_bind().dialect.name


def process_job(
    db: Session,
    job_id: int,
    apply: bool = False,
    on_gemini_request: Callable[[], None] | None = None,
) -> dict:
    """
    Analyze and optionally persist one job.

    apply=False:
        Inspect the job and determine whether analysis is required.
        No Gemini call and no database writes.

    apply=True:
        Call Gemini and persist the validated analysis atomically.
    """

    if _database_dialect(db) != "postgresql":
        raise RuntimeError(
            "AI processing requires PostgreSQL. "
            "SQLite processing is disabled."
        )

    if not apply:
        if db.in_transaction():
            raise RuntimeError(
                "Dry-run requires a session without an active transaction "
                "so read-only mode can be set before its first query."
            )
        try:
            # This must be the first SQL statement in the transaction.
            db.execute(text("SET TRANSACTION READ ONLY"))
            return _process_job(db, job_id, apply=False)
        finally:
            # A dry-run never commits; rollback closes the read-only transaction.
            db.rollback()

    return _process_job(
        db,
        job_id,
        apply=True,
        on_gemini_request=on_gemini_request,
    )


def _process_job(
    db: Session,
    job_id: int,
    apply: bool,
    on_gemini_request: Callable[[], None] | None = None,
) -> dict:

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
        is_consistent, explanation = _analysis_association_integrity(
            db,
            job.id,
            existing_analysis.result_json,
        )
        if not is_consistent:
            return {
                "status": "inconsistent",
                "job_id": job.id,
                "title": job.title,
                "reason": explanation,
            }
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
            on_request=on_gemini_request,
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
                or (
                    REQUIREMENT_PRIORITY[extracted_skill.requirement]
                    == REQUIREMENT_PRIORITY[current[0].requirement]
                    and len(extracted_skill.evidence) < len(current[0].evidence)
                )
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
