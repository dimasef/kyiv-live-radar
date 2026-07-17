"""Directional threat-axis fusion (app/domain/axes.py)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.domain.axes import AxisSignal, apply_axis_signal, close_stale_axes
from app.models import ThreatAxis

BASE = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


def _sig(when, *, sector="NE", target_type="ballistic", origin_key="bryansk", src="a", raw_id=1):
    return AxisSignal(sector=sector, target_type=target_type, when=when,
                      origin_key=origin_key, source_dedup_key=src, raw_id=raw_id)


async def _count(session):
    return await session.scalar(select(func.count()).select_from(ThreatAxis))


async def test_two_sources_corroborate_into_one_axis(session):
    a = await apply_axis_signal(session, _sig(BASE, src="a", raw_id=1))
    b = await apply_axis_signal(session, _sig(BASE + timedelta(minutes=1), src="b", raw_id=2))
    assert a.id == b.id
    assert await _count(session) == 1
    assert b.status == "corroborated"
    assert b.corroboration_count == 2


async def test_repost_from_same_source_does_not_inflate(session):
    await apply_axis_signal(session, _sig(BASE, src="a", raw_id=1))
    axis = await apply_axis_signal(session, _sig(BASE + timedelta(minutes=1), src="a", raw_id=2))
    assert axis.corroboration_count == 1
    assert axis.status == "unverified"


async def test_outside_fusion_window_starts_new_axis(session):
    await apply_axis_signal(session, _sig(BASE, src="a"))
    later = BASE + timedelta(minutes=settings.axis_fusion_window_minutes + 1)
    await apply_axis_signal(session, _sig(later, src="b"))
    assert await _count(session) == 2


async def test_different_sector_starts_new_axis(session):
    await apply_axis_signal(session, _sig(BASE, sector="NE", origin_key="bryansk", src="a"))
    await apply_axis_signal(session, _sig(BASE + timedelta(minutes=1), sector="S",
                                          origin_key="crimea", src="b"))
    assert await _count(session) == 2


async def test_ballistic_and_missile_same_sector_fuse(session):
    # ballistic is a specialization of missile — same inbound threat, one wedge.
    await apply_axis_signal(session, _sig(BASE, target_type="missile", src="a"))
    axis = await apply_axis_signal(session, _sig(BASE + timedelta(minutes=1),
                                                 target_type="ballistic", src="b"))
    assert await _count(session) == 1
    assert axis.target_type == "ballistic"  # upgraded to the more specific type


async def test_ttl_expiry(session):
    await apply_axis_signal(session, _sig(BASE, src="a"))
    now = BASE + timedelta(minutes=settings.axis_ttl_minutes + 1)
    expired = await close_stale_axes(session, now)
    assert len(expired) == 1
    assert expired[0].status == "expired"
    assert expired[0].expires_at is not None
    # A fresh axis is not expired.
    await apply_axis_signal(session, _sig(now, src="b", origin_key="crimea", sector="S"))
    assert len(await close_stale_axes(session, now)) == 0


async def test_disabled_axis_layer_is_noop(session, monkeypatch):
    monkeypatch.setattr(settings, "axis_enabled", False)
    assert await apply_axis_signal(session, _sig(BASE)) is None
    assert await _count(session) == 0


def test_axis_out_carries_source_coords_for_named_origin():
    # A named origin exposes its representative centroid so the client can morph
    # the edge wedge into an on-map source marker when zoomed out.
    from app.api.serialize import axis_out

    a = ThreatAxis(id=1, sector="NE", origin_key="bryansk", target_type="ballistic",
                   status="unverified", corroboration_count=1,
                   created_at=BASE, last_seen_at=BASE)
    out = axis_out(a)
    assert out.origin_name == "Брянщина"
    assert 53 < out.origin_lat < 54 and 34 < out.origin_lon < 35


def test_axis_out_has_no_coords_for_bare_sector():
    # A bare-sector axis (a direction with no named place) stays edge-only.
    from app.api.serialize import axis_out

    a = ThreatAxis(id=2, sector="N", origin_key=None, target_type="shahed",
                   status="unverified", corroboration_count=1,
                   created_at=BASE, last_seen_at=BASE)
    out = axis_out(a)
    assert out.origin_name is None
    assert out.origin_lat is None and out.origin_lon is None
