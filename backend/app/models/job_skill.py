from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)

from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class JobSkill(Base):

    __tablename__ = "job_skills"

    __table_args__ = (
        Index("ix_job_skills_skill_id", "skill_id"),
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )

    requirement: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="mentioned",
    )

    evidence: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
