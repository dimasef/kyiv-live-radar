"""Recording what a strike did to a raion — the aftermath layer's write path.

Deliberately NOT a `_dispatch` handler. It runs as a pre-step, returns nothing
and broadcasts nothing, because recording an aftermath is orthogonal to routing
the message: the layer is private (see api/public/threats.py's IMPACT_ROLES),
so it competes with no feed surface and has no reason to take precedence from
one.

That is not a stylistic choice. As a `_dispatch` branch it would have to sit
somewhere in the precedence chain, and every position costs something real:
after `summary` (step 2a-quater) it never sees the richest reports in the corpus
— «У Києві двоє людей постраждали… пожежі у Деснянському та Святошинському»
is a summary first, 2 of 20 measured — and before `summary` it would swallow
that message's feed card, which every ordinary reader can see and this layer's
readers are three accounts. As a pre-step both happen: the row is written AND
the card is published.

It also runs before the age veto (step 0), which is the other thing a branch
could not do. Aftermath arrives late BY NATURE — a «наслідки нічної атаки» post
lands the next morning — and the veto exists to stop a stale message OPENING
live state. A private record of something already over opens nothing.
"""

from __future__ import annotations

import logging

from ...domain.aftermath import read_aftermath
from ...domain.incidents import find_active_incident
from ...models import AftermathReport
from .context import IngestContext

log = logging.getLogger("aftermath")


async def record_aftermath(ctx: IngestContext) -> None:
    """Write one `AftermathReport` per raion this message named, if it should be
    recorded at all. No broadcast, no return value, no effect on routing.

    Two gates. `read_aftermath` rejects the look-alike classes (an announced
    controlled demolition, the rescue service's peacetime work) and anything it
    cannot categorise. Then the report must be connected to an attack: either
    the text says so, or the raion's region has a live incident.

    The second half of that OR is what makes the first affordable. Measured on
    the 20 real reports that name a place: the text alone drops 5 of 18 —
    «Поділ. Горять автомобілі» names no attack at all, and on its own could be
    a car fire in July — while the region's open incident recovers the four that
    arrived during that night's raid. What stays dropped is the days-later
    rescue update, which is the half a live map layer has least business
    showing.
    """
    parsed = ctx.parsed
    if not parsed.aftermath_districts:
        return
    reading = read_aftermath(parsed.raw_text)
    if reading is None:
        return

    session = ctx.session
    # One incident lookup per region, not per raion: a message naming several
    # raions of one oblast would otherwise re-run the same query for each.
    incident_open: dict[str, bool] = {}
    recorded = 0
    for hit in parsed.aftermath_districts:
        region = ctx.region_of(hit.district_id)
        if not reading.mentions_strike:
            if region not in incident_open:
                incident_open[region] = (
                    await find_active_incident(session, ctx.when, region)
                ) is not None
            if not incident_open[region]:
                continue
        session.add(AftermathReport(
            district_id=hit.district_id,
            region=region,
            reported_at=ctx.when,
            categories=reading.categories,
            text=parsed.raw_text,
            source_id=ctx.source_id,
            source_message_id=ctx.message_id,
            raw_id=ctx.raw.id,
        ))
        recorded += 1
    if recorded:
        # Committed here rather than left to a later handler: the normal fate of
        # an aftermath message is to be dropped at _dispatch step 2b, which
        # commits nothing of its own.
        await session.commit()
        log.info("aftermath recorded (raw %s, %d raion(s), %s)",
                 ctx.raw.id, recorded, "+".join(reading.categories))
