"""Address search — turning what a reader types into a point on the map.

Used by exactly one flow: placing your own home marker. It never feeds the
parser, and nothing here decides where a *threat* is; a wrong answer costs one
misplaced map camera, not a target on the wrong side of the country.

Two tiers, in order:

1. The gazetteer we already have. 700-odd settlements and micro-neighbourhoods
   with coordinates, answered from memory. Free, instant, and — the reason it
   goes first rather than second — still working when OSM is down.
2. Photon, for what the gazetteer does not know: streets and house numbers.

Photon and not Nominatim, and the difference is the whole feature. Nominatim's
`/search` matches whole words: «тираспольс» answers with nothing at all and
«тираспольська» answers with the street, so a search box built on it only works
for a reader who has already finished typing — measured, 2026-08-31. Photon
indexes the same OSM data for prefix search, which is what a box that answers
while you type needs.

Either way the call is proxied through the backend rather than made from the
browser: both services ask for a meaningful `User-Agent` (a header a page
cannot set) and for a request rate no client-side debounce can promise across
all our readers. The throttle and the cache below are that promise.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from .config import settings
from .gazetteer import CITYWIDE_NAME_EN, DISTRICTS, HOME_REGION
from .models import GeocodeSource
from .parsing.matcher import normalize
from .regions import REGION_SPECS, Region

log = logging.getLogger(__name__)

# Below this a query is noise: two letters match a third of the gazetteer and
# a third of the country. The frontend holds the same floor, this one is the
# enforced copy.
MIN_QUERY_LEN = 3
MAX_HITS = 6
_MAX_GAZETTEER_HITS = 3
# Bounded so a long session of searching cannot grow without limit; the whole
# point of the cache is repeated prefixes of one address, which is small.
_CACHE_MAX = 256

_REGION_NAMES = {spec.id: spec.name_uk for spec in REGION_SPECS}
_REGION_BBOX = {spec.id: spec.bbox for spec in REGION_SPECS}
# Fallback bounding box (south, west, north, east) for a reader who has not
# picked a region: the whole country, so the search is never unbounded.
_UKRAINE_BBOX = (44.0, 22.0, 52.5, 40.3)


@dataclass(frozen=True)
class GeoHit:
    """One place the reader could mean."""

    label: str
    sublabel: str | None
    lat: float
    lon: float
    source: GeocodeSource


def _match_rank(name: str, needle: str) -> int | None:
    """0 = the name starts with what was typed, 1 = merely contains it."""
    if name.startswith(needle):
        return 0
    if needle in name:
        return 1
    return None


def gazetteer_hits(q: str, region: Region | None = None) -> list[GeoHit]:
    """Places from our own gazetteer, the reader's own region first."""
    needle = normalize(q).strip()
    if len(needle) < MIN_QUERY_LEN:
        return []
    scored: list[tuple[tuple[int, int, str], GeoHit]] = []
    for entry in DISTRICTS:
        # The city-wide sentinel is a parser construct, not a place — matching
        # it would offer "Київ" as somewhere to put a house.
        if entry["name_en"] == CITYWIDE_NAME_EN:
            continue
        names = [entry["name_uk"], *entry.get("aliases", ())]
        ranks = [r for n in names if (r := _match_rank(normalize(n), needle)) is not None]
        if not ranks:
            continue
        entry_region = entry.get("region", HOME_REGION)
        scored.append((
            (min(ranks), 0 if entry_region == region else 1, entry["name_uk"]),
            GeoHit(
                label=entry["name_uk"],
                sublabel=_REGION_NAMES.get(entry_region),
                lat=entry["lat"],
                lon=entry["lon"],
                source="gazetteer",
            ),
        ))
    scored.sort(key=lambda pair: pair[0])
    return [hit for _, hit in scored[:_MAX_GAZETTEER_HITS]]


# Photon's context fields, widest-in last. The reader needs enough to tell two
# identically-named streets apart, not the full postal address.
_CONTEXT_FIELDS = ("district", "city", "county", "state")


def osm_label(props: dict) -> tuple[str, str | None]:
    """Build a heading and its context from one Photon feature's properties.

    Photon answers with parts rather than a single line, which is what lets the
    heading be the address alone («вулиця Хрещатик 22») and the rest — raion,
    city, oblast — sit under it in a quieter colour. A named building keeps its
    name in front of the address, because «Ощадбанк» is how the reader
    recognises the corner they mean.
    """
    name = str(props.get("name") or "").strip()
    street = str(props.get("street") or "").strip()
    number = str(props.get("housenumber") or "").strip()
    address = f"{street} {number}".strip()
    if address and name:
        label = f"{name}, {address}"
    else:
        label = name or address
    context: list[str] = []
    for field in _CONTEXT_FIELDS:
        part = str(props.get(field) or "").strip()
        # Skip what the heading already says — a street in Оболонь must not
        # read "Оболонь · Оболонь, Київ".
        if not part or part in label or part in context:
            continue
        context.append(part)
    return label, ", ".join(context[:2]) or None


