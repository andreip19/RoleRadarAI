import pytest

from scraper.greenhouse import (
    clean_html,
    normalize_greenhouse_job,
)


def test_clean_html():

    html = """
    <p>Python Developer</p>
    <p>Experience with <strong>FastAPI</strong></p>
    """

    result = clean_html(html)

    assert result == (
        "Python Developer Experience with FastAPI"
    )


def test_normalize_greenhouse_job():

    raw = {
        "id": 12345,
        "title": "Python Developer",
        "location": {
            "name": "Remote"
        },
        "content": "<p>Python and FastAPI</p>",
        "absolute_url": "https://example.com/job/12345",
        "updated_at": "2026-11-16T08:00:00Z",
        "departments": [
            {"name": "Engineering"}
        ],
        "offices": [
            {"name": "Remote"}
        ]
    }

    result = normalize_greenhouse_job(raw, "demo")

    assert result["external_id"] == "12345"
    assert result["source"] == "greenhouse"
    assert result["title"] == "Python Developer"
    assert result["location"] == "Remote"
    assert result["description"] == "Python and FastAPI"
    assert "Engineering" in result["departments"]


def test_invalid_job():

    with pytest.raises(ValueError):
        normalize_greenhouse_job(
            {"title": "Python Developer"},
            "demo"
        )