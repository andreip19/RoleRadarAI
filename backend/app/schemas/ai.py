from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RoleCategory = Literal[
    "software_engineering",
    "data_engineering",
    "data_science",
    "machine_learning",
    "devops",
    "cloud_engineering",
    "cybersecurity",
    "quality_assurance",
    "it_support",
    "enterprise_architecture",
    "professional_services",
    "consulting",
    "product_management",
    "project_management",
    "sales",
    "marketing",
    "customer_success",
    "design",
    "business_operations",
    "human_resources",
    "finance",
    "legal",
    "executive_management",
    "other",
]

SkillCategory = Literal[
    "programming_language",
    "framework",
    "library",
    "database",
    "cloud",
    "devops",
    "tool",
    "methodology",
    "concept",
    "other",
]

RequirementLevel = Literal[
    "required",
    "preferred",
    "mentioned",
]

SeniorityLevel = Literal[
    "intern",
    "junior",
    "mid",
    "senior",
    "lead",
    "manager",
    "principal",
    "director",
    "executive",
    "unknown",
]


class ExtractedSkill(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=120,
        description="Technical skill name, copied from the supporting evidence.",
    )

    category: SkillCategory

    requirement: RequirementLevel

    evidence: str = Field(
        min_length=3,
        max_length=500,
        description="Exact quotation from the job description supporting this skill.",
    )

    @field_validator("name", "evidence")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Value cannot be empty.")

        return value


class JobAnalysisResult(BaseModel):

    model_config = ConfigDict(extra="forbid")

    role_category: RoleCategory

    seniority: SeniorityLevel

    summary: str = Field(
        min_length=10,
        max_length=1000,
    )

    skills: list[ExtractedSkill] = Field(
        max_length=30,
    )

    @field_validator("skills")
    @classmethod
    def remove_duplicate_skills(
        cls,
        skills: list[ExtractedSkill],
    ) -> list[ExtractedSkill]:

        unique = {}

        for skill in skills:
            key = " ".join(skill.name.casefold().split())

            if key not in unique:
                unique[key] = skill

        return list(unique.values())
