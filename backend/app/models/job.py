from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class Job(Base):

    __tablename__ = "jobs"

    __table_args__ = (
        UniqueConstraint(
            "source",
            "board_token",
            "external_id",
            name="uq_job_source_board_external",
        ),
        Index("ix_jobs_title", "title"),
        Index("ix_jobs_company", "company"),
        Index("ix_jobs_location", "location"),
        Index("ix_jobs_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    board_token: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    external_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    company: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    source_updated_at: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    departments: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    offices: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    missing_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    inactive_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"Job(id={self.id}, "
            f"title={self.title!r}, "
            f"company={self.company!r}, "
            f"is_active={self.is_active})"
        )
