"""LLM target-type classifier: the gate that decides a message needs one, the
cross-channel context it gets, and how a verdict is applied/stored/replayed.

The API call itself is always stubbed — what matters here is that the classifier
is the LAST tier (it can never overrule a stated type), that shadow mode really
is inert, and that a stored verdict replays for free.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.gazetteer import DISTRICTS, SOURCES
from app.models import District, RawMessage, Source, Threat, utcnow
from app.parsing import DistrictMatcher, parse_message
from app.parsing.rules import LlmUsage
from app.parsing.type_llm import TypeVerdict, normalize_type_verdict
from app.pipeline.ingest import ingest_message
from app.pipeline.ingest.type_context import build_type_context, wants_llm_type

M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(District(name_uk=d["name_uk"], name_en=d["name_en"], lat=d["lat"],
                           lon=d["lon"], aliases=d.get("aliases", [])) for d in DISTRICTS)
        s.add_all(Source(channel_key=x["channel_key"], name=x["name"],
                         trust_weight=x["trust_weight"]) for x in SOURCES)
        await s.commit()
        matcher = DistrictMatcher(list(await s.scalars(select(District))))
        yield s, matcher
    await engine.dispose()


@pytest.fixture
def stub_type(monkeypatch):
    """Canned classifier. `calls` records every (text, context) it was handed —
    a test that expects NO call asserts on it being empty."""
    calls: list[tuple[str, str]] = []
    box = {"verdict": TypeVerdict("shahed", "context", 0.9)}

    async def _fake(text, context, source_label):
        calls.append((text, context))
        return box["verdict"], LlmUsage(700, 20, 0.0008)

    monkeypatch.setattr("app.parsing.type_llm.llm_target_type", _fake)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    return calls, box


# --- the gate ---------------------------------------------------------------

def test_gate_fires_on_an_untyped_localized_sighting():
    assert wants_llm_type(parse_message("Троєщина 🔴", M))


def test_gate_never_second_guesses_a_stated_type():
    # The classifier is the FOURTH tier. Anything the rules could read out of
    # the text is authoritative — this is what makes the feature unable to
    # regress a message the parser already handles.
    assert not wants_llm_type(parse_message("Шахед на Троєщину", M))


def test_gate_skips_messages_with_nothing_to_type():
    for txt in ["Донат на дрони, картка 5375...", "Чисто, відбій"]:
        assert not wants_llm_type(parse_message(txt, M)), txt


def test_gate_skips_clear_and_destroyed():
    # Their type decides which tracks get CLOSED, so a context guess there could
    # shut down a live target rather than mislabel a marker.
    r = parse_message("Мінус ціль над Троєщиною", M)
    assert r.status in ("destroyed", "clear")
    assert not wants_llm_type(r)


# --- the context ------------------------------------------------------------

async def test_context_is_cross_channel_and_time_bounded(db):
    session, _ = db
    now = utcnow()
    session.add_all([
        RawMessage(source_id=1, message_id=1, text="Балістика з Брянщини",
                   event_time=now - timedelta(minutes=10)),
        RawMessage(source_id=2, message_id=2, text="Група 3х на Бровари",
                   event_time=now - timedelta(minutes=5)),
        RawMessage(source_id=1, message_id=3, text="давня історія",
                   event_time=now - timedelta(minutes=600)),
    ])
    await session.commit()
    ctx = await build_type_context(session, now, exclude_raw_id=None)
    lines = ctx.splitlines()
    # Both channels, oldest first, and the out-of-window message dropped: the
    # whole point is the OTHER channel's announcement 10 minutes ago.
    assert len(lines) == 2
    assert "Балістика з Брянщини" in lines[0]
    assert "Група 3х на Бровари" in lines[1]
    assert "давня історія" not in ctx


async def test_context_excludes_the_message_being_classified(db):
    session, _ = db
    now = utcnow()
    raw = RawMessage(source_id=1, message_id=9, text="Троєщина 🔴",
                     event_time=now - timedelta(seconds=1))
    session.add(raw)
    await session.commit()
    ctx = await build_type_context(session, now, exclude_raw_id=raw.id)
    assert "Троєщина" not in ctx


# --- applying the verdict ---------------------------------------------------

async def _ingest(session, matcher, text, when=None, **kw):
    return await ingest_message(session, text=text, matcher=matcher,
                                when=when or utcnow(), source_id=1, **kw)


async def test_shadow_mode_stores_the_verdict_without_applying_it(db, stub_type, monkeypatch):
    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "shadow")
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    assert len(calls) == 1
    raw = (await session.scalars(select(RawMessage))).one()
    assert (raw.llm_type, raw.llm_type_evidence) == ("shahed", "context")
    assert raw.llm_cost_usd == 0.0008 and raw.llm_input_tokens == 700
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "unknown"   # shadow: recorded, never acted on


async def test_live_mode_types_the_track(db, stub_type, monkeypatch):
    session, matcher = db
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "shahed"


async def test_a_low_confidence_verdict_leaves_the_track_untyped(db, stub_type, monkeypatch):
    session, matcher = db
    _, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("ballistic", "context", 0.4)
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "unknown"   # a grey dot beats a wrong weapon icon
    raw = (await session.scalars(select(RawMessage))).one()
    assert raw.llm_type == "ballistic"      # …but the operator can still see why


async def test_evidence_none_is_never_applied(db, stub_type, monkeypatch):
    session, matcher = db
    _, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("shahed", "none", 0.95)
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "unknown"


async def test_a_typed_message_never_reaches_the_classifier(db, stub_type, monkeypatch):
    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    await _ingest(session, matcher, "Шахед на Троєщину", message_id=1)
    assert calls == []
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "shahed"


async def test_off_mode_makes_no_call_at_all(db, stub_type, monkeypatch):
    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "off")
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    assert calls == []


async def test_a_stored_verdict_is_replayed_without_a_new_call(db, stub_type, monkeypatch):
    """What makes an admin reprocess of a whole night free — and what keeps the
    rebuilt picture identical to the live one instead of re-rolling the dice."""
    from app.pipeline.ingest import process_parsed

    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    when = utcnow()
    raw = RawMessage(source_id=1, message_id=7, text="Троєщина 🔴", event_time=when,
                     llm_type="ballistic", llm_type_confidence=0.9,
                     llm_type_evidence="context")
    session.add(raw)
    await session.commit()
    await process_parsed(session, raw=raw, text=raw.text, matcher=matcher, when=when,
                         source_id=1, message_id=7, forwarded_from_id=None,
                         reply_to_message_id=None, triage="off")
    assert calls == []
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "ballistic"


async def test_no_llm_reprocess_does_not_start_new_calls(db, stub_type, monkeypatch):
    # `--no-llm` (and the admin reprocess) flips llm_fallback_enabled off; a
    # message with no stored verdict must then stay untyped rather than turning
    # a history rebuild into thousands of live calls.
    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    monkeypatch.setattr(settings, "llm_fallback_enabled", False)
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    assert calls == []
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "unknown"


# --- verdict normalization --------------------------------------------------

def test_a_junk_verdict_normalizes_to_unusable():
    v = normalize_type_verdict({"target_type": "нло", "evidence": "vibes", "confidence": "x"})
    assert v == TypeVerdict("unknown", "none", 0.0)
    assert not v.usable


def test_usable_requires_type_evidence_and_confidence():
    assert TypeVerdict("shahed", "context", 0.9).usable
    assert not TypeVerdict("unknown", "context", 0.9).usable
    assert not TypeVerdict("shahed", "none", 0.9).usable
    assert not TypeVerdict("shahed", "context", 0.5).usable
