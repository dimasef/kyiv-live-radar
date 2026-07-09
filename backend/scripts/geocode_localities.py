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
    # E. In-city Kyiv neighborhoods/landmarks — found via eval/ground_truth_sessions.json
    # (real spotter mentions, 2026-07-09 gazetteer-gap analysis).
    ("Trukhaniv Island", ["Труханів острів, Київ"]),
    ("Hidropark", ["Гідропарк, Київ"]),
    ("Kontraktova Square", ["Контрактова площа, Київ"]),
    ("Lypky", ["Липки, Печерський район, Київ"]),
    ("Klov", ["Клов, Київ"]),
    ("Kurenivka", ["Куренівка, Київ"]),
    ("Priorka", ["Пріорка, Київ"]),
    ("Minskyi Masyv", ["Мінський масив, Київ"]),
    ("Shuliavka", ["Шулявка, Київ"]),
    ("Nalyvaikivka", ["Наливайківка, Київ"]),
    ("Telychka", ["Теличка, Київ"]),
    ("Kharkivskyi Masyv", ["Харківський масив, Київ"]),
    ("Rusanivski Sady", ["Русанівські сади, Київ"]),
    ("Nyzhni Sady", ["Нижні Сади, Київ"]),
    ("Lisovyi Masyv", ["Лісовий масив, Київ"]),
    ("Zhuliany", ["Жуляни, Київ"]),
    ("Bykivnia", ["Биківня, Київ"]),
    ("Vokzalna Square", ["Вокзальна площа, Київ"]),
    ("Sky Mall Kyiv", ["Sky Mall, Київ"]),
    # F. Villages/settlements near Kyiv, mentioned as real sighting locations.
    ("Vorzel", ["Ворзель, Київська область"]),
    ("Voropaiv", ["Воропаїв, Київська область"]),
    ("Vyshenky", ["Вишеньки, Бориспільський район, Київська область"]),
    ("Hnidyn", ["Гнідин, Бориспільський район, Київська область"]),
    ("Horenka", ["Горенка, Київська область"]),
    ("Khotianivka", ["Хотянівка, Вишгородський район, Київська область"]),
    ("Chabany", ["Чабани, Київська область"]),
    ("Shchaslyve", ["Щасливе, Бориспільський район, Київська область"]),
    ("Zghurivka", ["Згурівка, Київська область"]),
    ("Kalynivka Kyiv Oblast", ["Калинівка, Києво-Святошинський район, Київська область"]),
    ("Novosilky", ["Новосілки, Києво-Святошинський район, Київська область"]),
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
