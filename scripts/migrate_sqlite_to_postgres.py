import argparse
import json
import os
import sqlite3

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from sqlalchemy import (
    Boolean,
    DateTime,
    JSON,
    create_engine,
    func,
    inspect,
    select,
    text,
)

from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.db.base import Base
from backend.app.models.job import Job
from backend.app.models.ingestion_run import IngestionRun


ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

SQLITE_PATH = ROOT / "data" / "roleradar.db"

MODELS = [
    Job,
    IngestionRun,
]

DEFAULTS = {
    "is_active": True,
    "missing_runs": 0,
    "inactive_at": None,
    "reactivated": 0,
    "deactivated": 0,
    "departments": [],
    "offices": [],
}


def convert_value(value, column):
    """Convert SQLite values into PostgreSQL-compatible values."""

    if value is None:
        return None

    if isinstance(column.type, Boolean):
        return bool(value)

    if isinstance(column.type, JSON):

        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

    if isinstance(column.type, DateTime):

        if isinstance(value, str):
            value = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        if column.type.timezone and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

    return value


def read_sqlite_table(
    connection: sqlite3.Connection,
    model,
) -> list[dict]:
    """Read an entire SQLite table and map its records to a model."""

    table = model.__table__

    cursor = connection.execute(
        f'SELECT * FROM "{table.name}"'
    )

    column_names = [
        description[0]
        for description in cursor.description
    ]

    actual_columns = set(column_names)

    if not actual_columns:
        raise RuntimeError(
            f"SQLite table {table.name} has no columns."
        )

    records = cursor.fetchall()

    result = []

    for record in records:

        raw = dict(zip(column_names, record))

        # Support the legacy source timestamp name.
        if (
            "source_updated_at" not in raw
            and "updated_at" in raw
        ):
            raw["source_updated_at"] = raw["updated_at"]

        item = {}

        for column in table.columns:

            name = column.name

            if name in raw:

                value = raw[name]

            elif name in DEFAULTS:

                value = DEFAULTS[name]

            elif column.nullable or column.server_default is not None:

                continue

            else:

                raise RuntimeError(
                    f"Missing required SQLite column: "
                    f"{table.name}.{name}"
                )

            item[name] = convert_value(value, column)

        result.append(item)

    # Protect against duplicate primary keys in the source.
    ids = [item["id"] for item in result]

    if len(ids) != len(set(ids)):
        raise RuntimeError(
            f"Duplicate primary keys found in SQLite table {table.name}."
        )

    return result


def inspect_destination(engine, model, source_count: int) -> int:
    """Check the target table without modifying PostgreSQL."""

    inspector = inspect(engine)
    table = model.__table__

    existing_tables = set(
        inspector.get_table_names(schema="public")
    )

    if table.name not in existing_tables:
        destination_count = 0

    else:

        with engine.connect() as connection:

            destination_count = connection.scalar(
                select(func.count()).select_from(table)
            ) or 0

    print(
        f"PostgreSQL {table.name}: "
        f"{destination_count} existing records"
    )

    if destination_count > source_count:

        raise RuntimeError(
            f"Destination table {table.name} contains more records "
            "than SQLite. Migration stopped to protect existing data."
        )

    return destination_count


def migrate_model(destination, model, rows: list[dict]) -> None:
    """Insert or update records and verify migrated primary keys."""

    table = model.__table__

    if rows:

        statement = pg_insert(table).values(rows)

        update_values = {
            column.name: statement.excluded[column.name]
            for column in table.columns
            if column.name != "id"
        }

        statement = statement.on_conflict_do_update(
            index_elements=[table.c.id],
            set_=update_values,
        )

        destination.execute(statement)

    migrated_count = destination.scalar(
        select(func.count()).select_from(table)
    ) or 0

    if migrated_count != len(rows):

        raise RuntimeError(
            f"Count mismatch for {table.name}: "
            f"SQLite={len(rows)}, PostgreSQL={migrated_count}"
        )

    source_ids = {
        item["id"]
        for item in rows
    }

    destination_ids = set(
        destination.scalars(
            select(table.c.id)
        ).all()
    )

    if source_ids != destination_ids:

        raise RuntimeError(
            f"Primary key mismatch detected in {table.name}."
        )

    # Synchronize PostgreSQL auto-increment sequence.
    sequence_name = destination.scalar(
        text(
            "SELECT pg_get_serial_sequence(:table_name, 'id')"
        ),
        {"table_name": f"public.{table.name}"},
    )

    if sequence_name:

        max_id = max(source_ids, default=0)

        if max_id > 0:

            destination.execute(
                text(
                    "SELECT setval("
                    "CAST(:sequence_name AS regclass), "
                    ":max_id, true)"
                ),
                {
                    "sequence_name": sequence_name,
                    "max_id": max_id,
                },
            )

    print(
        f"VERIFIED {table.name}: "
        f"{migrated_count} records, IDs match"
    )


def main(apply_changes: bool = False):

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL missing from .env"
        )

    if not SQLITE_PATH.exists():
        raise FileNotFoundError(SQLITE_PATH)

    sqlite_engine = create_engine(
        f"sqlite:///{SQLITE_PATH.as_posix()}"
    )

    postgres_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    try:

        print("=" * 55)
        print("ROLERADAR AI - SQLITE TO POSTGRESQL")
        print("=" * 55)

        all_rows = {}

        # Read the complete source database.
        with sqlite_engine.connect() as connection:

            for model in MODELS:

                rows = read_sqlite_table(
                    connection.connection.driver_connection,
                    model,
                )

                all_rows[model] = rows

                print(
                    f"SQLite {model.__tablename__}: "
                    f"{len(rows)} records"
                )

        # Inspect PostgreSQL without writing anything.
        print()
        print("Checking PostgreSQL destination...")

        for model in MODELS:

            inspect_destination(
                postgres_engine,
                model,
                len(all_rows[model]),
            )

        if not apply_changes:

            print()
            print("=" * 55)
            print("DRY RUN COMPLETED")
            print("No PostgreSQL tables or records were modified.")
            print("Review the counts before running with --apply.")
            print("=" * 55)

            return

        # Create missing tables only after explicit approval.
        print()
        print("Creating missing PostgreSQL tables...")

        Base.metadata.create_all(
            bind=postgres_engine
        )

        # Transfer all records in one database transaction.
        with postgres_engine.begin() as destination:

            for model in MODELS:

                migrate_model(
                    destination,
                    model,
                    all_rows[model],
                )

        print()
        print("=" * 55)
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 55)

    finally:

        sqlite_engine.dispose()
        postgres_engine.dispose()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Migrate RoleRadar AI from SQLite to PostgreSQL."
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration. Without this flag, only inspect.",
    )

    arguments = parser.parse_args()

    main(apply_changes=arguments.apply)
