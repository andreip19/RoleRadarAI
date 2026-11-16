from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    func,
    text,
)

from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class IngestionRun(Base):

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    board_token: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
    )

    fetched: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    inserted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    updated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    reactivated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    deactivated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
