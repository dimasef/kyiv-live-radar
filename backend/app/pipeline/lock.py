"""The single ingest serialization lock, in its own neutral module so the ingest
pipeline and the async triage engine can share it without an import cycle (they
call into each other, so the lock can't live in either)."""

from __future__ import annotations

import asyncio

# Serialize ingestion: concurrent inbound messages sharing one open track would
# otherwise race (split tracks, wrong corroboration, SQLite "database is locked").
# Single-instance MVP — one lock is enough; multi-instance would move to the DB.
ingest_lock = asyncio.Lock()

# True while a rebuild replays history. The sweeper closes by wall clock and
# would retire every just-rebuilt old track on its first tick; the rebuild
# sweeps by message time itself (pipeline/reprocess.py).
reprocess_running = False
