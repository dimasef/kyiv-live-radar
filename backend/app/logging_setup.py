"""Single place that configures process-wide logging — called once by each
entrypoint (main.py's API process, worker.py's standalone listener), so the
format/level can't drift between the two."""

from __future__ import annotations

import logging


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO)
