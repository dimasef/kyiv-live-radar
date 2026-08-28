"""One-off: fetch OSM boundary polygons for the WATCHED REGIONS (oblasts) and
write the committed data file the API serves. Sibling of
fetch_alert_zones.py — different key space (region id, not zone id) and a
different lifecycle: a raion roster changes when raions are added, an oblast
outline never does.

    cd backend && .venv/bin/python scripts/fetch_region_outlines.py

This layer is only ever drawn zoomed out past the raion layer, so it is
simplified harder than the zones (0.01° vs 0.005°) — all five oblasts together
should land around 25 KB.

A spec's `outline_queries` is a TUPLE for Kyiv's sake: Nominatim's «Київська
область» is very likely a donut with м. Київ cut out of it (a separate
first-level unit), and a click in the middle of Kyivshchyna — the most likely
click there is — would fall through the hole. Every query's parts are merged
into one MultiPolygon. Check the printed part counts when you run this.

Respect the Nominatim usage policy (<=1 req/s, real User-Agent).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_boundaries import UA, _simplify_geometry  # noqa: E402

from app.regions import REGION_SPECS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "region_outlines.json"
POLYGON_THRESHOLD = 0.01


def _fetch(query: str) -> dict | None:
    q = urllib.parse.quote(query)
    url = (f"https://nominatim.openstreetmap.org/search?q={q}"
           f"&format=json&polygon_geojson=1&polygon_threshold={POLYGON_THRESHOLD}"
           "&limit=1&countrycodes=ua")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not data:
        return None
    g = data[0].get("geojson")
    if not g or g["type"] not in ("Polygon", "MultiPolygon"):
        return None
    return g


def _polygons(geom: dict) -> list:
    """A geometry's rings as a list of Polygon coordinate arrays."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return list(geom["coordinates"])


def _count(c) -> int:
    if not c:
        return 0
    if isinstance(c[0], (int, float)):
        return 1
    return sum(_count(x) for x in c)


def main() -> None:
    out: dict[str, dict] = {}
    for spec in REGION_SPECS:
        parts: list = []
        for query in spec.outline_queries:
            try:
                geom = _fetch(query)
            except Exception as ex:
                print(f"  {spec.id}: FAIL {query!r} {ex}")
                continue
            finally:
                time.sleep(1.2)  # Nominatim rate limit
            if geom is None:
                print(f"  {spec.id}: no polygon for {query!r}")
                continue
            parts.extend(_polygons(_simplify_geometry(geom)))
        if not parts:
            print(f"  {spec.id}: nothing fetched")
            continue
        merged = {"type": "MultiPolygon", "coordinates": parts}
        out[spec.id] = {"name_uk": spec.name_uk, "geojson": merged}
        print(f"  {spec.id:12} {len(parts)} part(s), {_count(parts)} pts")

    missing = [s.id for s in REGION_SPECS if s.id not in out]
    OUT.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    print(f"\nwrote {len(out)}/{len(REGION_SPECS)} regions to {OUT}")
    if missing:
        print(f"MISSING (not clickable on the map): {', '.join(missing)}")


if __name__ == "__main__":
    main()
