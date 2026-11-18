import os

from pathlib import Path

from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load local environment configuration.
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

# SQLite remains the fallback when DATABASE_URL is not configured.
if not DATABASE_URL:

    DATA_DIR = PROJECT_ROOT / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    DATABASE_PATH = DATA_DIR / "roleradar.db"

    DATABASE_URL = URL.create(
        "sqlite",
        database=str(DATABASE_PATH),
    )


parsed_url = make_url(DATABASE_URL)

engine_options = {
    "pool_pre_ping": True,
}

if parsed_url.get_backend_name() == "sqlite":

    engine_options["connect_args"] = {
        "check_same_thread": False,
    }

    # Share one in-memory database between test connections.
    if parsed_url.database in (None, "", ":memory:"):

        engine_options["poolclass"] = StaticPool
else:
    engine_options.update(
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    )


engine = create_engine(
    DATABASE_URL,
    **engine_options,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)
