"""One-off: geocode Kyiv-area localities seen in the live feed but missing from
the gazetteer, so we can add accurate representative points. Prints ready-to-read
lat/lon per name. Respect Nominatim policy (<=1 req/s, real User-Agent).

    cd backend && .venv/bin/python scripts/geocode_localities.py
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

UA = "kyiv-live-radar/0.1 (situational-awareness dev tool)"

# name_en, and the query variants to try (most specific first).
QUERIES: list[tuple[str, list[str]]] = [
    # A. North / North-East (main threat axis)
    ("Kozelets", ["Козелець, Чернігівська область"]),
    ("Oster", ["Остер, Чернігівська область"]),
    ("Kalyta", ["Калита, Броварський район, Київська область"]),
    ("Semypolky", ["Семиполки, Броварський район, Київська область"]),
    ("Litky", ["Літки, Броварський район, Київська область"]),
    ("Bohdanivka", ["Богданівка, Броварський район, Київська область"]),
    ("Dymer", ["Димер, Вишгородський район, Київська область"]),
    ("Demydiv", ["Демидів, Вишгородський район, Київська область"]),
    ("Kozarovychi", ["Козаровичі, Вишгородський район, Київська область"]),
    ("Katiuzhanka", ["Катюжанка, Вишгородський район, Київська область"]),
    # B. South-East transit
    ("Pereiaslav", ["Переяслав, Київська область"]),
    ("Yahotyn", ["Яготин, Київська область"]),
    ("Baryshivka", ["Баришівка, Київська область"]),
    ("Hoholiv", ["Гоголів, Броварський район, Київська область"]),
    ("Trebukhiv", ["Требухів, Броварський район, Київська область"]),
    ("Kniazhychi", ["Княжичі, Броварський район, Київська область"]),
    # C. South / South-West suburbs
    ("Boiarka", ["Боярка, Київська область"]),
    ("Hlevakha", ["Глеваха, Київська область"]),
    ("Kriukivshchyna", ["Крюківщина, Київська область"]),
    ("Hatne", ["Гатне, Київська область"]),
    ("Ukrainka", ["Українка, Обухівський район, Київська область"]),
    ("Rzhyshchiv", ["Ржищів, Київська область"]),
    ("Kozyn", ["Козин, Обухівський район, Київська область"]),
    # D. North-West (from Belarus / Zhytomyr)
    ("Borodianka", ["Бородянка, Київська область"]),
    ("Nemishaieve", ["Немішаєве, Київська область"]),
    ("Klavdiieve", ["Клавдієво-Тарасове, Київська область", "Клавдієво, Київська область"]),
    ("Ivankiv", ["Іванків, Київська область"]),
    ("Piskivka", ["Пісківка, Київська область"]),
]


def _geocode(q: str) -> tuple[float, float] | None:
    url = ("https://nominatim.openstreetmap.org/search?"
           + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1}))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not data:
        return None
    return round(float(data[0]["lat"]), 4), round(float(data[0]["lon"]), 4)


def main() -> None:
    for name_en, variants in QUERIES:
        hit = None
        for q in variants:
            try:
                hit = _geocode(q)
            except Exception as ex:
                print(f"  {name_en}: ERROR {ex}")
                hit = None
            time.sleep(1.2)
            if hit:
                break
        if hit:
            print(f'  {name_en:16} lat={hit[0]}  lon={hit[1]}')
        else:
            print(f"  {name_en:16} NOT FOUND")


if __name__ == "__main__":
    main()
