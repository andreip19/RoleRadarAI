from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from backend.app.db.base import Base
from scripts import inspect_postgres_schema as schema_audit


class FakeResult:
    def __init__(self, row=None, values=None):
        self.row = row
        self.values = values or []

    def one(self):
        return self.row

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.values)


class FakeConnection:
    def __init__(self, events):
        self.events = events
        self.active = False
        self.closed = False
        self.rolled_back = False

    def execute(self, statement):
        sql = str(statement)
        self.events.append(sql)
        self.active = True
        if sql == "SET TRANSACTION READ ONLY":
            return FakeResult()
        if "current_database()" in sql:
            return FakeResult(("test_db", "public", "PostgreSQL 16.4"))
        return FakeResult(values=["baseline_revision"])

    def in_transaction(self):
        return self.active

    def rollback(self):
        self.events.append("ROLLBACK")
        self.rolled_back = True
        self.active = False

    def close(self):
        self.events.append("CLOSE")
        self.closed = True


class FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, connection=None, error=None):
        self.events = []
        self.connection = connection or FakeConnection(self.events)
        self.error = error

    def connect(self):
        self.events.append("CONNECT")
        if self.error:
            raise self.error
        return self.connection


class MetadataInspector:
    def __init__(self, connection):
        self.bind = connection

    def get_table_names(self, schema):
        return [*Base.metadata.tables, "alembic_version"]

    def get_columns(self, table_name, schema):
        result = []
        for model_column in Base.metadata.tables[table_name].columns:
            server_default = model_column.server_default
            default = (
                str(server_default.arg.compile(dialect=postgresql.dialect()))
                if server_default is not None
                else None
            )
            result.append(
                {
                    "name": model_column.name,
                    "type": model_column.type,
                    "nullable": model_column.nullable,
                    "default": default,
                }
            )
        return result

    def get_pk_constraint(self, table_name, schema):
        columns = Base.metadata.tables[table_name].primary_key.columns.keys()
        return {"constrained_columns": list(columns)}

    def get_foreign_keys(self, table_name, schema):
        result = []
        for constraint in Base.metadata.tables[table_name].foreign_key_constraints:
            elements = list(constraint.elements)
            result.append(
                {
                    "constrained_columns": [element.parent.name for element in elements],
                    "referred_table": elements[0].column.table.name,
                    "referred_columns": [element.column.name for element in elements],
                    "options": {"ondelete": elements[0].ondelete},
                }
            )
        return result

    def get_unique_constraints(self, table_name, schema):
        return [
            {"column_names": list(constraint.columns.keys())}
            for constraint in Base.metadata.tables[table_name].constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]

    def get_indexes(self, table_name, schema):
        return [
            {
                "column_names": list(index.columns.keys()),
                "unique": index.unique,
            }
            for index in Base.metadata.tables[table_name].indexes
        ]


def test_sqlite_is_refused_without_opening_a_connection():
    sqlite_engine = create_engine("sqlite://")
    try:
        report = schema_audit.inspect_postgres_schema(sqlite_engine)
    finally:
        sqlite_engine.dispose()

    assert report["connection"]["accessible"] is False
    assert report["error"]["type"] == "UnsupportedDialect"
    assert "no query was run" in report["error"]["message"]


def test_postgresql_sets_read_only_before_queries_and_rolls_back(monkeypatch):
    fake_engine = FakeEngine()

    def make_inspector(connection):
        assert fake_engine.events[1] == "SET TRANSACTION READ ONLY"
        assert "current_database()" in fake_engine.events[2]
        return MetadataInspector(connection)

    monkeypatch.setattr(schema_audit, "inspect", make_inspector)
    report = schema_audit.inspect_postgres_schema(fake_engine)

    assert report["connection"] == {
        "accessible": True,
        "database": "test_db",
        "schema": "public",
        "server_version": "PostgreSQL 16.4",
    }
    assert report["schema_comparison"]["missing_tables"] == []
    assert report["schema_comparison"]["type_differences"] == []
    assert report["schema_comparison"]["alembic_version"] == {
        "exists": True,
        "revisions": ["baseline_revision"],
    }
    assert fake_engine.connection.rolled_back is True
    assert fake_engine.connection.closed is True
    assert fake_engine.events[-2:] == ["ROLLBACK", "CLOSE"]


def test_connection_error_is_reported_with_sqlstate_and_sanitized_message():
    class DriverError(Exception):
        sqlstate = "08001"

    secret_url = "postgresql://user:private-password@private-host/db"
    failure = OperationalError("connect", {}, DriverError(secret_url))
    fake_engine = FakeEngine(error=failure)

    report = schema_audit.inspect_postgres_schema(fake_engine)

    assert report["connection"]["accessible"] is False
    assert report["error"]["type"] == "OperationalError"
    assert report["error"]["sqlstate"] == "08001"
    assert "driver details are omitted" in report["error"]["message"]
    assert secret_url not in str(report)
    assert "private-password" not in str(report)
    assert fake_engine.events == ["CONNECT"]


def test_connection_is_closed_if_schema_comparison_fails(monkeypatch):
    fake_engine = FakeEngine()

    def fail_inspection(_connection):
        raise RuntimeError("postgresql://user:secret@host/db")

    monkeypatch.setattr(schema_audit, "inspect", fail_inspection)
    report = schema_audit.inspect_postgres_schema(fake_engine)

    assert report["connection"]["accessible"] is True
    assert report["error"]["type"] == "RuntimeError"
    assert "secret@host" not in str(report)
    assert fake_engine.connection.rolled_back is True
    assert fake_engine.connection.closed is True
