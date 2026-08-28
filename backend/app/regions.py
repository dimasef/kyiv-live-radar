"""Every watched region, declared once.

Region metadata used to be restated in five places: the `Literal` in
`models.py`, the oblast display strings in `domain/alert_zones.py`,
`_REGION_LABEL` and the prose in `parsing/llm.py`, the stem tuples in
`domain/origins.py`, and `REGION_LABELS` on the frontend. This module is the one
declaration they all derive from.

Deliberately ORM-free and dependency-free — the same standing as
`gazetteer.py` — so `app.parsing` and `app.gazetteer` can import it without the
cycle that `parsing/toponyms.py` documents.

Code and not a DB table on purpose: `Region` has to stay a `Literal` for OpenAPI
to narrow it (and for `npm run gen:types` to emit a union), `origins.py` and
`vocab.py` compile their regexes at import time, and every region change ships
with gazetteer entries and a zone roster anyway — i.e. always a deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

# Watched regions. 'kyiv' = м. Київ + Київська обл. (everything the radar was
# built for); the rest are the early-warning approaches. A region owns its own
# track pool: corroboration, an all-clear and stale closure never reach across
# one, so a northern sighting can't join or close a Kyiv track. Only 'kyiv'
# feeds incidents, the city alert, the journal and home-danger push.
Region = Literal["kyiv", "chernihiv", "sumy", "kharkiv", "dnipro"]
REGIONS: tuple[Region, ...] = get_args(Region)
# The region the radar is actually ABOUT. It is both the default for anything
# that doesn't say (every pre-region row is Kyiv, which is what it implicitly
# was) and the gate for the Kyiv-only layers: incidents, the city alert, the
# journal/statistics and danger-near-home push.
HOME_REGION: Region = "kyiv"


@dataclass(frozen=True)
class RegionSpec:
    """Everything about one region that more than one module needs to know."""

    id: Region
    name_uk: str  # "Київщина" — the feed, the LLM prompt and the admin all show this
    name_en: str
    # Whether the parser treats this region as ours. A region is declared here
    # BEFORE it has gazetteer entries or a siren-zone roster, so that channels
    # can be tagged with it and raw messages start accumulating for the
    # gazetteer mining pass. While False it gates exactly two things — the
    # suppression split in `domain/origins.py` and the watched-region list in
    # the LLM prompt. Everything else degrades correctly on emptiness: no
    # gazetteer entry means nothing can localize into the region, no Zone row
    # means the siren provider's oblast is skipped, and an empty feed is a
    # truthful answer.
    active: bool
    # Oblast names exactly as the siren provider spells them. Kyiv carries two:
    # м. Київ is a separate first-level unit that alerts as one zone.
    oblasts: tuple[str, ...]
    # Nominatim queries for the map outline. A tuple because Kyiv oblast's
    # polygon is a donut with the city cut out — both parts are needed for a
    # click in the middle to hit something.
    outline_queries: tuple[str, ...]
    center: tuple[float, float]
    bbox: tuple[float, float, float, float]  # south, west, north, east
    # Word-start stems that name this region AS A TARGET AREA in a message.
    # Consumed only by the suppression split in `domain/origins.py`. Never a
    # gazetteer stem: the gazetteer localizes to settlements, not to oblasts.
    # The home region declares none — Kyiv is never "elsewhere", and leaving it
    # empty makes it structurally impossible for a derivation to suppress home.
    threat_stems: tuple[str, ...] = ()
    # The subset that is a CITY sharing its name with the oblast, so the
    # adjectival form means the oblast (`vocab._OBLAST_CITY_STEMS`).
    oblast_city_stems: tuple[str, ...] = ()
    # Names this region owns in OUT_OF_SCOPE_EXAMPLES below, dropped from the
    # prompt when the region goes active.
    prompt_names: tuple[str, ...] = ()


REGION_SPECS: tuple[RegionSpec, ...] = (
    RegionSpec(
        id="kyiv",
        name_uk="Київщина",
        name_en="Kyiv oblast",
        active=True,
        oblasts=("Київська область", "м. Київ"),
        outline_queries=("Київська область, Україна", "Київ, Україна"),
        center=(50.4501, 30.5234),
        bbox=(49.17, 29.27, 51.55, 32.16),
    ),
    RegionSpec(
        id="chernihiv",
        name_uk="Чернігівщина",
        name_en="Chernihiv oblast",
        active=True,
        oblasts=("Чернігівська область",),
        outline_queries=("Чернігівська область, Україна",),
        center=(51.49, 31.29),
        bbox=(50.35, 30.30, 52.38, 33.53),
        # Ніжин and Прилуки are here rather than in origins' other-oblast list
        # for the same reason Бахмач is in neither: they are watched towns, so a
        # target over one is ours to track but still not a Kyiv target.
        threat_stems=("чернігівщин", "чернігів", "ніжин", "прилук"),
        oblast_city_stems=("черніг",),
    ),
    # Активована 2026-08-28: 137 gazetteer entries mined from 3760 messages of
    # its two spotter channels (0% -> 64% rule coverage) plus the five-raion
    # roster in `domain/alert_zones.py`.
    RegionSpec(
        id="sumy",
        name_uk="Сумщина",
        name_en="Sumy oblast",
        active=True,
        oblasts=("Сумська область",),
        outline_queries=("Сумська область, Україна",),
        center=(50.91, 34.80),
        bbox=(50.13, 33.08, 52.36, 35.68),
        # "сум" is deliberately not here: it eats "сумно"/"сумнів" (the note in
        # origins.py records the sweep). The explicit "суми"/"сумах" forms carry it.
        threat_stems=("сумщин", "суми", "сумах", "конотоп", "ромн"),
        prompt_names=("Суми",),
    ),
    # Declared, not yet covered. Each still needs gazetteer entries and a raion
    # roster in `domain/alert_zones.py` before `active` can go True — see the
    # activation checklist in `.claude/plans/region-expansion.md`.
    RegionSpec(
        id="kharkiv",
        name_uk="Харківщина",
        name_en="Kharkiv oblast",
        active=False,
        oblasts=("Харківська область",),
        outline_queries=("Харківська область, Україна",),
        center=(49.99, 36.23),
        bbox=(48.53, 34.79, 50.45, 38.10),
        # Note what is NOT here: the Ukrainian "харків". It is absent from the
        # curated list too, so «Ціль на Харків» is not suppressed today — a
        # live gap to close when this region is worked on, not by adding the
        # stem here (that would suppress it for one deploy and then unsuppress
        # it again on activation).
        threat_stems=("харківщин", "харков"),
        prompt_names=("Харків",),
    ),
    RegionSpec(
        id="dnipro",
        name_uk="Дніпропетровщина",
        name_en="Dnipropetrovsk oblast",
        active=False,
        oblasts=("Дніпропетровська область",),
        outline_queries=("Дніпропетровська область, Україна",),
        center=(48.46, 35.05),
        bbox=(47.45, 33.28, 49.19, 37.12),
        # NOT "дніпро", even though the curated list carries it: the stems here
        # are word-START anchored with no tail constraint, so a bare "дніпро"
        # also fires inside Kyiv's own «Дніпровський» raion. Activating this
        # region must first split that entry into a whole-word form.
        threat_stems=("дніпропетровщин", "дніпропетровськ"),
    ),
)

SPEC_BY_ID: dict[str, RegionSpec] = {s.id: s for s in REGION_SPECS}
HOME_SPEC: RegionSpec = SPEC_BY_ID[HOME_REGION]

# Places named to the model as explicitly out of scope. A curated list of the
# confusable ones the prompt actually had to correct, in the order it names
# them — not an inventory of every oblast. An entry leaves the prompt when the
# region that owns it (`RegionSpec.prompt_names`) goes active.
OUT_OF_SCOPE_EXAMPLES: tuple[str, ...] = (
    "Харків", "Запоріжжя", "Миколаїв", "Суми", "Полтава",
)

# How many watched regions the prompt claims there are, spelled out because the
# sentence reads "other than the two watched ones".
_COUNT_WORDS = ("zero", "one", "two", "three", "four", "five")


def active_regions() -> tuple[RegionSpec, ...]:
    return tuple(s for s in REGION_SPECS if s.active)


def watched_regions() -> tuple[RegionSpec, ...]:
    """Active regions other than home — the approach corridors."""
    return tuple(s for s in active_regions() if s.id != HOME_REGION)


def label(region: str) -> str:
    """Ukrainian name of a region, falling back to the raw id for a value that
    predates the registry (a stored row, a hand-made query)."""
    spec = SPEC_BY_ID.get(region)
    return spec.name_uk if spec else region


def out_of_scope_examples() -> tuple[str, ...]:
    owned = {n for s in active_regions() for n in s.prompt_names}
    return tuple(n for n in OUT_OF_SCOPE_EXAMPLES if n not in owned)


def active_count_word() -> str:
    n = len(active_regions())
    return _COUNT_WORDS[n] if n < len(_COUNT_WORDS) else str(n)
