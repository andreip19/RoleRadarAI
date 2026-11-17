import asyncio
import json
import logging

from backend.app.core.logging_config import configure_logging
from backend.app.db.session import SessionLocal
from backend.app.services.ingestion_service import run_all_ingestion


def main() -> int:
    """Execute all configured job ingestion connectors."""

    configure_logging()

    logger = logging.getLogger("roleradar.runner")

    try:

        with SessionLocal() as db:
            result = asyncio.run(
                run_all_ingestion(db)
            )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )

        if result.get("failed", 0) > 0:
            logger.error("ingestion_runner_failed")
            return 1

        if result.get("succeeded") != result.get("total_sources"):
            logger.error("ingestion_runner_incomplete")
            return 1

        logger.info("ingestion_runner_successful")

        return 0

    except Exception:

        logger.exception("ingestion_runner_crashed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
