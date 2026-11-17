from sqlalchemy import inspect as sqlalchemy_inspect, select

from backend.app.db.session import SessionLocal
from backend.app.models.job import Job
from backend.app.services.gemini_service import extract_job_analysis


SAMPLE_JOB_IDS = [1124, 1125, 1123, 1114, 1119]


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

    if active_field:
        statement = statement.where(
            getattr(Job, active_field).is_(True)
        )

    with SessionLocal() as db:
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
            })

    found_ids = {record["id"] for record in records}
    missing_ids = set(SAMPLE_JOB_IDS) - found_ids

    if missing_ids:
        raise RuntimeError(
            f"Joburi inexistente sau inactive: {sorted(missing_ids)}"
        )

    records.sort(key=lambda record: SAMPLE_JOB_IDS.index(record["id"]))

    print("=" * 75)
    print("ROLERADAR AI - TESTARE GEMINI PE CINCI JOBURI REALE")
    print("=" * 75)

    successful = 0
    failed = 0

    for index, record in enumerate(records, start=1):
        title = str(record["title"] or "Untitled")
        description = str(record["description"] or "").strip()
        company = record["company"]

        print(f"\n\n{'=' * 75}")
        print(f"TEST {index}/5")
        print(f"ID: {record['id']}")
        print(f"Companie: {company or 'N/A'}")
        print(f"Sursa: {record['source'] or 'N/A'}")
        print(f"Titlu: {title}")
        print(f"Lungime descriere: {len(description)} caractere")
        print("=" * 75)

        if len(description) < 200:
            print("EROARE: Descriere prea scurta.")
            failed += 1
            continue

        try:
            result = extract_job_analysis(
                title=title,
                description=description,
                company=company,
            )

            print("\nREZULTAT GEMINI:")
            print(result.model_dump_json(indent=2))

            print(f"\nNumar competente: {len(result.skills)}")
            successful += 1

        except Exception as exc:
            print(f"\nTEST ESUAT: {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n\n{'=' * 75}")
    print("REZUMAT TESTARE")
    print("=" * 75)
    print(f"Teste reusite: {successful}/5")
    print(f"Teste esuate: {failed}/5")
    print("Baza de date nu a fost modificata.")
    print("=" * 75)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
