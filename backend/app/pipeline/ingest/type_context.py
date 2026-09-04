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
from ...parsing import DistrictMatcher, ParseResult, parse_message
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


def _not_about_the_sky(text: str, matcher: DistrictMatcher | None) -> bool:
    """Whether a candidate context line is consequence news rather than a report
    of what is flying — the one class that must not reach the prompt.

    Narrow on purpose, and the width was measured. The obvious version of this
    filter is "drop every line the parser suppressed", and it is wrong: the
    suppressor flags answer «should this raise a TRACK?», not «does this
    describe the current sky». Replayed over the 406 stored classifier calls,
    dropping every suppressed line removes 4.7% of the feed and takes five
    verdicts with it whose only type evidence was a `negated` or `summary` line
    — «На жаль, пуски реактивних цілей з півночі постійно тривають», «Вечірній
    звіт …: чергові запуски реактивних БПЛА» — all of which describe the sky
    perfectly well. Dropping only `aftermath` removes 0.4% of the feed and costs
    ZERO verdicts.

    The case it exists for, 2026-09-04 07:18: a Сумщина post about a strike on
    an air-defence unit near Sochi carried «зенітно-ракетний комплекс С-300 або
    С-400» — literally the prompt's own ballistic vocabulary — and was the only
    ballistic token anywhere in that night's feed. The classifier read it and
    typed a Бориспіль/Трипілля callout `ballistic` 0.75, which then became the
    Kyiv channel's context and rode two more tracks. A second instance running
    a wider channel roster, whose 25-line window pushed that post out, answered
    `jet_drone` 0.85 on the same message in the same second.

    `matcher` is the reporting channel's own, so foreign-oblast lines can lose
    the impact carve-out and read as aftermath here when they would not under
    their own matcher. Measured at 25 messages in 19 356 (0.1%), all of them
    strike reports we would rather not prompt with anyway.
    """
    if matcher is None:
        return False
    return parse_message(text or "", matcher).aftermath


async def build_type_context(
    session, when: datetime, *, exclude_raw_id: int | None, region: str | None = None,
    matcher: DistrictMatcher | None = None,
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
    # Filtered AFTER the limit, not folded into the query, so the window stays
    # the same 25+20 messages the sizing above was measured on — over-fetching
    # to refill the dropped slots would quietly widen it.
    rows = [r for r in rows if not _not_about_the_sky(r[1], matcher)]
    return "\n".join(
        f"[-{_age_minutes(when, event_time)}хв {label(row_region or HOME_REGION)}"
        f"/{name or 'канал'}] "
        + " ".join((text or "").split())[:_MAX_LINE_CHARS]
        for _id, text, event_time, name, row_region in rows
    )
