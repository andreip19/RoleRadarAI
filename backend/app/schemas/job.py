from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int

    source: str
    board_token: str
    external_id: str

    title: str
    company: str | None
    location: str | None

    description: str | None
    url: str | None

    source_updated_at: str | None

    departments: list[str]
    offices: list[str]

    first_seen_at: datetime
    last_seen_at: datetime


class JobListResponse(BaseModel):

    total: int
    limit: int
    offset: int

    items: list[JobRead]