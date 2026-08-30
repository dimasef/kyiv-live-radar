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
from app.models import District, RawMessage, Source, Threat, ThreatEvent, utcnow
from app.parsing import DistrictMatcher, parse_message
from app.parsing.rules import LlmUsage
from app.parsing.type_llm import TypeVerdict, normalize_type_verdict
from app.pipeline.ingest import ingest_message
from app.pipeline.ingest.type_context import build_type_context, wants_llm_type
from tests.conftest import district_rows

M = DistrictMatcher([{"id": i + 1, **d} for i, d in enumerate(DISTRICTS)])


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(district_rows())
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

    async def _fake(text, context, source_label, region=None):
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
    # Every line names its channel's REGION. A national window is the point of
    # this tier, but a Сумщина FPV callout must be discountable by a model
    # classifying a Kyiv target — see build_type_context's docstring.
    assert all(line.startswith("[-") and "Київщина/" in line for line in lines)


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


# --- the per-source switch (Source.llm_enabled) ------------------------------


async def test_a_channel_with_the_llm_switch_off_is_never_classified(db, stub_type, monkeypatch):
    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    src = await session.get(Source, 1)
    src.llm_enabled = False
    await session.commit()
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    assert calls == []
    track = (await session.scalars(select(Threat))).one()
    # The sighting still becomes a track — the switch removes the LLM tier, not
    # the channel.
    assert track.target_type == "unknown"


async def test_the_switch_is_per_channel_and_not_global(db, stub_type, monkeypatch):
    """The whole point of the column: silencing one channel used to mean
    switching the classifier off for everyone (`llm_type_mode`)."""
    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    off = await session.get(Source, 1)
    off.llm_enabled = False
    await session.commit()
    await ingest_message(session, text="Троєщина 🔴", matcher=matcher, when=utcnow(),
                         source_id=2, message_id=1)
    assert len(calls) == 1
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "shahed"


async def test_the_switch_also_blocks_replay_of_a_stored_verdict(db, stub_type, monkeypatch):
    """Deliberately NOT the reprocess-is-deterministic rule
    (test_a_stored_verdict_is_replayed_without_a_new_call): a channel the
    operator took off the LLM must not have last week's verdicts re-applied to
    it by the next rebuild — that would make the switch un-actionable on the
    history it was flipped because of."""
    from app.pipeline.ingest import process_parsed

    session, matcher = db
    calls, _ = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    src = await session.get(Source, 1)
    src.llm_enabled = False
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
    assert track.target_type == "unknown"
    # The stored verdict is untouched: turning the switch back on restores it.
    assert raw.llm_type == "ballistic"


# --- the verdict feeds back into the channel context -------------------------
#
# Before it did, the fourth tier was per-MESSAGE: 2026-08-23, one loitering jet
# drone over Новгород-Сіверський bought three identical verdicts in twelve
# minutes (16:35, 16:40, 16:47 — all jet_drone/0.85/context) because the answer
# never reached `_recent_type`. Replayed over five days of stored messages,
# feeding it back cuts calls 845 -> 435 and raises typed coverage 81% -> 90%.
#
# These use the NORTHERN channel's real messages on purpose. Incidents are
# Kyiv-only, so a Kyiv scenario would have the incident prior (tier 2) typing
# the follow-ups anyway — the test would pass with the feature reverted.

async def test_a_verdict_types_the_next_bare_toponym_without_a_second_call(
    db, stub_type, monkeypatch
):
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("jet_drone", "context", 0.85)
    t0 = utcnow()
    await _ingest(session, matcher, "Рогівка зайшов", when=t0, message_id=1)
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️",
                  when=t0 + timedelta(minutes=3), message_id=2)
    assert len(calls) == 1
    assert {t.target_type for t in await session.scalars(select(Threat))} == {"jet_drone"}


