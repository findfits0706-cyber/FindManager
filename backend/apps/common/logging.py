import json
import logging
from datetime import UTC, datetime

from .request_context import get_request_id


class SafeJsonFormatter(logging.Formatter):
    """Emit a fixed metadata allowlist; request bodies and headers never enter the record."""

    optional_fields = (
        "method",
        "path",
        "status",
        "duration_ms",
        "user_id",
        "role",
        "exception_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
        }
        for field in self.optional_fields:
            value = getattr(record, field, None)
            if value not in {None, ""}:
                payload[field] = value
        if record.exc_info and "exception_type" not in payload:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
