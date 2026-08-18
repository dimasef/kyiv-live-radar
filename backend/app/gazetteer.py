from __future__ import annotations

# Seed gazetteer of Kyiv districts and well-known microdistricts.
#
# Coordinates are a single representative point per area (approximate centroid),
# adequate for placing a marker and a coarse movement vector. For real work,
# replace with OSM boundary polygons and use centroid/nearest-edge logic.
#
# `aliases` lists spelling variants / abbreviations that spotters actually use;
# the parser matches against these (case-insensitive, later morphology-aware).

# name_en of the city-wide sentinel "district" (see its entry at the end of the
# list). DistrictMatcher skips this one so a real "київ" never over-matches, and
# ingest attaches city-wide ThreatEvents to it. Referenced here and in ingest.
CITYWIDE_NAME_EN = "Kyiv (citywide)"

# Rough geographic center of Kyiv — initial map framing AND the sentinel
# "district"'s coordinates below (a city-wide threat has to point somewhere).
KYIV_CENTER = {"lat": 50.4501, "lon": 30.5234}

DISTRICTS: list[dict] = [
    # --- 10 administrative raions ---
    {"name_uk": "Голосіївський", "name_en": "Holosiivskyi", "lat": 50.381, "lon": 30.508,
     # "голосіїв" is spelled with ї — its stem doesn't cover the common spotter
     # form "Голосієво" (є, no ї); added explicitly rather than relying on the
     # stemmer to bridge the two spellings. "голос" is the terse callout form
     # ("Голос 🔴") and is WHOLE-WORD-only (_WHOLE_WORD_ALIASES): as a stem it
     # would fire inside "голосно"/"голосування".
     "aliases": ["голосіїв", "голосіївський район", "голосієво", "голос"]},
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
     # "солома"/"соломі"/"на Соломі" — the colloquial short name (stem "солом").
     # Corpus-swept: all 11 "солом…" forms are this raion, no "солома"=straw noise.
     "aliases": ["солом'янка", "солом'янський район", "соломянський", "солома"]},
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
    {"name_uk": "Пуща-Водиця", "name_en": "PushchaVodytsia", "lat": 50.5371, "lon": 30.3564,
     # Called by its first word alone ("Пуща 🔴"). The bare stem is safe: every
     # corpus near-miss is "запущено"/"пуски", which the word-start boundary
     # already blocks.
     # Case forms are listed explicitly: the stem floor keeps "пущ" out (it would
     # fire on "Пущено ракети"), and "пуща"+tail doesn't reach "Пущею"/"Пущі".
     "aliases": ["пуща", "пущі", "пущу", "пущею", "пуща водиця", "пущаводиця"]},
    {"name_uk": "Виноградар", "name_en": "Vynohradar", "lat": 50.500, "lon": 30.415,
     "aliases": ["виноградар"]},
    {"name_uk": "Нивки", "name_en": "Nyvky", "lat": 50.460, "lon": 30.410,
     # "Антонов" = the Antonov plant/aerodrome by Нивки — spotters use it as a
     # landmark for this area ("на нивки антонов", "Нивок (Антонов)"). The
     # street guard keeps "вул. Антоновича" (a downtown street) from matching.
     "aliases": ["нивки", "антонов"]},
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
    # Київська ТЕЦ-5 (Теличка, Голосіївський р-н, правий берег) — a named target.
    # ONLY the numbered forms: a bare "тец" stem would wrongly capture the ТЕЦ-6
    # mentions in the real corpus (a DIFFERENT plant on the left bank/Воскресенка).
    # Hyphen is preserved by normalize(); "тец5" also covers the no-hyphen form,
    # and тэц-* the Russian spelling. name_uk itself yields the "тец-5" stem.
    {"name_uk": "ТЕЦ-5", "name_en": "TETs-5 (CHP-5)", "lat": 50.3942, "lon": 30.5684,
     "aliases": ["тец-5", "тец5", "тэц-5", "тэц5"]},
    # Київська ТЕЦ-6 (Деснянський р-н, лівий берег біля Воскресенки/Троєщини) —
    # a DIFFERENT plant from ТЕЦ-5; the corpus names it ("ТЕЦ-6/Воскресенка").
    # Numbered forms only, same reasoning as ТЕЦ-5.
    {"name_uk": "ТЕЦ-6", "name_en": "TETs-6 (CHP-6)", "lat": 50.5312, "lon": 30.667,
     "aliases": ["тец-6", "тец6", "тэц-6", "тэц6"]},

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
     # "Вишня" — spotter slang for the town mid-salvo ("Вишня!!!"). Corpus-swept:
     # every "вишн…" form in the real feed is this town, zero cherry noise.
     "aliases": ["вишневого", "вишня", "вишню"]},
    {"name_uk": "Вишгород", "name_en": "Vyshhorod", "lat": 50.585, "lon": 30.490,
     "aliases": ["вишгорода"]},
    {"name_uk": "Бровари", "name_en": "Brovary", "lat": 50.511, "lon": 30.790,
     # "Торгмаш" is the plant on Brovary's eastern edge (50.5068, 30.8266) that
     # spotters call targets over. An ALIAS, not its own entry: 2.5 km from the
     # town centroid is inside this map's precision, and sharing the id means a
     # "Торгмаш" callout corroborates a "Бровари" one instead of splitting it.
     "aliases": ["броварів", "броварський", "торгмаш"]},
    {"name_uk": "Бориспіль", "name_en": "Boryspil", "lat": 50.353, "lon": 30.955,
     "aliases": ["борисполя"]},
    {"name_uk": "Васильків", "name_en": "Vasylkiv", "lat": 50.185, "lon": 30.315,
     # "Васік" — spotter slang ("Васік!"); both і/и spellings appear in feeds.
     "aliases": ["василькова", "васік", "васик"]},
    {"name_uk": "Обухів", "name_en": "Obukhiv", "lat": 50.107, "lon": 30.615,
     "aliases": ["обухова"]},
    {"name_uk": "Фастів", "name_en": "Fastiv", "lat": 50.078, "lon": 29.910,
     "aliases": ["фастова"]},
    # 07-18 mass-attack gaps — real sighting callouts with no entry (geocoded
    # via Nominatim, corpus-swept: only target contexts).
    {"name_uk": "Наливайківка", "name_en": "Nalyvaikivka", "lat": 50.484, "lon": 29.711,
     "aliases": ["наливайківку", "наливайківки"]},
    {"name_uk": "Трипілля", "name_en": "Trypillia", "lat": 50.115, "lon": 30.777,
     "aliases": ["трипілля", "трипільськ"]},

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
    # East approach, on the Baryshivka line ("Баришівка/Березань перші в сторону
    # Борисполя"). Stems to "березан", which the March month "березень" (е, not
    # а) never reaches.
    {"name_uk": "Березань", "name_en": "Berezan", "lat": 50.3133, "lon": 31.4689, "aliases": []},
    {"name_uk": "Гоголів", "name_en": "Hoholiv", "lat": 50.5127, "lon": 31.0226, "aliases": []},
    {"name_uk": "Требухів", "name_en": "Trebukhiv", "lat": 50.4833, "lon": 30.9011, "aliases": []},
    {"name_uk": "Княжичі", "name_en": "Kniazhychi", "lat": 50.4604, "lon": 30.7862, "aliases": []},
    # C. South / South-West suburbs.
    {"name_uk": "Боярка", "name_en": "Boiarka", "lat": 50.3357, "lon": 30.2848, "aliases": []},
    {"name_uk": "Глеваха", "name_en": "Hlevakha", "lat": 50.2597, "lon": 30.3059, "aliases": []},
    {"name_uk": "Крюківщина", "name_en": "Kriukivshchyna", "lat": 50.3719, "lon": 30.3716, "aliases": []},
    {"name_uk": "Гатне", "name_en": "Hatne", "lat": 50.3585, "lon": 30.3963, "aliases": []},
    # SW-approach village (Києво-Святошинський) — a recurring reactive-shahed
    # callout ("Білогородка увага по БпЛА", "на Білогородку/Васильків звернув").
    {"name_uk": "Білогородка", "name_en": "Bilohorodka", "lat": 50.3772, "lon": 30.2837, "aliases": []},
    # (Українка deliberately omitted: name collides with "Ukrainka" — a Russian
    #  strategic bomber airbase in Amur Oblast, ~7000km away — that gets named in
    #  Ukrainian-language strategic aviation reports far more often than the Kyiv
    #  suburb does. A real report about Ту-95МС at "аеродром «Українка»" was
    #  mislocalized onto this Kyiv suburb. Same class of bug as Остер/"остерігайтеся".)
    {"name_uk": "Ржищів", "name_en": "Rzhyshchiv", "lat": 49.9682, "lon": 31.0412, "aliases": []},
    {"name_uk": "Козин", "name_en": "Kozyn", "lat": 50.229, "lon": 30.6479, "aliases": []},
    # C-bis. The SOUTHERN staging ring — 2026-08-18 coverage-gap export. Drones
    # loiter and turn over these towns before entering the city, and every
    # callout naming them ("Рокитне/БЦ уважно по двох групах БПЛА", "Райони
    # Миронівки/Таращі/Богуслава уважно по третьому ланцюгу") localized nowhere.
    # Geocoded via scripts/geocode_localities.py, corpus-swept for collisions.
    {"name_uk": "Біла Церква", "name_en": "BilaTserkva", "lat": 49.797, "lon": 30.1158,
     # Space-separated names never match as one stem (see Труханів острів), so
     # the town rides on its second word — gated on a preceding "Біл…" via
     # vocab._ALIAS_PREV_WORD_REQUIRED, or "приліт у церкву" would pin a strike
     # 80 km out of town. "бц" is the spotters' own abbreviation (14 corpus
     # hits, all this town) and is whole-word-only.
     "aliases": ["церкв", "білоцерк", "бц"]},
    {"name_uk": "Рокитне", "name_en": "Rokytne", "lat": 49.6867, "lon": 30.473, "aliases": []},
    {"name_uk": "Тараща", "name_en": "Tarashcha", "lat": 49.5555, "lon": 30.5023, "aliases": []},
    {"name_uk": "Богуслав", "name_en": "Bohuslav", "lat": 49.5476, "lon": 30.8733, "aliases": []},
    {"name_uk": "Миронівка", "name_en": "Myronivka", "lat": 49.6583, "lon": 30.9825, "aliases": []},
    {"name_uk": "Кагарлик", "name_en": "Kaharlyk", "lat": 49.8651, "lon": 30.8227, "aliases": []},
    # D. North-West (from Belarus / Zhytomyr).
    {"name_uk": "Бородянка", "name_en": "Borodianka", "lat": 50.6438, "lon": 29.9278, "aliases": []},
    {"name_uk": "Немішаєве", "name_en": "Nemishaieve", "lat": 50.568, "lon": 30.1015, "aliases": []},
    {"name_uk": "Клавдієво", "name_en": "Klavdiieve", "lat": 50.5841, "lon": 30.0095,
     "aliases": ["клавдієво-тарасове"]},
    {"name_uk": "Іванків", "name_en": "Ivankiv", "lat": 50.933, "lon": 29.9043, "aliases": []},
    {"name_uk": "Пісківка", "name_en": "Piskivka", "lat": 50.6969, "lon": 29.5931, "aliases": []},
    # West approach (Fastiv raion, on the Zhytomyr axis). Nominative stems to
    # "бишів", but the oblique cases carry the і→е alternation (Бишева/Бишеві →
    # stem "бишев"), so alias both — same pattern as Макарів's genitive aliases.
    # Corpus-swept: every "биш…" hit is this toponym, zero collisions.
    {"name_uk": "Бишів", "name_en": "Byshiv", "lat": 50.2666, "lon": 29.8869,
     "aliases": ["бишева", "бишеві"]},

    # === In-city micro-neighborhoods/landmarks + a few more approach-corridor
    #     villages, found via eval/ground_truth_sessions.json (2026-07-09
    #     gazetteer-gap analysis on real backfilled feed data). Geocoded via
    #     scripts/geocode_localities.py; false-positive-swept against the same
    #     871-message real corpus before commit (see memory / commit message).
    # E. In-city Kyiv neighborhoods/landmarks.
    {"name_uk": "Труханів острів", "name_en": "TrukhanivIsland", "lat": 50.4852, "lon": 30.5484,
     "aliases": ["труханів", "труханова"]},
    {"name_uk": "Гідропарк", "name_en": "Hidropark", "lat": 50.4385, "lon": 30.5796, "aliases": []},
    {"name_uk": "Контрактова площа", "name_en": "KontraktovaSquare", "lat": 50.4627, "lon": 30.5184,
     "aliases": ["контрактова"]},
    {"name_uk": "Липки", "name_en": "Lypky", "lat": 50.4449, "lon": 30.5331, "aliases": []},
    {"name_uk": "Клов", "name_en": "Klov", "lat": 50.44, "lon": 30.5346, "aliases": []},
    {"name_uk": "Куренівка", "name_en": "Kurenivka", "lat": 50.4885, "lon": 30.4703, "aliases": []},
    {"name_uk": "Пріорка", "name_en": "Priorka", "lat": 50.5047, "lon": 30.4525, "aliases": []},
    {"name_uk": "Мінський масив", "name_en": "MinskyiMasyv", "lat": 50.5192, "lon": 30.4619,
     "aliases": ["мінський"]},
    {"name_uk": "Шулявка", "name_en": "Shuliavka", "lat": 50.45, "lon": 30.444, "aliases": []},
    {"name_uk": "Теличка", "name_en": "Telychka", "lat": 50.3956, "lon": 30.5711, "aliases": []},
    {"name_uk": "Харківський масив", "name_en": "KharkivskyiMasyv", "lat": 50.4118, "lon": 30.6581,
     "aliases": ["харківський"]},
    # "ПОХ" = Позняки-Осокорки-Харківський, the spotters' name for the one
    # left-bank strip those three massifs form. Deliberately ONE entry at their
    # centroid, not the alias on all three: DistrictMatcher keeps a single hit
    # per match offset, and three ids for one callout would read as three
    # simultaneous targets (see rules._multi_targets). Whole-word only — as a
    # stem it would fire inside "похолодання"/"поховались"/"походу".
    {"name_uk": "Позняки-Осокорки-Харківський", "name_en": "PoznyakyOsokorkyKharkivskyi",
     "lat": 50.4029, "lon": 30.6363, "aliases": ["пох"]},
    {"name_uk": "Русанівські сади", "name_en": "RusanivskiSady", "lat": 50.4744, "lon": 30.5753,
     "aliases": []},
    {"name_uk": "Нижні Сади", "name_en": "NyzhniSady", "lat": 50.3682, "lon": 30.6076, "aliases": []},
    {"name_uk": "Лісовий масив", "name_en": "LisovyiMasyv", "lat": 50.4746, "lon": 30.6302,
     # The two-word name can't match on its own (its stem loses the space);
     # "лісовий" is the single-word form spotters actually inflect ("на лісовий
     # масив"). Corpus-swept: every "лісов…" hit is this neighbourhood.
     "aliases": ["лісовий"]},
    {"name_uk": "Жуляни", "name_en": "Zhuliany", "lat": 50.3928, "lon": 30.4422, "aliases": []},
    {"name_uk": "Биківня", "name_en": "Bykivnia", "lat": 50.476, "lon": 30.6705, "aliases": []},
    {"name_uk": "Вокзальна площа", "name_en": "VokzalnaSquare", "lat": 50.4406, "lon": 30.4901,
     "aliases": ["вокзальна"]},
    # (Наливайківка deliberately omitted: the in-city Sviatoshynskyi neighborhood
    #  isn't resolvable via Nominatim — every query variant matched a same-named
    #  but different village in Bucha raion, ~45km away. Same class of issue as
    #  Заспа. Sky Mall / Калинівка / Новосілки: not found at all, skipped.)

    # F. Villages/settlements near Kyiv, real sighting locations from the feed.
    {"name_uk": "Ворзель", "name_en": "Vorzel", "lat": 50.5457, "lon": 30.1563, "aliases": []},
    {"name_uk": "Воропаїв", "name_en": "Voropaiv", "lat": 50.7692, "lon": 30.6582, "aliases": []},
    {"name_uk": "Вишеньки", "name_en": "Vyshenky", "lat": 50.3043, "lon": 30.7147, "aliases": []},
    # Dnipro-bank village south of Boryspil, called in as targets follow the
    # river ("Кийлів район. Фіксується один, другий зник").
    {"name_uk": "Кийлів", "name_en": "Kyiliv", "lat": 50.1485, "lon": 30.8845, "aliases": []},
    {"name_uk": "Гнідин", "name_en": "Hnidyn", "lat": 50.3287, "lon": 30.7058, "aliases": []},
    {"name_uk": "Горенка", "name_en": "Horenka", "lat": 50.5596, "lon": 30.3123, "aliases": []},
    {"name_uk": "Хотянівка", "name_en": "Khotianivka", "lat": 50.5959, "lon": 30.5668, "aliases": []},
    {"name_uk": "Чабани", "name_en": "Chabany", "lat": 50.3414, "lon": 30.4271, "aliases": []},
    # "Щасливе" also means "happy" (щасливий/-а/-е) — a very common Ukrainian
    # adjective/farewell word ("будьте щасливі"). High collision risk, same
    # class as Остер; kept ONLY because the false-positive sweep (see commit)
    # found zero bad matches in the real corpus — revisit if that changes.
    {"name_uk": "Щасливе", "name_en": "Shchaslyve", "lat": 50.3782, "lon": 30.7913, "aliases": []},
    {"name_uk": "Згурівка", "name_en": "Zghurivka", "lat": 50.4951, "lon": 31.7692, "aliases": []},
    # Southern / SW approach-corridor villages — real 2026-07-31 feed gaps (a
    # reactive-Shahed incursion named every one of these; each was lost as
    # "без району" or "не про загрозу"). Coords via geocode_localities.py
    # (Nominatim) unless noted.
    {"name_uk": "Ходосівка", "name_en": "Khodosivka", "lat": 50.2728, "lon": 30.5221, "aliases": []},
    # Конча-Заспа: the hyphenated stem ("конча-засп") only matched the hyphenated
    # spelling, and _stem() strips spaces, so a multiword alias can never match
    # spaced text — spotters write "Конча Заспа" too and both forms were lost
    # (2026-08-16 raw 6278/6237). Fixed with the "конча" alias (stem "конч"),
    # which covers every spelling: 4 corpus hits, all this place, zero collisions
    # in 4243 unique messages.
    # Bare "Заспа" is still NOT an alias — its stem "засп" is corpus-clean at
    # 14/15 but the 15th is "заспокоїтись", and a different village "Заспа"
    # ~45 km away breaks Nominatim (see the omitted-Заспа note above).
    {"name_uk": "Конча-Заспа", "name_en": "KonchaZaspa", "lat": 50.3007, "lon": 30.5765,
     "aliases": ["конча"]},
    # "Рогозів" stem "рогоз" also matches the plant рогоза (cattail); the FP
    # sweep of the real corpus found zero such uses — revisit if that changes
    # (same treatment as Щасливе).
    {"name_uk": "Рогозів", "name_en": "Rohoziv", "lat": 50.2339, "lon": 31.055, "aliases": []},
    # "Пирогів" stem "пирог" collides with пироги/пиріг (pies); the corpus sweep
    # found only the museum «Пирогів» (relevant), zero food mentions — Щасливе-
    # class risk, revisit if that changes.
    {"name_uk": "Пирогів", "name_en": "Pyrohiv", "lat": 50.3545, "lon": 30.5145, "aliases": []},
    # Чапаївка (Holosiivskyi urochyshche near Пирогів). Point HAND-SET: Nominatim
    # resolves the name to a homonym near Kryvyi Rih (~350 km) and a Kyiv-bounded
    # query finds nothing — same "not reliably geocodable" class as Наливайківка.
    # Stem "чапаївк" is specific, no collision.
    {"name_uk": "Чапаївка", "name_en": "Chapaivka", "lat": 50.343, "lon": 30.522, "aliases": []},
    # Віта-Поштова: hyphenated compound only (stem "віта-поштов"). Bare "Віта" is
    # deliberately NOT an alias — its stem "віта" collides with вітаю/вітання.
    {"name_uk": "Віта-Поштова", "name_en": "VitaPoshtova", "lat": 50.3197, "lon": 30.3809, "aliases": []},
    # Трипільська ТЕС (Українка, Обухівський р-н — south of Kyiv, область) — a
    # major, repeatedly-targeted station; the corpus names the DIRECTION ("у бік
    # Трипілля"). The village of Трипілля is ~2 km away — same target cluster,
    # so the "трипіл" stem covers both. Bare "тес" is NOT an alias (it collides
    # with тест/тесля/… — a short, common substring); the "трипіл" stem is specific.
    {"name_uk": "Трипільська ТЕС", "name_en": "Trypilska TES", "lat": 50.1333, "lon": 30.75,
     "aliases": ["трипілля", "трипільська", "трипіл"]},
    # Kyiv Reservoir (north of the city near Vyshhorod) — real spotters say
    # just "водосховище" (bare word), never the full official name, hence the
    # alias. "водосховище" is generic (there are other reservoirs downstream
    # on the Dnipro — Канівське/Каховське etc.), but swept the full real
    # corpus first: only 2 occurrences, both unambiguously this one (one
    # explicitly ties it to Оболонь, a Kyiv district right next to it).
    {"name_uk": "Київське водосховище", "name_en": "KyivReservoir", "lat": 50.9218, "lon": 30.5047,
     "aliases": ["водосховище"]},
    # The "sea" — how spotters call the Kyiv Reservoir's NEAR-northern approach
    # (Вишгород dam → Жукин sector), the corridor targets from Чернігівщина ride
    # into the city ("3х реактивних БПЛА в район моря", "на море ракети,
    # Вишгород та північ Києва"). A SEPARATE, nearer point than KyivReservoir
    # above (50.92 is ~40km north — the far water; "район моря" operationally
    # means the near edge, always paired with готовність Вишгород/Оболонь/Троя).
    # Aliases carry море AND its genitive/locative моря/морі: the stem matcher
    # keeps each inflection distinct (a 4-char stem can't strip below 4), and a
    # bare "мор" stem would collide with морально/мороз. FP sweep of the real
    # corpus: море/моря/морі cleanly hit the 8 genuine spotter calls; the ONLY
    # false hit is "Каспійського/Чорного моря" (bomber launch-zones in strategic
    # reports) — rejected by matcher._is_foreign_sea (a foreign-sea adjective
    # right before the token), NOT by dropping the alias.
    {"name_uk": "Район моря", "name_en": "KyivSeaApproach", "lat": 50.66, "lon": 30.52,
     "aliases": ["море", "моря", "морі"]},

    # --- Far-northern approach: drones from Belarus enter the oblast over the
    # exclusion zone, so these are the first Kyiv-relevant fix on that corridor
    # (2026-08-17 feed gaps — every mention was lost as "не про загрозу").
    # Coords via geocode_localities.py (Nominatim).
    # "ЧЗВ" is how spotters always write it (8 real messages: "2 в ЧЗВ", "Їх три,
    # летять на ЧЗВ", "через ЧЗВ пара на захід йде"). It is 3 chars, BELOW the
    # matcher's stem floor, so it needs vocab._WHOLE_WORD_ALIASES to match at all
    # — as a whole word, never inside another word. "чорнобиль" carries the
    # spelled-out form ("в район Чорнобиля", "вздовж Чорнобильскої зони"); all 3
    # of its corpus hits are geographic. Bare "зона" is NOT an alias (it is a
    # common noun); the multiword name is a label only, since _stem() strips
    # spaces (same convention as "Київське водосховище").
    {"name_uk": "Чорнобильська зона", "name_en": "ChornobylZone", "lat": 51.2705, "lon": 30.2196,
     "aliases": ["чзв", "чорнобиль"]},
    # Страхолісся (Іванківська громада) — on the same corridor between Іванків
    # and the reservoir. Stem "страхолісс" is 10 chars and distinctive: 1 corpus
    # hit, the sighting itself.
    {"name_uk": "Страхолісся", "name_en": "Strakholissia", "lat": 51.0755, "lon": 30.395,
     "aliases": []},

    # Sentinel "district" for CITY-WIDE threats — a strike aimed at the city as
    # a whole ("ціль на місто", "балістика на Київ") that no spotter localizes
    # to a raion. It is NOT a real matchable place: DistrictMatcher skips it (its
    # name would otherwise over-match every "у Києві…" mention), and the LLM
    # fallback never sees it. It exists only so a city-wide ThreatEvent has a
    # valid point (city centre) and a display name; the map renders such threats
    # as a banner, not this point. Detection is the parser's `citywide` flag.
    {"name_uk": "Київ", "name_en": CITYWIDE_NAME_EN,
     "lat": KYIV_CENTER["lat"], "lon": KYIV_CENTER["lon"], "aliases": []},
]


# Seed set of monitored sources. `channel_key` is the Telegram handle we'd
# subscribe to via Telethon later; `trust_weight` biases fusion confidence.
# The aggregator has a low weight because it mostly reposts the others.
SOURCES: list[dict] = [
    {"channel_key": "kyiv_ppo", "name": "Київ ППО монітор", "trust_weight": 1.0},
    {"channel_key": "povitryanka", "name": "Повітряна тривога", "trust_weight": 1.0},
    {"channel_key": "shahed_watch", "name": "Shahed Watch", "trust_weight": 0.8},
    {"channel_key": "aggregator", "name": "Агрегатор (репости)", "trust_weight": 0.4},
    # role='alert' -> routed through alert_parser.py, not the spotter parser
    # (see telegram_listener.py). Dormant unless ALERT_CHANNELS names it.
    # trust_weight is unused for an alert-role source (spotter fusion only).
    {"channel_key": "KyivCityOfficial", "name": "КМДА – офіційний канал",
     "trust_weight": 1.0, "role": "alert"},
]
