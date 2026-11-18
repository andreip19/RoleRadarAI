from sqlalchemy import inspect as sqlalchemy_inspect, select, text

from backend.app.db.session import SessionLocal
from backend.app.models.job import Job
from backend.app.services.skill_extraction_service import PIPELINE_VERSION


SAMPLE_JOB_IDS = [
    1124, 1125, 1123, 1114, 1119,
    231, 633, 1014, 1107, 1117, 1120, 629, 997, 338, 255,
]
MIN_DESCRIPTION_LENGTH = 200


def find_field(fields, candidates, required=True):
    for candidate in candidates:
        if candidate in fields:
            return candidate

    if required:
        raise RuntimeError(
            f"Camp lipsa. Campuri disponibile: {sorted(fields)}"
        )

    return None


def main():
    fields = {
        column.key
        for column in sqlalchemy_inspect(Job).column_attrs
    }

    id_field = find_field(fields, ("id",))
    title_field = find_field(fields, ("title", "job_title"))
    description_field = find_field(
        fields,
        ("description", "description_text", "job_description", "raw_description"),
    )
    company_field = find_field(
        fields,
        ("company", "company_name", "employer"),
        required=False,
    )
    source_field = find_field(
        fields,
        ("source",),
        required=False,
    )
    active_field = find_field(
        fields,
        ("is_active",),
        required=False,
    )

    statement = select(Job).where(
        getattr(Job, id_field).in_(SAMPLE_JOB_IDS)
    )

    with SessionLocal() as db:
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        elif dialect == "sqlite":
            db.execute(text("PRAGMA query_only = ON"))

        jobs = db.execute(statement).scalars().all()

        records = []

        for job in jobs:
            records.append({
                "id": getattr(job, id_field),
                "title": getattr(job, title_field),
                "description": getattr(job, description_field),
                "company": (
                    getattr(job, company_field)
                    if company_field else None
                ),
                "source": (
                    getattr(job, source_field)
                    if source_field else None
                ),
                "is_active": (
                    getattr(job, active_field)
                    if active_field else True
                ),
            })

    records_by_id = {record["id"]: record for record in records}
    missing_ids = set(SAMPLE_JOB_IDS) - records_by_id.keys()
    inactive_ids = sorted(
        job_id
        for job_id in SAMPLE_JOB_IDS
        if job_id in records_by_id and not records_by_id[job_id]["is_active"]
    )
    short_description_ids = sorted(
        job_id
        for job_id in SAMPLE_JOB_IDS
        if (
            job_id in records_by_id
            and len(str(records_by_id[job_id]["description"] or "").strip())
            < MIN_DESCRIPTION_LENGTH
        )
    )

    if missing_ids or inactive_ids or short_description_ids:
        problems = []
        if missing_ids:
            problems.append(f"ID-uri inexistente: {sorted(missing_ids)}")
        if inactive_ids:
            problems.append(f"ID-uri inactive: {inactive_ids}")
        if short_description_ids:
            problems.append(
                "Descrieri prea scurte (sub "
                f"{MIN_DESCRIPTION_LENGTH} caractere): "
                f"{short_description_ids}"
            )
        raise RuntimeError(
            "Validarea esantionului a esuat inainte de apelurile Gemini. "
            + "; ".join(problems)
        )

    records.sort(key=lambda record: SAMPLE_JOB_IDS.index(record["id"]))

    from backend.app.services.gemini_service import extract_job_analysis

    print("=" * 75)
    print(f"ROLERADAR AI - TESTARE GEMINI V{PIPELINE_VERSION} PE 15 JOBURI REALE")
    print("=" * 75)

    successful = 0
    failed = 0

    for index, record in enumerate(records, start=1):
        title = str(record["title"] or "Untitled")
        description = str(record["description"] or "").strip()
        company = record["company"]

        print(f"\n\n{'=' * 75}")
        print(f"TEST {index}/{len(SAMPLE_JOB_IDS)}")
        print(f"ID: {record['id']}")
        print(f"Companie: {company or 'N/A'}")
        print(f"Sursa: {record['source'] or 'N/A'}")
        print(f"Titlu: {title}")
        print(f"Lungime descriere: {len(description)} caractere")
        print("=" * 75)

        try:
            result = extract_job_analysis(
                title=title,
                description=description,
                company=company,
            )

            print("\nREZULTAT GEMINI:")
            print(f"Categorie rol: {result.role_category}")
            print(f"Senioritate: {result.seniority}")
            print(f"Rezumat: {result.summary}")
            print(f"\nCompetente extrase ({len(result.skills)}):")

            for skill in result.skills:
                print(
                    f"- {skill.name} | categorie: {skill.category} | "
                    f"cerinta: {skill.requirement} | "
                    f"dovada: {skill.evidence}"
                )

            successful += 1

        except Exception as exc:
            print(f"\nTEST ESUAT: {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n\n{'=' * 75}")
    print("REZUMAT TESTARE")
    print("=" * 75)
    print(f"Teste reusite: {successful}/{len(SAMPLE_JOB_IDS)}")
    print(f"Teste esuate: {failed}/{len(SAMPLE_JOB_IDS)}")
    print(f"Total joburi in esantion: {len(SAMPLE_JOB_IDS)}")
    print(f"ID-uri: {', '.join(map(str, SAMPLE_JOB_IDS))}")
    print("Baza de date nu a fost modificata.")
    print("=" * 75)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
