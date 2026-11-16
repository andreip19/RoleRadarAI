from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_metrics_endpoint():

    # Generate at least one HTTP metric.
    health_response = client.get("/health")

    assert health_response.status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200

    assert (
        "roleradar_http_requests_total"
        in response.text
    )

    assert (
        "roleradar_http_request_duration_seconds"
        in response.text
    )

    assert 'route="/health"' in response.text


def test_metrics_content_type():

    response = client.get("/metrics")

    assert response.status_code == 200

    assert response.headers["content-type"].startswith(
        "text/plain"
    )
