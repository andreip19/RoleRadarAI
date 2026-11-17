from sqlalchemy import inspect

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.models.job import Job
from backend.app.models.skill import Skill
from backend.app.models.job_skill import JobSkill
from backend.app.models.job_analysis import JobAnalysis


NEW_TABLES = [
    Skill.__table__,
    JobSkill.__table__,
    JobAnalysis.__table__,
]


def main():

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "AI tables must be created in Supabase PostgreSQL."
        )

    inspector = inspect(engine)

    existing = set(
        inspector.get_table_names(schema="public")
    )

    if Job.__tablename__ not in existing:
        raise RuntimeError(
            "Existing jobs table not found in PostgreSQL."
        )

    print("Existing jobs table: CONFIRMED")

    print("\nChecking AI tables...")

    for table in NEW_TABLES:

        if table.name in existing:
            print(f"{table.name}: already exists")
        else:
            print(f"{table.name}: will be created")

    print("\nCreating missing tables...")

    Base.metadata.create_all(
        bind=engine,
        tables=NEW_TABLES,
    )

    final_tables = set(
        inspect(engine).get_table_names(schema="public")
    )

    for table in NEW_TABLES:

        if table.name not in final_tables:
            raise RuntimeError(
                f"Table creation failed: {table.name}"
            )

        print(f"VERIFIED: public.{table.name}")

    print("\nAI DATABASE SCHEMA CREATED SUCCESSFULLY")


if __name__ == "__main__":

    try:
        main()

    finally:
        engine.dispose()
