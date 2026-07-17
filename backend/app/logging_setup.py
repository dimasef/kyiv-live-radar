"""Single place that configures process-wide logging — called once by each
entrypoint (main.py's API process, worker.py's standalone listener), so the
format/level can't drift between the two."""

from __future__ import annotations

import json
import logging

from .config import settings


class _JsonFormatter(logging.Formatter):
    """One JSON object per line so Railway's log viewer can parse/filter fields.
    Deliberately dependency-free (no python-json-logger) — the record has only a
    handful of fields worth shipping."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    if settings.log_json:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    else:
        logging.basicConfig(level=logging.INFO)