async def test_carrying_a_type_forward_keeps_it_alive(db, stub_type, monkeypatch):
    """A callout is evidence the wave is still running, so inheriting restarts
    the window. Before that, the window measured silence since somebody last
    happened to NAME the weapon — and on 2026-08-30 it lapsed 3 seconds before
    the next callout, bought a second answer on an unchanged feed, and got a
    different one."""
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    monkeypatch.setattr(settings, "type_inherit_window_minutes", 5)
    box["verdict"] = TypeVerdict("jet_drone", "context", 0.85)
    t0 = utcnow()
    await _ingest(session, matcher, "Рогівка зайшов", when=t0, message_id=1)
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️",
                  when=t0 + timedelta(minutes=3), message_id=2)
    await _ingest(session, matcher, "Ще є Новгород",
                  when=t0 + timedelta(minutes=7), message_id=3)
    # One call, not two: the middle message pushed the window forward.
    assert len(calls) == 1
    for track in await session.scalars(select(Threat)):
        assert track.target_type == "jet_drone"


async def test_one_answer_cannot_ride_past_the_total_age_cap(db, stub_type, monkeypatch):
    """The refresh above is bounded by TOTAL age, which is why the old design
    refused to refresh at all: uncapped, one guess owns the channel for as long
    as it keeps talking."""
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    monkeypatch.setattr(settings, "type_inherit_window_minutes", 5)
    monkeypatch.setattr(settings, "type_inherit_max_age_minutes", 6)
    box["verdict"] = TypeVerdict("jet_drone", "context", 0.85)
    t0 = utcnow()
    await _ingest(session, matcher, "Рогівка зайшов", when=t0, message_id=1)
    for i, minutes in enumerate((3, 6, 9, 12), start=2):
        await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️",
                      when=t0 + timedelta(minutes=minutes), message_id=i)
    # t0+6 is the last refresh the cap allows, so the window then runs out from
    # a frozen mark and t0+12 buys a fresh answer. The tail is therefore bounded
    # at cap + one window, never at "as long as the channel keeps talking".
    assert len(calls) == 2


async def test_a_stated_type_still_overrules_an_inferred_one(db, stub_type, monkeypatch):
    session, matcher = db
    _, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("jet_drone", "context", 0.85)
    t0 = utcnow()
    await _ingest(session, matcher, "Рогівка зайшов", when=t0, message_id=1)
    await _ingest(session, matcher, "Балістика на Рогівку",
                  when=t0 + timedelta(minutes=1), message_id=2)
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️",
                  when=t0 + timedelta(minutes=2), message_id=3)
    newest = (await session.scalars(select(Threat).order_by(Threat.id.desc()))).first()
    assert newest.target_type == "ballistic"


async def test_an_unusable_verdict_is_not_remembered(db, stub_type, monkeypatch):
    """Only what we were willing to put on the map is worth caching — a verdict
    below llm_type_min_confidence must not silently type later messages that the
    classifier itself never got to see."""
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("jet_drone", "context", 0.4)
    t0 = utcnow()
    await _ingest(session, matcher, "Рогівка зайшов", when=t0, message_id=1)
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️",
                  when=t0 + timedelta(minutes=1), message_id=2)
    assert len(calls) == 2
    assert {t.target_type for t in await session.scalars(select(Threat))} == {"unknown"}


async def test_shadow_mode_does_not_leak_its_verdict_into_the_context(
    db, stub_type, monkeypatch
):
    """Shadow mode's whole point is being inert. Caching a type it was not
    allowed to apply would have let it steer the map through the back door."""
    session, matcher = db
    monkeypatch.setattr(settings, "llm_type_mode", "shadow")
    t0 = utcnow()
    await _ingest(session, matcher, "Рогівка зайшов", when=t0, message_id=1)
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️",
                  when=t0 + timedelta(minutes=1), message_id=2)
    assert {t.target_type for t in await session.scalars(select(Threat))} == {"unknown"}


