"""Sanity checks for the real-data replay feed (app/replay.py) — not a full
871-message run (too slow for CI), just that the bundled dataset is valid and
the pipeline accepts it end-to-end for a handful of messages."""

from datetime import datetime

import pytest_asyncio

from app.feeds.replay import _CHANNELS, _load_messages
from app.models import Source
from app.pipeline.ingest import ingest_message
from tests.conftest import district_rows


@pytest_asyncio.fixture
async def ctx(session, standard_matcher):
    session.add_all(district_rows())
    await session.commit()
    return session, standard_matcher


def test_dataset_loads_and_is_well_formed():
    messages = _load_messages()
    assert len(messages) > 500  # the bundled backfill has 871
    for m in messages[:20]:
        assert m["channel_key"] in _CHANNELS
        assert m["text"]
        datetime.fromisoformat(m["time"])  # must not raise


def test_dataset_is_chronologically_sorted():
    messages = _load_messages()
    times = [datetime.fromisoformat(m["time"]) for m in messages]
    assert times == sorted(times)


async def test_replay_a_handful_of_messages_through_the_real_pipeline(ctx):
    """Confirms real captured text flows through the real ingest pipeline
    without raising — a lightweight stand-in for run_replay() itself, which
    uses its own SessionLocal (tied to the app's configured DB) rather than
    this test's temp engine."""
    s, m = ctx
    key_to_id = {}
    for key, name in _CHANNELS.items():
        src = Source(channel_key=key, name=name)
        s.add(src)
        await s.flush()
        key_to_id[key] = src.id
    await s.commit()

    for msg in _load_messages()[:5]:
        await ingest_message(
            s, text=msg["text"], matcher=m,
            when=datetime.fromisoformat(msg["time"]),
            source_id=key_to_id[msg["channel_key"]], message_id=msg["message_id"],
            reply_to_message_id=msg["reply_to_message_id"],
        )
