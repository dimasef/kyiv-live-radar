from __future__ import annotations

# Seed gazetteer of Kyiv districts and well-known microdistricts.
#
# Coordinates are a single representative point per area (approximate centroid),
# adequate for placing a marker and a coarse movement vector. For real work,
# replace with OSM boundary polygons and use centroid/nearest-edge logic.
#
# `aliases` lists spelling variants / abbreviations that spotters actually use;
# the parser matches against these (case-insensitive, later morphology-aware).
#
# `region` (see models.REGIONS) is optional and defaults to "kyiv" — write it out
# only for entries outside м. Київ + Київська обл. It decides which track pool a
# sighting joins, so it must follow real geography, not "which channel usually
# reports it".

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
    # --- 08-20 feed analysis. These three cost far more than their own messages:
    # each was the FIRST post of a reply chain on the threading channel, so with
    # no event to hang off, every follow-up reply started a track of its own.
    # «Деміївка 🔴.» → «Совки/Солома/Жуляни 🔴.» → «Чабани/Боярка 🔴.» was one
    # drone crossing the city as three unrelated tracks. A missing root is the
    # most expensive kind of gap there is.
    {"name_uk": "Деміївка", "name_en": "Demiivka", "lat": 50.404, "lon": 30.5159,
     "aliases": []},
    {"name_uk": "Іподром", "name_en": "Ippodrom", "lat": 50.3766, "lon": 30.469,
     "aliases": []},
    # "совк" is a 4-letter stem and those are the ones that bite (see Остер,
    # Заспа). Swept: 1 hit in 5000+ messages, the callout itself, and none of the
    # words it could have collided with ("совковий") appear at all.
    {"name_uk": "Совки", "name_en": "Sovky", "lat": 50.4062, "lon": 30.4852,
     "aliases": []},
    # «Центр» is WHOLE-WORD ONLY (see vocab._WHOLE_WORD_ALIASES) — its stem is a
    # prefix of an adjectival family the spotters never mean: "центральній",
    # "центрального", "центрів", and inside a word "укргідрометцентр",
    # "концентрацію". Swept: 37 standalone uses, ~30 of them live callouts
    # («центр 🔴!», «на центр летить! в укриття!», «2 курсом на центр») — it is
    # one of the most-named places in the whole corpus and had no entry at all.
    # The rest are prose the message-level suppressors already reject.
    # Point: Хрещатик, which is what a spotter means by "центр".
    {"name_uk": "Центр", "name_en": "KyivCentre", "lat": 50.4472, "lon": 30.5229,
     "aliases": ["центру", "центрі"]},
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
    # Славутич is administratively KYIV oblast but sits 150 km north, an enclave
    # inside Чернігівщина, and it is the northern channel's single most-named
    # place (26 events in two days). Region here is not an administrative label —
    # it decides which track pool a sighting joins and which region the event
    # feed files it under, so leaving it "kyiv" put a target 150 km away into the
    # Kyiv pool and past the feed's region filter. Its geography is what matters
    # for both, and that is northern.
    {"name_uk": "Славутич", "name_en": "Slavutych", "lat": 51.519, "lon": 30.746,
     "region": "chernihiv", "aliases": ["славутича", "славутичі"]},
    # смт Десна is in Козелецький р-н CHERNIHIV oblast, not Kyiv — it was added
    # as a Kyiv early-warning waypoint before regions existed. Kyiv channels
    # still name it (it is on their northern corridor); the region only decides
    # which track pool a sighting there joins.
    {"name_uk": "Десна", "name_en": "Desna", "lat": 50.9248, "lon": 30.773,
     "region": "chernihiv", "aliases": ["десну", "десни"]},
    {"name_uk": "Жукин", "name_en": "Zhukyn", "lat": 50.716, "lon": 30.628,
     "aliases": ["жукина", "жукині"]},
    {"name_uk": "Боденьки", "name_en": "Bodenky", "lat": 50.740, "lon": 30.590,
     "aliases": ["боденьок"]},
    # Chernihiv-oblast highway junction (M-01/M-02) — northern early-warning
    # waypoint named heavily by «Віраж Києва» (kiev_trevoha).
    {"name_uk": "Кіпті", "name_en": "Kipti", "lat": 51.147, "lon": 31.305,
     "region": "chernihiv", "aliases": ["кіптях", "кіптів", "кіптями"]},

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
    # Кіпті/Козелець sit in CHERNIHIV oblast — they were added as Kyiv early-warning
    # waypoints before regions existed. Labelled truthfully now: a target seen only
    # there is northern approach, not Kyiv activity, so it must not raise a Kyiv
    # attack banner or count in the journal until it crosses the border.
    {"name_uk": "Козелець", "name_en": "Kozelets", "lat": 50.9161, "lon": 31.1168,
     "region": "chernihiv", "aliases": []},
    # (Остер deliberately omitted: stem "остер" false-matches "остерігайтеся"=beware;
    #  Козелець on the same M-01 axis covers that corridor.)
    {"name_uk": "Калита", "name_en": "Kalyta", "lat": 50.7499, "lon": 31.0249, "aliases": []},
    {"name_uk": "Семиполки", "name_en": "Semypolky", "lat": 50.7235, "lon": 30.9461, "aliases": []},
    {"name_uk": "Літки", "name_en": "Litky", "lat": 50.7069, "lon": 30.743, "aliases": []},
    {"name_uk": "Богданівка", "name_en": "Bohdanivka", "lat": 50.625, "lon": 30.9138, "aliases": []},
    {"name_uk": "Димер", "name_en": "Dymer", "lat": 50.7864, "lon": 30.3039, "aliases": []},
    # The alias is the entry's whole point: the matcher stems a multi-word name
    # with the spaces removed ("великадимерк"), which never appears in text, so
    # the two-word form alone would match nothing. "димерка" is what spotters
    # actually write ("Димерка/Бровари 🔴", 20 real messages), and until this
    # entry existed every one of them landed on Димер — 47 km away on the far
    # side of Kyiv. See the twin Чернігівська Димерка entry below for why both
    # are needed.
    {"name_uk": "Велика Димерка", "name_en": "Velyka Dymerka", "lat": 50.5914, "lon": 30.9016,
     "aliases": ["димерка"]},
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


    # --- G. Чернігівщина: the northern approach corridor -------------------
    # Mined from 300 real messages of @chyste_nebochernigv (32 h,
    # eval/chyste_nebochernigv_sample.jsonl) — every name here is one that
    # channel actually calls out. Coordinates verified to sit in Чернігівська
    # область (several of these names also exist in the Chornobyl zone).
    # They take that feed's rule coverage from 20% to 72%, and the number of
    # messages naming TWO places (i.e. drawing a vector) from 2 to 58.
    #
    # `region: "chernihiv"` keeps them in the northern track pool: they are
    # early warning, not Kyiv activity, and the journal/statistics ignore them
    # until a track crosses into Київщина (see domain/tracking.py).
    #
    # Rejected here: «Берелівка» (Nominatim has no point), «Городище» (several
    # in the oblast, none clearly on the corridor), «Полісся» (used both as the
    # village and as the region-wide noun).
    {"name_uk": "Любеч", "name_en": "Liubech", "lat": 51.7005, "lon": 30.6587,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Остер", "name_en": "Oster", "lat": 50.9508, "lon": 30.8782,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Городня", "name_en": "Horodnia", "lat": 51.8915, "lon": 31.5955,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Гончарівське", "name_en": "Honcharivske", "lat": 51.299, "lon": 30.9276,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Хрінівка", "name_en": "Khrinivka", "lat": 52.0691, "lon": 31.8401,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Ріпки", "name_en": "Ripky", "lat": 51.8036, "lon": 31.0931,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Сеньківка", "name_en": "Senkivka", "lat": 52.1064, "lon": 31.7809,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Будище", "name_en": "Budyshche", "lat": 51.3024, "lon": 30.77,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Седнів", "name_en": "Sedniv", "lat": 51.6421, "lon": 31.5624,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Олешня", "name_en": "Oleshnia", "lat": 51.9459, "lon": 31.1714,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Морівськ", "name_en": "Morivsk", "lat": 51.0923, "lon": 30.8675,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Лошакова Гута", "name_en": "Loshakova Huta", "lat": 51.0291, "lon": 30.656,
     "region": "chernihiv", "aliases": ["лошакова", "лошакову"]},
    {"name_uk": "Василева Гута", "name_en": "Vasyleva Huta", "lat": 51.288, "lon": 30.7064,
     "region": "chernihiv", "aliases": ["василева", "василеву"]},
    {"name_uk": "Чудівка", "name_en": "Chudivka", "lat": 51.8765, "lon": 30.9985,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Хотівля", "name_en": "Khotivlia", "lat": 51.9585, "lon": 31.5016,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Сорокошичі", "name_en": "Sorokoshychi", "lat": 51.1916, "lon": 30.6344,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Носівка", "name_en": "Nosivka", "lat": 50.9378, "lon": 31.5812,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Ловинь", "name_en": "Lovyn", "lat": 51.8908, "lon": 31.1857,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Косачівка", "name_en": "Kosachivka", "lat": 51.1019, "lon": 30.6453,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Гірськ", "name_en": "Hirsk", "lat": 52.0186, "lon": 31.8535,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Грабів", "name_en": "Hrabiv", "lat": 51.8395, "lon": 30.9721,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Боровики", "name_en": "Borovyky", "lat": 51.2962, "lon": 30.7339,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Старосілля", "name_en": "Starosillia", "lat": 52.01, "lon": 31.6259,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Рівнопілля", "name_en": "Rivnopillia", "lat": 51.6067, "lon": 31.2331,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Рудня", "name_en": "Rudnia", "lat": 51.5677, "lon": 30.733,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Отрохи", "name_en": "Otrokhy", "lat": 51.1026, "lon": 30.8204,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Олишівка", "name_en": "Olyshivka", "lat": 51.2179, "lon": 31.3299,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Ніжин", "name_en": "Nizhyn", "lat": 51.0465, "lon": 31.8806,
     "region": "chernihiv", "aliases": []},
    # Bare "новгород" is how the channel shortens it («з сумської на новгород»).
    # The hyphenated stem cannot reach that form, and the Russian Новгороди never
    # appear on this feed — swept, both corpus hits are this town.
    {"name_uk": "Новгород-Сіверський", "name_en": "Novhorod-Siverskyi", "lat": 52.0043, "lon": 33.278,
     "region": "chernihiv", "aliases": ["новгород-сіверськ", "новгород"]},
    # --- 08-20 gap analysis of the northern channel. The first two are plain
    # coverage: "БпЛА біля Рогівки" resolved to nothing at all, which also broke
    # the reply chain hanging off it — the follow-up "На Новгород-сіверський"
    # replied to a message that had produced no event, so it opened its own track
    # and inherited a type from an unrelated target 103 km away.
    {"name_uk": "Рогівка", "name_en": "Rohivka", "lat": 52.1603, "lon": 33.3102,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Леньків", "name_en": "Lenkiv", "lat": 52.0731, "lon": 33.2637,
     "region": "chernihiv", "aliases": []},
    # The next three are the opposite problem — a northern toponym with NO entry
    # of its own, captured by a Kyiv-oblast stem, which drew a target reported
    # 130 km away on the edge of the city:
    #   "Є пироговці" / "Пирогівці є" -> Пирогів (the Kyiv museum), stem "пирог"
    #   "Понори на Обухове"           -> Обухів,  via its "обухова" alias
    # Пирогівці wins on specificity ("пирогівц" is longer than "пирог"); Обухове
    # ties with Обухів's alias, so `prefer_region` decides — and that is correct
    # both ways, since "Район Обухова" (16 real messages, all Kyiv channels) must
    # keep resolving to Обухів.
    # The alias covers the і↔о alternation: both real messages are the same
    # place two days apart, spelled "Пирогівці є" and "Є пироговці". The stemmer
    # only strips case ENDINGS, so it cannot bridge a vowel change inside the
    # root — without this alias the о-form still fell through to "пирог".
    {"name_uk": "Пирогівці", "name_en": "Pyrohivtsi", "lat": 50.6205, "lon": 32.3506,
     "region": "chernihiv", "aliases": ["пироговці"]},
    {"name_uk": "Обухове", "name_en": "Obukhove", "lat": 50.8483, "lon": 33.0297,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Понори", "name_en": "Ponory", "lat": 50.9264, "lon": 33.1148,
     "region": "chernihiv", "aliases": []},
    # Понорниця is here BECAUSE of Понори: its stem "понор" is a prefix of it, so
    # without an entry of its own "На понорницю" / "Понорниця на Корюківку" would
    # have been pinned on a village 90 km south. Found by the corpus sweep, which
    # is the whole reason that sweep is mandatory before adding a short stem.
    {"name_uk": "Понорниця", "name_en": "Ponornytsia", "lat": 51.7205, "lon": 32.844,
     "region": "chernihiv", "aliases": []},
    # Димерка/Велика Димерка are true homonyms across the oblast border, exactly
    # the case `prefer_region` exists for. The sweep is what turned this from a
    # one-message fix into a real one: 20 corpus messages say "Димерка", ALL of
    # them Kyiv channels pairing it with Бровари ("Димерка/Бровари 🔴"), i.e. the
    # Kyiv-oblast Велика Димерка — and every one of them was resolving to Димер
    # (Вишгородський р-н), 47 km away on the wrong side of the city, because
    # "димер" was the only stem that matched. Adding the northern one alone would
    # have hijacked all 20; adding both, each channel now gets its own.
    {"name_uk": "Димерка", "name_en": "Dymerka", "lat": 51.0699, "lon": 31.0659,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Мрин", "name_en": "Mryn", "lat": 51.0544, "lon": 31.5414,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Мощенка", "name_en": "Moshchenka", "lat": 52.0302, "lon": 31.7395,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Куликівка", "name_en": "Kulykivka", "lat": 51.3736, "lon": 31.6456,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Кратинь", "name_en": "Kratyn", "lat": 51.7806, "lon": 30.8425,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Вертіївка", "name_en": "Vertiivka", "lat": 51.1637, "lon": 31.8483,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Борзна", "name_en": "Borzna", "lat": 51.2534, "lon": 32.4263,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Бобровиця", "name_en": "Bobrovytsia", "lat": 50.7415, "lon": 31.3861,
     "region": "chernihiv", "aliases": []},
    # Second Chernihiv sweep (2026-08-20). Mined from the SHORT callouts of
    # @chyste_nebochernigv that still localized nowhere — the eastern half of
    # the oblast (Прилуки/Бахмач/Борзна) was thin, while the north-western
    # corridor was already covered. This is also the biggest single class of
    # wasted LLM calls: the model is handed an enum of known ids, so a village
    # missing from it is a call that can only come back empty.
    #
    # Rejected here: «Тростянка» and «Дмитрівка» (Nominatim returns several in
    # the oblast, none clearly the one the channel means), «летовище» (the
    # Nizhyn airfield — a common noun, and local airfield defence is not this
    # map's business), «Гути» (collides with the two Гута entries above).
    {"name_uk": "Дідівці", "name_en": "Didivtsi", "lat": 50.5848, "lon": 32.4758,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Голубівка", "name_en": "Holubivka", "lat": 50.5581, "lon": 32.492,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Плиски", "name_en": "Plysky", "lat": 51.1133, "lon": 32.4311,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Талалаївка", "name_en": "Talalaivka", "lat": 50.8317, "lon": 33.1344,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Вербівка", "name_en": "Verbivka", "lat": 52.0257, "lon": 31.2314,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Бахмач", "name_en": "Bakhmach", "lat": 51.1827, "lon": 32.8291,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Ряшки", "name_en": "Riashky", "lat": 50.6997, "lon": 32.5604,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Мньов", "name_en": "Mnov", "lat": 51.4531, "lon": 30.656,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Срібне", "name_en": "Sribne", "lat": 50.6616, "lon": 32.9174,
     "region": "chernihiv", "aliases": []},
    # «Короп» is a prefix of «Коропʼє», a different village 150 km away that the
    # same channel also calls out — so the two ship together, and the
    # longest-matched-stem rule in matcher.find keeps them apart. Adding the
    # town alone would have pinned every Коропʼє sighting onto Короп.
    {"name_uk": "Короп", "name_en": "Korop", "lat": 51.5671, "lon": 32.9521,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Коропʼє", "name_en": "Koropie", "lat": 51.0278, "lon": 30.8336,
     "region": "chernihiv", "aliases": ["коропє"]},
    {"name_uk": "Оленівка", "name_en": "Olenivka", "lat": 51.2557, "lon": 32.3019,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Форостовичі", "name_en": "Forostovychi", "lat": 52.0203, "lon": 33.1129,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Тужар", "name_en": "Tuzhar", "lat": 51.1698, "lon": 30.6412,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Смолянка", "name_en": "Smolianka", "lat": 51.2456, "lon": 31.4603,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Рудка", "name_en": "Rudka", "lat": 51.5718, "lon": 31.1218,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Прилуки", "name_en": "Pryluky", "lat": 50.5951, "lon": 32.3867,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Пилипча", "name_en": "Pylypcha", "lat": 51.8689, "lon": 31.0374,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Петрушин", "name_en": "Petrushyn", "lat": 51.6486, "lon": 31.3503,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Льгів", "name_en": "Lhiv", "lat": 51.4943, "lon": 31.1476,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Дроздовиця", "name_en": "Drozdovytsia", "lat": 51.9578, "lon": 31.4151,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Диханівка", "name_en": "Dykhanivka", "lat": 51.9512, "lon": 31.3931,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Басань", "name_en": "Basan", "lat": 50.5728, "lon": 31.5184,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Автуничі", "name_en": "Avtunychi", "lat": 52.0282, "lon": 31.653,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Михайло-Коцюбинське", "name_en": "Mykhailo-Kotsiubynske", "lat": 51.4502, "lon": 31.0793,
     "region": "chernihiv", "aliases": ["коцюбинське"]},
    {"name_uk": "Чернігів", "name_en": "Chernihiv", "lat": 51.4941, "lon": 31.2943,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Сновськ", "name_en": "Snovsk", "lat": 51.8188, "lon": 31.9449,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Корюківка", "name_en": "Koriukivka", "lat": 51.7745, "lon": 32.2513,
     "region": "chernihiv", "aliases": []},
    # Four letters, so the stemmer refuses to strip the ending (it will not cut
    # below four characters) and the stem stays the NOMINATIVE — «на сосницю
    # мену» and «район мени» both missed. The oblique forms have to be spelled
    # out as aliases. Checked the whole gazetteer: this is the only entry short
    # enough to land in that trap.
    {"name_uk": "Мена", "name_en": "Mena", "lat": 51.5228, "lon": 32.2164,
     "region": "chernihiv", "aliases": ["мену", "мени"]},
    # 08-20: both are chain roots the northern channel opened with.
    {"name_uk": "Лосинівка", "name_en": "Losynivka", "lat": 50.8422, "lon": 31.917,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Сосниця", "name_en": "Sosnytsia", "lat": 51.5245, "lon": 32.5029,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Березна", "name_en": "Berezna", "lat": 51.5779, "lon": 31.7903,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Чемер", "name_en": "Chemer", "lat": 51.1002, "lon": 31.2122,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Кукшин", "name_en": "Kukshyn", "lat": 51.1661, "lon": 31.6523,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Борсуків", "name_en": "Borsukiv", "lat": 51.0995, "lon": 30.976,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Зруб", "name_en": "Zrub", "lat": 51.1357, "lon": 31.6772,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Хоробичі", "name_en": "Khorobychi", "lat": 52.0255, "lon": 31.5118,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Тупичів", "name_en": "Tupychiv", "lat": 51.7686, "lon": 31.436,
     "region": "chernihiv", "aliases": []},

    # Homonyms across the oblast border. Each of these names a village in BOTH
    # Київська and Чернігівська область, and the text never says which — the
    # reporting channel's region does (DistrictMatcher(prefer_region=...)).
    # «Лебедівка на гончарівське» from a northern spotter is the one 3 km from
    # Гончарівське, not the Vyshhorod-district village 60 km away.
    {"name_uk": "Лебедівка", "name_en": "LebedivkaCH", "lat": 51.2309, "lon": 30.9683,
     "region": "chernihiv", "aliases": []},
    {"name_uk": "Рокитне", "name_en": "RokytneCH", "lat": 50.5673, "lon": 31.3601,
     "region": "chernihiv", "aliases": []},
    # Stems identically to Kyiv's «Дніпровський» raion («дніпровськ»), so the
    # tie-break is the ONLY thing that separates them.
    {"name_uk": "Дніпровське", "name_en": "DniprovskeCH", "lat": 51.3551, "lon": 30.6892,
     "region": "chernihiv", "aliases": []},

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
