import re
from typing import Any, Literal

import httpx

from scraper.greenhouse import clean_html


GLOBAL_API = "https://api.lever.co/v0/postings"
EU_API = "https://api.eu.lever.co/v0/postings"


def normalize_lever_job(
    raw: dict[str, Any],
    site: str,
    company_name: str | None = None,
) -> dict[str, Any]:
    """Normalize a Lever posting into the RoleRadar AI job format."""

    job_id = raw.get("id")
    title = raw.get("text")

    if not job_id or not title:
        raise ValueError("Lever job must contain an ID and title.")

    categories = raw.get("categories") or {}

    if not isinstance(categories, dict):
        categories = {}

    locations = categories.get("allLocations") or []

    if not isinstance(locations, list):
        locations = []

    locations = [
        str(location).strip()
        for location in locations
        if location
    ]

    primary_location = categories.get("location")

    if not primary_location and locations:
        primary_location = locations[0]

    department = categories.get("department")

    departments = (
        [str(department).strip()]
        if department
        else []
    )

    description = (
        raw.get("descriptionPlain")
        or raw.get("descriptionBodyPlain")
        or clean_html(raw.get("description"))
    )

    updated_at = raw.get("updatedAt")

    return {
        "source": "lever",
        "board_token": site,
        "external_id": str(job_id),

        "title": str(title).strip(),
        "company": company_name,
        "location": primary_location,

        "description": description,
        "url": raw.get("hostedUrl"),

        "updated_at": (
            str(updated_at)
            if updated_at is not None
            else None
        ),

        "departments": departments,
        "offices": locations or (
            [primary_location]
            if primary_location
            else []
        ),
    }


async def fetch_lever_jobs(
    site: str,
    http_client: httpx.AsyncClient | None = None,
    company_name: str | None = None,
    region: Literal["global", "eu"] = "global",
    page_size: int = 100,
    max_pages: int = 50,
) -> list[dict[str, Any]]:
    """
    Retrieve all public Lever postings using pagination.

    Public GET endpoint. No API key required.
    """

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", site):
        raise ValueError("Invalid Lever site identifier.")

    if region not in ("global", "eu"):
        raise ValueError("Region must be 'global' or 'eu'.")

    if not 1 <= page_size <= 100:
        raise ValueError("Page size must be between 1 and 100.")

    if not 1 <= max_pages <= 50:
        raise ValueError("Max pages must be between 1 and 50.")

    api_base = EU_API if region == "eu" else GLOBAL_API

    url = f"{api_base}/{site}"

    async def collect(client: httpx.AsyncClient):
        all_jobs: list[dict[str, Any]] = []
        skip = 0

        for _ in range(max_pages):

            response = await client.get(
                url,
                params={
                    "mode": "json",
                    "skip": skip,
                    "limit": page_size,
                },
            )

            response.raise_for_status()

            payload = response.json()

            if not isinstance(payload, list):
                raise ValueError(
                    "Invalid Lever response: expected a JSON array."
                )

            for item in payload:

                if not isinstance(item, dict):
                    continue

                if not item.get("id") or not item.get("text"):
                    continue

                all_jobs.append(
                    normalize_lever_job(
                        item,
                        site=site,
                        company_name=company_name,
                    )
                )

            if len(payload) < page_size:
                return all_jobs

            skip += len(payload)

        raise RuntimeError(
            "Lever pagination reached its safety limit. "
            "The collection may be incomplete."
        )

    if http_client is not None:
        return await collect(http_client)

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": "RoleRadarAI/0.2",
        },
    ) as client:
        return await collect(client)