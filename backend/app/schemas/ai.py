import re
import unicodedata
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
    "technical_writing",
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


def _normalize_skill_key(value: str) -> str:
    """Create a stable key for punctuation and spacing variants."""

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[\s._/\-\u2010-\u2015]+", "", normalized)


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
        """Deduplicate skill variants while retaining the strongest evidence."""

        requirement_priority = {
            "mentioned": 1,
            "preferred": 2,
            "required": 3,
        }

        unique = {}

        for skill in skills:
            key = _normalize_skill_key(skill.name)
            current = unique.get(key)

            if current is None:
                unique[key] = skill
                continue

            new_priority = requirement_priority[skill.requirement]
            current_priority = requirement_priority[current.requirement]

            # Prefer a stronger requirement. For equal levels, prefer
            # the shorter, more focused evidence quotation.
            if (
                new_priority > current_priority
                or (
                    new_priority == current_priority
                    and len(skill.evidence) < len(current.evidence)
                )
            ):
                unique[key] = skill

        return list(unique.values())