def _osm_hit(feature: dict) -> GeoHit | None:
    props = feature.get("properties") or {}
    # The bounding box bleeds over four borders; the country code is what keeps
    # a Belarusian village out of a Kyiv search.
    if props.get("countrycode") != "UA":
        return None
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    label, sublabel = osm_label(props)
    if not label:
        return None
    return GeoHit(label=label, sublabel=sublabel, lat=lat, lon=lon, source="osm")


def _dedupe(hits: list[GeoHit]) -> list[GeoHit]:
    """One row per address text.

    OSM holds a house as a node, a way and sometimes a relation, and answers
    with all of them: «Хрещатик 22» really comes back as three identical lines
    metres apart. Deduping on the TEXT rather than on distance is what keeps
    number 22 and number 24 — a few metres apart and genuinely different
    homes — as two choices.
    """
    seen: set[tuple[str, str | None]] = set()
    out: list[GeoHit] = []
    for hit in hits:
        key = (hit.label, hit.sublabel)
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out


_lock = asyncio.Lock()
_last_call = 0.0
_cache: dict[str, tuple[float, list[GeoHit]]] = {}


def reset_cache() -> None:
    """Drop the memo — for tests, which must not inherit each other's answers."""
    global _last_call
    _cache.clear()
    _last_call = 0.0


async def _fetch(q: str, region: Region | None) -> list[dict]:
    # Photon reads a bbox as lon,lat,lon,lat while the region roster stores
    # south,west,north,east. It is a filter, not a preference — the reader is
    # placing their own home, so an answer from another oblast is never the one
    # they meant. No `lang`: the default returns each place's local name, which
    # here is the Ukrainian one.
    south, west, north, east = _REGION_BBOX.get(region or "") or _UKRAINE_BBOX
    params: dict[str, str | int] = {
        "q": q,
        "limit": MAX_HITS,
        "bbox": f"{west},{south},{east},{north}",
    }
    async with httpx.AsyncClient(timeout=settings.geocode_timeout_s) as client:
        resp = await client.get(
            settings.geocode_url,
            params=params,
            headers={"User-Agent": settings.geocode_user_agent},
        )
        resp.raise_for_status()
        data = resp.json()
    features = data.get("features") if isinstance(data, dict) else None
    return features if isinstance(features, list) else []


async def osm_hits(q: str, region: Region | None = None) -> list[GeoHit]:
    """Nominatim results, rate-limited and memoized. Never raises.

    A geocoder that occasionally answers 500 is worse than one that
    occasionally knows less: the search box is a convenience over a map the
    reader can still pan by hand, so every failure degrades to the gazetteer
    tier instead of breaking the input.
    """
    needle = normalize(q).strip()
    if not settings.geocode_osm_enabled or len(needle) < MIN_QUERY_LEN:
        return []
    key = f"{region or ''}|{needle}"
    hit = _cached(key)
    if hit is not None:
        return hit
    global _last_call
    async with _lock:
        # Re-checked inside the lock: identical queries queue up behind each
        # other (a debounce losing a race, two devices), and the second one
        # must read the first one's answer rather than spend another second.
        hit = _cached(key)
        if hit is not None:
            return hit
        wait = settings.geocode_min_interval_s - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            raw = await _fetch(q, region)
        except Exception as ex:  # noqa: BLE001 — any failure degrades, none propagates
            log.warning("geocode: OSM lookup failed for %r: %s", q, ex)
            return []
        finally:
            _last_call = time.monotonic()
    hits = _dedupe([h for item in raw if (h := _osm_hit(item))])[:MAX_HITS]
    _memo(key, hits)
    return hits


def _cached(key: str) -> list[GeoHit] | None:
    entry = _cache.get(key)
    if entry is None or time.monotonic() - entry[0] > settings.geocode_cache_ttl_s:
        return None
    return entry[1]


def _memo(key: str, hits: list[GeoHit]) -> None:
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)), None)
    _cache[key] = (time.monotonic(), hits)


def _same_place(a: GeoHit, b: GeoHit) -> bool:
    """Roughly half a kilometre apart — a village the gazetteer and OSM both
    know, answered twice."""
    return abs(a.lat - b.lat) < 0.005 and abs(a.lon - b.lon) < 0.005


async def search(q: str, region: Region | None = None) -> list[GeoHit]:
    """Both tiers, gazetteer first, one entry per place."""
    ours = gazetteer_hits(q, region)
    theirs = await osm_hits(q, region)
    merged = ours + [h for h in theirs if not any(_same_place(h, o) for o in ours)]
    return merged[:MAX_HITS]
