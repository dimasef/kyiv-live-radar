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
    ("Kyiv Reservoir", ["Київське водосховище, Вишгородський район, Київська область"]),
    # G. Northern approach — 2026-08-17 feed gaps (drones enter Kyiv oblast via
    # the exclusion zone from Belarus; every "ЧЗВ"/"Страхолісся" mention was
    # lost as "не про загрозу").
    ("Strakholissia", ["Страхолісся, Вишгородський район, Київська область"]),
    ("Chornobyl Zone", ["Чорнобиль, Київська область",
                        "Чорнобильська зона відчуження"]),
    # H. Spotter shorthand — 2026-08-18 coverage-gap export. "ПОХ" (Позняки-
    # Осокорки-Харківський) and "Торгмаш" are decoded by the maintainer, not by
    # a search engine; only the two real toponyms are geocodable here.
    ("Pushcha-Vodytsia", ["Пуща-Водиця, Київ"]),
    ("Torhmash Brovary", ["Торгмаш, Бровари, Київська область",
                          "завод Торгмаш, Бровари"]),
    # I. Southern/eastern approach towns of Kyiv oblast — 2026-08-18 coverage-gap
    # export. Drones are called in over these on the way to the city.
    ("Berezan", ["Березань, Броварський район, Київська область"]),
    ("Bila Tserkva", ["Біла Церква, Київська область"]),
    ("Kaharlyk", ["Кагарлик, Обухівський район, Київська область"]),
    ("Rokytne", ["Рокитне, Білоцерківський район, Київська область"]),
    ("Myronivka", ["Миронівка, Обухівський район, Київська область"]),
    ("Tarashcha", ["Тараща, Білоцерківський район, Київська область"]),
    ("Bohuslav", ["Богуслав, Обухівський район, Київська область"]),
    ("Kyiliv", ["Кийлів, Бориспільський район, Київська область"]),
    # G. Chernihiv oblast — the northern approach, mined from 300 real messages
    # of @chyste_nebochernigv (eval/chyste_nebochernigv_sample.jsonl). Every
    # name below is one the channel actually calls out; they are what takes the
    # parser from 20% to 72% coverage on that feed.
    ("Liubech", ["Любеч, Ріпкинський район, Чернігівська область"]),
    ("Oster", ["Остер, Козелецький район, Чернігівська область"]),
    ("Horodnia", ["Городня, Чернігівська область"]),
    ("Horodyshche CH", ["Городище, Чернігівський район, Чернігівська область"]),
    ("Honcharivske", ["Гончарівське, Чернігівський район, Чернігівська область"]),
    ("Khrinivka", ["Хрінівка, Городнянський район, Чернігівська область"]),
    ("Ripky", ["Ріпки, Чернігівська область"]),
    ("Senkivka CH", ["Сеньківка, Городнянський район, Чернігівська область"]),
    ("Budyshche CH", ["Будище, Чернігівський район, Чернігівська область"]),
    ("Sedniv", ["Седнів, Чернігівський район, Чернігівська область"]),
    ("Oleshnia", ["Олешня, Ріпкинський район, Чернігівська область"]),
    ("Morivsk", ["Морівськ, Козелецький район, Чернігівська область"]),
    ("Loshakova Huta", ["Лошакова Гута, Чернігівська область"]),
    ("Vasyleva Huta", ["Василева Гута, Чернігівська область"]),
    ("Chudivka", ["Чудівка, Ріпкинський район, Чернігівська область"]),
    ("Khotivlia", ["Хотівля, Городнянський район, Чернігівська область"]),
    ("Sorokoshychi", ["Сорокошичі, Козелецький район, Чернігівська область"]),
    ("Nosivka", ["Носівка, Ніжинський район, Чернігівська область"]),
    ("Lovyn", ["Ловинь, Ріпкинський район, Чернігівська область"]),
    ("Kosachivka", ["Косачівка, Козелецький район, Чернігівська область"]),
    ("Hirsk", ["Гірськ, Чернігівський район, Чернігівська область"]),
    ("Hrabiv", ["Грабів, Чернігівська область"]),
    ("Borovyky", ["Боровики, Чернігівський район, Чернігівська область"]),
    ("Starosillia CH", ["Старосілля, Чернігівська область"]),
    ("Rivnopillia", ["Рівнопілля, Чернігівський район, Чернігівська область"]),
    ("Rudnia CH", ["Рудня, Ріпкинський район, Чернігівська область"]),
    ("Otrokhy", ["Отрохи, Чернігівський район, Чернігівська область"]),
    ("Olyshivka", ["Олишівка, Чернігівський район, Чернігівська область"]),
    ("Nizhyn", ["Ніжин, Чернігівська область"]),
    ("Novhorod-Siverskyi", ["Новгород-Сіверський, Чернігівська область"]),
    ("Mryn", ["Мрин, Ніжинський район, Чернігівська область"]),
    ("Moshchenka", ["Мощенка, Городнянський район, Чернігівська область"]),
    ("Kulykivka", ["Куликівка, Чернігівський район, Чернігівська область"]),
    ("Kratyn", ["Кратинь, Ріпкинський район, Чернігівська область"]),
    ("Vertiivka", ["Вертіївка, Ніжинський район, Чернігівська область"]),
    ("Borzna", ["Борзна, Чернігівська область"]),
    ("Bobrovytsia", ["Бобровиця, Чернігівська область"]),
    ("Forostovychi", ["Форостовичі, Чернігівська область"]),
    ("Tuzhar", ["Тужар, Чернігівська область"]),
    ("Smolianka", ["Смолянка, Чернігівська область"]),
    ("Rudka CH", ["Рудка, Ріпкинський район, Чернігівська область"]),
    ("Pryluky", ["Прилуки, Чернігівська область"]),
    ("Pylypcha", ["Пилипча, Чернігівська область"]),
    ("Petrushyn", ["Петрушин, Чернігівський район, Чернігівська область"]),
    ("Lhiv", ["Льгів, Чернігівська область"]),
    ("Drozdovytsia", ["Дроздовиця, Городнянський район, Чернігівська область"]),
    ("Dykhanivka", ["Диханівка, Чернігівська область"]),
    ("Berelivka", ["Берелівка, Чернігівська область"]),
    ("Basan", ["Басань, Чернігівська область"]),
    ("Avtunychi", ["Автуничі, Городнянський район, Чернігівська область"]),
    ("Mykhailo-Kotsiubynske", ["Михайло-Коцюбинське, Чернігівський район"]),
    ("Chernihiv", ["Чернігів, Чернігівська область"]),
    ("Snovsk", ["Сновськ, Чернігівська область"]),
    ("Koriukivka", ["Корюківка, Чернігівська область"]),
    ("Mena", ["Мена, Чернігівська область"]),
    ("Berezna", ["Березна, Менський район, Чернігівська область"]),
    ("Chemer", ["Чемер, Козелецький район, Чернігівська область"]),
    ("Kukshyn", ["Кукшин, Ніжинський район, Чернігівська область"]),
    ("Borsukiv", ["Борсуків, Чернігівська область"]),
    ("Zrub", ["Зруб, Чернігівська область"]),
    ("Khorobychi", ["Хоробичі, Городнянський район, Чернігівська область"]),
    ("Tupychiv", ["Тупичів, Городнянський район, Чернігівська область"]),
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
