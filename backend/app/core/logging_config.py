import json
import logging

from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format application logs as structured JSON."""

    EXTRA_FIELDS = (
        "method",
        "route",
        "status_code",
        "duration_ms",
        "source",
        "board_token",
        "fetched",
        "inserted",
        "updated",
        "reactivated",
        "deactivated",
    )

    def format(self, record: logging.LogRecord) -> str:

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in self.EXTRA_FIELDS:

            if hasattr(record, field):
                payload[field] = getattr(record, field)

        if record.exc_info:

            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )


def configure_logging() -> None:
    """Configure JSON logging for the application."""

    root_logger = logging.getLogger()

    root_logger.setLevel(logging.INFO)

    already_configured = any(
        getattr(handler, "_roleradar_json_handler", False)
        for handler in root_logger.handlers
    )

    if already_configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    handler._roleradar_json_handler = True

    root_logger.addHandler(handler)
