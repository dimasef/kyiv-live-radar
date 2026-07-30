"""Gamification domain rules — card deck + analysis eligibility.

Kept deliberately thin and pure (no DB, no FastAPI): the API layer
(app/api/gamification.py) owns the persistence + the first-writer-wins race,
this module only answers "is this threat analysable, and which card drops".

The card *art/metadata* lives on the frontend (frontend/src/lib/cards.ts) — the
backend only deals in `card_id` integers, so a card re-theme never needs a
backend deploy. The only contract is the count: keep CARD_COUNT in sync with
the frontend catalog length.
"""
from __future__ import annotations

import random
from datetime import timedelta

from ..models import Threat

# A target older than this (last-seen) is "stale" — no longer analysable. Keeps
# the mechanic tied to the live threat picture, not the historical archive.
STALE_AFTER = timedelta(hours=12)

# Number of distinct collectible cards. MUST match the length of the frontend
# catalog in frontend/src/lib/cards.ts.
CARD_COUNT = 22

# Relative drop weight per rarity — higher = more likely. Target type never
# biases the drop; only card rarity. Tuned so the weighted sum over the whole
# deck is exactly 1000 (9×83 + 6×34 + 3×12 + 3×4 + 1×1), making 'eternal'
# («Кінець Війни») a clean 1-in-1000 drop. MUST cover every rarity in CARD_RARITY.
RARITY_WEIGHT = {"common": 83, "rare": 34, "legendary": 12, "epic": 4, "eternal": 1}

# Each card's rarity, by id — MUST mirror the `rarity` field of the frontend
# catalog (frontend/src/lib/cards.ts). Kept here so the weighted draw needs no
# per-card table on the frontend; the frontend still owns all art/copy. A card
# id absent here falls back to 'common'.
CARD_RARITY = {
    1: "common", 2: "legendary", 3: "rare", 4: "common", 5: "rare",
    6: "common", 7: "legendary", 8: "rare", 9: "rare", 10: "rare",
    11: "epic", 12: "epic", 13: "epic", 14: "eternal", 15: "common",
    16: "common", 17: "common", 18: "legendary", 19: "rare", 20: "common",
    21: "common", 22: "common",
}

_CARD_IDS = list(range(1, CARD_COUNT + 1))
_DRAW_WEIGHTS = [RARITY_WEIGHT[CARD_RARITY.get(i, "common")] for i in _CARD_IDS]

# Target types that represent a real inbound weapon a spotter would track — the
# only ones eligible for analysis. Excludes 'unknown' (unclassified/banner rows).
ANALYSABLE_TARGET_TYPES = frozenset({"shahed", "jet_drone", "missile", "ballistic"})


def draw_card() -> int:
    """A random card id in [1, CARD_COUNT], weighted by rarity (rarer cards drop
    less often — see RARITY_WEIGHT). Duplicates are allowed: a repeat just stacks
    in the owner's collection (count += 1), there is no re-roll to guarantee a
    new card."""
    return random.choices(_CARD_IDS, weights=_DRAW_WEIGHTS, k=1)[0]


# Track lifecycle → which analysis it offers. 'track' while the target is live;
# 'remains' once it's off the board (shot down, lost contact, or already struck).
LIVE_STATUSES = frozenset({"unconfirmed", "tracking"})
REMAINS_STATUSES = frozenset({"destroyed", "lost", "impact"})


def eligible_kind_for(threat: Threat, kind: str) -> bool:
    """Whether `kind` ('track' | 'remains') may be analysed for this threat right
    now. Mirrors the frontend's button logic so a stale client can't force an
    analysis the UI wouldn't offer:

    - Only real localized targets qualify (a known weapon type, a district-scope
      track — never a city-wide banner or an unclassified row).
    - `track` requires the target to still be live (unconfirmed / tracking).
    - `remains` requires it to be off the board — destroyed, lost, or impacted
      (analyse the debris). 'dismissed' qualifies for neither.
    """
    if threat.scope != "district":
        return False
    if threat.target_type not in ANALYSABLE_TARGET_TYPES:
        return False
    if kind == "track":
        return threat.status in LIVE_STATUSES
    if kind == "remains":
        return threat.status in REMAINS_STATUSES
    return False
