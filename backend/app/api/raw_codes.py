"""Parse T{threat_id}/M{event_id}/N{notice_id} codes — the same identifiers
shown as dev badges in the feed (see frontend ThreatLog/badges.tsx) — out of
a free-text search query, so /raw_messages can filter by them directly
instead of treating them as literal substrings (they never appear in a
message's own text)."""

from __future__ import annotations

import re

_CODE_RE = re.compile(r"\b([TMN])(\d+)\b", re.IGNORECASE)


def parse_codes(q: str) -> list[tuple[str, int]]:
    """[('T', 217), ('M', 668), ...] — empty if `q` has no recognizable code."""
    return [(kind.upper(), int(num)) for kind, num in _CODE_RE.findall(q)]
