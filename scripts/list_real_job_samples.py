from sqlalchemy import inspect as sqlalchemy_inspect, select

from backend.app.db.session import SessionLocal
from backend.app.models.job import Job


def main():
    fields = {
        column.key
        for column in sqlalchemy_inspect(Job).column_attrs
    }

    def find_field(*names):
        return next((name for name in names if name in fields), None)

    id_field = find_field("id")
    title_field = find_field("title", "job_title")
    company_field = find_field("company", "company_name", "employer")
    source_field = find_field("source")
    description_field = find_field(
        "description",
        "description_text",
        "job_description",
        "raw_description",
    )
    active_field = find_field("is_active")

    if not all((id_field, title_field, description_field)):
        raise RuntimeError(f"Campuri insuficiente: {sorted(fields)}")

    statement = select(Job).where(
        getattr(Job, description_field).is_not(None)
    )

    if active_field:
        statement = statement.where(
            getattr(Job, active_field).is_(True)
        )

    statement = statement.order_by(Job.id.desc()).limit(40)

    with SessionLocal() as db:
        jobs = db.execute(statement).scalars().all()

    print("=" * 100)
    print("JOBURI ACTIVE DISPONIBILE PENTRU TESTAREA GEMINI")
    print("=" * 100)

    count = 0

    for job in jobs:
        description = str(getattr(job, description_field) or "").strip()

        if len(description) < 200:
            continue

        count += 1

        company = (
            getattr(job, company_field)
            if company_field else "N/A"
        )

        source = (
            getattr(job, source_field)
            if source_field else "N/A"
        )

        print(
            f"\nID: {getattr(job, id_field)}"
            f"\nCompanie: {company}"
            f"\nSursa: {source}"
            f"\nTitlu: {getattr(job, title_field)}"
            f"\nDescriere: {len(description)} caractere"
        )

        if count >= 20:
            break

    print(f"\nTotal afisat: {count}")
    print("Nu s-au modificat datele din baza de date.")


if __name__ == "__main__":
    main()
