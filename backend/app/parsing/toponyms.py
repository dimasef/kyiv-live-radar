"""Place-name candidates the gazetteer does not know yet — what feeds the admin
coverage-gap queue.

Deliberately NOT `pipeline.ingest.resolve.should_fallback`. That gate decides
whether to spend an LLM call, so it is narrow on purpose: it requires a target
TYPE and refuses a message that names none. The northern spotters write bare
vectors — «Жукотки», «Павлівка на ТЕЦ», «Довжик на жукля» — with no type word
anywhere, so every one of them fails that test. Measured over 2026-08-18..21: of
200 unlocalized messages from the Chernihiv channel, `should_fallback` accepted
**zero**. The queue meant to surface missing gazetteer entries could not, by
construction, surface the channel that needed it most.

This gate is the mirror image. Being wrong here costs nothing — no API call, no
map pin, just a row in an admin list — so it is biased toward RECALL. A false
candidate costs the operator a glance; a missed one costs a night of blank map.

The method is the house one: a curated word list, not NLP. A token survives only
if nothing already explains it — not the gazetteer, not the parser's own
vocabulary, not the oblast/chatter lists below.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .matcher import DistrictMatcher, normalize
from .vocab import NON_TOPONYM_STEMS, NON_TOPONYM_WORDS

# `DistrictMatcher` drops any stem shorter than this, so a shorter candidate
# could not be added to the gazetteer even if it really were a place — proposing
# it would be proposing something unactionable.
_MIN_LEN = 4

_WORD_RE = re.compile(r"[а-яіїєґ][а-яіїєґ\-]{2,}")

# --- Oblast and region names ---
# An oblast is never a gazetteer entry: the parser localizes to a settlement or
# a raion, and a message whose only place is «на Чернігівщині» has nothing
# finer to pin (see origins.target_not_kyiv, which suppresses exactly these on
# the LLM path). Listed EXPLICITLY rather than as a blanket "-щина" rule,
# because Півнівщина and Бубнівщина are real Chernihiv villages that such a rule
# would have thrown away — the one thing this module must never do.
#
# Not reused from `domain.origins`: that table keeps only genuine ATTACK origins
# and deliberately drops target oblasts (Дніпро/Харків/Одеса), which are just as
# much noise here. It also lives under `app.domain`, which imports back into
# this package.
_OBLAST_STEMS = (
    "київщин", "чернігівщин", "житомирщин", "полтавщин", "сумщин", "черкащин",
    "харківщин", "херсонщин", "миколаївщин", "дніпропетровщин", "кіровоградщин",
    "вінниччин", "хмельниччин", "тернопільщин", "львівщин", "франківщин",
    "закарпатт", "рівненщин", "волинщин", "одещин", "запоріжж", "запорізьк",
    "донеччин", "луганщин", "буковин", "чернівеччин",
    # Launch-side regions the spotters name as the origin of a wave.
    "брянщин", "брянськ", "курщин", "курськ", "білгородщин", "ростовщин",
    "воронеж", "воронєж", "орловщин", "оленья", "енгельс",
    # Oblast centres that appear only as "the threat is over there, not here".
    # No bare "дніпро": it is the head of Дніпровський (a Kyiv raion) and
    # Дніпровське (a village on both sides of the border). The city itself
    # reaches us almost only as «Ціль на Дніпро», one candidate row's worth of
    # noise — cheaper than losing the next Дніпров- settlement.
    "дніпропетровськ", "одес", "херсон", "запоріж", "полтав",
    "черкас", "кропивницьк", "житомир", "вінниц", "львів", "рівне",
    "луцьк", "ужгород", "тернопіл", "хмельницьк", "чернівц", "кременчук",
    # NOT "харків" any more either: it left on 2026-08-29, the same day the
    # first Харківщина channels started filling the corpus and «Харківська» (a
    # Суми street) became a gazetteer entry. Prefix-based muting meant the queue
    # could not have proposed that entry, nor Харків itself once its own batch
    # lands — the exact failure the three below record.
    #
    # NOT "суми"/"шостк"/"конотоп" any more, and NOT bare "миколаїв". The first
    # three left this list when Сумщина got a gazetteer (2026-08-28): they name
    # OUR places now, and muting them here would have kept the coverage-gap
    # queue from ever proposing Суми, Шостка, Конотоп or Сумихімпром. "миколаїв"
    # went for the reason the "дніпро" note above gives — it is the head of
    # Миколаївка, a village name too common to lose. The bare oblast centres
    # cost one candidate row each; a village costs a night of blank map.
)

# --- Ordinary words the parser has no opinion about ---
# Everything here was observed in the 2026-08-18..21 corpus sitting in a message
# the parser could not localize. They are grouped only to keep the list
# reviewable; the code treats them as one set. Add to it when a real export
# shows a word repeatedly ranking as a candidate — that is the maintenance loop
# this list is meant to have.
_CHATTER_WORDS = (
    # Kyiv itself. `DistrictMatcher` skips the city-wide sentinel on purpose, so
    # `find("київ")` reports nothing and the bare city name would otherwise rank
    # as the single most frequent "missing place" in the whole feed.
    # "кияни" is NOT here: it is the head of Кияниця. The inhabitants are
    # matched whole in vocab.NON_TOPONYM_WORDS instead, the same move «пара»
    # made for Парафіївка.
    "київ", "києв", "київськ",
    # Observation verbs and their forms.
    "спостеріга", "спостерігаєт", "спостерігают", "спостерігаються", "фіксуєт",
    "фіксується", "фіксуют", "зникл", "зникає", "залітают", "залітають",
    "заходят", "заходять", "заходить", "підлітают", "підлітають", "летит",
    "летить", "летят", "летять", "йдут", "йдуть", "ідут", "ідуть", "маневрут",
    "маневрують", "манерв", "рухают", "рухаються", "лазит", "лазить", "лазят",
    "лазять", "тримают", "тримають", "звернул", "звернули", "повернув",
    "залишил", "залишився", "залишилось", "залишилося", "виліз", "злетіл",
    "злетіли", "працюют", "працюють", "працюємо", "продовжуют", "продовжують",
    "продовжує", "продовжуємо", "слідку", "слідкую", "відбуваєт", "відбувається",
    "сховал", "сховались", "сидіт", "переживає", "переживают",
    # Time, place-adverbs, quantities.
    "поки", "наразі", "зараз", "сьогодн", "вчора", "ввечері", "вечора", "ночі",
    "ранку", "далі", "потім", "знову", "вже", "ще", "трохи", "загалом",
    "приблизно", "практично", "мінімум", "метрів", "метрах", "висоті",
    "хвилин", "протягом", "надалі", "останній", "перший", "перші", "другий",
    # "пара" is NOT here — as a prefix it eats Парафіївка; it moved to
    # vocab.NON_TOPONYM_WORDS, matched whole like the numerals.
    "третій", "четвертий", "весь", "всього", "всіх", "деяких",
    "багато", "наче", "ніби", "майже",
    # Directions and generic geography (real bearings; never a gazetteer entry).
    "північ", "півночі", "північна", "північно", "південь", "півдня",
    "південна", "захід", "заходу", "західна", "схід", "сходу", "східна",
    "берег", "лівий", "правий", "область", "області", "обл", "район",
    "районі", "районах", "району", "межах", "межа", "сектор", "сторони",
    "сторону", "напрямку", "напрямок", "маршрут", "маршрутом", "повітрі",
    "столиц", "столиці", "столицю", "місто", "місті", "міста",
    # Modality, hedging, meta-commentary.
    "ймовірно", "можливо", "можлив", "можут", "можуть", "може", "могли",
    "буде", "будут", "будуть", "була", "були", "бути", "тільки", "якщо",
    "через", "тому", "стосовно", "відносно", "щодо", "типу", "ситуація",
    "історія", "інформац", "попередженн", "попередити", "повідомл", "думаю",
    "розумію", "хочу", "надіюсь", "сподіва", "мабуть", "звісно", "просто",
    "варто", "потрібно", "треба",
    # Address to the reader, thanks, sign-offs — the channels talk to people.
    "дякую", "дякуємо", "друзі", "хлопці", "будь", "ласка", "бережіт",
    "бережіть", "себе", "безпеці", "спокійно", "спокійного", "спокійніше",
    "тихого", "тихо", "мирного", "бажаю", "уважно", "увага", "обережно",
    "додому", "дістатися", "стаємо", "нарешті", "підтримку", "підтримк",
    # "пост" would be the head of Постольне; the noun is matched whole instead.
    "канал", "читач", "звязку", "звязок", "емоці",
    # Adversary and generic threat nouns that are not target types.
    "ворог", "ворожих", "ворожі", "росія", "росіян", "терор", "атак", "обстріл",
    "удар", "ударів", "завдава", "нанесенн", "пуски", "пускові", "виліт",
    "бойовий", "борти", "аеродром", "аеродрому", "авіаці", "авіації",
    "стратегічн", "стратегічної", "передислокац", "далекого", "керован",
    "керовані", "керуванні", "акустик", "розвід", "чисто", "чергов",
    # Misc observed one-offs that are unmistakably not places.
    "новий", "нова", "нові", "нових", "новим", "група", "групи", "групою",
    # "борщ" was tempting (a real joke post, «Борщ ага») and REJECTED: it is a
    # prefix of Борщагівка, exactly the collision class app/gazetteer.py warns
    # about. A one-off noise word is never worth risking a place name.
    "штук", "кошмарит", "кошмарят", "вони", "мене", "себе", "цього",
    "цей", "така", "такий", "сама", "самий", "інших", "інша", "інші",
    # Second pass over the same corpus: everything that still ranked in the top
    # 130 candidates after the lists above. The queue is meant to be pruned this
    # way — read the ranking, move what is plainly speech down here.
    "відб", "очіку", "повторн", "залиша", "залишок", "також", "всім", "один",
    "одна", "одне", "одні", "дали", "дати", "день", "дуже", "бачу", "бачим",
    "більше", "довго", "декілька", "данний", "даний", "момент", "відпочива",
    "жесть", "злипают", "змін", "знаю", "камер", "коли", "контент", "котики",
    "куди", "мною", "наприклад", "наша", "наші", "нерви", "низько", "ніяко",
    "панік", "паніку", "пильну", "питанн", "пишу", "напишу", "позаду",
    "походу", "проблем", "пустил", "пустит", "після", "реагува", "робот",
    "бойов", "світл", "сильно", "ситуаці", "скоро", "сунут", "сунуть",
    "тепер", "того", "хлопц", "часом", "частин", "частков", "чому",
    "щонайменше", "ігноруй", "активність", "аналіз", "аналітик", "банально",
    "бджілк", "безпечн", "ближче", "близько", "було",
    "боєприпас", "обійма", "любимо", "хейт", "ресурс", "виношува",
    "критично", "остання", "останні", "успішн", "радіо", "ефір", "тримайт",
    "кружля", "пролітают", "наближат", "повідомл",
    "вибачайте", "вибачте", "виходжу", "ціню", "увагу",
    # Third pass. Each of these is spelled to stop just short of a place name:
    # "бортів" and not "борт" (Бортничі), "південні" and not "південн"
    # (Південне). «Велика»/«Великий» are deliberately absent — they are the
    # first word of Велика Димерка, Великий Щимель and Велике Устя.
    "біля", "цілям", "цілях", "цілями", "зник", "бортів", "залітає",
    "ймовірн", "південні", "сумськ", "превентивн",
    # Fourth pass, against the live queue rather than the export — the loop this
    # list is meant to have: read the ranking, move what is plainly speech here.
    # Not bare "ворож" — that is the head of Ворожба. Spelt out to the letter
    # after the stem, so every adjective form still counts and the town does not.
    "тримаєм", "тримают", "фіксац", "висовуй", "працює", "бют",
    "ворожа", "ворожо", "ворожу", "ворожи", "ворожі", "вороже",
    "відомо", "краще", "лівом", "навіть", "немає", "нехай", "основном",
    "перебува", "попередн", "проте",
    # Fifth pass, 2026-08-30. Once a candidate had to stand where a PLACE stands
    # (`_place_positions`), the prose noise went with the change and what was
    # left ranking were the ONE-WORD status messages — a message that is nothing
    # but «Впали» looks exactly like a message that is nothing but «Гучин».
    # Spelt to stop short of a name each time: "впал" and not "впад" (Впадище),
    # "здох" is its own word, "гучн" ⊄ any entry (Гучин is "гучин").
    "впав", "впала", "впали", "впало", "здох", "здохл", "гучно", "гучні",
    "бухнул", "видихаєм", "знижуєт", "знижуют", "збиванн", "збиття",
    "вилетів", "вилетіл", "кордон", "нашої", "нашій", "нашу", "подальш",
    "офлайн", "болотах",
    # The zone-status posts the Сумщина channel repeats per raion («Сумський
    # район - повітряна тривога!»). They are whole short messages, so the
    # boilerplate detector deliberately leaves them alone (see
    # api.coverage.channel_boilerplate) and the vocabulary has to.
    "повітрян", "локаційн", "станом", "транзит", "маневрує", "назад",
    "скоріш", "найближч", "становл", "уважні", "чути", "спати", "південних",
)

_KNOWN_STEMS: tuple[str, ...] = tuple(
    sorted(NON_TOPONYM_STEMS | set(_OBLAST_STEMS) | set(_CHATTER_WORDS))
)
_KNOWN_RE = re.compile(
    r"^(?:" + "|".join(re.escape(s) for s in _KNOWN_STEMS) + r")", re.IGNORECASE
)
# Matched whole, never as a prefix — see vocab.NON_TOPONYM_WORDS.
_KNOWN_EXACT: frozenset[str] = NON_TOPONYM_WORDS


def is_known_word(token: str) -> bool:
    """Whether anything already explains this word — the parser's vocabulary, an
    oblast name, or ordinary speech. Prefix-based, matching how every other stem
    list in this package is applied ("реактивних" starts with "реактив"), except
    for the numerals, which are whole-word only."""
    return token in _KNOWN_EXACT or bool(_KNOWN_RE.match(token))


# --- Where a place stands ---------------------------------------------------
# Words that anchor a place on either side. A locational preposition is the
# obvious one; «район»/«курс» work the same way, and the anchor also counts
# BACKWARDS, because «Володимирівка на Клубівку» names a place on each side of
# it — the "A на B" vector shape the gazetteer passes are mined from.
_ANCHOR = (
    r"(?:на|над|у|в|біля|поблизу|повз|через|під|коло|бік|до|від|з|зі|між|"
    r"курс|курсом|район|районі|району|масив|масиві)"
)
_TOKEN = r"[а-яіїєґ][а-яіїєґ'\-]{2,}"
_AFTER_ANCHOR = re.compile(_ANCHOR + r"\s+(" + _TOKEN + r")")
_BEFORE_ANCHOR = re.compile(r"(" + _TOKEN + r")\s+" + _ANCHOR + r"\s")
# «Строївка/Паперня 4», «Тростянець > Охтирка», «Козин, Українка» — a list of
# places is a place position for every item in it.
_LIST_PAIR = re.compile(r"(" + _TOKEN + r")\s*[/>,]\s*(" + _TOKEN + r")")
# A message this short IS the callout, so every word in it stands where a place
# stands: the northern channels' dominant form is a bare «Жукотки» or «Замглай
# два», and an anchor-only extractor would see none of them. Measured against
# the whole stored corpus, the four rules together see 97% of the place mentions
# the gazetteer actually matched — and a name the queue is meant to propose
# repeats, so the other 3% surface from their other occurrences.
_SHORT_MESSAGE_WORDS = 6


def _place_positions(norm: str) -> set[str]:
    """The words in `norm` that stand where a place stands."""
    out: set[str] = set()
    for regex in (_AFTER_ANCHOR, _BEFORE_ANCHOR):
        for m in regex.finditer(norm):
            out.add(m.group(1))
    for m in _LIST_PAIR.finditer(norm):
        out.update(m.groups())
    words = _WORD_RE.findall(norm)
    if len(words) <= _SHORT_MESSAGE_WORDS:
        out.update(words)
    return out


def strip_boilerplate(norm: str, boilerplate: frozenset[str]) -> str:
    """Drop the lines a channel appends to every post — see
    `api.coverage.channel_boilerplate` for how they are found.

    A signature is the worst possible input to a list ranked by FREQUENCY: it
    repeats mechanically, so it outranks every real village. «Підписатись |
    Відправити новину» took three of the queue's top six rows on 2026-08-30,
    while Володимирівка — eight real callouts in the same window — was nowhere
    on it.
    """
    if not boilerplate:
        return norm
    kept = [ln for ln in norm.splitlines() if ln.strip() not in boilerplate]
    return "\n".join(kept)


def unknown_toponyms(
    text: str, matcher: DistrictMatcher, boilerplate: frozenset[str] = frozenset()
) -> list[str]:
    """Normalized words in `text` that look like a place the gazetteer is
    missing — deduplicated, in the order they appear.

    A word counts only where a PLACE could stand (`_place_positions`), which
    includes a short message being nothing but the callout. The rule used to be
    "every unknown word", on the grounds that the northern channels write bare
    one-word callouts an anchor-based extractor would miss — true, and that is
    why the short-message rule exists rather than a bare preposition
    requirement. What the old rule could not survive was prose: a long post
    contributes every noun it contains, so the ranking filled with verbs and
    channel signatures and the real names sank under them.
    """
    norm = strip_boilerplate(normalize(text), boilerplate)
    positions = _place_positions(norm)
    out: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(norm):
        word = match.group(0)
        if len(word) < _MIN_LEN or word in seen:
            continue
        seen.add(word)
        if word not in positions:
            continue
        # Gazetteer FIRST, and that order is load-bearing. Several stem lists
        # above are prefixes of real place names — the numerals alone swallow
        # Трипілля ("три"), Семиполки ("семи") and Троєщина ("троє"), and
        # "харків" swallows the Харківський масив. Asking the matcher first
        # means a place we already know can never be hidden by a word list;
        # `tests/test_toponyms.py` sweeps the whole gazetteer to keep it so.
        if matcher.find(word) or is_known_word(word):
            continue
        out.append(word)
    return out


def rank_candidates(
    texts: Iterable[tuple[str, object]],
    matcher: DistrictMatcher,
    boilerplate: frozenset[str] = frozenset(),
) -> list[dict]:
    """Aggregate `unknown_toponyms` over many messages into a work-list ranked
    by how often each candidate occurs.

    The ranking is the point. One unlocalized message is an anecdote — the same
    unknown word in six of them over one night is a gazetteer entry worth
    geocoding, and hand-mining a corpus to notice that is what this replaces.
    Each `texts` item is (message text, an opaque id echoed back as the example).
    """
    counts: dict[str, int] = {}
    example: dict[str, tuple[str, object]] = {}
    for text, ref in texts:
        for word in unknown_toponyms(text, matcher, boilerplate):
            counts[word] = counts.get(word, 0) + 1
            example.setdefault(word, (text, ref))
    return [
        {
            "name": word,
            "count": count,
            "example_text": example[word][0],
            "example_raw_message_id": example[word][1],
        }
        # Frequency first, then alphabetically so equal-count rows keep a stable
        # order between loads (the list is re-derived on every request).
        for word, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
