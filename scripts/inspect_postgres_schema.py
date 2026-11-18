"""Read-only comparison of PostgreSQL schema state with SQLAlchemy metadata."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, column, inspect, select, table, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.sqltypes import Integer

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app.models.ingestion_run import IngestionRun  # noqa: F401
from backend.app.models.job import Job  # noqa: F401
from backend.app.models.job_analysis import JobAnalysis  # noqa: F401
from backend.app.models.job_skill import JobSkill  # noqa: F401
from backend.app.models.skill import Skill  # noqa: F401


FOCUS_TABLES = {"jobs", "skills", "job_skills", "job_analyses"}
DEFAULT_REPORT = Path("reports") / "postgres_schema_inspection.json"


def _sqlstate(exc: BaseException) -> str | None:
    current: BaseException | None = exc
    while current is not None:
        value = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if value:
            return str(value)
        current = (
            getattr(current, "orig", None)
            or current.__cause__
            or current.__context__
        )
    return None


def _safe_error_message(exc: BaseException) -> str:
    """Return a generic message; driver messages can contain host/user details."""
    if isinstance(exc, SQLAlchemyError):
        return "PostgreSQL operation failed; driver details are omitted."
    return "Schema inspection failed; details are omitted."


def _type_name(sql_type: Any) -> str:
    return re.sub(r"\s+", " ", sql_type.compile(dialect=postgresql.dialect())).strip().lower()


def _default_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _normalize_default(value: Any) -> str | None:
    result = _default_value(value)
    if result is None:
        return None
    result = result.lower().replace('"', "").replace("'", "")
    result = re.sub(r"::(?:character varying|varchar|text|boolean|integer|bigint)\b", "", result)
    result = re.sub(r"[()\s]", "", result)
    return result


def _index_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(item.get("column_names") or []),
        bool(item.get("unique")),
    )


def compare_schema(
    metadata: MetaData,
    inspector: Any,
    schema: str,
    connection: Any,
) -> dict[str, Any]:
    """Compare reflected PostgreSQL objects with SQLAlchemy declarations."""
    expected_names = set(metadata.tables)
    actual_names = set(inspector.get_table_names(schema=schema))
    alembic_exists = "alembic_version" in actual_names
    missing_tables = sorted(expected_names - actual_names)
    extra_tables = sorted(actual_names - expected_names - {"alembic_version"})

    compatible_objects: list[str] = []
    missing_columns: list[dict[str, str]] = []
    extra_columns: list[dict[str, str]] = []
    type_differences: list[dict[str, Any]] = []
    nullability_differences: list[dict[str, Any]] = []
    default_differences: list[dict[str, Any]] = []
    missing_constraints: list[dict[str, Any]] = []
    extra_constraints: list[dict[str, Any]] = []
    missing_indexes: list[dict[str, Any]] = []
    extra_indexes: list[dict[str, Any]] = []
    table_reports: dict[str, Any] = {}

    for table_key, model_table in metadata.tables.items():
        table_name = model_table.name
        if table_name not in actual_names:
            continue

        actual_columns = {
            item["name"]: item for item in inspector.get_columns(table_name, schema=schema)
        }
        expected_columns = {item.name: item for item in model_table.columns}
        per_table = {
            "columns": [],
            "primary_key": {},
            "foreign_keys": {"missing": [], "extra": []},
            "unique_constraints": {"missing": [], "extra": []},
            "indexes": {"missing": [], "extra": []},
        }

        for name, model_column in expected_columns.items():
            label = f"{table_name}.{name}"
            actual = actual_columns.get(name)
            if actual is None:
                missing_columns.append({"table": table_name, "column": name})
                per_table["columns"].append({"column": name, "status": "missing"})
                continue

            column_compatible = True
            model_type = _type_name(model_column.type)
            actual_type = _type_name(actual["type"])
            if model_type != actual_type:
                column_compatible = False
                type_differences.append(
                    {"table": table_name, "column": name, "expected": model_type, "actual": actual_type}
                )

            expected_nullable = bool(model_column.nullable)
            actual_nullable = bool(actual["nullable"])
            if expected_nullable != actual_nullable:
                column_compatible = False
                nullability_differences.append(
                    {
                        "table": table_name,
                        "column": name,
                        "expected_nullable": expected_nullable,
                        "actual_nullable": actual_nullable,
                    }
                )

            expected_default = (
                str(model_column.server_default.arg.compile(dialect=postgresql.dialect()))
                if model_column.server_default is not None
                else None
            )
            actual_default = _default_value(actual.get("default"))
            generated_integer_pk = (
                model_column.primary_key
                and model_column.autoincrement is not False
                and isinstance(model_column.type, Integer)
                and (
                    bool(actual.get("identity"))
                    or (actual_default or "").lower().startswith("nextval(")
                )
            )
            defaults_match = (
                generated_integer_pk
                or _normalize_default(expected_default) == _normalize_default(actual_default)
            )
            if not defaults_match:
                column_compatible = False
                default_differences.append(
                    {
                        "table": table_name,
                        "column": name,
                        "expected_server_default": expected_default,
                        "actual_default": actual_default,
                        "application_default": (
                            repr(model_column.default.arg)
                            if model_column.default is not None
                            else None
                        ),
                    }
                )

            status = "compatible" if column_compatible else "different"
            per_table["columns"].append({"column": name, "status": status})
            if column_compatible:
                compatible_objects.append(label)

        for name in sorted(actual_columns.keys() - expected_columns.keys()):
            extra_columns.append({"table": table_name, "column": name})

        expected_pk = tuple(model_table.primary_key.columns.keys())
        actual_pk = tuple((inspector.get_pk_constraint(table_name, schema=schema) or {}).get("constrained_columns") or [])
        per_table["primary_key"] = {"expected": list(expected_pk), "actual": list(actual_pk)}
        if expected_pk == actual_pk:
            compatible_objects.append(f"{table_name}.primary_key")
        else:
            missing_constraints.append(
                {"table": table_name, "kind": "primary_key", "expected_columns": list(expected_pk), "actual_columns": list(actual_pk)}
            )

        expected_fks = {
            (
                tuple(fk.parent.name for fk in constraint.elements),
                fk_target_table(constraint),
                tuple(element.column.name for element in constraint.elements),
                (next((element.ondelete for element in constraint.elements), None) or "").upper(),
            )
            for constraint in model_table.foreign_key_constraints
        }
        reflected_fks = inspector.get_foreign_keys(table_name, schema=schema)
        actual_fks = {
            (
                tuple(item.get("constrained_columns") or []),
                item.get("referred_table"),
                tuple(item.get("referred_columns") or []),
                ((item.get("options") or {}).get("ondelete") or "").upper(),
            )
            for item in reflected_fks
        }
        per_table["foreign_keys"] = {
            "missing": [list(item) for item in sorted(expected_fks - actual_fks, key=repr)],
            "extra": [list(item) for item in sorted(actual_fks - expected_fks, key=repr)],
        }
        missing_constraints.extend(
            {"table": table_name, "kind": "foreign_key", "signature": list(item)}
            for item in sorted(expected_fks - actual_fks, key=repr)
        )
        extra_constraints.extend(
            {"table": table_name, "kind": "foreign_key", "signature": list(item)}
            for item in sorted(actual_fks - expected_fks, key=repr)
        )
        if expected_fks == actual_fks:
            compatible_objects.extend(f"{table_name}.foreign_key" for _ in expected_fks)

        expected_unique = {
            tuple(constraint.columns.keys())
            for constraint in model_table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        actual_unique = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints(table_name, schema=schema)
        }
        per_table["unique_constraints"] = {
            "missing": [list(item) for item in sorted(expected_unique - actual_unique)],
            "extra": [list(item) for item in sorted(actual_unique - expected_unique)],
        }
        missing_constraints.extend(
            {"table": table_name, "kind": "unique", "columns": list(item)}
            for item in sorted(expected_unique - actual_unique)
        )
        extra_constraints.extend(
            {"table": table_name, "kind": "unique", "columns": list(item)}
            for item in sorted(actual_unique - expected_unique)
        )
        if expected_unique == actual_unique:
            compatible_objects.extend(f"{table_name}.unique:{','.join(item)}" for item in expected_unique)

        expected_indexes = {_index_signature({"column_names": list(index.columns.keys()), "unique": index.unique}) for index in model_table.indexes}
        actual_index_rows = [
            item
            for item in inspector.get_indexes(table_name, schema=schema)
            if not item.get("duplicates_constraint")
        ]
        actual_indexes = {_index_signature(item) for item in actual_index_rows}
        per_table["indexes"] = {
            "missing": [list(item[0]) + [item[1]] for item in sorted(expected_indexes - actual_indexes)],
            "extra": [list(item[0]) + [item[1]] for item in sorted(actual_indexes - expected_indexes)],
        }
        missing_indexes.extend(
            {"table": table_name, "columns": list(item[0]), "unique": item[1]}
            for item in sorted(expected_indexes - actual_indexes)
        )
        extra_indexes.extend(
            {"table": table_name, "columns": list(item[0]), "unique": item[1]}
            for item in sorted(actual_indexes - expected_indexes)
        )
        if expected_indexes == actual_indexes:
            compatible_objects.extend(
                f"{table_name}.index:{','.join(item[0])}" for item in expected_indexes
            )

        table_reports[table_name] = per_table

    compatible_tables = [
        table_name
        for table_name, details in table_reports.items()
        if all(item["status"] == "compatible" for item in details["columns"])
        and not any(
            details[key].get("missing") or details[key].get("extra")
            for key in ("foreign_keys", "unique_constraints", "indexes")
        )
        and details["primary_key"]["expected"] == details["primary_key"]["actual"]
        and not any(item["table"] == table_name for item in extra_columns)
    ]

    alembic_revisions: list[str] = []
    if alembic_exists:
        version_table = table("alembic_version", column("version_num"), schema=schema)
        alembic_revisions = [
            str(value) for value in connection.execute(select(version_table.c.version_num)).scalars()
        ]

    return {
        "expected_tables": sorted(expected_names),
        "actual_tables": sorted(actual_names),
        "compatible_tables": sorted(compatible_tables),
        "compatible_objects": sorted(compatible_objects),
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "type_differences": type_differences,
        "nullability_differences": nullability_differences,
        "default_differences": default_differences,
        "missing_constraints": missing_constraints,
        "extra_constraints": extra_constraints,
        "missing_indexes": missing_indexes,
        "extra_indexes": extra_indexes,
        "tables": table_reports,
        "alembic_version": {
            "exists": alembic_exists,
            "revisions": alembic_revisions,
        },
        "focus_tables": sorted(FOCUS_TABLES & expected_names),
    }


def fk_target_table(constraint: Any) -> str:
    return next(iter(constraint.elements)).column.table.name


def inspect_postgres_schema(database_engine: Engine) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "connection": {"accessible": False, "database": None, "schema": None, "server_version": None},
        "schema_comparison": None,
        "error": None,
    }

    if database_engine.dialect.name != "postgresql":
        report["error"] = {
            "type": "UnsupportedDialect",
            "sqlstate": None,
            "message": "Schema inspection requires PostgreSQL; no query was run.",
        }
        return report

    connection = None
    try:
        connection = database_engine.connect()
        # This must be the first SQL statement in the transaction.
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection_info = connection.execute(
            text(
                "SELECT current_database(), current_schema(), "
                "current_setting('server_version')"
            )
        ).one()
        database_name, schema_name, server_version = connection_info
        report["connection"] = {
            "accessible": True,
            "database": database_name,
            "schema": schema_name,
            "server_version": server_version,
        }
        schema_inspector = inspect(connection)
        report["schema_comparison"] = compare_schema(
            Base.metadata,
            schema_inspector,
            schema_name,
            connection,
        )
    except Exception as exc:
        report["error"] = {
            "type": type(exc).__name__,
            "sqlstate": _sqlstate(exc),
            "message": _safe_error_message(exc),
        }
    finally:
        if connection is not None:
            try:
                if connection.in_transaction():
                    connection.rollback()
            except Exception as exc:
                if report["error"] is None:
                    report["error"] = {
                        "type": type(exc).__name__,
                        "sqlstate": _sqlstate(exc),
                        "message": _safe_error_message(exc),
                    }
            finally:
                try:
                    connection.close()
                except Exception as exc:
                    if report["error"] is None:
                        report["error"] = {
                            "type": type(exc).__name__,
                            "sqlstate": _sqlstate(exc),
                            "message": _safe_error_message(exc),
                        }

    return report


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    report = inspect_postgres_schema(engine)
    write_report(report, args.output)
    print(f"Schema report written to {args.output}")
    if report["error"]:
        print(
            "PostgreSQL schema inspection failed: "
            f"{report['error']['type']}; {report['error']['message']}"
        )
        return 2 if report["error"]["type"] == "UnsupportedDialect" else 1
    print(
        "PostgreSQL accessible: "
        f"database={report['connection']['database']} "
        f"schema={report['connection']['schema']} "
        f"version={report['connection']['server_version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
