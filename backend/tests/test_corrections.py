"""Harvesting admin actions into the parser-corrections dataset
(app/domain/corrections.py) + the corrections_eval agreement check.

Events here are linked to real RawMessage rows (via source_id +
source_message_id) so `_raw_for_event` resolves — that linkage is what makes the
correction land."""
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.security import encode_access
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import (
    District,
    ParserCorrection,
    RawMessage,
    Source,
    Threat,
    ThreatEvent,
    User,
)


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_jwt_secret", "corrections-secret")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        async def _override():
            yield s

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, s
        app.dependency_overrides.clear()
    await engine.dispose()


async def _admin_headers(session) -> dict:
    user = User(email="admin@x.com", role="admin", password_hash="x")
    session.add(user)
    await session.commit()
    return {"Authorization": f"Bearer {encode_access(user)}"}


async def _setup(session, *, target_type="shahed", text="Шахед над Троєщиною"):
    """A district, a source, a raw message, and a track whose single event is
    linked to that raw message."""
    d = District(name_uk="Троєщина", name_en="Troieshchyna", lat=50.5, lon=30.6)
    src = Source(channel_key="spotter1", name="Spotter 1")
    session.add_all([d, src])
    await session.commit()
    raw = RawMessage(source_id=src.id, message_id=1001, text=text)
    threat = Threat(target_type=target_type, status="tracking")
    session.add_all([raw, threat])
    await session.commit()
    ev = ThreatEvent(
        threat_id=threat.id, district_id=d.id, raw_text=text,
        source_id=src.id, source_message_id=1001,
    )
    session.add(ev)
    await session.commit()
    return d, raw, threat, ev


async def _corrections(session) -> list[ParserCorrection]:
    return list(await session.scalars(select(ParserCorrection).order_by(ParserCorrection.id)))


async def test_dismiss_records_false_positive(client):
    c, s = client
    headers = await _admin_headers(s)
    _, raw, threat, _ = await _setup(s)

    r = await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    assert r.status_code == 200
    rows = await _corrections(s)
    assert len(rows) == 1
    assert rows[0].kind == "false_positive"
    assert rows[0].raw_message_id == raw.id
    assert rows[0].expected == {"suppressed": True}
    assert rows[0].text == raw.text


async def test_restore_removes_false_positive(client):
    c, s = client
    headers = await _admin_headers(s)
    _, _, threat, _ = await _setup(s)

    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    await c.post(f"/admin/threats/{threat.id}/restore", headers=headers)
    assert await _corrections(s) == []


async def test_dismiss_dedupes(client):
    c, s = client
    headers = await _admin_headers(s)
    _, _, threat, _ = await _setup(s)

    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    await c.post(f"/admin/threats/{threat.id}/restore", headers=headers)
    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)
    rows = await _corrections(s)
    assert len(rows) == 1  # upsert on (raw_message_id, kind), never duplicated


async def test_retype_records_correction(client):
    c, s = client
    headers = await _admin_headers(s)
    _, raw, threat, _ = await _setup(s, target_type="shahed")

    r = await c.patch(
        f"/admin/threats/{threat.id}", json={"target_type": "ballistic"}, headers=headers
    )
    assert r.status_code == 200
    rows = await _corrections(s)
    assert len(rows) == 1
    assert rows[0].kind == "retype"
    assert rows[0].expected == {"target_type": "ballistic"}


async def test_move_event_records_relocate(client):
    c, s = client
    headers = await _admin_headers(s)
    _, _, _, ev = await _setup(s)
    d2 = District(name_uk="Позняки", name_en="Pozniaky", lat=50.4, lon=30.6)
    s.add(d2)
    await s.commit()

    r = await c.patch(f"/admin/events/{ev.id}", json={"district_id": d2.id}, headers=headers)
    assert r.status_code == 200
    rows = await _corrections(s)
    assert len(rows) == 1
    assert rows[0].kind == "relocate"
    assert rows[0].expected == {"district_id": d2.id, "district_en": "Pozniaky"}


async def test_delete_event_records_false_positive(client):
    c, s = client
    headers = await _admin_headers(s)
    _, raw, _, ev = await _setup(s)

    r = await c.delete(f"/admin/events/{ev.id}", headers=headers)
    assert r.status_code == 200
    rows = await _corrections(s)
    assert len(rows) == 1
    assert rows[0].kind == "false_positive"
    assert rows[0].raw_message_id == raw.id


async def test_admin_corrections_endpoint(client):
    c, s = client
    headers = await _admin_headers(s)
    _, raw, threat, _ = await _setup(s)
    await c.post(f"/admin/threats/{threat.id}/dismiss", headers=headers)

    r = await c.get("/admin/corrections", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["kind"] == "false_positive" and row["raw_message_id"] == raw.id for row in rows)
    assert all("resolved" in row for row in rows)


