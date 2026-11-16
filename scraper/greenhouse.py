import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx


class HTMLTextParser(HTMLParser):
    """Extract readable text from an HTML document."""

    BLOCK_TAGS = {
        "p", "div", "br", "li", "ul", "ol",
        "h1", "h2", "h3", "h4", "section"
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def clean_html(content: str | None) -> str | None:
    """Convert HTML job descriptions into readable text."""

    if not content:
        return None

    parser = HTMLTextParser()
    parser.feed(unescape(content))
    parser.close()

    text = " ".join(" ".join(parser.parts).split())

    return text or None


def normalize_greenhouse_job(
    raw: dict[str, Any],
    board_token: str
) -> dict[str, Any]:
    """Convert a Greenhouse job into the internal data format."""

    job_id = raw.get("id")
    title = raw.get("title")

    if job_id is None or not title:
        raise ValueError("Job must contain an ID and title.")

    location = raw.get("location")

    if isinstance(location, dict):
        location = location.get("name")

    def extract_names(items):
        if not isinstance(items, list):
            return []

        return [
            item["name"]
            for item in items
            if isinstance(item, dict) and item.get("name")
        ]

    return {
        "source": "greenhouse",
        "external_id": str(job_id),
        "board_token": board_token,
        "title": str(title).strip(),
        "company": raw.get("company_name"),
        "location": location,
        "description": clean_html(raw.get("content")),
        "url": raw.get("absolute_url"),
        "updated_at": raw.get("updated_at"),
        "departments": extract_names(raw.get("departments")),
        "offices": extract_names(raw.get("offices")),
    }


async def fetch_greenhouse_jobs(
    board_token: str,
    http_client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Fetch all published jobs from a public Greenhouse board."""

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", board_token):
        raise ValueError("Invalid Greenhouse board token.")

    url = (
        "https://boards-api.greenhouse.io"
        f"/v1/boards/{board_token}/jobs"
    )

    async def request(client):
        response = await client.get(
            url,
            params={"content": "true"},
            headers={
                "Accept": "application/json",
                "User-Agent": "RoleRadarAI/0.1",
            }
        )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Invalid Greenhouse response.")

        jobs = payload.get("jobs", [])

        if not isinstance(jobs, list):
            raise ValueError("Invalid jobs collection.")

        return [
            normalize_greenhouse_job(job, board_token)
            for job in jobs
            if isinstance(job, dict)
        ]

    if http_client is not None:
        return await request(http_client)

    async with httpx.AsyncClient(
        timeout=25.0,
        follow_redirects=True
    ) as client:
        return await request(client)