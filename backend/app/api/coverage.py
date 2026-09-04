"""Coverage-gap detection for the admin console.

A "gap" is a message that produced NO sighting and NO notice — neither the
rules, the LLM nor triage could pin it to a district — and which still contains
a word that looks like a place we don't have. That's almost always a missing
gazetteer entry, the primary accuracy lever (see CLAUDE.md / WORKFLOW.md).

This used to gate on `should_fallback`, i.e. on the same test that decides
whether to spend an LLM call. It was the wrong test: that gate requires a target
TYPE, and the northern spotters write bare vectors with no type word at all
(«Жукотки», «Довжик на жукля»). Measured over 2026-08-18..21, it let through
**0 of 200** unlocalized messages from the Chernihiv channel — the queue whose
whole job is finding missing gazetteer entries was structurally blind to the
channel with the biggest gap. The gates are separate now: `should_fallback`
stays narrow because a call costs money, `parsing.toponyms` is wide because a
row in an admin list costs nothing.

Wide, but not indiscriminate — a list ranked by FREQUENCY is only as good as
what it lets repeat. Three filters, added 2026-08-30 after the ranking had 3
real names in its top 40:

- a word counts only where a PLACE stands (`toponyms._place_positions`), so a
  long post no longer contributes every noun it contains;
- a line a channel appends to every post is dropped (`channel_boilerplate`) —
  «Підписатись | Відправити новину» held three of the top six rows while
  Володимирівка, eight real callouts in the same window, was nowhere on it;
- a word the operator ruled out by hand stays out (`models.ToponymDismissal`).

Kept out of routes.py so the scan logic is unit-testable on its own.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from ..feeds.common import build_region_matchers
from ..models import Notice, RawMessage, Source, ThreatEvent, ToponymDismissal
from ..parsing import DistrictMatcher, normalize, parse_message
from ..parsing.toponyms import rank_candidates, unknown_toponyms

# The message-level suppressors, in the order `api.raw_diagnosis` checks them. A
# message the parser already ruled out (donation post, casualty news, negation)
# is not a coverage gap even when it names an unknown word — surfacing those
# would bury the real ones, which is the failure mode a ranked list can't
# recover from.
_SUPPRESSORS = (
    "aftermath", "promo", "civic_notice", "eppo_marks", "ground_war",
    "personal_post", "negated", "siren_only",
    "political_quote", "reportage", "day_recap", "lost_signal", "summary",
)


# How many times a line must repeat inside the scan window to count as a
# channel's signature. Low, because a real callout does not repeat verbatim in
# five different messages — and a signature repeats in every single one.
_BOILERPLATE_MIN = 5


def channel_boilerplate(texts: list[str]) -> frozenset[str]:
    """The lines a channel appends to every post — its signature, its «Підписатись
    | Відправити новину», the alert channel's shelter advisory.

    Found rather than listed: a signature is whatever repeats verbatim across
    many messages while never being a message on its own. That second half is
    what makes the rule safe — «Лівий берег!» repeats 54 times and is a real
    callout, but it is a whole message, so it is never taken for boilerplate.
    """
    line_counts: Counter[str] = Counter()
    whole: set[str] = set()
    for text in texts:
        norm = normalize(text or "")
        lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
        if len(lines) == 1:
            whole.add(lines[0])
        for ln in lines:
            line_counts[ln] += 1
    return frozenset(
        ln for ln, n in line_counts.items() if n >= _BOILERPLATE_MIN and ln not in whole
    )


async def dismissed_words(session) -> frozenset[str]:
    """Words the operator marked «не прогалина» — see models.ToponymDismissal."""
    return frozenset(await session.scalars(select(ToponymDismissal.word)))


async def find_coverage_gaps(
    session, matcher: DistrictMatcher, *, limit: int = 50, scan: int = 800
) -> list[dict]:
    """The gap rows themselves — see `scan_coverage_gaps`, which also hands back
    the signature lines it had to detect to produce them."""
    gaps, _ = await scan_coverage_gaps(session, matcher, limit=limit, scan=scan)
    return gaps


async def scan_coverage_gaps(
    session, matcher: DistrictMatcher, *, limit: int = 50, scan: int = 800
) -> tuple[list[dict], frozenset[str]]:
    """Scan the most recent `scan` raw messages, return up to `limit` gaps
    (newest first). Bounded window keeps it cheap for the single-user MVP.

    `matcher` is the fallback for a row whose channel is unknown; every row that
    has one is matched with ITS OWN region's matcher instead. Without that, a
    region-only entry («ТЕЦ») is invisible to the home-region matcher and the
    queue keeps proposing a place we already have.
    """
    matchers = await build_region_matchers(session)
    raws = list(
        await session.scalars(select(RawMessage).order_by(RawMessage.id.desc()).limit(scan))
    )
    # Messages that already became a sighting or a notice are handled — exclude
    # them. Keyed by (source_id, message_id), the raw↔event/notice link.
    #
    # Restricted to the message ids actually in the scan window: these used to be
    # unbounded reads of the whole `threat_events` and `notices` tables, built
    # into Python sets, to filter 800 rows.
    scanned_message_ids = [r.message_id for r in raws if r.message_id is not None]
    localized: set[tuple[int | None, int | None]] = set()
    noticed: set[tuple[int | None, int | None]] = set()
    if scanned_message_ids:
        localized = {
            (r.source_id, r.source_message_id)
            for r in (
                await session.execute(
                    select(ThreatEvent.source_id, ThreatEvent.source_message_id).where(
                        ThreatEvent.source_message_id.in_(scanned_message_ids)
                    )
                )
            ).all()
        }
        noticed = {
            (r.source_id, r.source_message_id)
            for r in (
                await session.execute(
                    select(Notice.source_id, Notice.source_message_id).where(
                        Notice.source_message_id.in_(scanned_message_ids)
                    )
                )
            ).all()
        }
    sources = {s.id: s for s in await session.scalars(select(Source))}
    source_names = {sid: s.name for sid, s in sources.items()}
    source_regions = {sid: s.region for sid, s in sources.items()}
    # Both computed over the scan window, once: the signature lines to ignore
    # and the words the operator has already ruled out.
    boilerplate = channel_boilerplate([r.text for r in raws])
    dismissed = await dismissed_words(session)

    gaps: list[dict] = []
    for raw in raws:
        if (raw.source_id, raw.message_id) in localized:
            continue
        if (raw.source_id, raw.message_id) in noticed:
            continue
        row_matcher = (
            matchers.for_region(source_regions[raw.source_id])
            if raw.source_id in source_regions
            else matcher
        )
        parsed = parse_message(raw.text, row_matcher)
        if parsed.districts or any(getattr(parsed, flag) for flag in _SUPPRESSORS):
            continue
        candidates = [
            w for w in unknown_toponyms(raw.text, row_matcher, boilerplate)
            if w not in dismissed
        ]
        if not candidates:
            continue
        gaps.append(
            {
                "raw_message_id": raw.id,
                "text": raw.text,
                "event_time": raw.event_time,
                "source_name": source_names.get(raw.source_id),
                "detected_target_type": parsed.target_type,
                "detected_status": parsed.status,
                "candidates": candidates,
            }
        )
        if len(gaps) >= limit:
            break
    # The boilerplate travels with the rows: it was computed over the WHOLE scan
    # window, and the ranking below has to use that same set. Recomputing it
    # from the surviving gap rows alone would see each signature fewer times
    # than the threshold and let it back into the counts.
    return gaps, boilerplate


async def find_toponym_candidates(
    session, matcher: DistrictMatcher, *, limit: int = 60, scan: int = 2000
) -> list[dict]:
    """The same scan, aggregated into a ranked work-list of unknown place-names.

    This is the view that actually drives gazetteer work. One unlocalized
    message is an anecdote; the same unknown word in six of them over one night
    is an entry worth geocoding. Producing that ranking by hand — export the
    feed, tokenize, subtract the gazetteer, count — is a whole session's work,
    and it was the only way to see the Chernihiv gap at all.

    Scans deeper than the message list by default: a candidate's whole value is
    its frequency, and a window too short to repeat cannot show one.
    """
    gaps, boilerplate = await scan_coverage_gaps(session, matcher, limit=scan, scan=scan)
    # Boilerplate has to reach the ranking itself — it decides the COUNTS, which
    # are the whole signal — while a dismissal only hides a finished row.
    dismissed = await dismissed_words(session)
    ranked = rank_candidates(
        ((g["text"], g["raw_message_id"]) for g in gaps), matcher, boilerplate
    )
    return [r for r in ranked if r["name"] not in dismissed][:limit]
