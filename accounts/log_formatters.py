import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy to grep, ship to ELK/Loki, or load in pandas."""

    def format(self, record):
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            entry.update({k: v for k, v in ctx.items() if v not in (None, "", {})})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)
