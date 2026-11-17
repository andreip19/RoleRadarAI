import argparse

from backend.app.db.session import SessionLocal, engine
from backend.app.services.skill_extraction_service import process_job


SAMPLE_JOB_IDS = [
    1124,
    1125,
    1123,
    1114,
    1119,
]


def main():
    parser = argparse.ArgumentParser(
        description="RoleRadar AI - controlled job analysis"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call Gemini and save results in PostgreSQL.",
    )

    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        raise SystemExit(
            "ERROR: DATABASE_URL must point to PostgreSQL. "
            "No processing was started."
        )

    print("=" * 75)
    print("ROLERADAR AI - JOB SKILL EXTRACTION PIPELINE")
    print("=" * 75)

    if args.apply:
        print("MODE: APPLY - Gemini calls and database writes enabled")
    else:
        print("MODE: DRY-RUN - no Gemini calls and no database writes")

    print(f"Database: {engine.dialect.name}")
    print(f"Selected jobs: {len(SAMPLE_JOB_IDS)}")

    successful = 0
    failed = 0

    with SessionLocal() as db:
        for index, job_id in enumerate(SAMPLE_JOB_IDS, start=1):
            print(f"\n{'=' * 75}")
            print(f"JOB {index}/{len(SAMPLE_JOB_IDS)}")
            print(f"ID: {job_id}")
            print("-" * 75)

            try:
                result = process_job(
                    db=db,
                    job_id=job_id,
                    apply=args.apply,
                )

                print(f"Status: {result['status']}")

                if result.get("title"):
                    print(f"Title: {result['title']}")

                if result.get("company"):
                    print(f"Company: {result['company']}")

                if result.get("category"):
                    print(f"Category: {result['category']}")

                if result.get("seniority"):
                    print(f"Seniority: {result['seniority']}")

                if result.get("skills_count") is not None:
                    print(f"Skills saved: {result['skills_count']}")

                successful += 1

            except Exception as exc:
                print(
                    f"ERROR: {type(exc).__name__}: {exc}"
                )
                failed += 1

    print(f"\n{'=' * 75}")
    print("FINAL SUMMARY")
    print("=" * 75)
    print(f"Jobs processed successfully: {successful}/5")
    print(f"Jobs with errors: {failed}/5")

    if args.apply:
        print("Mode: database persistence")
    else:
        print("Mode: read-only dry-run")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
