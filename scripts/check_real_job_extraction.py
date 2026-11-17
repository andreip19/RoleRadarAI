from sqlalchemy import inspect as sqlalchemy_inspect, select

from backend.app.db.session import SessionLocal
from backend.app.models.job import Job
from backend.app.services.gemini_service import extract_job_analysis


def find_field(available_fields: set[str], candidates: tuple[str, ...], required: bool = True):
    for candidate in candidates:
        if candidate in available_fields:
            return candidate

    if required:
        raise RuntimeError(
            f"Nu am identificat câmpul necesar. "
            f"Câmpuri disponibile: {sorted(available_fields)}"
        )

    return None


def main():
    available_fields = {
        column.key
        for column in sqlalchemy_inspect(Job).column_attrs
    }

    title_field = find_field(
        available_fields,
        ("title", "job_title"),
    )

    description_field = find_field(
        available_fields,
        ("description", "description_text", "job_description", "raw_description"),
    )

    company_field = find_field(
        available_fields,
        ("company", "company_name", "employer"),
        required=False,
    )

    active_field = find_field(
        available_fields,
        ("is_active",),
        required=False,
    )

    print("=" * 65)
    print("ROLERADAR AI - TEST GEMINI PE UN JOB REAL")
    print("=" * 65)

    statement = select(Job).where(
        getattr(Job, description_field).is_not(None)
    )

    if active_field:
        statement = statement.where(
            getattr(Job, active_field).is_(True)
        )

    if "id" in available_fields:
        statement = statement.order_by(Job.id.desc())

    statement = statement.limit(100)

    with SessionLocal() as db:
        jobs = db.execute(statement).scalars().all()

    jobs = [
        job for job in jobs
        if len(str(getattr(job, description_field) or "").strip()) >= 200
    ]

    if not jobs:
        raise RuntimeError(
            "Nu am găsit un job activ cu o descriere de cel puțin 200 de caractere."
        )

    job = max(
        jobs,
        key=lambda item: len(
            str(getattr(item, description_field) or "").strip()
        ),
    )

    title = str(getattr(job, title_field) or "Untitled")
    description = str(getattr(job, description_field)).strip()

    company = None
    if company_field:
        company_value = getattr(job, company_field)
        company = str(company_value) if company_value else None

    print("\nJOB SELECTAT:")
    print(f"ID: {getattr(job, 'id', 'N/A')}")
    print(f"Titlu: {title}")
    print(f"Companie: {company or 'Nespecificată'}")
    print(f"Lungime descriere: {len(description)} caractere")
    print("\nPREVIEW DESCRIERE:")
    print("-" * 65)
    print(description[:1200])
    print("-" * 65)

    print("\nSe trimite descrierea către Gemini...")

    result = extract_job_analysis(
        title=title,
        description=description,
        company=company,
    )

    print("\nREZULTAT GEMINI:")
    print("=" * 65)
    print(result.model_dump_json(indent=2))

    print("\n" + "=" * 65)
    print("TEST PE JOB REAL REUSIT")
    print("Nu s-au efectuat modificări în baza de date.")
    print("=" * 65)


if __name__ == "__main__":
    main()