async def test_coverage_gaps(client):
    c, s = client
    headers = await _admin_headers(s)
    d = District(name_uk="Троєщина", name_en="Troieshchyna", lat=50.5, lon=30.6)
    src = Source(channel_key="s1", name="S1")
    s.add_all([d, src])
    await s.commit()
    # Threat-flavored but names a place not in the (test) gazetteer → a gap.
    gap = RawMessage(source_id=src.id, message_id=5001, text="Шахед курс на Гатне")
    # A bare toponym callout with NO target type — the northern spotters' normal
    # message shape, and what the old `should_fallback` gate rejected outright.
    bare = RawMessage(source_id=src.id, message_id=5003, text="Жукотки")
    # Junk with no target → not a gap.
    junk = RawMessage(source_id=src.id, message_id=5002, text="Дякуємо ППО за роботу!")
    s.add_all([gap, bare, junk])
    await s.commit()

    r = await c.get("/admin/coverage_gaps", headers=headers)
    assert r.status_code == 200
    rows = {g["raw_message_id"]: g for g in r.json()}
    assert gap.id in rows
    assert bare.id in rows
    assert junk.id not in rows
    # Each row names the word it was admitted for, so the operator knows what to
    # look up rather than re-reading the message.
    assert rows[bare.id]["candidates"] == ["жукотки"]

    # ...and the aggregated view ranks those words for gazetteer work.
    r = await c.get("/admin/coverage_candidates", headers=headers)
    assert r.status_code == 200
    by_name = {row["name"]: row for row in r.json()}
    assert by_name["жукотки"]["count"] == 1
    assert by_name["жукотки"]["example_raw_message_id"] == bare.id

    # The export path asks for a deeper scan + a bigger page than the UI list.
    r = await c.get("/admin/coverage_gaps?limit=500&scan=5000", headers=headers)
    assert r.status_code == 200
    assert gap.id in {g["raw_message_id"] for g in r.json()}


def test_corrections_eval_check():
    """The pure agreement check, no DB — a false positive the parser now
    suppresses agrees; a retype whose type the parser matches agrees."""
    from eval.corrections_eval import _matcher, check

    m = _matcher()

    # A junk message with no toponym → parser localizes nothing → FP is 'fixed'.
    fp = ParserCorrection(text="Дякуємо ППО за роботу!", kind="false_positive", expected={})
    agrees, _ = check(fp, m)
    assert agrees is True

    # A real shahed sighting the parser still reads as shahed → retype to shahed agrees.
    rt = ParserCorrection(
        text="Шахед над Троєщиною", kind="retype", expected={"target_type": "shahed"}
    )
    agrees, _ = check(rt, m)
    assert agrees is True


async def test_channel_signature_never_ranks_as_a_place(client):
    """A footer repeats mechanically, so on a list ranked by FREQUENCY it beats
    every real village. Live on 2026-08-30 «Підписатись | Відправити новину»
    held three of the queue's top six rows while Володимирівка — eight real
    callouts in the same window — was nowhere on it."""
    c, s = client
    headers = await _admin_headers(s)
    src = Source(channel_key="s-sig", name="Sig")
    s.add(src)
    await s.commit()
    # Six posts carrying the same signature line, and one real bare callout.
    for i in range(6):
        s.add(RawMessage(source_id=src.id, message_id=6100 + i,
                         text=f"Ціль {i} рухається\nПідписатись | Відправити новину"))
    s.add(RawMessage(source_id=src.id, message_id=6200, text="Володимирівка"))
    await s.commit()

    r = await c.get("/admin/coverage_candidates", headers=headers)
    names = [row["name"] for row in r.json()]
    assert "володимирівка" in names
    for footer_word in ("підписатись", "відправити", "новину"):
        assert footer_word not in names


async def test_a_word_only_counts_where_a_place_stands(client):
    """A long post contributes every noun it contains, which is what buried the
    ranking. The four positions in `_place_positions` are what a callout uses —
    including being the whole short message, the northern channels' own form."""
    c, s = client
    headers = await _admin_headers(s)
    src = Source(channel_key="s-pos", name="Pos")
    s.add(src)
    await s.commit()
    s.add_all([
        RawMessage(source_id=src.id, message_id=6300, text="Жукотки"),
        RawMessage(source_id=src.id, message_id=6301, text="Довжик на жукля"),
        RawMessage(source_id=src.id, message_id=6302, text="Строївка/Паперня 4"),
        # Prose: the unknown words sit nowhere a place could stand.
        RawMessage(source_id=src.id, message_id=6303, text=(
            "Хочу подякувати кожному, хто лишається з нами цієї виснажливої "
            "доби, ваша підтримка неймовірно допомагає тримати цей ресурс "
            "живим щодня попри втому")),
    ])
    await s.commit()

    r = await c.get("/admin/coverage_candidates", headers=headers)
    names = {row["name"] for row in r.json()}
    assert {"жукотки", "жукля", "строївка", "паперня"} <= names
    assert "виснажливої" not in names
    assert "неймовірно" not in names


async def test_operator_can_rule_a_candidate_out_and_put_it_back(client):
    """The queue's word lists live in code because each is a decision with a
    failure mode; this is their operator-editable half — one exact word, no
    deploy, and reversible."""
    c, s = client
    headers = await _admin_headers(s)
    src = Source(channel_key="s-dis", name="Dis")
    s.add(src)
    await s.commit()
    s.add(RawMessage(source_id=src.id, message_id=6400, text="Огірками"))
    await s.commit()

    assert "огірками" in {row["name"] for row in (
        await c.get("/admin/coverage_candidates", headers=headers)).json()}

    r = await c.post("/admin/coverage_candidates/dismiss",
                     json={"name": "Огірками"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == ["огірками"]  # normalized, and echoed back in full

    assert "огірками" not in {row["name"] for row in (
        await c.get("/admin/coverage_candidates", headers=headers)).json()}
    # ...and the message it was the only candidate of stops being a gap at all.
    assert 6400 not in {g["raw_message_id"] for g in (
        await c.get("/admin/coverage_gaps", headers=headers)).json()}

    # Dismissing twice is not an error, and the list stays one row.
    r = await c.post("/admin/coverage_candidates/dismiss",
                     json={"name": "огірками"}, headers=headers)
    assert r.json() == ["огірками"]

    r = await c.delete("/admin/coverage_candidates/dismiss/огірками", headers=headers)
    assert r.json() == []
    assert "огірками" in {row["name"] for row in (
        await c.get("/admin/coverage_candidates", headers=headers)).json()}
