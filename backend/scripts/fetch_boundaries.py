"""One-off: fetch real OSM boundary polygons for Kyiv's 10 administrative raions
from Nominatim, simplify them (Ramer-Douglas-Peucker), and write a committed data
file the app seeds from. Run rarely — the output is checked into the repo so the
app has zero runtime dependency on Nominatim.

    cd backend && .venv/bin/python scripts/fetch_boundaries.py

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

from app.gazetteer import DISTRICTS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "boundaries.json"
UA = "kyiv-live-radar/0.1 (situational-awareness dev tool)"
RDP_TOL = 0.0004  # ~40m — plenty for district-level rendering

# The 10 administrative raions (real official boundaries exist in OSM).
RAIONS = [d for d in DISTRICTS if d["name_uk"].endswith("ський") or d["name_uk"].endswith("цький")]


def _perp_dist(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    px, py = x1 + t * dx, y1 + t * dy
    return ((x - px) ** 2 + (y - py) ** 2) ** 0.5


def _rdp(points: list, tol: float) -> list:
    if len(points) < 3:
        return points
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        left = _rdp(points[: idx + 1], tol)
        right = _rdp(points[idx:], tol)
        return left[:-1] + right
    return [points[0], points[-1]]


def _simplify_geometry(geom: dict) -> dict:
    def ring(r):
        return _rdp(r, RDP_TOL)

    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring(r) for r in geom["coordinates"]]}
    if geom["type"] == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [[ring(r) for r in poly] for poly in geom["coordinates"]],
        }
    return geom


def _fetch(name_uk: str) -> dict | None:
    q = urllib.parse.quote(f"{name_uk} район, Київ")
    url = (f"https://nominatim.openstreetmap.org/search?q={q}"
           "&format=json&polygon_geojson=1&limit=1")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not data:
        return None
    g = data[0].get("geojson")
    if not g or g["type"] not in ("Polygon", "MultiPolygon"):
        return None
    return g


def main() -> None:
    out = {}
    for d in RAIONS:
        try:
            geom = _fetch(d["name_uk"])
        except Exception as ex:
            print(f"  {d['name_en']}: FAIL {ex}")
            continue
        if geom is None:
            print(f"  {d['name_en']}: no polygon")
            continue
        simplified = _simplify_geometry(geom)
        out[d["name_en"]] = simplified

        def count(c):
            if not c or isinstance(c[0], (int, float)):
                return 1 if c and isinstance(c[0], (int, float)) else 0
            return sum(count(x) for x in c)

        print(f"  {d['name_en']:16} {geom['type']:12} "
              f"{count(geom['coordinates'])} -> {count(simplified['coordinates'])} pts")
        time.sleep(1.2)  # Nominatim rate limit

    OUT.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    print(f"\nwrote {len(out)} boundaries to {OUT.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
