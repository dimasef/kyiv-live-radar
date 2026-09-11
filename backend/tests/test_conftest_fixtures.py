"""Invariants the shared fixtures in `conftest.py` rely on.

`standard_matcher`/`standard_district_ids` are built ONCE (session-scoped) from
their own throwaway DB and reused across the whole run — a real per-test cost
cut, but only sound if every fresh seed of the standard gazetteer produces the
identical id sequence. This pins that assumption so a change to
`district_rows()`/seeding order fails here loudly instead of leaking a stale
id into a test that queries `District` itself.
"""

from sqlalchemy import select

from app.config import settings
from app.models import District


async def test_standard_matcher_ids_match_a_fresh_seed(seeded_session, standard_district_ids):
    fresh_ids = tuple(
        d.id for d in await seeded_session.scalars(select(District).order_by(District.id))
    )
    assert fresh_ids == standard_district_ids


def test_the_suite_cannot_reach_the_anthropic_api():
    """Load-bearing invariant, not a smoke test: every LLM consumer gates on
    `settings.anthropic_api_key` being non-empty, so this blank is what stands
    between the suite and the maintainer's billing. The env stub that sets it
    lives at the top of `conftest.py`; pytest never collects tests from there,
    so the check has to live in a file it does collect."""
    assert not settings.anthropic_api_key
