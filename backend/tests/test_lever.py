import asyncio

import httpx
import pytest

from scraper.lever import (
    fetch_lever_jobs,
    normalize_lever_job,
)


def test_normalize_lever_job():

    raw = {
        "id": "job-123",
        "text": "Python Backend Developer",

        "categories": {
            "location": "Remote",
            "allLocations": [
                "Remote",
                "Poland",
            ],
            "department": "Engineering",
            "team": "Platform",
        },

        "descriptionPlain": "Python and FastAPI experience.",
        "hostedUrl": "https://jobs.lever.co/demo/job-123",
    }

    result = normalize_lever_job(
        raw,
        site="demo",
        company_name="Demo Company",
    )

    assert result["source"] == "lever"
    assert result["board_token"] == "demo"
    assert result["external_id"] == "job-123"
    assert result["title"] == "Python Backend Developer"
    assert result["company"] == "Demo Company"
    assert result["location"] == "Remote"
    assert result["description"] == "Python and FastAPI experience."
    assert result["departments"] == ["Engineering"]
    assert "Poland" in result["offices"]


def test_invalid_lever_job():

    with pytest.raises(ValueError):

        normalize_lever_job(
            {"text": "Python Developer"},
            site="demo",
        )


def test_invalid_site():

    with pytest.raises(ValueError):

        asyncio.run(
            fetch_lever_jobs("../invalid")
        )


def test_lever_pagination():

    calls = []

    page_one = [
        {
            "id": "job-1",
            "text": "Backend Developer",
            "categories": {"location": "Remote"},
            "descriptionPlain": "Python",
        },
        {
            "id": "job-2",
            "text": "Python Developer",
            "categories": {"location": "Poland"},
            "descriptionPlain": "FastAPI",
        },
    ]

    page_two = [
        {
            "id": "job-3",
            "text": "AI Engineer",
            "categories": {"location": "Remote"},
            "descriptionPlain": "Machine Learning",
        }
    ]

    def handler(request: httpx.Request):

        skip = int(request.url.params.get("skip", "0"))

        calls.append(skip)

        if skip == 0:
            return httpx.Response(200, json=page_one)

        if skip == 2:
            return httpx.Response(200, json=page_two)

        return httpx.Response(200, json=[])

    async def run_test():

        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(
            transport=transport
        ) as client:

            jobs = await fetch_lever_jobs(
                site="demo",
                http_client=client,
                company_name="Demo Company",
                page_size=2,
            )

            return jobs

    jobs = asyncio.run(run_test())

    assert len(jobs) == 3
    assert calls == [0, 2]

    assert jobs[0]["external_id"] == "job-1"
    assert jobs[2]["title"] == "AI Engineer"