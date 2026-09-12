"""GET /sync must give a reconnecting client exactly what it missed — no more
(a full re-fetch after a deploy is the storm this exists to prevent) and never
less (a missed frame is a target the reader does not see)."""
from __future__ import annotations

from collections import deque

from app.realtime.ws import manager
from app.schemas import WSMessage


async def test_client_at_the_head_of_the_stream_is_current(client):
    r = (await client.get(f"/sync?epoch={manager.epoch}&seq={manager.seq}")).json()
    assert r["status"] == "current"
    assert r["frames"] == [] and r["snapshot"] is None


async def test_missed_frames_are_replayed_in_order(client):
    at = manager.seq
    await manager.broadcast(WSMessage(type="health", feed_ok=True))
    await manager.broadcast(WSMessage(type="ping"))
    await manager.broadcast(WSMessage(type="health", feed_ok=False))
    r = (await client.get(f"/sync?epoch={manager.epoch}&seq={at}")).json()
    assert r["status"] == "delta"
    assert [f["type"] for f in r["frames"]] == ["health", "health"]
    assert [f["feed_ok"] for f in r["frames"]] == [True, False]
    assert [f["seq"] for f in r["frames"]] == [at + 1, at + 2]
    assert r["seq"] == at + 2


async def test_another_process_means_a_full_snapshot(client):
    r = (await client.get(f"/sync?epoch={manager.epoch - 1}&seq=0")).json()
    assert r["status"] == "full"
    snap = r["snapshot"]
    assert set(snap) >= {
        "threats", "incidents", "recent_incidents", "axes", "alerts", "zones",
        "events", "notices", "sources", "server_time", "feed_ok",
    }
    assert snap["threats"] == (await client.get("/threats/active")).json()
    assert snap["events"] == (await client.get("/events/recent?limit=60")).json()


async def test_a_gap_older_than_the_history_is_a_full_snapshot(client, monkeypatch):
    monkeypatch.setattr(manager, "_history", deque(maxlen=2))
    at = manager.seq
    for ok in (True, False, True):
        await manager.broadcast(WSMessage(type="health", feed_ok=ok))
    assert (await client.get(f"/sync?epoch={manager.epoch}&seq={at}")).json()["status"] == "full"
    assert (await client.get(f"/sync?epoch={manager.epoch}&seq={at + 1}")).json()["status"] == "delta"


async def test_no_position_is_a_full_snapshot(client):
    assert (await client.get("/sync")).json()["status"] == "full"


async def test_the_feed_slice_honours_the_reader_s_page(client):
    r = (await client.get("/sync?limit=30&region=kyiv")).json()
    assert r["snapshot"]["events"] == (await client.get("/events/recent?limit=30&region=kyiv")).json()
