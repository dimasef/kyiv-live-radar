"""The WebSocket fan-out (app/pipeline/broadcast.py).

One message naming several raions produces one Broadcast PER RAION for the same
track (handlers._handle_sighting). The fan-out used to re-read that track, and
re-run the danger assessment — which scans every push subscription — once per
raion. Each client still gets its per-raion frame; the per-TRACK work happens
once.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.models import District, Threat, ThreatEvent
from app.pipeline import broadcast as broadcast_mod
from app.pipeline.broadcast import broadcast_results
from app.pipeline.results import Broadcast


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'b.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _track_over(session, names: list[str]) -> tuple[Threat, list[ThreatEvent]]:
    threat = Threat(target_type="shahed", status="tracking")
    session.add(threat)
    await session.commit()
    events = []
    for i, name in enumerate(names):
        d = District(name_uk=name, name_en=name, lat=50.4 + i / 100, lon=30.5)
        session.add(d)
        await session.commit()
        ev = ThreatEvent(threat_id=threat.id, district_id=d.id, raw_text=name)
        session.add(ev)
        await session.commit()
        events.append(ev)
    return threat, events


async def test_one_track_over_five_raions_is_loaded_and_assessed_once(db, monkeypatch):
    threat, events = await _track_over(db, ["A", "B", "C", "D", "E"])

    loads: list[int] = []
    real_load = broadcast_mod._load_full

    async def counting_load(session, threat_id):
        loads.append(threat_id)
        return await real_load(session, threat_id)

    danger_calls: list[int] = []

    async def fake_danger(session, t):
        danger_calls.append(t.id)

    sent: list = []

    async def fake_broadcast(msg):
        sent.append(msg)

    monkeypatch.setattr(broadcast_mod, "_load_full", counting_load)
    monkeypatch.setattr(broadcast_mod, "evaluate_home_danger", fake_danger)
    monkeypatch.setattr(broadcast_mod.manager, "broadcast", fake_broadcast)

    await broadcast_results(db, [Broadcast("event", threat, ev) for ev in events])

    # Every raion still reaches the clients…
    assert len(sent) == 5
    # …but the per-track work happens once.
    assert loads == [threat.id]
    assert danger_calls == [threat.id]


async def test_two_different_tracks_are_each_loaded(db, monkeypatch):
    # The dedup must be per track, not "only the first one" — two genuinely
    # different targets in one batch both need loading and assessing.
    first, first_events = await _track_over(db, ["A"])
    second, second_events = await _track_over(db, ["B"])

    loads: list[int] = []
    real_load = broadcast_mod._load_full

    async def counting_load(session, threat_id):
        loads.append(threat_id)
        return await real_load(session, threat_id)

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(broadcast_mod, "_load_full", counting_load)
    monkeypatch.setattr(broadcast_mod, "evaluate_home_danger", noop)
    monkeypatch.setattr(broadcast_mod.manager, "broadcast", noop)

    await broadcast_results(
        db,
        [
            Broadcast("event", first, first_events[0]),
            Broadcast("event", second, second_events[0]),
        ],
    )
    assert sorted(loads) == sorted([first.id, second.id])


async def test_impact_markers_never_reach_a_client(db, monkeypatch):
    # Where a strike landed is withheld live (see api/public/threats.py). The
    # filter lives in the fan-out so a new producer can't reintroduce the leak.
    threat, events = await _track_over(db, ["A"])
    threat.kind = "impact"
    await db.commit()

    sent: list = []

    async def fake_broadcast(msg):
        sent.append(msg)

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(broadcast_mod, "evaluate_home_danger", noop)
    monkeypatch.setattr(broadcast_mod.manager, "broadcast", fake_broadcast)

    await broadcast_results(db, [Broadcast("event", threat, events[0])])
    assert sent == []
