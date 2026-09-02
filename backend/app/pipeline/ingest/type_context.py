"""The "what is in the sky right now" feed handed to the LLM target-type
classifier, plus the gate that decides a message needs it.

Deliberately CROSS-CHANNEL and wide (see parsing/type_llm.py for the measurement
that forced it): the per-channel `_note_and_inherit_type` window already covers
the case where the same spotter typed the wave a minute ago. What it cannot
cover — and what this is for — is the wave being announced once, in the other
channel, forty minutes before the toponym callouts start.

Built from stored `raw_messages` by `event_time`, so a reprocess assembles the
same feed for the same message and replays deterministically.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from ...config import settings
from ...models import RawMessage, Source
from ...parsing import ParseResult
from ...regions import HOME_REGION, label
from ...timeutil import naive

# One line per message: enough text to carry the type word and the direction,
# not enough for a long donation post to eat the window.
_MAX_LINE_CHARS = 170


def wants_llm_type(parsed: ParseResult) -> bool:
    """Whether this message is worth a type call — the FOURTH tier, reached only
    after the text, the channel context and the incident prior all failed.

    Narrow on purpose, because each condition is a way to be wrong rather than
    merely unhelpful:
      * `matched` + a place — anything else produces no track to type;
      * clear/destroyed are excluded: their type selects which tracks get
        CLOSED (handlers.close_all_active), so a context guess there could shut
        down a live target instead of mislabelling a marker;
      * `anticipated`/`summary` speak about a wave that is not in the sky, which
        is the exact confusion the classifier is told to avoid — no reason to
        pay for it and then hope.
    """
    if parsed.target_type != "unknown":
        return False
    if not parsed.matched:
        return False
    if not (parsed.districts or parsed.citywide):
        return False
    if parsed.status in ("clear", "destroyed"):
        return False
    return not (parsed.anticipated or parsed.summary)


def _age_minutes(when: datetime, then: datetime) -> int:
    return max(0, int((naive(when) - naive(then)).total_seconds() // 60))


async def build_type_context(
    session, when: datetime, *, exclude_raw_id: int | None, region: str | None = None
) -> str:
    """The recent feed, as the classifier sees it: the last
    `llm_type_context_messages` messages from every channel within
    `llm_type_context_minutes` before `when`, plus up to
    `llm_type_context_own_messages` more from `region` alone — oldest first,
    one line each, deduped.

    Each line is labelled with its channel's REGION as well as its name. The
    national window is deliberately still national — a cruise or ballistic wave
    crosses three oblasts inside one of these windows, and reading the
    neighbouring feed is what makes the tier work at all (measured:
    cross-channel context types 22 of 25 cases, own-channel 3; and 34% of the
    typings it gets right had the type word ONLY in a neighbouring oblast). But
    it stopped being safe to leave the region implicit once Сумщина went live:
    that feed posts ~188 messages a day, most of them about FPV quadcopters
    with a 20 km reach, which say nothing whatsoever about a target over Kyiv.
    Naming the region lets the model discount them.

    The own-region top-up fixes the other half of the same problem, which
    labelling cannot: a busy raid elsewhere does not just add noise, it takes
    the SLOTS. On 2026-09-02 a Kyiv sighting got 13 Харківщина lines out of 25
    and five Kyiv ones that named no type, while the Kyiv feed had said
    «Реактивний …» three times in the preceding half hour. Additive, so the
    corridor above is untouched — see settings.llm_type_context_own_messages
    for the measurement behind the size.

    `exclude_raw_id` drops the message being classified: on the live path it is
    already stored by the time this runs, and seeing itself in its own context
    invites the model to treat a bare toponym as its own evidence.
    """
    window_start = naive(when) - timedelta(minutes=settings.llm_type_context_minutes)

    def _recent(limit: int, only_region: str | None):
        stmt = (
            select(RawMessage.id, RawMessage.text, RawMessage.event_time,
                   Source.name, Source.region)
            .outerjoin(Source, RawMessage.source_id == Source.id)
            .where(RawMessage.event_time < when, RawMessage.event_time >= window_start)
            .order_by(RawMessage.event_time.desc(), RawMessage.id.desc())
            .limit(limit)
        )
        if only_region is not None:
            stmt = stmt.where(Source.region == only_region)
        if exclude_raw_id is not None:
            stmt = stmt.where(RawMessage.id != exclude_raw_id)
        return stmt

    rows = list(await session.execute(_recent(settings.llm_type_context_messages, None)))
    if region is not None and settings.llm_type_context_own_messages > 0:
        seen = {r[0] for r in rows}
        own = await session.execute(
            _recent(settings.llm_type_context_own_messages, region)
        )
        rows.extend(r for r in own if r[0] not in seen)
    # One chronological transcript, however the two queries interleaved.
    rows.sort(key=lambda r: (r[2], r[0]))
    return "\n".join(
        f"[-{_age_minutes(when, event_time)}хв {label(row_region or HOME_REGION)}"
        f"/{name or 'канал'}] "
        + " ".join((text or "").split())[:_MAX_LINE_CHARS]
        for _id, text, event_time, name, row_region in rows
    )