async def test_an_inherited_guess_never_splits_a_ballistic_enumeration(
    db, stub_type, monkeypatch
):
    """The reason TypeContext carries `inferred`. «Холми Рогівка» is split into
    two simultaneous targets only when the wave is KNOWN to be ballistic; on a
    guess it stays one meandering track (handlers._handle_sighting)."""
    session, matcher = db
    _, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("ballistic", "context", 0.9)
    t0 = utcnow()
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️", when=t0, message_id=1)
    await _ingest(session, matcher, "Холми Рогівка",
                  when=t0 + timedelta(minutes=1), message_id=2)
    tracks = list(await session.scalars(select(Threat)))
    assert len(tracks) == 2          # the Новгород track + ONE for the pair
    events = list(await session.scalars(
        select(ThreatEvent).where(ThreatEvent.threat_id == tracks[-1].id)))
    assert len(events) == 2


# --- a decline is an answer too --------------------------------------------

async def test_a_decline_is_not_re_asked_while_the_feed_says_the_same_thing(
    db, stub_type, monkeypatch
):
    """2026-08-23 18:40-18:41: three bare toponyms from one channel bought three
    identical `unknown`/`none` verdicts in fifty seconds ($0.0058). The
    classifier had already read that feed and said it could not tell; nothing
    stated a type in between, so it was being asked the same question."""
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("unknown", "none", 0.3)
    t0 = utcnow()
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️", when=t0, message_id=1)
    await _ingest(session, matcher, "Рогівка зайшов",
                  when=t0 + timedelta(seconds=20), message_id=2)
    await _ingest(session, matcher, "На холми лізе",
                  when=t0 + timedelta(seconds=50), message_id=3)
    assert len(calls) == 1


async def test_a_stated_type_anywhere_makes_a_decline_worth_re_asking(
    db, stub_type, monkeypatch
):
    """The invalidator, and what makes a 30-minute decline window safe: the one
    thing that changes the classifier's answer is a wave being ANNOUNCED, and an
    announcement is a stated type. It counts from any channel — the context it
    reads is cross-channel by design."""
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("unknown", "none", 0.3)
    t0 = utcnow()
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️", when=t0, message_id=1)
    await ingest_message(session, text="Балістика!", matcher=matcher,
                         when=t0 + timedelta(seconds=20), source_id=2, message_id=2)
    await _ingest(session, matcher, "Рогівка зайшов",
                  when=t0 + timedelta(seconds=40), message_id=3)
    assert len(calls) == 2


async def test_a_weak_answer_is_not_a_decline(db, stub_type, monkeypatch):
    """Live counter-example from the same night: «Новгород з півночі» scored
    shahed 0.65 at 18:49:31 — below the apply threshold — and the next call 37
    seconds later scored 0.75 and WAS applied. Backing off on a weak answer
    would have thrown that away."""
    session, matcher = db
    calls, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("shahed", "context", 0.65)
    t0 = utcnow()
    await _ingest(session, matcher, "Новгород ⚠️⚠️⚠️", when=t0, message_id=1)
    await _ingest(session, matcher, "Рогівка зайшов",
                  when=t0 + timedelta(seconds=37), message_id=2)
    assert len(calls) == 2


async def test_an_operator_retype_types_the_next_callout_for_free(db, monkeypatch):
    """End of the same chain: with the correction in the channel context, the
    next bare toponym inherits it and never reaches the classifier at all."""
    from app.pipeline.ingest import note_operator_type

    session, matcher = db
    calls: list = []

    async def _fake(text, context, source_label):
        calls.append(text)
        return TypeVerdict("shahed", "context", 0.9), LlmUsage(700, 20, 0.0008)

    monkeypatch.setattr("app.parsing.type_llm.llm_target_type", _fake)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    t0 = utcnow()
    note_operator_type({1}, "jet_drone", t0)
    await _ingest(session, matcher, "Рогівка зайшов", when=t0 + timedelta(minutes=1),
                  message_id=1)
    assert calls == []
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "jet_drone"   # the operator's, not the stub's shahed


