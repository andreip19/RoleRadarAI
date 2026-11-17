from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.dependencies import get_db
from backend.app.main import app
from backend.app.models.job import Job


def test_job_search_matches_company_and_source_filter_paginates():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with Session(engine) as db:
            db.add_all(
                [
                    Job(source="greenhouse", board_token="acme", external_id="1", title="Backend Engineer", company="Acme Labs", description="Build APIs", last_seen_at=datetime.now(timezone.utc)),
                    Job(source="lever", board_token="acme", external_id="2", title="Backend Engineer", company="Acme Labs", description="Build services", last_seen_at=datetime.now(timezone.utc)),
                    Job(source="lever", board_token="other", external_id="3", title="Data Engineer", company="Other Co", description="Build data systems", last_seen_at=datetime.now(timezone.utc)),
                ]
            )
            db.commit()

        client = TestClient(app)
        response = client.get(
            "/api/v1/jobs",
            params={"q": "Acme Labs", "source": "lever", "limit": 1},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["limit"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["source"] == "lever"
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()
