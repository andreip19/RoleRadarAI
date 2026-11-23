import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.app.db.base import Base
from backend.app.models import ingestion_run, job, job_analysis, job_skill, skill  # noqa: F401


ROOT = Path(__file__).resolve().parents[2]


def test_alembic_config_and_revision_head_are_loadable():
    config = Config(str(ROOT / "alembic.ini"))

    assert Path(config.get_main_option("script_location")).resolve() == (ROOT / "migrations").resolve()
    assert set(ScriptDirectory.from_config(config).get_heads()) == {"20261123_0001"}


def test_model_metadata_registers_all_tables_and_cascades():
    assert set(Base.metadata.tables) == {
        "jobs",
        "ingestion_runs",
        "job_analyses",
        "job_skills",
        "skills",
    }

    job_analysis_table = Base.metadata.tables["job_analyses"]
    assert next(iter(job_analysis_table.foreign_keys)).ondelete == "CASCADE"
    job_skill_table = Base.metadata.tables["job_skills"]
    assert {fk.ondelete for fk in job_skill_table.foreign_keys} == {"CASCADE"}


def test_alembic_heads_works_outside_repository_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "heads"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "20261123_0001 (head)" in result.stdout