async def test_a_call_that_never_completes_is_still_recorded_as_attempted(db, monkeypatch):
    """A timeout used to leave no trace whatsoever — llm_attempted=0, no verdict,
    no cost — so /raw showed it as "no call was made" and an analysis of the
    2026-08-23 feed went looking for a config difference that did not exist."""
    async def _timeout(text, context, source_label, region=None):
        return None, None

    monkeypatch.setattr("app.parsing.type_llm.llm_target_type", _timeout)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    session, matcher = db
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    raw = (await session.scalars(select(RawMessage))).one()
    assert raw.llm_attempted is True
    assert raw.llm_cost_usd is None and raw.llm_type is None
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


# --- the region gate on inferred types (domain.target_types) -----------------


def test_reach_limited_types_are_gated_by_region():
    from app.domain.target_types import type_plausible_in

    # Measured, not assumed: kab/fpv are 28%/9% of Сумщина's stated types and
    # 15%/5.5% of Харківщина's, against 0 of 195 in Чернігівщина and 0 of 1814
    # in Київщина (the one Kyiv "kab" is a fundraising post about Запоріжжя).
    assert type_plausible_in("kab", "sumy")
    assert type_plausible_in("fpv", "kharkiv")
    assert not type_plausible_in("kab", "kyiv")
    assert not type_plausible_in("kab", "chernihiv")
    assert not type_plausible_in("fpv", "chernihiv")
    # Everything else travels; and an unresolved region never costs a type.
    assert type_plausible_in("shahed", "chernihiv")
    assert type_plausible_in("ballistic", "kyiv")
    assert type_plausible_in("kab", None)


async def test_a_kab_verdict_is_refused_over_the_northern_regions(db, stub_type, monkeypatch):
    """The 2026-08-30 06:54 failure: the classifier read Сумщина/Харківщина КАБ
    traffic out of its cross-channel context and typed a drone over Ріпки with
    it, which then rode the channel's inheritance chain into nine tracks."""
    session, matcher = db
    _, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("kab", "context", 0.95)
    src = await session.get(Source, 1)
    src.region = "chernihiv"
    await session.commit()
    await _ingest(session, matcher, "Троєщина 🔴", message_id=1)
    track = (await session.scalars(select(Threat))).one()
    assert track.target_type == "unknown"
    # Still recorded, so the operator can see what was refused and why.
    raw = (await session.scalars(select(RawMessage))).one()
    assert raw.llm_type == "kab"


async def test_the_same_verdict_stands_where_the_weapon_reaches(db, stub_type, monkeypatch):
    session, matcher = db
    _, box = stub_type
    monkeypatch.setattr(settings, "llm_type_mode", "live")
    box["verdict"] = TypeVerdict("kab", "context", 0.95)
    src = await session.get(Source, 1)
    src.region = "sumy"
    await session.commit()
    # A Сумщина toponym, so the message's own region — the one the gate reads,
    # exactly like the track pool it will join — is sumy.
    await _ingest(session, matcher, "Ромни 🔴", message_id=1)
    track = (await session.scalars(select(Threat))).one()
    assert track.region == "sumy"
    assert track.target_type == "kab"


def test_the_enum_rail_drops_the_word_entirely():
    """Belt and braces: the model is never even offered a type it could not be
    right about, so the check on the answer only has to catch a REPLAYED
    verdict stored before the rail existed."""
    from app.parsing.type_llm import _schema

    north = _schema(("shahed", "jet_drone", "missile", "ballistic", "unknown"))
    assert "kab" not in north["properties"]["target_type"]["enum"]
    assert "fpv" not in north["properties"]["target_type"]["enum"]


def test_a_stored_out_of_region_verdict_does_not_come_back_on_replay():
    from app.parsing.type_llm import normalize_type_verdict

    allowed = ("shahed", "jet_drone", "missile", "ballistic", "unknown")
    verdict = normalize_type_verdict(
        {"target_type": "kab", "evidence": "context", "confidence": 0.9}, allowed
    )
    assert verdict.target_type == "unknown"
