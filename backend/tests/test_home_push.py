"""Danger-near-home push transitions (app/pipeline/home_push.py).

Drives evaluate_home_danger directly with in-DB threats and a captured _send —
no network, no real webpush. Geometry itself is covered by test_home_danger.py;
here the subject is the ESCALATION state machine: push once per level climb,
cooldown on oscillation, prune on close, drop dead endpoints.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.models import District, PushSubscription, Threat, ThreatEvent
from app.pipeline import home_push
from app.pipeline.home_push import evaluate_home_danger

BASE = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
KM_PER_DEG_LAT = math.pi / 180 * 6371.0

HOME_LAT, HOME_LON = 50.5, 30.5


def _latlon(km_south: float, km_east: float = 0.0) -> tuple[float, float]:
    lat = HOME_LAT - km_south / KM_PER_DEG_LAT
    lon = HOME_LON + km_east / (KM_PER_DEG_LAT * math.cos(math.radians(HOME_LAT)))
    return lat, lon


@pytest_asyncio.fixture
async def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "test-pub")
    monkeypatch.setattr(settings, "vapid_private_key", "test-priv")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        sub = PushSubscription(
            endpoint="https://push.example/abc", p256dh="k", auth="a",
            home_lat=HOME_LAT, home_lon=HOME_LON, home_radius_km=3.0,
        )
        s.add(sub)
        await s.commit()
        yield s, sub
    await engine.dispose()


@pytest.fixture
def sent(monkeypatch):
    """Capture payloads instead of doing real web pushes."""
    captured: list[dict] = []

    async def _fake_send(session, sub, payload):
        captured.append(payload)

    monkeypatch.setattr(home_push, "_send", _fake_send)
    return captured


async def _mk_district(s, km_south: float, km_east: float = 0.0) -> District:
    lat, lon = _latlon(km_south, km_east)
    d = District(name_uk="Тест", name_en="Test", lat=lat, lon=lon, aliases=[])
    s.add(d)
    await s.commit()
    return d


async def _mk_threat(s, target_type="shahed", scope="district") -> Threat:
    t = Threat(target_type=target_type, scope=scope)
    s.add(t)
    await s.commit()
    return t


async def _add_event(s, threat: Threat, district: District, minute: int) -> None:
    s.add(ThreatEvent(
        threat_id=threat.id, district_id=district.id,
        event_time=BASE + timedelta(minutes=minute),
    ))
    await s.commit()


async def _load_threat(s, threat_id: int) -> Threat:
    stmt = (
        select(Threat).where(Threat.id == threat_id)
        .options()
    )
    t = await s.scalar(stmt)
    await s.refresh(t, ["events"])
    for ev in t.events:
        await s.refresh(ev, ["district"])
    return t


async def test_warning_then_danger_pushes_once_each(ctx, sent):
    s, sub = ctx
    far = await _mk_district(s, 20)
    approaching = await _mk_district(s, 15)
    inside = await _mk_district(s, 2)
    t = await _mk_threat(s)

    await _add_event(s, t, far, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert sent == []  # single point, no vector, far away

    await _add_event(s, t, approaching, 5)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert [p["level"] for p in sent] == ["warning"]

    # same level again — no re-push
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1

    await _add_event(s, t, inside, 8)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert [p["level"] for p in sent] == ["warning", "danger"]

    # danger repeats — still no re-push
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 2

    # tag is stable per track, so escalation REPLACES the warning notification
    assert {p["tag"] for p in sent} == {f"klr-home-{t.id}"}
    # level is encoded in the title: marker + «Увага:» phrasing per level
    assert sent[0]["title"].startswith("⚠️ Увага:")
    assert sent[1]["title"].startswith("‼️ Увага:")


async def test_oscillation_within_cooldown_does_not_repush(ctx, sent):
    s, sub = ctx
    far = await _mk_district(s, 20)
    approaching = await _mk_district(s, 15)
    away = await _mk_district(s, 15, km_east=18)
    t = await _mk_threat(s)

    await _add_event(s, t, far, 0)
    await _add_event(s, t, approaching, 5)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1  # warning

    # veers away -> none
    await _add_event(s, t, away, 7)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1

    # veers back onto a homeward course (far -> approaching = due north) ->
    # warning again, but within the cooldown AND already pushed at this level
    # -> silent
    await _add_event(s, t, far, 8)
    await _add_event(s, t, approaching, 9)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1


async def test_reescalation_after_cooldown_repushes(ctx, sent):
    s, sub = ctx
    far = await _mk_district(s, 20)
    approaching = await _mk_district(s, 15)
    away = await _mk_district(s, 15, km_east=18)
    t = await _mk_threat(s)

    await _add_event(s, t, far, 0)
    await _add_event(s, t, approaching, 5)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    await _add_event(s, t, away, 7)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1

    # simulate the cooldown having lapsed (relative to REAL now — the cooldown
    # clock is wall time, unlike the synthetic event times)
    state = dict(sub.danger_state)
    entry = dict(state[str(t.id)])
    entry["pushed_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    state[str(t.id)] = entry
    sub.danger_state = state
    await s.commit()

    # back onto a homeward course (far -> approaching = due north)
    await _add_event(s, t, far, 30)
    await _add_event(s, t, approaching, 40)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 2


async def test_mixed_tz_event_times_still_push(ctx, sent):
    """Live-session shape: earlier events reloaded from SQLite are naive UTC,
    the newest one still carries its aware Telegram timestamp. The whole
    evaluate path (assess + payload head-event max) must survive the mix —
    the 2026-07-18 live-e2e crash."""
    s, sub = ctx
    far = await _mk_district(s, 20)
    approaching = await _mk_district(s, 15)
    t = await _mk_threat(s)
    await _add_event(s, t, far, 0)
    await _add_event(s, t, approaching, 5)
    loaded = await _load_threat(s, t.id)
    loaded.events[0].event_time = loaded.events[0].event_time.replace(tzinfo=None)
    await evaluate_home_danger(s, loaded)
    assert [p["level"] for p in sent] == ["warning"]


async def test_ballistic_on_home_raion_goes_straight_to_danger(ctx, sent):
    s, sub = ctx
    raion = await _mk_district(s, 12)
    sub.home_district_ids = [raion.id]
    await s.commit()
    t = await _mk_threat(s, target_type="ballistic")
    await _add_event(s, t, raion, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert [p["level"] for p in sent] == ["danger"]
    # Ballistic body says «близько» with no km figure — a centroid distance
    # next to «ціль поруч» reads as contradiction.
    assert "близько" in sent[0]["body"]
    assert "км" not in sent[0]["body"]


async def test_closed_track_prunes_state(ctx, sent):
    s, sub = ctx
    inside = await _mk_district(s, 2)
    t = await _mk_threat(s)
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1
    assert str(t.id) in sub.danger_state

    t.closed_at = BASE + timedelta(minutes=10)
    await s.commit()
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert str(t.id) not in sub.danger_state


async def test_citywide_pushes_once_per_track(ctx, sent):
    # Default prefs: the city-wide alert pushes — once per track, so repeated
    # corroborations (and a grace-period reopen, same id) never re-push.
    s, sub = ctx
    inside = await _mk_district(s, 0)
    t = await _mk_threat(s, target_type="ballistic", scope="city")
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1 and sent[0]["kind"] == "citywide"


async def test_citywide_opt_out_is_silent(ctx, sent):
    s, sub = ctx
    sub.prefs = {"citywide": False}
    await s.commit()
    inside = await _mk_district(s, 0)
    t = await _mk_threat(s, target_type="ballistic", scope="city")
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert sent == []


async def test_type_filter_skips_disallowed_home_push(ctx, sent):
    # «тільки балістика»: a shahed near home stays silent, a ballistic pushes.
    s, sub = ctx
    sub.prefs = {"types": ["ballistic"]}
    await s.commit()
    inside = await _mk_district(s, 0)
    t = await _mk_threat(s, target_type="shahed")
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert sent == []
    tb = await _mk_threat(s, target_type="ballistic")
    await _add_event(s, tb, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, tb.id))
    assert len(sent) == 1


async def test_danger_only_floor_skips_warning(ctx, sent):
    # min_level=danger: the approach WARNING stays silent; the close-in DANGER
    # still pushes even though warning was never sent.
    s, sub = ctx
    sub.prefs = {"min_level": "danger"}
    await s.commit()
    far = await _mk_district(s, 9)     # warning band
    near = await _mk_district(s, 1)    # danger band
    t = await _mk_threat(s, target_type="shahed")
    await _add_event(s, t, far, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert sent == []
    await _add_event(s, t, near, 1)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert len(sent) == 1 and sent[0]["level"] == "danger"


async def test_unconfigured_push_is_silent_noop(ctx, sent, monkeypatch):
    s, sub = ctx
    monkeypatch.setattr(settings, "vapid_private_key", "")
    inside = await _mk_district(s, 0)
    t = await _mk_threat(s)
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    assert sent == []


async def test_gone_endpoint_deletes_subscription(ctx, monkeypatch):
    s, sub = ctx

    class _Resp:
        status_code = 410

    def _fake_webpush(**kwargs):
        from pywebpush import WebPushException

        raise WebPushException("gone", response=_Resp())

    monkeypatch.setattr("pywebpush.webpush", _fake_webpush)
    inside = await _mk_district(s, 0)
    t = await _mk_threat(s)
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))
    remaining = list(await s.scalars(select(PushSubscription)))
    assert remaining == []
