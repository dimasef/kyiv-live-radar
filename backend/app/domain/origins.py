"""Curated launch/approach origins for the directional threat-axis layer.

An origin is NOT a Kyiv gazetteer point — it's a far-away launch zone or
approach corridor ("з Брянщини", "з боку Чорного моря") that a directional
callout names. The map renders these as a screen-edge wedge pointing along the
origin's compass bearing, never as a district pin (see WORKFLOW.md "threat
context layer": source toponyms are deliberately outside the Kyiv gazetteer).

This is the origin analogue of the district gazetteer: a small curated table,
grown reactively from real feed callouts. The set seeds from
`ingest._OTHER_OBLAST`, but keeps ONLY genuine attack origins — target-location
oblasts (Дніпро/Харків/Одеса/…) are someone else's threat, never an axis toward
Kyiv. `origin_place` in the LLM triage schema is an enum of these keys (+ 'none')
so the model can name an origin but never invent one, exactly as `district_ids`
is enum-railed. Bearing/sector geometry lives here, in code — never asked of the
model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Compass sector -> representative bearing (deg, 0=N, 90=E), the wedge direction
# the frontend draws when only a sector is known (no specific origin toponym).
SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SECTOR_BEARING = {"N": 0, "NE": 45, "E": 90, "SE": 135,
                  "S": 180, "SW": 225, "W": 270, "NW": 315}


@dataclass(frozen=True)
class Origin:
    key: str          # stable id, used in the LLM enum + stored on ThreatAxis
    name_uk: str      # display label ("Брянщина")
    sector: str       # one of SECTORS — the compass octant toward Kyiv
    bearing_deg: int  # finer bearing from Kyiv (0=N, 90=E), for the edge wedge
    stems: tuple[str, ...]  # normalized word-start stems that name this origin
    # Representative centroid (lat, lon) of the origin region/place. COARSE on
    # purpose — most origins are whole oblasts/seas, not points; the frontend
    # draws a soft zone here (not a precise pin) only when the operator zooms out
    # far enough that this location enters the viewport, morphing the edge wedge
    # into an on-map source marker. Never used for bearing/trajectory math.
    lat: float
    lon: float


# Bearings are from Kyiv (~50.45N, 30.52E) toward each origin, rounded — coarse
# on purpose (an edge wedge, not a firing solution). Grow this table the same way
# the gazetteer grows: when a real callout names an origin we don't cover.
ORIGINS: tuple[Origin, ...] = (
    Origin("bryansk", "Брянщина", "NE", 40, ("брянськ", "брянщин", "брянс"), 53.24, 34.36),
    Origin("kursk", "Курщина", "NE", 60, ("курськ", "курщин", "курс"), 51.73, 36.19),
    Origin("oryol", "Орловщина", "NE", 50, ("орел", "орл", "орловщин"), 52.97, 36.07),
    Origin("shatalovo", "Шаталове", "N", 12, ("шаталов",), 54.35, 32.53),
    # "воронєж" (є-spelling) appears in the real feed alongside "воронеж" — the
    # stem matcher won't bridge є↔е, so both are listed explicitly.
    Origin("voronezh", "Воронежчина", "E", 72, ("воронеж", "воронєж", "воронезьк"), 51.66, 39.20),
    Origin("millerovo", "Міллерово", "SE", 105, ("міллеров", "мілеров"), 48.92, 40.40),
    Origin("rostov", "Ростовщина", "SE", 115, ("ростов", "ростовщин"), 47.24, 39.71),
    Origin("engels", "Енгельс", "E", 85, ("енгельс",), 51.48, 46.12),
    Origin("caspian", "Каспій", "E", 95, ("каспійськ", "каспій"), 42.00, 50.00),
    Origin("black_sea", "Чорне море", "S", 185, ("чорного мор", "чорне мор", "чорному мор"), 44.00, 32.00),
    Origin("azov", "Приморсько-Ахтарськ", "SE", 135, ("ахтарськ", "приморсько"), 46.05, 38.17),
    Origin("crimea", "Крим", "S", 170, ("крим",), 45.30, 34.40),
    Origin("belarus", "Білорусь", "N", 340, ("білорус", "мозир", "брагін"), 52.05, 29.25),
    Origin("chernihiv", "Чернігівщина", "N", 20, ("чернігівщин", "чернігів"), 51.49, 31.29),
    Origin("sumy", "Сумщина", "E", 75, ("сумщин", "сум"), 50.91, 34.80),
)

ORIGIN_BY_KEY = {o.key: o for o in ORIGINS}
ORIGIN_KEYS = tuple(o.key for o in ORIGINS)

# From-position preposition + optional bridge word, mirroring
# ingest._OBLAST_ORIGIN_RE: "з Брянщини", "з боку Чорного моря", "від Ростова",
# "з району Ростова". Only an origin in this position becomes an axis — a bare
# mention ("удар по Брянщині") is not an inbound direction toward us.
_FROM_PREFIX = (
    r"(?<![а-яіїєґ])(?:з|зі|із|від)\s+"
    r"(?:боку\s+|напрямку\s+|сторони\s+|району\s+|р-ну\s+)?"
)
# One regex per origin so a match maps straight back to its key; each stem
# allows a Ukrainian case tail ("брянщин" -> "брянщини").
_ORIGIN_RES: tuple[tuple[str, re.Pattern], ...] = tuple(
    (
        o.key,
        re.compile(
            _FROM_PREFIX + r"(?:" + "|".join(sorted(map(re.escape, o.stems), key=len, reverse=True))
            + r")[а-яіїєґ]*"
        ),
    )
    for o in ORIGINS
)


def match_origin(norm: str) -> Origin | None:
    """The origin named in FROM-position in `norm`, if any (first by text order,
    then by stem specificity when two match at the same spot). `norm` must be
    matcher.normalize()-d text. Returns None when no curated origin is named as
    an inbound direction — the common case."""
    best: tuple[int, int, Origin] | None = None  # (start, -stem_specificity, origin)
    for key, pat in _ORIGIN_RES:
        m = pat.search(norm)
        if m is None:
            continue
        origin = ORIGIN_BY_KEY[key]
        spec = max(len(s) for s in origin.stems)
        cand = (m.start(), -spec, origin)
        if best is None or cand[:2] < best[:2]:
            best = cand
    return best[2] if best is not None else None


# --- Target-elsewhere detection (shared by parsing.rules and pipeline.ingest) ---
# Oblasts/cities/border regions this feed regularly mentions. When one is the
# target's LOCATION ("ціль на Дніпро", "курсом на Дніпропетровщину") the threat
# is someone else's — no Kyiv district to find AND no Kyiv-relevant axis to
# raise. An ORIGIN mention ("з Чернігівщини", heading toward us) is different —
# that IS Kyiv-relevant. This is the same set the LLM system prompt is told to
# return empty for.
#
# The second block was added from a 5000-message coverage sweep: every entry
# there is a place the feed named as a TARGET while the first block stayed
# silent, so the message reached the LLM and came back empty ("Ракета ввійшла в
# ПП Польща", "Пара БПЛА на Прилуки", "В Сумах впали"). City forms are listed
# next to their oblast because the spotters use both.
#
# Rejected after the corpus sweep, each for a real collision:
#   "сум"     — eats "сумно"/"сумнів"; the explicit "суми"/"сумах" forms are used;
#   "житомир" — Kyiv's own metro station and highway ("станції метро
#               «Житомирська»", "Житомирська траса"); only the oblast forms are;
#   "львів"   — Львівська площа is in Shevchenkivskyi; only "львівщин" is;
#   "рівне"   — too close to the adjective;
#   "вологд"  — appears only as a launch ORIGIN ("пуски з району Вологди"),
#               which must stay Kyiv-relevant.
#
# Чернігівщина USED to be in this list (with its city and the towns Ніжин /
# Прилуки). It no longer is: it is a WATCHED region now — targets over it are
# the early warning this radar exists for, and suppressing them threw away the
# 20 minutes of notice the northern corridor buys. Removing it costs nothing
# elsewhere, because a message naming ONLY Чернігівщина as a target has always
# had somewhere to go: its own region's track pool. What still has to hold is
# that «з Чернігівщини курсом на Дніпро» stays suppressed — Дніпро is in this
# list and is not in origin position, so the count below still catches it.
_OTHER_OBLAST = ("брянщин", "курщин", "ростов", "воронеж", "воронєж",
                 "дніпропетровщин", "дніпро", "запоріжж", "миколаївщин", "сумщин",
                 "полтавщин", "харківщин", "харков", "білорус", "крим",
                 "житомирщин", "вінницьк", "вінниччин", "вінничин",
                 "черкащин", "одещин", "херсонщин",
                 "черкас", "полтав", "суми", "сумах", "житомирську обл",
                 "житомирської обл", "жашків", "одес", "миколаїв",
                 "львівщин", "дрогобич", "самбір", "стрий", "рівненщин", "волин",
                 "тернопільщин", "тернопіл", "закарпат", "франківськ",
                 "хмельниччин", "хмельницьк", "кіровоградщин", "донеччин",
                 "луганщин", "чернівц", "буковин",
                 "польщ", "люблін", "молдов", "румун",
                 # Third sweep, same rule as the second: a TOWN the feed names
                 # as the target while its oblast is never mentioned, so the
                 # message reached the LLM and came back empty — «Реактивний
                 # біля Пирятина» (Poltava), «На Конотоп йде ймовірно
                 # бандероль» (Sumy), «Є загроза Кропивницькому» (Kirovohrad).
                 # Zero collisions across the 4900-message corpus.
                 #
                 # NOT here, deliberately: Бахмач. It is CHERNIHIV oblast, a
                 # watched region — «Ще бандероль на Бахмач з Сумської» is the
                 # northern corridor doing its job, and it belongs in the
                 # gazetteer, not in this list. Same for Ніжин and Прилуки, see
                 # _WATCHED_OBLAST below.
                 "пирятин", "конотоп", "кропивницьк")
# Regions we WATCH but that are still not Kyiv. A target over one of them is
# ours to track (its own pool) — but it is not a Kyiv target, so anything that
# speaks specifically about the KYIV city alert must keep ignoring it: a terse
# «Цілі на Чернігівщині» must not corroborate the city-wide alert, and a
# «По Чернігівщині тихо» bulletin is not a Kyiv bulletin.
_WATCHED_OBLAST = ("чернігівщин", "чернігів", "ніжин", "прилук")


def _alt(forms) -> str:
    return "|".join(sorted(map(re.escape, forms), key=len, reverse=True))


_OBLAST_ALT_ANY = _alt(_OTHER_OBLAST)
_OBLAST_ALT_NON_KYIV = _alt(_OTHER_OBLAST + _WATCHED_OBLAST)
# Any other-oblast mention.
_OBLAST_ANY_RE = re.compile(r"(?<![а-яіїєґ])(?:" + _OBLAST_ALT_ANY + r")")
# The same, widened to every non-Kyiv region including the watched ones.
_NON_KYIV_ANY_RE = re.compile(r"(?<![а-яіїєґ])(?:" + _OBLAST_ALT_NON_KYIV + r")")
# An other-oblast in ORIGIN position ("з боку Сумщини", "з району Ростова"). Same
# from-preposition + bridge shape as _FROM_PREFIX above. One preposition can
# govern a coordinated LIST ("загроза балістики з Брянщини, Курщини та з району
# Ростова" — all three are origins) — the tail alternation swallows the
# continuation so those oblasts count as origin-form too.
_OBLAST_BRIDGE = r"(?:боку\s+|напрямку\s+|район\w*\s+|р-ну\s+|межах\s+|межа\w*\s+)?"
def _origin_re(alt: str) -> re.Pattern:
    return re.compile(
        r"(?<![а-яіїєґ])(?:з|зі|із|від)\s+"
        + _OBLAST_BRIDGE
        + r"(?:" + alt + r")[а-яіїєґ]*"
        r"(?:\s*(?:,|та|і|й)\s+(?:(?:з|зі|із|від)\s+)?" + _OBLAST_BRIDGE
        + r"(?:" + alt + r")[а-яіїєґ]*)*"
    )


_OBLAST_ORIGIN_RE = _origin_re(_OBLAST_ALT_ANY)
_NON_KYIV_ORIGIN_RE = _origin_re(_OBLAST_ALT_NON_KYIV)


# A far city's name used for a road/street that runs through OUR area is not
# another oblast: "Маневр по трасі Київ-Суми" and "ДТП на Одеській трасі" are
# both about Kyivshchyna. Blanked before counting, so the highway register can't
# suppress a local sighting.
_ROAD_USE_RE = re.compile(
    r"(?:" + _OBLAST_ALT_ANY + r")[а-яіїєґ]*\s+(?:трас|шосе|площ|вулиц|проспект)[а-яіїєґ]*"
    r"|(?<![а-яіїєґ])київ[а-яіїєґ]*\s*[-–—]\s*(?:" + _OBLAST_ALT_ANY + r")[а-яіїєґ]*"
)


# Us as the stated DESTINATION — vetoes the whole check below.
_KYIV_DESTINATION_RE = re.compile(
    r"(?<![а-яіїєґ])(?:на|до|в бік|у бік|курс(?:ом)? на)\s+(?:київ|києва|київщин|столиц)"
)


def target_elsewhere(norm: str) -> bool:
    """True if the message names another oblast as a target LOCATION (not merely
    an inbound target's origin) — then the threat genuinely isn't ours: no Kyiv
    district to localize AND no Kyiv-relevant axis to raise. An origin-only
    mention ("з Чернігівщини", heading to us) returns False. Conservative when
    unclear: a non-origin oblast mention suppresses."""
    norm = _ROAD_USE_RE.sub(" ", norm)
    if _KYIV_DESTINATION_RE.search(norm):
        # The message states US as the destination ("зі Сумщини пішли в район
        # Ніжин, далі ймовірно на Київщину") — whatever else it names on the way,
        # it is exactly the message this feed exists for.
        return False
    return _targets_a_region(norm, _OBLAST_ANY_RE, _OBLAST_ORIGIN_RE)


def target_not_kyiv(norm: str) -> bool:
    """Like `target_elsewhere`, but the WATCHED regions count as elsewhere too.

    For anything scoped to the Kyiv city alert specifically — a terse pulse
    corroborating it, a threat-level bulletin about it — «Чернігівщина» is not
    Kyiv, even though it is now a region we track."""
    norm = _ROAD_USE_RE.sub(" ", norm)
    if _KYIV_DESTINATION_RE.search(norm):
        return False
    return _targets_a_region(norm, _NON_KYIV_ANY_RE, _NON_KYIV_ORIGIN_RE)


def _targets_a_region(norm: str, any_re: re.Pattern, origin_re: re.Pattern) -> bool:
    total = len(any_re.findall(norm))
    if total == 0:
        return False
    # Count oblasts INSIDE each origin-form span (a coordinated list is one
    # match carrying several oblasts), so it compares apples to `total`.
    origins = sum(len(any_re.findall(m.group(0))) for m in origin_re.finditer(norm))
    return origins < total


def bearing_for(origin_key: str | None, sector: str | None) -> int:
    """Wedge bearing for an axis: prefer the specific origin's bearing, else the
    sector's representative bearing, else due north."""
    if origin_key and origin_key in ORIGIN_BY_KEY:
        return ORIGIN_BY_KEY[origin_key].bearing_deg
    if sector and sector in SECTOR_BEARING:
        return SECTOR_BEARING[sector]
    return 0
