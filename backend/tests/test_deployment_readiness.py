from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app import main
from backend.app.api import ingestion
from backend.app.core.security import require_admin, validate_production_config


client = TestClient(main.app)


def test_write_route_rejects_missing_admin_token_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_API_TOKEN", "deployment-test-token")

    response = client.post("/api/v1/ingestion/run-all")

    assert response.status_code == 401


def test_write_route_accepts_admin_bearer_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_API_TOKEN", "deployment-test-token")

    async def fake_run_all(_db):
        return {"status": "accepted"}

    monkeypatch.setattr(ingestion, "run_all_ingestion", fake_run_all)
    response = client.post(
        "/api/v1/ingestion/run-all",
        headers={"Authorization": "Bearer deployment-test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}


def test_read_routes_remain_public(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_API_TOKEN", "deployment-test-token")

    response = client.get("/health")

    assert response.status_code == 200


def test_production_startup_requires_admin_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    try:
        validate_production_config()
    except RuntimeError as exc:
        assert "ADMIN_API_TOKEN" in str(exc)
    else:
        raise AssertionError("Production configuration should require a token.")


def test_ready_returns_503_without_database_connection(monkeypatch):
    monkeypatch.setattr(
        main.engine,
        "connect",
        lambda: (_ for _ in ()).throw(
            OperationalError("SELECT 1", {}, Exception("private connection detail"))
        ),
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "service": "backend"}
    assert "private connection detail" not in response.text


def test_ready_executes_database_query(monkeypatch):
    class Connection:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            self.statements.append(str(statement))

    connection = Connection()
    monkeypatch.setattr(main.engine, "connect", lambda: connection)

    response = client.get("/ready")

    assert response.status_code == 200
    assert connection.statements == ["SELECT 1"]


def test_development_admin_access_is_explicitly_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    assert require_admin() is None


def test_development_cors_includes_local_vite_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")

    origins = main.configured_cors_origins()

    assert origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_production_cors_requires_explicit_origin_and_rejects_wildcard(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.invalid")

    assert main.configured_cors_origins() == ["https://example.invalid"]

    monkeypatch.setenv("CORS_ORIGINS", "*")
    try:
        main.configured_cors_origins()
    except RuntimeError as exc:
        assert "wildcard" in str(exc)
    else:
        raise AssertionError("Wildcard CORS origins must be rejected.")
