"""Read-only report for catalog aliases and saved analysis associations."""

from collections import defaultdict

from sqlalchemy import select, text

from backend.app.db.session import SessionLocal
from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_skill import JobSkill
from backend.app.models.skill import Skill
from backend.app.services.skill_extraction_service import (
    _analysis_association_integrity,
    canonicalize_skill,
    normalize_skill_name,
)


def main() -> int:
    try:
        with SessionLocal() as db:
            if db.get_bind().dialect.name != "postgresql":
                print("Diagnostic requires PostgreSQL; no query was run.")
                return 2

            try:
                db.execute(text("SET TRANSACTION READ ONLY"))

                analyses = db.scalars(
                    select(JobAnalysis).order_by(JobAnalysis.job_id)
                ).all()

                canonical_groups = defaultdict(list)
                oidc_rows = []
                catalog_rows = db.execute(
                    select(Skill.id, Skill.name, JobSkill.evidence)
                    .outerjoin(JobSkill, JobSkill.skill_id == Skill.id)
                    .order_by(Skill.id)
                ).all()
                seen_oidc = set()
                for skill_id, skill_name, evidence in catalog_rows:
                    canonical_name = canonicalize_skill(skill_name, evidence or "")
                    key = normalize_skill_name(canonical_name)
                    entry = (skill_id, skill_name)
                    if entry not in canonical_groups[key]:
                        canonical_groups[key].append(entry)
                    if (
                        normalize_skill_name(skill_name) in {"oidc", "openidconnect"}
                        and skill_id not in seen_oidc
                    ):
                        oidc_rows.append((skill_id, skill_name, canonical_name))
                        seen_oidc.add(skill_id)

                duplicate_groups = [
                    (key, rows)
                    for key, rows in canonical_groups.items()
                    if len(rows) > 1
                ]
                inconsistent = []
                for analysis in analyses:
                    if analysis.status != "success":
                        continue
                    consistent, reason = _analysis_association_integrity(
                        db,
                        analysis.job_id,
                        analysis.result_json,
                    )
                    if not consistent:
                        inconsistent.append((analysis.job_id, reason))

                print("OIDC / OpenID Connect catalog entries:")
                if oidc_rows:
                    for skill_id, name, canonical_name in oidc_rows:
                        print(f"  id={skill_id} name={name!r} canonical={canonical_name!r}")
                else:
                    print("  none")

                print("Duplicate catalog groups after canonicalization:")
                if duplicate_groups:
                    for key, rows in duplicate_groups:
                        members = "; ".join(
                            f"id={sid} name={name!r}" for sid, name in rows
                        )
                        print(f"  key={key!r}: {members}")
                else:
                    print("  none")

                print("Successful analyses with incomplete/mismatched job_skills:")
                if inconsistent:
                    for job_id, reason in inconsistent:
                        print(f"  job_id={job_id}: {reason}")
                else:
                    print("  none")

                db.rollback()
                return 0
            finally:
                # Never commit this diagnostic transaction.
                if db.in_transaction():
                    db.rollback()
    except Exception as exc:
        # Avoid printing SQLAlchemy connection diagnostics or configuration.
        print(f"Diagnostic failed ({type(exc).__name__}); details suppressed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
