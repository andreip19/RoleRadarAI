from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    String,
    UniqueConstraint,
    func,
)

from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class Skill(Base):

    __tablename__ = "skills"

    __table_args__ = (
        UniqueConstraint(
            "normalized_name",
            name="uq_skill_normalized_name",
        ),
        Index("ix_skills_category", "category"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    category: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"Skill(id={self.id}, "
            f"name={self.name!r}, "
            f"category={self.category!r})"
        )
