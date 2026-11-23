import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from backend.app.db.base import Base
from backend.app.models.ingestion_run import IngestionRun  # noqa: F401
from backend.app.models.job import Job  # noqa: F401
from backend.app.models.job_analysis import JobAnalysis  # noqa: F401
from backend.app.models.job_skill import JobSkill  # noqa: F401
from backend.app.models.skill import Skill  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configured_url() -> str:
    """Use the runtime URL without logging it; config has a safe local fallback."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Validate without rendering or logging credentials.
        make_url(database_url)
        return database_url
    fallback = config.get_main_option("sqlalchemy.url")
    if not fallback:
        raise RuntimeError("Set DATABASE_URL or configure sqlalchemy.url for Alembic.")
    return fallback


def run_migrations_offline() -> None:
    url = _configured_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if connection := config.attributes.get("connection"):
        _run_with_connection(connection)
        return

    url = make_url(_configured_url())
    config_section = config.get_section(config.config_ini_section, {})
    config_section["sqlalchemy.url"] = url.render_as_string(hide_password=False).replace("%", "%%")
    connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    try:
        with connectable.connect() as connection:
            _run_with_connection(connection)
    finally:
        connectable.dispose()


def _run_with_connection(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
