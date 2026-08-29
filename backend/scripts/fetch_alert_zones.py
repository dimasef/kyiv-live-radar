"""One-off: fetch OSM boundary polygons for the alert zones the map paints (the
raions of every covered oblast, plus Kyiv city) and write the committed data
file the API serves. Same shape and rationale as fetch_boundaries.py — the
output is checked in, so the app has zero runtime dependency on Nominatim.

    cd backend && .venv/bin/python scripts/fetch_alert_zones.py

Nominatim can simplify server-side (`polygon_threshold`), which is both cheaper
and better than round-tripping a 120 KB raion outline just to RDP it here; the
local simplify from fetch_boundaries.py still runs as a floor.

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

from app.domain.alert_zones import ZONES  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "alert_zones.json"
# ~0.005° of arc. A raion outline is painted at oblast zoom, where anything
# finer is invisible — this keeps all 13 shapes to ~100 KB total.
POLYGON_THRESHOLD = 0.005


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


def _count(c) -> int:
    if not c:
        return 0
    if isinstance(c[0], (int, float)):
        return 1
    return sum(_count(x) for x in c)


def main() -> None:
    out: dict[str, dict] = {}
    for zone in ZONES:
        try:
            geom = _fetch(zone.query)
        except Exception as ex:
            print(f"  {zone.id}: FAIL {ex}")
            continue
        if geom is None:
            print(f"  {zone.id}: no polygon")
            continue
        simplified = _simplify_geometry(geom)
        out[zone.id] = {
            "name_uk": zone.name_uk,
            "oblast": zone.oblast,
            "geojson": simplified,
        }
        print(f"  {zone.id:34} {geom['type']:12} "
              f"{_count(geom['coordinates'])} -> {_count(simplified['coordinates'])} pts")
        time.sleep(1.2)  # Nominatim rate limit

    missing = [z.id for z in ZONES if z.id not in out]
    OUT.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    print(f"\nwrote {len(out)}/{len(ZONES)} zones to {OUT}")
    if missing:
        print(f"MISSING (the map will not paint these): {', '.join(missing)}")


if __name__ == "__main__":
    main()
