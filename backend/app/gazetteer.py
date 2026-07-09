from __future__ import annotations

# Seed gazetteer of Kyiv districts and well-known microdistricts.
#
# Coordinates are a single representative point per area (approximate centroid),
# adequate for placing a marker and a coarse movement vector. For real work,
# replace with OSM boundary polygons and use centroid/nearest-edge logic.
#
# `aliases` lists spelling variants / abbreviations that spotters actually use;
# the parser matches against these (case-insensitive, later morphology-aware).

DISTRICTS: list[dict] = [
    # --- 10 administrative raions ---
    {"name_uk": "Голосіївський", "name_en": "Holosiivskyi", "lat": 50.381, "lon": 30.508,
     "aliases": ["голосіїв", "голосіївський район"]},
    {"name_uk": "Дарницький", "name_en": "Darnytskyi", "lat": 50.410, "lon": 30.630,
     "aliases": ["дарниця", "дарницький район"]},
    {"name_uk": "Деснянський", "name_en": "Desnianskyi", "lat": 50.515, "lon": 30.605,
     "aliases": ["деснянський район"]},
    {"name_uk": "Дніпровський", "name_en": "Dniprovskyi", "lat": 50.455, "lon": 30.610,
     "aliases": ["дніпровський район"]},
    {"name_uk": "Оболонський", "name_en": "Obolonskyi", "lat": 50.520, "lon": 30.498,
     "aliases": ["оболонський район"]},
    {"name_uk": "Печерський", "name_en": "Pecherskyi", "lat": 50.425, "lon": 30.540,
     "aliases": ["печерськ", "печерський район"]},
    {"name_uk": "Подільський", "name_en": "Podilskyi", "lat": 50.470, "lon": 30.515,
     "aliases": ["поділ", "подільський район"]},
    {"name_uk": "Солом'янський", "name_en": "Solomianskyi", "lat": 50.430, "lon": 30.450,
     "aliases": ["солом'янка", "солом'янський район", "соломянський"]},
    {"name_uk": "Шевченківський", "name_en": "Shevchenkivskyi", "lat": 50.455, "lon": 30.470,
     "aliases": ["шевченківський район"]},
    {"name_uk": "Святошинський", "name_en": "Sviatoshynskyi", "lat": 50.455, "lon": 30.365,
     "aliases": ["святошино", "святошин", "святошинський район"]},

    # --- Notable microdistricts spotters name directly ---
    {"name_uk": "Троєщина", "name_en": "Troieshchyna", "lat": 50.515, "lon": 30.600,
     "aliases": ["троя", "трої", "трою", "троєю", "троєщино"]},
    {"name_uk": "Оболонь", "name_en": "Obolon", "lat": 50.510, "lon": 30.498,
     "aliases": ["оболонь"]},
    {"name_uk": "Позняки", "name_en": "Pozniaky", "lat": 50.397, "lon": 30.635,
     "aliases": ["позняки"]},
    {"name_uk": "Осокорки", "name_en": "Osokorky", "lat": 50.400, "lon": 30.610,
     "aliases": ["осокорки"]},
    {"name_uk": "Виноградар", "name_en": "Vynohradar", "lat": 50.500, "lon": 30.415,
     "aliases": ["виноградар"]},
    {"name_uk": "Нивки", "name_en": "Nyvky", "lat": 50.460, "lon": 30.410,
     "aliases": ["нивки"]},
    {"name_uk": "Борщагівка", "name_en": "Borshchahivka", "lat": 50.435, "lon": 30.375,
     "aliases": ["борщагівка", "борщага"]},
    {"name_uk": "Теремки", "name_en": "Teremky", "lat": 50.360, "lon": 30.455,
     "aliases": ["теремки"]},
    {"name_uk": "Русанівка", "name_en": "Rusanivka", "lat": 50.440, "lon": 30.590,
     "aliases": ["русанівка"]},
    {"name_uk": "Бортничі", "name_en": "Bortnychi", "lat": 50.395, "lon": 30.700,
     "aliases": ["бортничі"]},
    {"name_uk": "ДВРЗ", "name_en": "DVRZ", "lat": 50.445, "lon": 30.660,
     "aliases": ["дврз"]},
    {"name_uk": "Лівобережний", "name_en": "Livoberezhnyi", "lat": 50.452, "lon": 30.598,
     "aliases": ["лівий берег", "лівобережна"]},

    # --- More in-city microdistricts spotters name (from real channel feed) ---
    {"name_uk": "Сирець", "name_en": "Syrets", "lat": 50.478, "lon": 30.430,
     "aliases": ["сирця", "сирці"]},
    {"name_uk": "Почайна", "name_en": "Pochaina", "lat": 50.485, "lon": 30.500,
     "aliases": ["почайни"]},
    {"name_uk": "Наталка", "name_en": "Natalka", "lat": 50.522, "lon": 30.508,
     "aliases": []},
    {"name_uk": "Лук'янівка", "name_en": "Lukianivka", "lat": 50.473, "lon": 30.470,
     "aliases": ["лукянівка"]},
    {"name_uk": "Чоколівка", "name_en": "Chokolivka", "lat": 50.425, "lon": 30.440,
     "aliases": []},
    {"name_uk": "Отрадний", "name_en": "Otradnyi", "lat": 50.453, "lon": 30.418,
     "aliases": ["відрадний"]},
    {"name_uk": "Академмістечко", "name_en": "Akademmistechko", "lat": 50.464, "lon": 30.363,
     "aliases": ["академ"]},
    {"name_uk": "Феофанія", "name_en": "Feofaniia", "lat": 50.343, "lon": 30.487,
     "aliases": []},
    {"name_uk": "Березняки", "name_en": "Berezniaky", "lat": 50.418, "lon": 30.600,
     "aliases": []},
    {"name_uk": "Воскресенка", "name_en": "Voskresenka", "lat": 50.470, "lon": 30.590,
     "aliases": []},
    {"name_uk": "Микільська Слобідка", "name_en": "Nykilska Slobidka", "lat": 50.452, "lon": 30.578,
     "aliases": ["слобідка"]},
    {"name_uk": "Вигурівщина", "name_en": "Vyhurivshchyna", "lat": 50.4985, "lon": 30.6018,
     "aliases": []},
    {"name_uk": "Видубичі", "name_en": "Vydubychi", "lat": 50.4147, "lon": 30.568,
     "aliases": []},

    # --- Approach-corridor localities (Kyiv oblast) — targets are tracked here
    #     as they head toward the city; coordinates are approximate. ---
    {"name_uk": "Макарів", "name_en": "Makariv", "lat": 50.463, "lon": 29.812,
     "aliases": ["макарова", "макарову"]},
    {"name_uk": "Буча", "name_en": "Bucha", "lat": 50.545, "lon": 30.213,
     "aliases": ["бучі", "бучу"]},
    {"name_uk": "Ірпінь", "name_en": "Irpin", "lat": 50.522, "lon": 30.250,
     "aliases": ["ірпеня", "ірпені"]},
    {"name_uk": "Гостомель", "name_en": "Hostomel", "lat": 50.575, "lon": 30.266,
     "aliases": ["гостомеля"]},
    {"name_uk": "Бузова", "name_en": "Buzova", "lat": 50.423, "lon": 30.020,
     "aliases": ["бузової", "бузову"]},
    {"name_uk": "Чайки", "name_en": "Chaiky", "lat": 50.393, "lon": 30.302,
     "aliases": ["чайках"]},
    {"name_uk": "Вишневе", "name_en": "Vyshneve", "lat": 50.386, "lon": 30.372,
     "aliases": ["вишневого"]},
    {"name_uk": "Вишгород", "name_en": "Vyshhorod", "lat": 50.585, "lon": 30.490,
     "aliases": ["вишгорода"]},
    {"name_uk": "Бровари", "name_en": "Brovary", "lat": 50.511, "lon": 30.790,
     "aliases": ["броварів", "броварський"]},
    {"name_uk": "Бориспіль", "name_en": "Boryspil", "lat": 50.353, "lon": 30.955,
     "aliases": ["борисполя"]},
    {"name_uk": "Васильків", "name_en": "Vasylkiv", "lat": 50.185, "lon": 30.315,
     "aliases": ["василькова"]},
    {"name_uk": "Обухів", "name_en": "Obukhiv", "lat": 50.107, "lon": 30.615,
     "aliases": ["обухова"]},
    {"name_uk": "Фастів", "name_en": "Fastiv", "lat": 50.078, "lon": 29.910,
     "aliases": ["фастова"]},

    # --- Northern approach corridor (from the live feed) — targets are tracked
    #     here heading down toward the city from the north/north-east. ---
    {"name_uk": "Славутич", "name_en": "Slavutych", "lat": 51.519, "lon": 30.746,
     "aliases": ["славутича", "славутичі"]},
    {"name_uk": "Десна", "name_en": "Desna", "lat": 50.900, "lon": 30.792,
     "aliases": ["десну", "десни"]},
    {"name_uk": "Жукин", "name_en": "Zhukyn", "lat": 50.716, "lon": 30.628,
     "aliases": ["жукина", "жукині"]},
    {"name_uk": "Боденьки", "name_en": "Bodenky", "lat": 50.740, "lon": 30.590,
     "aliases": ["боденьок"]},
    # Chernihiv-oblast highway junction (M-01/M-02) — northern early-warning
    # waypoint named heavily by «Віраж Києва» (kiev_trevoha).
    {"name_uk": "Кіпті", "name_en": "Kipti", "lat": 51.147, "lon": 31.305,
     "aliases": ["кіптях", "кіптів", "кіптями"]},

    # --- Left-bank / northern approach villages named in the feed (Vyshhorod &
    #     Brovary raions), targets tracked here on the way into the city. ---
    {"name_uk": "Осещина", "name_en": "Oseshchyna", "lat": 50.5756, "lon": 30.5478,
     "aliases": []},
    {"name_uk": "Погреби", "name_en": "Pohreby", "lat": 50.5546, "lon": 30.6425,
     "aliases": []},
    {"name_uk": "Зазимʼя", "name_en": "Zazymia", "lat": 50.5739, "lon": 30.6749,
     "aliases": []},
    {"name_uk": "Пухівка", "name_en": "Pukhivka", "lat": 50.5909, "lon": 30.7169,
     "aliases": []},
    {"name_uk": "Рожни", "name_en": "Rozhny", "lat": 50.6707, "lon": 30.741,
     "aliases": []},
    {"name_uk": "Пірнове", "name_en": "Pirnove", "lat": 50.7528, "lon": 30.6686,
     "aliases": []},
    {"name_uk": "Лебедівка", "name_en": "Lebedivka", "lat": 50.7137, "lon": 30.5446,
     "aliases": []},

    # === Approach-corridor ring around Kyiv (proactive coverage so a target
    #     transiting a not-yet-named locality still places). Grouped by threat
    #     axis; coords geocoded via scripts/geocode_localities.py. ===
    # A. North / North-East (main threat axis: Chernihiv obl + Vyshhorod/Brovary).
    {"name_uk": "Козелець", "name_en": "Kozelets", "lat": 50.9161, "lon": 31.1168, "aliases": []},
    # (Остер deliberately omitted: stem "остер" false-matches "остерігайтеся"=beware;
    #  Козелець on the same M-01 axis covers that corridor.)
    {"name_uk": "Калита", "name_en": "Kalyta", "lat": 50.7499, "lon": 31.0249, "aliases": []},
    {"name_uk": "Семиполки", "name_en": "Semypolky", "lat": 50.7235, "lon": 30.9461, "aliases": []},
    {"name_uk": "Літки", "name_en": "Litky", "lat": 50.7069, "lon": 30.743, "aliases": []},
    {"name_uk": "Богданівка", "name_en": "Bohdanivka", "lat": 50.625, "lon": 30.9138, "aliases": []},
    {"name_uk": "Димер", "name_en": "Dymer", "lat": 50.7864, "lon": 30.3039, "aliases": []},
    {"name_uk": "Демидів", "name_en": "Demydiv", "lat": 50.7277, "lon": 30.3306, "aliases": []},
    {"name_uk": "Козаровичі", "name_en": "Kozarovychi", "lat": 50.7561, "lon": 30.3519, "aliases": []},
    {"name_uk": "Катюжанка", "name_en": "Katiuzhanka", "lat": 50.8034, "lon": 30.1338, "aliases": []},
    # B. South-East transit (toward Poltava/Cherkasy; named in feed examples).
    {"name_uk": "Переяслав", "name_en": "Pereiaslav", "lat": 50.0644, "lon": 31.4447, "aliases": []},
    {"name_uk": "Яготин", "name_en": "Yahotyn", "lat": 50.2759, "lon": 31.7635, "aliases": []},
    {"name_uk": "Баришівка", "name_en": "Baryshivka", "lat": 50.3645, "lon": 31.3257, "aliases": []},
    {"name_uk": "Гоголів", "name_en": "Hoholiv", "lat": 50.5127, "lon": 31.0226, "aliases": []},
    {"name_uk": "Требухів", "name_en": "Trebukhiv", "lat": 50.4833, "lon": 30.9011, "aliases": []},
    {"name_uk": "Княжичі", "name_en": "Kniazhychi", "lat": 50.4604, "lon": 30.7862, "aliases": []},
    # C. South / South-West suburbs.
    {"name_uk": "Боярка", "name_en": "Boiarka", "lat": 50.3357, "lon": 30.2848, "aliases": []},
    {"name_uk": "Глеваха", "name_en": "Hlevakha", "lat": 50.2597, "lon": 30.3059, "aliases": []},
    {"name_uk": "Крюківщина", "name_en": "Kriukivshchyna", "lat": 50.3719, "lon": 30.3716, "aliases": []},
    {"name_uk": "Гатне", "name_en": "Hatne", "lat": 50.3585, "lon": 30.3963, "aliases": []},
    {"name_uk": "Українка", "name_en": "Ukrainka", "lat": 50.1537, "lon": 30.7421, "aliases": []},
    {"name_uk": "Ржищів", "name_en": "Rzhyshchiv", "lat": 49.9682, "lon": 31.0412, "aliases": []},
    {"name_uk": "Козин", "name_en": "Kozyn", "lat": 50.229, "lon": 30.6479, "aliases": []},
    # D. North-West (from Belarus / Zhytomyr).
    {"name_uk": "Бородянка", "name_en": "Borodianka", "lat": 50.6438, "lon": 29.9278, "aliases": []},
    {"name_uk": "Немішаєве", "name_en": "Nemishaieve", "lat": 50.568, "lon": 30.1015, "aliases": []},
    {"name_uk": "Клавдієво", "name_en": "Klavdiieve", "lat": 50.5841, "lon": 30.0095,
     "aliases": ["клавдієво-тарасове"]},
    {"name_uk": "Іванків", "name_en": "Ivankiv", "lat": 50.933, "lon": 29.9043, "aliases": []},
    {"name_uk": "Пісківка", "name_en": "Piskivka", "lat": 50.6969, "lon": 29.5931, "aliases": []},
]

# Rough geographic center of Kyiv, for initial map framing.
KYIV_CENTER = {"lat": 50.4501, "lon": 30.5234}


# Seed set of monitored sources. `channel_key` is the Telegram handle we'd
# subscribe to via Telethon later; `trust_weight` biases fusion confidence.
# The aggregator has a low weight because it mostly reposts the others.
SOURCES: list[dict] = [
    {"channel_key": "kyiv_ppo", "name": "Київ ППО монітор", "trust_weight": 1.0},
    {"channel_key": "povitryanka", "name": "Повітряна тривога", "trust_weight": 1.0},
    {"channel_key": "shahed_watch", "name": "Shahed Watch", "trust_weight": 0.8},
    {"channel_key": "aggregator", "name": "Агрегатор (репости)", "trust_weight": 0.4},
]
