"""Danger-near-home push transitions (app/pipeline/home_push.py).

Drives evaluate_home_danger directly with in-DB threats and a captured _send —
no network, no real webpush. Geometry itself is covered by test_home_danger.py;
here the subject is the ESCALATION state machine: push once per level climb,
cooldown on oscillation, prune on close, drop dead endpoints.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.models import District, Notice, PushSubscription, Source, Threat, ThreatEvent
from app.pipeline import home_push
from app.pipeline.home_push import evaluate_home_danger, evaluate_regional_ballistic

BASE = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
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

    async def _fake_send(session, sub, payload, ttl=300):
        captured.append(payload)

    # home_push now calls the shared webpush.send_push (imported into its module
    # namespace) — patch that bound name.
    monkeypatch.setattr(home_push, "send_push", _fake_send)
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
    # Type leads the title; level is encoded by the marker + phrasing.
    assert sent[0]["title"].startswith("⚠️ ") and "прямує у ваш бік" in sent[0]["title"]
    assert sent[1]["title"].startswith("‼️ ") and "поруч із домом" in sent[1]["title"]


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
    entry["pushed_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
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
    # Type leads the title; ballistic carries NO km figure in the body (a
    # centroid distance next to «поруч» reads as a contradiction) — just the raion.
    assert "поруч із домом" in sent[0]["title"]
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


async def test_a_legacy_subscription_with_null_state_still_pushes(ctx, sent):
    # danger_state is nullable and rows predating it carry SQL NULL. Every
    # `.get`/`in` in the evaluator turned that into an AttributeError raised
    # INSIDE the fan-out, taking down the notification for everyone batched
    # with it — not just the one stale row.
    s, sub = ctx
    sub.danger_state = None
    await s.commit()

    inside = await _mk_district(s, 2)
    t = await _mk_threat(s)
    await _add_event(s, t, inside, 0)
    await evaluate_home_danger(s, await _load_threat(s, t.id))

    assert len(sent) == 1
    assert str(t.id) in sub.danger_state


async def test_a_legacy_subscription_with_null_state_survives_citywide(ctx, sent):
    s, sub = ctx
    sub.danger_state = None
    await s.commit()

    t = await _mk_threat(s, target_type="ballistic", scope="city")
    await evaluate_home_danger(s, await _load_threat(s, t.id))

    assert len(sent) == 1


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


# --- Oblast-wide ballistic (evaluate_regional_ballistic) --------------------
#
# The northern channels never name a raion for ballistics, so those messages
# never become a track — they arrive as a threat-level NOTICE and the raion
# escalation has nothing to fire on. These cover the replacement path and, just
# as importantly, that it stays OFF for the homes the raion path already serves.

async def _mk_source(s, region: str) -> Source:
    src = Source(channel_key=f"ch_{region}", name=region, region=region)
    s.add(src)
    await s.commit()
    return src


async def _mk_notice(s, source: Source, *, kind="forecast", text="Загроза балістики",
                     target_type="ballistic", origin=None) -> Notice:
    n = Notice(kind=kind, text=text, target_type=target_type, origin=origin,
               source_id=source.id, event_time=BASE)
    s.add(n)
    await s.commit()
    await s.refresh(n, ["source"])
    return n


async def test_oblast_ballistic_warns_a_home_the_raion_path_cannot_serve(ctx, sent):
    s, sub = ctx
    sub.region = "sumy"
    await s.commit()
    n = await _mk_notice(s, await _mk_source(s, "sumy"), origin="kursk")

    await evaluate_regional_ballistic(s, n)

    assert len(sent) == 1
    assert sent[0]["level"] == "warning"
    assert sent[0]["kind"] == "regional-ballistic"
    # Both names nominative — see _regional_ballistic_payload.
    assert "Сумщина." in sent[0]["body"]
    assert "Курщина" in sent[0]["body"]


async def test_a_kyiv_city_home_is_not_woken_twice(ctx, sent):
    """The gate that keeps Kyiv exactly as it is: a home that resolved to raion
    ids already has the (sharper) raion escalation, so the oblast one skips it."""
    s, sub = ctx
    sub.home_district_ids = [1, 2]
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "kyiv")))

    assert sent == []


async def test_a_kyiv_oblast_home_outside_the_city_does_get_it(ctx, sent):
    """boundaries.json covers the 10 city raions only, so a home in Бровари
    resolves to no raion at all — the gap this path exists for."""
    s, sub = ctx
    sub.home_district_ids = []
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "kyiv")))

    assert len(sent) == 1


async def test_a_device_following_another_region_stays_asleep(ctx, sent):
    s, sub = ctx
    sub.region = "chernihiv"
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "sumy")))

    assert sent == []


@pytest.mark.parametrize("text", [
    "Найближчим часом можлива повторна хвиля балістики",
    "Поки ще діє балістична загроза",
])
async def test_a_wave_that_is_not_in_the_sky_does_not_push(ctx, sent, text):
    """Same distinction ingest/context.py draws: what MIGHT come, and what is
    already ongoing, are both not a new escalation."""
    s, sub = ctx
    sub.region = "sumy"
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "sumy"), text=text))

    assert sent == []


@pytest.mark.parametrize("kind,target_type", [
    ("summary", "ballistic"),   # retrospective tally
    ("status", "ballistic"),    # "по балістиці тихо"
    ("forecast", "shahed"),     # the oblast path is ballistic-only
])
async def test_only_a_ballistic_threat_bulletin_pushes(ctx, sent, kind, target_type):
    s, sub = ctx
    sub.region = "sumy"
    await s.commit()
    n = await _mk_notice(s, await _mk_source(s, "sumy"), kind=kind, target_type=target_type)

    await evaluate_regional_ballistic(s, n)

    assert sent == []


async def test_the_episode_pushes_once_and_a_vidbii_reopens_it(ctx, sent):
    s, sub = ctx
    sub.region = "sumy"
    await s.commit()
    src = await _mk_source(s, "sumy")

    await evaluate_regional_ballistic(s, await _mk_notice(s, src))
    await evaluate_regional_ballistic(s, await _mk_notice(s, src))
    assert len(sent) == 1, "a second bulletin in the same episode is not a new escalation"

    await evaluate_regional_ballistic(
        s, await _mk_notice(s, src, kind="clear", text="Відбій загрози балістики"))
    await evaluate_regional_ballistic(s, await _mk_notice(s, src))
    assert len(sent) == 2, "after відбій the next threat is a new episode"


async def test_danger_only_floor_opts_out_of_the_oblast_warning(ctx, sent):
    s, sub = ctx
    sub.region = "sumy"
    sub.prefs = {"min_level": "danger"}
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "sumy")))

    assert sent == []


async def test_type_filter_opts_out_of_the_oblast_warning(ctx, sent):
    s, sub = ctx
    sub.region = "sumy"
    sub.prefs = {"types": ["shahed"]}
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "sumy")))

    assert sent == []


async def test_a_homeless_subscription_gets_nothing(ctx, sent):
    """Consistent with the rest of the subsystem: only `citywide` reaches a
    device with no home zone."""
    s, sub = ctx
    sub.region = "sumy"
    sub.home_lat = None
    sub.home_lon = None
    await s.commit()

    await evaluate_regional_ballistic(s, await _mk_notice(s, await _mk_source(s, "sumy")))

    assert sent == []
