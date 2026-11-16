from sqlalchemy import inspect, text

from backend.app.db.session import engine


def migrate_sqlite_schema() -> None:
    """Apply safe additive SQLite schema migrations."""

    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:

        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        if "jobs" in tables:

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("jobs")
            }

            migrations = {
                "is_active": (
                    "ALTER TABLE jobs "
                    "ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                ),
                "inactive_at": (
                    "ALTER TABLE jobs "
                    "ADD COLUMN inactive_at DATETIME NULL"
                ),
                "missing_runs": (
                    "ALTER TABLE jobs "
                    "ADD COLUMN missing_runs INTEGER NOT NULL DEFAULT 0"
                ),
            }

            for column_name, statement in migrations.items():

                if column_name not in columns:
                    connection.execute(text(statement))

        if "ingestion_runs" in tables:

            columns = {
                column["name"]
                for column in inspect(connection).get_columns(
                    "ingestion_runs"
                )
            }

            migrations = {
                "reactivated": (
                    "ALTER TABLE ingestion_runs "
                    "ADD COLUMN reactivated INTEGER NOT NULL DEFAULT 0"
                ),
                "deactivated": (
                    "ALTER TABLE ingestion_runs "
                    "ADD COLUMN deactivated INTEGER NOT NULL DEFAULT 0"
                ),
            }

            for column_name, statement in migrations.items():

                if column_name not in columns:
                    connection.execute(text(statement))
