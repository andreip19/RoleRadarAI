from datetime import datetime

from pydantic import BaseModel


class AnalysisSkillRead(BaseModel):
    id: int
    name: str
    category: str | None
    requirement: str
    evidence: str


class JobAnalysisRead(BaseModel):
    job_id: int
    content_hash: str
    model_name: str
    status: str
    category: str | None
    seniority: str | None
    summary: str | None
    result_json: dict | None
    analyzed_at: datetime | None
    skills: list[AnalysisSkillRead]


class SkillCatalogItem(BaseModel):
    id: int
    name: str
    normalized_name: str
    category: str | None
    job_count: int


class SkillListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SkillCatalogItem]


class SkillSummary(BaseModel):
    id: int
    name: str
    normalized_name: str
    category: str | None


class SkillJobItem(BaseModel):
    job_id: int
    title: str
    company: str | None
    location: str | None
    source: str
    url: str | None
    is_active: bool
    requirement: str
    evidence: str


class SkillJobsResponse(BaseModel):
    skill: SkillSummary
    total: int
    limit: int
    offset: int
    items: list[SkillJobItem]
