"""Create the initial RoleRadar schema.

Revision ID: 20261123_0001
Revises:
Create Date: 2026-11-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261123_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("board_token", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("reactivated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deactivated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_runs_source", "ingestion_runs", ["source"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("board_token", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("source_updated_at", sa.String(length=100), nullable=True),
        sa.Column("departments", sa.JSON(), nullable=False),
        sa.Column("offices", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("missing_runs", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("inactive_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "board_token", "external_id", name="uq_job_source_board_external"),
    )
    op.create_index("ix_jobs_company", "jobs", ["company"], unique=False)
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"], unique=False)
    op.create_index("ix_jobs_location", "jobs", ["location"], unique=False)
    op.create_index("ix_jobs_title", "jobs", ["title"], unique=False)

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", name="uq_skill_normalized_name"),
    )
    op.create_index("ix_skills_category", "skills", ["category"], unique=False)

    op.create_table(
        "job_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_job_analysis_job_id"),
    )
    op.create_index("ix_job_analyses_status", "job_analyses", ["status"], unique=False)

    op.create_table(
        "job_skills",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("requirement", sa.String(length=20), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "skill_id"),
    )
    op.create_index("ix_job_skills_skill_id", "job_skills", ["skill_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_skills_skill_id", table_name="job_skills")
    op.drop_table("job_skills")
    op.drop_index("ix_job_analyses_status", table_name="job_analyses")
    op.drop_table("job_analyses")
    op.drop_index("ix_skills_category", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_jobs_title", table_name="jobs")
    op.drop_index("ix_jobs_location", table_name="jobs")
    op.drop_index("ix_jobs_is_active", table_name="jobs")
    op.drop_index("ix_jobs_company", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_ingestion_runs_source", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
