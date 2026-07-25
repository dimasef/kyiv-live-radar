"""Harvest admin console actions into a labeled parser-correction dataset.

Every manual override in /admin is free ground truth: a dismiss says "this
message should not have localized", a retype says "the target type was wrong", a
district move says "the district was wrong". We persist these as
`ParserCorrection` rows so `eval/corrections_eval.py` can later check the CURRENT
parser no longer reproduces the mistake — turning one-off operator effort into a
permanent regression signal.

Linking: a `ThreatEvent` records `source_id` + `source_message_id`, which
uniquely identify the originating `RawMessage`; we resolve that to snapshot the
text and anchor the correction. Events with no source message (e.g. simulator
feed) are skipped — there's nothing to re-parse.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..models import District, ParserCorrection, RawMessage, Threat, ThreatEvent
from ..parsing import DistrictMatcher, parse_message

log = logging.getLogger("corrections")


def parser_agrees(
    correction: ParserCorrection, matcher: DistrictMatcher, id_to_en: dict[int, str]
) -> tuple[bool, str]:
    """Does the CURRENT rule parser now produce what this correction says it
    should? The single agreement rule shared by eval/corrections_eval.py and the
    /admin/corrections endpoint. `id_to_en` maps a district id (DB ids in the
    app, gazetteer-index ids in the offline eval) to its English name.

    Returns (agrees, human-readable actual-vs-expected).
    """
    res = parse_message(correction.text, matcher)
    got = {id_to_en.get(h.district_id) for h in res.districts}
    exp = correction.expected or {}
    if correction.kind == "false_positive":
        return (not got, f"got districts {sorted(filter(None, got))}")
    if correction.kind == "retype":
        want = exp.get("target_type")
        return (res.target_type == want, f"got type {res.target_type!r} exp {want!r}")
    if correction.kind == "relocate":
        want = exp.get("district_en")
        return (want in got, f"got {sorted(filter(None, got))} exp {want!r}")
    return (False, f"unknown kind {correction.kind!r}")


async def _raw_for_event(session, event: ThreatEvent) -> RawMessage | None:
    if event.source_message_id is None:
        return None
    return await session.scalar(
        select(RawMessage).where(
            RawMessage.source_id == event.source_id,
            RawMessage.message_id == event.source_message_id,
        )
    )


async def _record(
    session, *, raw: RawMessage, kind: str, expected: dict, origin: str, user_id: int | None
) -> None:
    """Upsert by (raw_message_id, kind) so re-doing the same action on the same
    message refreshes rather than duplicates."""
    existing = await session.scalar(
        select(ParserCorrection).where(
            ParserCorrection.raw_message_id == raw.id, ParserCorrection.kind == kind
        )
    )
    if existing is not None:
        existing.expected = expected
        existing.origin = origin
        existing.created_by_user_id = user_id
        return
    session.add(
        ParserCorrection(
            raw_message_id=raw.id,
            text=raw.text,
            kind=kind,
            expected=expected,
            origin=origin,
            created_by_user_id=user_id,
        )
    )


async def _distinct_raws(session, threat: Threat):
    """The distinct raw messages that produced a localized event on this track
    (requires threat.events loaded). Yields (raw) once per message."""
    seen: set[int] = set()
    for ev in threat.events:
        raw = await _raw_for_event(session, ev)
        if raw is None or raw.id in seen:
            continue
        seen.add(raw.id)
        yield raw


async def record_false_positive_for_track(session, threat: Threat, user_id: int | None) -> None:
    """A dismissed track — every message that localized it was a false positive."""
    async for raw in _distinct_raws(session, threat):
        await _record(
            session, raw=raw, kind="false_positive",
            expected={"suppressed": True}, origin="dismiss", user_id=user_id,
        )


async def record_retype_for_track(
    session, threat: Threat, target_type: str, user_id: int | None
) -> None:
    """A retyped track — its messages should parse to `target_type`."""
    async for raw in _distinct_raws(session, threat):
        await _record(
            session, raw=raw, kind="retype",
            expected={"target_type": target_type}, origin="retype_threat", user_id=user_id,
        )


async def record_relocate_for_event(
    session, event: ThreatEvent, district: District, user_id: int | None
) -> None:
    """A moved sighting — its message should localize to `district`."""
    raw = await _raw_for_event(session, event)
    if raw is None:
        return
    await _record(
        session, raw=raw, kind="relocate",
        expected={"district_id": district.id, "district_en": district.name_en},
        origin="move_event", user_id=user_id,
    )


async def record_false_positive_for_event(
    session, event: ThreatEvent, user_id: int | None
) -> None:
    """A deleted sighting — its message should not have localized here."""
    raw = await _raw_for_event(session, event)
    if raw is None:
        return
    await _record(
        session, raw=raw, kind="false_positive",
        expected={"suppressed": True}, origin="move_event", user_id=user_id,
    )


async def remove_false_positives_for_track(session, threat: Threat) -> None:
    """Undo on restore — a track brought back was NOT a false positive, so drop
    the labels its dismiss created (requires threat.events loaded)."""
    async for raw in _distinct_raws(session, threat):
        c = await session.scalar(
            select(ParserCorrection).where(
                ParserCorrection.raw_message_id == raw.id,
                ParserCorrection.kind == "false_positive",
            )
        )
        if c is not None:
            await session.delete(c)
