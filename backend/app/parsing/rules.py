"""Rule-based parser: raw Ukrainian channel text -> structured event.

This is the primary parsing layer (spec §5): cheap, instant, no network. It
recognizes target type, status, and mentioned districts. Ambiguous / unmatched
text is where the optional LLM fallback (Claude Haiku 4.5) plugs in later — this
module deliberately returns low confidence and empty districts rather than
guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..domain.origins import Origin, match_origin, target_elsewhere, target_not_kyiv
from .matcher import DistrictHit, DistrictMatcher, normalize
from .vocab import (
    _AD_ACTION,
    _AD_RECRUIT,
    _ADVISORY_RELAY,
    _AFTERMATH,
    _BALLISTIC,
    _BUZZ_CHATTER,
    _CARD_NUMBER_RE,
    _CITYWIDE_BARE_RE,
    _CITYWIDE_STRONG,
    _CITYWIDE_WEAK,
    _CIVIC_NOTICE,
    _CLEAR,
    _CLEAR_ANTICIPATION,
    _CONDITIONAL_CONSEQUENCE,
    _CONDITIONAL_IDIOM_EXCLUDE,
    _CONDITIONAL_PHRASES,
    _CONFIRMED,
    _COUNT_AFTER_PLACE_RE,
    _COUNT_BEFORE_PLACE_RE,
    _COUNT_MOVING_RE,
    _COUNT_NOUN_RE,
    _COUNT_RE,
    _COUNT_TO_PLACE_RE,
    _DAY_RECAP_WORD,
    _DECOY,
    _DESTROYED,
    _ENGAGEMENT,
    _EPPO_DISMISS,
    _EPPO_WORD,
    _EXPLAINER,
    _FORECAST_TIMEFRAME,
    _FORECAST_VERB,
    _HEDGE_MODAL_RE,
    _HYPERSONIC,
    _IMPACT,
    _JET,
    _JET_MODEL,
    _LEVEL_AHEAD_RE,
    _LEVEL_LAUNCH_RE,
    _LEVEL_OBLAST,
    _LEVEL_QUIET,
    _LEVEL_QUIET_WEAK,
    _LEVEL_RAISED,
    _LINK_MARKERS,
    _LIST_JOIN_RE,
    _LOST_WORD,
    _MASC_ONE_RE,
    _MISSILE,
    _MISSILE_CARRIER,
    _MOVEMENT_CUE,
    _NEGATION,
    _NEW_TARGET,
    _NEW_TARGET_COUNT_RE,
    _OWN_SCOPE_RE,
    _PATH_CONNECTIVE,
    _PATH_COUNT_BREAK,
    _PATH_FILLER,
    _POWER_OUTAGE,
    _PREPOSITION_BEFORE_DISTRICT,
    _PULSE_PREP_KNOWN,
    _PULSE_TARGET_PREP,
    _PULSE_WORD,
    _QUOTE_ATTRIBUTION_RE,
    _READINESS_RE,
    _RECON_ANALYSIS,
    _REPORTAGE,
    _RETROSPECTIVE,
    _SENTENCE_END_RE,
    _SHAHED,
    _SIREN_WORD,
    _STANDDOWN_CLEAN_RE,
    _STANDDOWN_LIVE_THREAT,
    _SUMMARY,
    _SUMMARY_NO_DISTRICT,
    _THREAT_CONTEXT,
    _TOPONYM_WORD_RE,
    _UNCONFIRMED,
    _UNSCOPED_CLEAR_WORD,
    count_value,
)


@dataclass
class LlmUsage:
    """Token usage + cost for one LLM fallback call — recorded regardless of
    whether the call recovered a usable district, since a call that found
    nothing still spent the budget. See parsing/llm.py::llm_extract."""

    input_tokens: int
    output_tokens: int
    cost_usd: float


def _has_conditional_hedge(norm: str) -> bool:
    if any(p in norm for p in _CONDITIONAL_PHRASES):
        return True
    if "у разі" in norm and not any(x in norm for x in _CONDITIONAL_IDIOM_EXCLUDE):
        return True
    if "якщо" in norm and any(w in norm for w in _CONDITIONAL_CONSEQUENCE):
        return True
    if _HEDGE_MODAL_RE.search(norm):
        return True
    if any(v in norm for v in _FORECAST_VERB) and any(w in norm for w in _THREAT_CONTEXT):
        return True
    if any(p in norm for p in _FORECAST_TIMEFRAME) and any(w in norm for w in _THREAT_CONTEXT):
        return True
    # Retrospective/forecast recon-analysis write-up (see _RECON_ANALYSIS) — the
    # enemy-scouting register, not a live sighting; gated by a weapon word like
    # the forecast rows so it can't swallow a terse real callout.
    if any(p in norm for p in _RECON_ANALYSIS) and any(w in norm for w in _THREAT_CONTEXT):
        return True
    # Advisory / relayed-opinion preview of which raions MIGHT be hit — see
    # _ADVISORY_RELAY. The relay/warning phrases carry the class on their own;
    # the nominal «підвищена загроза»/«райони підвищеного ризику» and «ворога
    # цікавлять» speculation need a co-occurring weapon word (same gate as the
    # forecast rows above).
    if any(p in norm for p in _ADVISORY_RELAY):
        return True
    if ("підвищен" in norm and ("загроз" in norm or "ризик" in norm)
            and any(w in norm for w in _THREAT_CONTEXT)):
        return True
    if "цікавл" in norm and "ворог" in norm:
        return True
    return False


@dataclass
class ParseResult:
    target_type: str  # 'shahed' | 'jet_drone' | 'missile' | 'ballistic' | 'unknown'
    status: str       # 'confirmed' | 'sighting' | 'unconfirmed' | 'destroyed' | 'clear'
    is_new_target: bool
    districts: list[DistrictHit]
    confidence: float
    target_count: int | None = None  # stated group size ("2х"), None if unstated
    raw_text: str = ""
    matched: bool = field(default=False)
    aftermath: bool = field(default=False)
    # A link-bearing promo/donation/ad/meta message ("створив ракетний канал…
    # https://t.me/…") — suppressed like aftermath (impact/clear/destroyed win).
    promo: bool = field(default=False)
    # Air defence engaged ("Відпрацювали установки по X") — defensive action,
    # not an incoming target. Stored so ingest can keep it out of the
    # per-channel type context.
    ad_action: bool = field(default=False)
    # A localized confirmed strike ("влучання ... в Дніпровському районі") — a
    # terminal marker to place on the map, NOT an active inbound target. Keeps
    # its district (unlike aftermath, which suppresses).
    impact: bool = field(default=False)
    negated: bool = field(default=False)
    siren_only: bool = field(default=False)
    # A civic/transport notice ("змінять маршрути тролейбусів", "обмежать рух
    # транспорту") — names a place a gazetteer entry can match but is city news,
    # not a target. Suppressed like aftermath; the T217/M668 FP class.
    civic_notice: bool = field(default=False)
    # єППО-app marks the spotter is relaying but dismissing ("локаційно не видно,
    # відмітки єППО X, Y") — the named districts are unverified app marks, not
    # live targets. Suppressed like civic_notice (see rules._eppo_marks).
    eppo_marks: bool = field(default=False)
    day_recap: bool = field(default=False)
    # Talk that NAMES a weapon without one being in the sky: spotter buzz-slang
    # ("бджілки"/"бджоли" = our drones) and explainer posts ("що таке
    # Бандероль"). Must not set/consume the per-channel live target-type context
    # (see ingest._note_and_inherit_type). Barely a suppressor — with no district
    # it forms no track either way — but it keeps such a message out of type
    # inheritance, which it otherwise poisons ("реактивні бджілки" -> jet_drone),
    # and out of the triage LLM, which has no place in the text to find.
    chatter: bool = field(default=False)
    political_quote: bool = field(default=False)
    # Relayed news of a destruction elsewhere ("Повідомляють про знищення в
    # Сибіру…") — suppressed so it can't adopt an open track and close it as
    # «знищено». Only ever set on a destroyed message with no district of its own.
    reportage: bool = field(default=False)
    lost_signal: bool = field(default=False)
    # A city-level threat with no raion of its own ("Ціль на місто!") — ingest
    # raises a single city-wide alert instead of a per-district track.
    citywide: bool = field(default=False)
    # A retrospective recap of the attack ("загалом ... 8 ракет"), not a live
    # target — info only, must not raise a city alert or track.
    summary: bool = field(default=False)
    # A terse target/launch callout with no place ("Ціль!", "Ще вихід") — only
    # acted on (as corroboration) when a city-wide alert is already open.
    target_pulse: bool = field(default=False)
    # Speaks about a wave that has NOT arrived ("можлива повторна хвиля
    # балістики", "очікуємо ракети 3-4 ранку"). Surfaces as a forecast notice,
    # but must never set the channel's live target type: on 2026-08-19 22:20 two
    # such posts about a possible NEXT ballistic wave relabelled the Kalibrs
    # then in the air, for the fifteen minutes it took them to reach Kyiv.
    anticipated: bool = field(default=False)
    # A threat-LEVEL bulletin about a target type with no target of its own
    # ("червоний рівень по балістиці" / "по балістиці тихо"): 'forecast' when
    # the level is up, 'status' when that type is quiet. Never a live target and
    # never an all-clear — ingest turns it into a feed notice of that kind.
    notice_kind: str | None = field(default=None)
    # None = a genuine full clear ("Відбій тривоги та всіх загроз") — closes
    # every open track. A target type = an all-clear scoped to just THAT
    # type ("Відбій балістичної загрози з Криму") — must not close unrelated
    # open tracks (e.g. an active shahed). Only set when status == "clear".
    clear_scope: str | None = field(default=None)
    # Decoy/EW vocabulary present ("імітація", "РЕБ", "хибна ціль") — a
    # modifier accumulated onto the incident (see app/domain/attack.py), not a
    # replacement classification.
    decoy: bool = field(default=False)
    # A hypersonic system named (Кинджал/Циркон/aeroballistic) — a flag on
    # the incident, not a 6th target_type.
    hypersonic: bool = field(default=False)
    # A directional/origin threat callout ("Балістика з Брянщини") with no Kyiv
    # raion — ingest raises a directional AXIS (a screen-edge wedge), not a track.
    # `origin_key` is a curated origin (origins.ORIGIN_KEYS); `origin_sector` its
    # compass octant. Only set when directional is True.
    directional: bool = field(default=False)
    origin_key: str | None = field(default=None)
    origin_sector: str | None = field(default=None)
    # 2+ districts named as a bare enumeration ("Вишневе Жуляни", "Троя,Оболонь
    # увага!") — SIMULTANEOUS separate targets, one track per district. False
    # for a movement frame ("через Бровари", "курсом на Троєщину") — that's a
    # route and stays one track (the vector case).
    multi_targets: bool = field(default=False)
    # A path was STATED between two named places in this one message («Мамекине
    # на Смяч») — the districts are waypoints of one trajectory, in text order,
    # not an enumeration. Display metadata only: it never changes which track a
    # sighting joins, it tells the map that a single-timestamp track is a real
    # vector (see track.ts::hasMovement). Distinct from `multi_targets`, which
    # is the NEGATIVE of the same question and also False for a plain
    # prepositional frame ("удар по Оболоні") that states no path.
    movement: bool = field(default=False)


# Some keywords are short abbreviations that collide with common words (e.g.
# "каб" inside "кабель"/"кабіна", "реб" inside "теребити"/"ребро"). Match
# those as whole words; match everything else at a word start so inflected
# suffixes still hit (ракет→ракети).
_WHOLE_WORD = {"каб", "реб"}


def _kw_regex(words) -> re.Pattern:
    parts = []
    for w in words:
        esc = re.escape(w)
        if w in _WHOLE_WORD:
            parts.append(r"(?<![а-яіїєґ])" + esc + r"(?![а-яіїєґ])")
        else:
            parts.append(r"(?<![а-яіїєґ])" + esc)
    if not parts:
        # "|".join([]) is the EMPTY pattern, which matches at every position —
        # an emptied keyword list would silently label every message with that
        # type. Fail closed instead: match nothing.
        return re.compile(r"(?!)")
    return re.compile("|".join(parts))


_BALLISTIC_RE = _kw_regex(_BALLISTIC)
_MISSILE_RE = _kw_regex(_MISSILE)
_JET_MODEL_RE = _kw_regex(_JET_MODEL)
_JET_RE = _kw_regex(_JET)
_SHAHED_RE = _kw_regex(_SHAHED)
_DECOY_RE = _kw_regex(_DECOY)
_HYPERSONIC_RE = _kw_regex(_HYPERSONIC)

# A type named only to DENY it ("…це не БПЛА, воно з лівого на правий за
# секунди") must not type the message — on 07-18 that exact sentence typed a
# spotter aside as `shahed` and the next "Увага на Київ!" inherited it, so the
# main city-wide card of a ballistic salvo spent 15 minutes labeled БПЛА. Only
# the adjacent "не <type>" form is masked; a non-adjacent negation ("траєкторія
# не притаманна для «Іскандер-М»") still talks about that type for real.
_NEGATED_TYPE_RE = re.compile(
    r"(?<![а-яіїєґ])не\s+(?:"
    + "|".join(re.escape(w) for w in (*_BALLISTIC, *_MISSILE, *_JET_MODEL, *_JET, *_SHAHED))
    + r")[а-яіїєґ]*"
)


def _target_type(norm: str) -> str:
    norm = _NEGATED_TYPE_RE.sub(" ", norm)
    if _BALLISTIC_RE.search(norm):
        return "ballistic"
    # A named jet model beats the generic missile list — the same message often
    # carries both ("10 ракет Бандероль"), and the model is the more specific
    # statement. Mirrors why ballistic is checked first.
    if _JET_MODEL_RE.search(norm):
        return "jet_drone"
    if _MISSILE_RE.search(norm):
        return "missile"
    if _JET_RE.search(norm):
        return "jet_drone"
    if _SHAHED_RE.search(norm):
        return "shahed"
    if _MASC_ONE_RE.search(norm):
        return "shahed"
    return "unknown"


def _place_follows(end: int, districts) -> bool:
    """Whether a gazetteer-matched place starts right where a phrase ended.

    This is what makes the bare-number count form safe: the number only counts
    when a KNOWN place follows it. The couple of characters of slack absorb a
    stray quote or double space between the preposition and the name."""
    return any(0 <= h.position - end <= 2 for h in districts)


def _target_count(norm: str, districts) -> int | None:
    """The largest sane group count stated in the text ("2х"->2, "3 ракети"->3,
    "3 на Славутич"->3, "3 долітають до Броварів"->3).

    Still the size of ONE group flying together, an annotation on the track — it
    never fabricates N tracks, and the multi-district enumeration path
    deliberately refuses to stamp it per district (see handlers.py)."""
    nums = [int(m.group(1)) for m in _COUNT_RE.finditer(norm)]
    # Every rule below accepts a numeral WORD as well as digits, so the value has
    # to be resolved rather than int()'d (see vocab._NUM_WORDS).
    nums += [count_value(m.group(1)) for m in _COUNT_NOUN_RE.finditer(norm)]
    nums += [
        count_value(m.group(1))
        for m in _COUNT_TO_PLACE_RE.finditer(norm)
        if _place_follows(m.end(), districts)
    ]
    nums += [count_value(m.group(1)) for m in _COUNT_MOVING_RE.finditer(norm)]
    # The place-adjacent form ("Замглай два", "Два хрінівка на Добрянка"). Its
    # anchor is a gazetteer hit rather than a word, so the scan lives here — and
    # it uses the hit's real END, which is what keeps the "5" of «ТЕЦ-5» out.
    for h in districts:
        after = _COUNT_AFTER_PLACE_RE.match(norm[h.end:])
        if after:
            nums.append(count_value(after.group(1)))
        before = _COUNT_BEFORE_PLACE_RE.search(norm[:h.position])
        if before:
            nums.append(count_value(before.group(1)))
    nums = [n for n in nums if n is not None and 1 <= n <= 50]  # junk like "100х"/years
    return max(nums) if nums else None


def _status(text: str, norm: str) -> tuple[str, float]:
    """Return (status, base_confidence)."""
    if any(k in norm for k in _CLEAR) and not any(a in norm for a in _CLEAR_ANTICIPATION):
        return "clear", 0.9
    if any(k in norm for k in _DESTROYED):
        return "destroyed", 0.85
    if any(k in norm for k in _UNCONFIRMED):
        return "unconfirmed", 0.35
    if "🔴" in text or any(k in norm for k in _CONFIRMED):
        return "confirmed", 0.9
    return "sighting", 0.6


# --- Message-level predicates, computed in this exact order by parse_message.
# Each takes only the upstream values it needs; the dependency chain (impact
# feeds aftermath/ad_action; the suppressor flags feed citywide/target_pulse/
# matched; district-clearing happens once, after matched) mirrors the original
# inline computation exactly — do not reorder without re-running the eval gate. ---


def _clear_scope(status: str, target_type: str, norm: str) -> str | None:
    """A clear/відбій is scoped to just the named type when the message states a
    missile-family type ("Відбій балістичної загрози" -> ballistic; a cruise
    "відбій ракетної небезпеки" -> missile) and doesn't ALSO say the siren
    itself ended. A ballistic stand-down must not close active cruise/shahed
    tracks, and vice versa. See _UNSCOPED_CLEAR_WORD's comment for the real
    example this guards."""
    return (
        target_type
        if status == "clear" and target_type in ("ballistic", "missile")
        and _UNSCOPED_CLEAR_WORD not in norm
        else None
    )


def _impact(districts, norm: str, status: str) -> bool:
    """Impact / localized strike ("влучання по будівлі в Дніпровському районі"):
    a confirmed hit whose LOCATION we map as a terminal marker. Needs a
    district; a destroyed/clear keyword is a stronger, more specific status
    and wins over an impact reading. A power-outage notice ("аварійне
    пошкодження ... немає світла") also says "пошкодж" but that's grid damage —
    blocked unless an unambiguous strike word (влучанн/приліт) is also present,
    so it falls back to plain aftermath suppression."""
    grid_only = any(k in norm for k in _POWER_OUTAGE) and not any(
        k in norm for k in ("влучанн", "приліт")
    )
    return (
        bool(districts)
        and any(k in norm for k in _IMPACT)
        and status not in ("clear", "destroyed")
        and not any(k in norm for k in _RETROSPECTIVE)
        and not grid_only
    )


def _aftermath(norm: str, status: str, impact: bool) -> bool:
    """Aftermath/consequence news ("постраждала багатоповерхівка", "врятували
    дитину") mentions a district but is NOT a live target — suppress it, unless
    it's an all-clear (which legitimately closes tracks) or a localized impact
    (which we keep and map — the strike location is the useful signal)."""
    return any(k in norm for k in _AFTERMATH) and status != "clear" and not impact


def _ad_action(norm: str, status: str, impact: bool) -> bool:
    """Air-defence engaged over some districts ("Відпрацювали установки по X та
    Y") — defensive action, not an incoming target. Suppressed like aftermath so
    it never becomes a track (and never a bogus X→Y vector); a real strike
    keyword in the same message still wins via the impact carve-out."""
    return any(k in norm for k in _AD_ACTION) and status not in ("clear", "destroyed") and not impact


def _civic_notice(target_type: str, status: str, norm: str, impact: bool) -> bool:
    """City-news suppressor: a public-transport route/schedule change or road
    closure ("тимчасово змінять маршрути тролейбусів", "обмежать рух
    транспорту") that mentions a street/neighbourhood the gazetteer matches but
    is not a live target — the T217/M668 false-positive class. Only on a
    type-unknown message (a named threat is never a bus notice) and with the
    same impact/clear/destroyed carve-out as aftermath, so a real strike report
    is never silenced by a coincidental transport word."""
    return (
        target_type == "unknown"
        and status not in ("clear", "destroyed")
        and not impact
        and any(k in norm for k in _CIVIC_NOTICE)
    )


def _eppo_marks(target_type: str, status: str, norm: str, impact: bool) -> bool:
    """єППО (crowd/sensor app) marks the spotter RELAYS but DISMISSES as not seen
    on their own tracking ("локаційно не видно, відмітки єППО Вишневе, Макарів…")
    — unverified app marks, not live targets, so the coincidentally-named
    districts must not become tracks. Requires BOTH an єППО mention AND a
    "not seen / dorozvidka / false" cue, so a genuine "єППО показує ціль на
    Троєщині, підтверджую" is untouched. Guarded like civic_notice: type-unknown
    only, with the clear/destroyed/impact carve-out."""
    return (
        target_type == "unknown"
        and status not in ("clear", "destroyed")
        and not impact
        and any(w in norm for w in _EPPO_WORD)
        and any(w in norm for w in _EPPO_DISMISS)
    )


def _negated(norm: str, status: str, impact: bool) -> bool:
    """Explicit denial ("Не йде на Оболонь") mentions a district but says the
    target is NOT there — suppress it, same carve-out as aftermath: an
    explicit clear/destroyed keyword elsewhere in the message still wins (its
    own keyword signal is stronger evidence than a coincidental negation word).
    A conditional/speculative hedge ("якщо піде…", "у разі оголошення
    тривоги…", "можуть бути вибухи…") gets the same treatment — see
    _has_conditional_hedge. Same impact carve-out as _aftermath/_ad_action: a
    confirmed strike report can coincidentally use hedge words for an
    unrelated clause ("...під завалами можуть бути люди") and must not have
    its real impact districts wiped by that coincidence."""
    return (
        (any(k in norm for k in _NEGATION) or _has_conditional_hedge(norm))
        and status not in ("clear", "destroyed")
        and not impact
    )


def _reportage(norm: str, districts, status: str) -> bool:
    """Relayed news of a destruction that happened somewhere we don't track
    ("Повідомляють про знищення в Сибіру ешелону...") — not a stand-down for any
    of OUR tracks. Every other suppressor is powerless here: a "destroyed"
    message deliberately bypasses promo/negated/siren (a real «мінус» must always
    be able to close a track), and with no district of its own the destroyed
    handler adopts whichever track is open — closing a live one as «знищено»
    (T3332, 2026-08-14).

    Gated on no-district AND destroyed, the two things that make a relayed item
    dangerous rather than merely noisy. A first-hand callout always localizes, so
    the two real reportage-marked sightings in the corpus ("Гатне повідомляють
    про приліт") keep their districts and pass through untouched."""
    return any(k in norm for k in _REPORTAGE) and not districts and status == "destroyed"


def _siren_only(target_type: str, status: str, districts, norm: str) -> bool:
    """Siren-status echo: names a district, mentions "тривога", but states no
    target type at all — the technical "alarm is on here" notice, not a
    sighting. Only applies to sighting/confirmed statuses; an explicit
    clear/destroyed keyword is still a real signal worth keeping."""
    return (
        target_type == "unknown"
        and status in ("sighting", "confirmed")
        and bool(districts)
        and _SIREN_WORD in norm
    )


def _day_recap(target_type: str, status: str, districts, norm: str) -> bool:
    """Day-summary commentary ("...під атакою сьогодні"): same shape as
    siren_only (no target type at all), but "сьогодні" alone isn't a clean
    enough marker to justify dropping the district outright, so this only
    softens confidence instead of suppressing the sighting."""
    return (
        target_type == "unknown"
        and status == "sighting"
        and bool(districts)
        and _DAY_RECAP_WORD in norm
    )


def _political_quote(target_type: str, status: str, districts, norm: str) -> bool:
    """Political/official quote naming a place, no stated target type — a news
    repost of a statement, not a spotter sighting. Same shape-gate as
    siren_only (target type unresolved + a district present); an explicit
    target type stated elsewhere in the same message still wins."""
    return (
        target_type == "unknown"
        and status in ("sighting", "confirmed")
        and bool(districts)
        and bool(_QUOTE_ATTRIBUTION_RE.search(norm))
    )


def _lost_signal(norm: str, districts, status: str) -> bool:
    """"Дорозвідка": ППО no longer has/sees targets of the stated type (or, if
    unstated, no targets at all) — a real stand-down signal handled directly
    by ingest.py (closes matching open tracks), not a suppression like the
    flags above. Gate is deliberately just "no district" — see _LOST_WORD's
    comment for why a district-bearing message must never match this. Same
    carve-out as negated/siren_only: an explicit clear/destroyed keyword in
    the SAME message ("Мінуснули, Дорозвідка" — one target confirmed
    destroyed, "дорозвідка" here is just a follow-up status note) is the
    stronger, more specific signal and must win — otherwise it would
    incorrectly close EVERY open track as "lost" instead of just the one
    destroyed target."""
    if districts or status in ("clear", "destroyed"):
        return False
    # A live-threat continuation clause in the same message («…але паралельно
    # триває загроза балістики з Брянщини») outranks the stand-down half —
    # leaving lost_signal unset lets the directional/origin path handle it.
    if any(k in norm for k in _STANDDOWN_LIVE_THREAT):
        return False
    if _LOST_WORD in norm:
        return True
    # "Чисто!" — same stand-down in spotter shorthand, but only when the
    # message isn't scoped to another oblast ("По Житомирщині чисто поки").
    return bool(_STANDDOWN_CLEAN_RE.search(norm)) and not target_elsewhere(norm)


def _summary(norm: str, target_type: str, has_district: bool) -> bool:
    """Retrospective summary of the whole attack (aggregate/past-frame count) —
    info, not a live target. Blocks the city-alert / track it would otherwise
    raise. Only meaningful on a threat-flavoured message.

    `_SUMMARY_NO_DISTRICT` markers (past-strike "вдарил") count only when NO
    raion is named: "6 балістичних вдарило по Києву" is a citywide recap, but
    a district-bearing "ракета вдарила по Троєщині" must stay a live impact."""
    if not (target_type != "unknown" or any(w in norm for w in _THREAT_CONTEXT)):
        return False
    if any(k in norm for k in _SUMMARY):
        return True
    if not has_district and any(k in norm for k in _SUMMARY_NO_DISTRICT):
        return True
    return False


def _promo(norm: str, status: str, impact: bool) -> bool:
    """A message carrying a URL, a bare payment-card number, a link-less
    channel-recruitment phrase (_AD_RECRUIT) or a donation/engagement frame
    (_ENGAGEMENT) is promo / donation / channel-boost / ad / meta, never a live
    target callout — a spotter's sighting never links out or advertises
    (validated against the real corpus: zero such sightings). Suppress it like
    aftermath: a real clear/destroyed keyword or a confirmed impact in the same
    message still wins."""
    return (
        (any(m in norm for m in _LINK_MARKERS) or bool(_CARD_NUMBER_RE.search(norm))
         or any(m in norm for m in _AD_RECRUIT) or any(m in norm for m in _ENGAGEMENT))
        and status not in ("clear", "destroyed")
        and not impact
    )


@dataclass(frozen=True)
class Suppressors:
    """Every message-level reason to hold something back, computed once.

    These used to be threaded through as positional bools — seventeen of them
    into `_level_notice` alone — with each predicate re-listing by hand the
    subset it cared about. The lists drifted, which is not a hypothetical: only
    four of the five listed `promo`, and `_target_pulse` was one of the ones
    that didn't. Since `_dispatch` acts on `target_pulse` twenty-one lines
    BEFORE it checks `matched`, a three-word recruitment line carrying a pulse
    word corroborated the live city-wide alert and raised its confidence.

    Passing the record whole makes that class of divergence impossible to
    express: the subsets below are named once, here, next to the reason they
    differ.
    """

    aftermath: bool
    negated: bool
    siren_only: bool
    political_quote: bool
    lost_signal: bool
    summary: bool
    ad_action: bool
    civic_notice: bool
    eppo_marks: bool
    promo: bool
    reportage: bool
    day_recap: bool

    @property
    def blocks_surface(self) -> bool:
        """Reasons a message must not raise a live surface — a city-wide alert,
        a terse pulse, an origin axis or a level bulletin.

        `reportage` and `day_recap` are deliberately absent: they are record-
        level judgements (is this a target we log?) and a confidence softener
        respectively, and `blocks_record` below is where reportage belongs.
        """
        return (
            self.aftermath
            or self.negated
            or self.siren_only
            or self.political_quote
            or self.lost_signal
            or self.summary
            or self.ad_action
            or self.civic_notice
            or self.eppo_marks
            or self.promo
        )

    @property
    def blocks_record(self) -> bool:
        """Reasons there is nothing structured to record at all (`matched`).

        Narrower than `blocks_surface` on purpose: `lost_signal` and `summary`
        are ACTIONABLE — `_dispatch` routes both to their own handlers before it
        reaches the matched check — so treating them as suppressors here would
        drop a stand-down. `reportage` is only ever a reason not to record.
        """
        return (
            self.aftermath
            or self.negated
            or self.siren_only
            or self.political_quote
            or self.ad_action
            or self.promo
            or self.civic_notice
            or self.eppo_marks
            or self.reportage
        )

    @property
    def clears_districts(self) -> bool:
        """Reasons the matched raions must be dropped from the result.

        `blocks_record` minus `reportage`: a news report that names a raion is
        still naming a real place, and the hits stay on the result for the
        gazetteer/eval tooling even though nothing is tracked from them.
        """
        return (
            self.aftermath
            or self.negated
            or self.siren_only
            or self.political_quote
            or self.ad_action
            or self.promo
            or self.civic_notice
            or self.eppo_marks
        )


def _level_notice(target_type: str, districts, citywide: bool, directional: bool, status: str,
                  norm: str, target_count: int | None, sup: Suppressors) -> str | None:
    """Threat-level bulletin about a target TYPE with nothing to localize —
    'forecast' (the level is up) or 'status' (that type is quiet, is somewhere in
    the oblast, or arrives as a bare count) — the two notice kinds the feed
    renders. Requires a named type: an untyped "поки тихо" is chatter, while "по
    балістиці тихо" is the standing bulletin the spotters keep beside the live
    callouts.

    Everything that localizes or supersedes wins first: a raion, a CITY-WIDE
    callout ("Загроза балістики на Київ" is a live alert, not a bulletin), an
    ORIGIN ("Загроза балістики з Брянщини" is an axis — by far the commonest
    shape of this sentence), a clear/destroyed, any suppressor. So this only
    fires where the message would otherwise have produced nothing at all. A pulse-shaped bulletin («🟣 Загроза
    БАЛІСТИКИ») deliberately keeps BOTH flags: with a city-wide alert already
    open it corroborates as a pulse, and only the fall-through case — nothing
    open to corroborate — reaches the notice branch in _dispatch."""
    if (districts or citywide or directional or target_type == "unknown"
            or status in ("clear", "destroyed")):
        return None
    if sup.blocks_surface:
        return None
    # "по Житомирщині тихо" — someone else's bulletin. `target_not_kyiv`, not
    # `target_elsewhere`: a bulletin about the watched north is still not a
    # bulletin about Kyiv, which is what this feed card claims to be. Unless the
    # message claims our scope outright, in which case the foreign oblast is the
    # contrast half of "quiet here, busy there" — see _OWN_SCOPE_RE.
    if target_not_kyiv(norm) and not _OWN_SCOPE_RE.search(norm):
        return None
    if any(p in norm for p in _LEVEL_RAISED):
        return "forecast"
    if any(p in norm for p in _LEVEL_QUIET):
        return "status"
    if any(p in norm for p in _LEVEL_OBLAST):
        return "status"
    # After the quiet/oblast branches — see the comment on these three families.
    if (_LEVEL_LAUNCH_RE.search(norm) or _LEVEL_AHEAD_RE.search(norm)
            or any(p in norm for p in _MISSILE_CARRIER)):
        return "forecast"
    if any(p in norm for p in _LEVEL_QUIET_WEAK):
        return "status"
    # A stated COUNT with nowhere to put it ("Вже близько 21 ракет пустили",
    # "Був залп з 5 ракет") — during a salvo this number IS the situation, and
    # it is the one thing the feed used to lose entirely. Terse counts that
    # arrive while a city-wide alert is open never get here: _dispatch runs the
    # pulse handler first, and corroborating the live track beats a notice.
    if target_count is not None:
        return "status"
    return None


def _citywide(districts, status: str, norm: str, sup: Suppressors) -> bool:
    """City-wide threat: a city-level phrase with NO raion of its own — a strong
    directional phrase on its own, or a weak one plus a threat-context word.
    Only when nothing else localizes or supersedes it: a real district, an
    all-clear/destroyed, aftermath/negation/siren/quote, a civic notice, or a
    retrospective summary all take precedence. ingest.py turns this into ONE
    city-level alert."""
    return (
        not districts
        and status not in ("clear", "destroyed")
        and not sup.blocks_surface
        and (
            any(p in norm for p in _CITYWIDE_STRONG)
            or bool(_CITYWIDE_BARE_RE.match(norm))
            or (any(p in norm for p in _CITYWIDE_WEAK)
                and any(w in norm for w in _THREAT_CONTEXT))
        )
    )


_PULSE_TRIM = " .,!?:;()«»\"'…—–-+"


def _pulse_tokens(norm: str) -> list[str]:
    """Words of a normalized message with punctuation trimmed off each end."""
    return [w for w in (t.strip(_PULSE_TRIM) for t in norm.split()) if w]


def _pulse_names_unknown_place(words: list[str]) -> bool:
    """A word sitting in TARGET position after a place preposition that the
    gazetteer did NOT match ("Реактивний біля Пирятина", "На короп крилаті").

    The message names somewhere we don't know, and pulsing it would credit the
    open KYIV city alert with that somewhere's sighting — the T2445 class one
    step past what `target_not_kyiv` can see, since that one knows oblast names
    and this is an unrecognized settlement. Such a message is exactly the
    gazetteer gap the LLM fallback exists for, so refusing to pulse also keeps
    it flowing there.

    Only the preposition form is caught. A bare trailing toponym ("Виліз
    реактивний Тростянка") reads the same as a target word to any rule we have
    and still pulses — a pre-existing limit of the pulse shape, not one this
    guard introduces."""
    for prev, word in zip(words, words[1:], strict=False):
        if prev not in _PULSE_TARGET_PREP:
            continue
        if word[0].isdigit():  # "До 5ти ракет!" — a count, not a place
            continue
        if any(p in word for p in _PULSE_WORD + _PULSE_PREP_KNOWN):
            continue
        return True
    return False


def _pulse_type_denied(words: list[str]) -> bool:
    """A bare denial of the type ("Не реактивні", "Не ракети") — the spotter is
    correcting what's in the sky, not calling a new target in. `_negated` misses
    it: its vocabulary expects a verb ("не йде на…"), and two words don't give
    it one."""
    return any(prev == "не" and any(p in word for p in _PULSE_WORD)
               for prev, word in zip(words, words[1:], strict=False))


def _target_pulse(districts, citywide: bool, status: str, norm: str,
                  sup: Suppressors) -> bool:
    """Terse target/launch pulse: a very short callout ("Ціль!", "Ще вихід",
    "Групова ціль", "3 ракети") naming a target/launch but no place. The
    length cap keeps out longer sentences (which are usually status prose,
    e.g. "Наразі повторні цілі відсутні…"), and all the suppressor flags are
    excluded so a negated/recap line never pulses. ingest.py only ACTS on this
    when a city-wide alert is already open — alone it's too terse to localize.

    A pulse scoped to ANOTHER oblast is not ours: "Ціль на Сумщині" fits the
    shape exactly (3 words, "ціль"), and since acting on a pulse corroborates
    the open KYIV city alert, it added a Sumy sighting to a Kyiv track and
    bumped its confidence (live 2026-08-01, T2445). Same guard `_lost_signal`
    already applies to "Чисто!"."""
    words = _pulse_tokens(norm)
    return (
        not districts
        and not citywide
        and status not in ("clear", "destroyed")
        and not sup.blocks_surface
        and len(norm.split()) <= 3
        and any(any(p in w for p in _PULSE_WORD) for w in norm.split())
        # A pulse corroborates the KYIV city-wide alert, so anything scoped to
        # another region — watched or not — must not pulse (live 2026-08-01:
        # "Ціль на Сумщині" pushed a Kyiv card's confidence to 0.7).
        and not target_not_kyiv(norm)
        and not _pulse_names_unknown_place(words)
        and not _pulse_type_denied(words)
    )


def _hit_end(hit: DistrictHit, norm: str) -> int:
    """Char offset just past a gazetteer hit's own word (it carries only its
    start; the matched form is one word, or the first word of a short phrase)."""
    word = _TOPONYM_WORD_RE.match(norm[hit.position:])
    return hit.position + (word.end() if word else 0)


def _standby_districts(districts, norm: str) -> set[int]:
    """Indices of hits the message merely puts on STANDBY rather than reports a
    target over — the raions governed by a «готовність» (see _READINESS_RE).

    The marker governs forward to the end of its sentence («готовність Вишгород,
    Оболонь та Троя»), and backward only when it sits immediately after a raion
    with nothing but a space between («Троя готовність», «Прилукам готовність»).
    That tight backward window is what separates it from «Пухівка/Зазимʼя 🔴 та
    готовність Бровари», where the two before the marker are the sighting and
    only Бровари is on standby. A coordinated list right before the marker goes
    on standby whole («Район Обухова/Василькова/Фастова готовність»)."""
    standby: set[int] = set()
    order = sorted(range(len(districts)), key=lambda i: districts[i].position)
    for marker in _READINESS_RE.finditer(norm):
        for i, hit in enumerate(districts):
            if hit.position >= marker.end():
                if not _SENTENCE_END_RE.search(norm[marker.end():hit.position]):
                    standby.add(i)
            else:
                end = _hit_end(hit, norm)
                if 0 <= marker.start() - end <= 2 and not norm[end:marker.start()].strip():
                    standby.add(i)
    for pos in range(len(order) - 1, 0, -1):
        cur, prev = order[pos], order[pos - 1]
        gap = norm[_hit_end(districts[prev], norm):districts[cur].position]
        if cur in standby and _LIST_JOIN_RE.match(gap):
            standby.add(prev)
    return standby


def _drop_standby_districts(districts, norm: str):
    """Standby raions, dropped — but ONLY from a message that also reports a real
    sighting. Then nothing is lost: the message still surfaces on the raion the
    spotter actually saw the target over, and the one he told to get ready stops
    being drawn as a target overhead.

    When EVERY raion in the message is on standby («Район Обухова/Василькова/
    Фастова готовність»), the list is left alone: dropping it would delete the
    message from the feed entirely, and a heads-up the operator can see is worth
    more than a track he has to discount. Representing that properly — feed-only,
    or its own map state — is a product decision, not a parser one."""
    if not districts:
        return districts
    standby = _standby_districts(districts, norm)
    if not standby or len(standby) == len(districts):
        return districts
    return [h for i, h in enumerate(districts) if i not in standby]


def _multi_targets(districts, norm: str) -> bool:
    """Bare enumeration of 2+ districts = simultaneous separate targets (see
    ParseResult.multi_targets). Any movement cue, or any district sitting in a
    prepositional phrase, reads as a located/route frame instead — one track."""
    if len(districts) < 2:
        return False
    if any(c in norm for c in _MOVEMENT_CUE):
        return False
    for h in districts:
        before = norm[: h.position].rstrip(" ,./—–-")
        word = before.rsplit(" ", 1)[-1] if before else ""
        if word in _PREPOSITION_BEFORE_DISTRICT:
            return False
    return True


def _movement_path(districts, norm: str) -> bool:
    """Did this ONE message state a path between two named places?

    True when a path connective sits in the gap BETWEEN two consecutive district
    hits («Мамекине [на] Смяч», «Реактивний йде григорівка [на район] Дмитрівка»)
    — so the hits, already ordered by text position, are waypoints of one
    trajectory. A bare enumeration («Троя, Оболонь») has no connective in the
    gap and stays False, which is what keeps this off the Kyiv channels'
    meandering-drone shape.

    Positive-signal-only on purpose: `not multi_targets` would be far broader
    (it is also False for "удар по Оболоні", a located frame stating no path).

    Three guards, each earned from a real Kyiv-channel false positive — the
    connective alone is far too weak (measured 2026-08-24: it fired on 29
    Kyiv-channel messages, of which ~14 were separate targets or unrelated
    prose):
      * a sentence or line break ends the statement — «повз Десну на південь.
        Ще один реактивний…» is two targets;
      * a count inside the gap makes it a distribution, not a path;
      * whatever follows the connective must be the destination itself, not a
        threat noun («через БпЛА»).
    """
    if len(districts) < 2:
        return False
    for a, b in zip(districts, districts[1:], strict=False):
        gap = norm[a.end:b.position]
        if re.search(r"[.!?\n]", gap) or re.search(r"\d", gap):
            continue
        if any(w in gap for w in _PATH_COUNT_BREAK):
            continue
        last = max((m.end() for c in _PATH_CONNECTIVE
                    for m in re.finditer(
                        rf"(?<![а-яіїєґ]){re.escape(c)}(?![а-яіїєґ])", gap)),
                   default=None)
        if last is None:
            continue
        tail = [w for w in re.split(r"[^а-яіїєґ-]+", gap[last:]) if w]
        if all(w in _PATH_FILLER for w in tail):
            return True
    return False


def _origin_present(origin: Origin | None, status: str, target_type: str, norm: str,
                    sup: Suppressors) -> bool:
    """A curated inbound origin named in FROM-position ("з Брянщини", "з боку
    Чорного моря") on a threat-flavoured, non-suppressed message. Set whether or
    not the message ALSO localizes to a raion/city — so "Балістика на Київ з
    Брянщини" raises the city alert AND a NE wedge. The directional AXIS is
    raised from this; the `directional` flag below marks the standalone case."""
    return (
        origin is not None
        and status not in ("clear", "destroyed")
        and (target_type != "unknown" or any(w in norm for w in _THREAT_CONTEXT))
        and not target_elsewhere(norm)  # "з Чернігівщини курсом на Дніпро" -> not ours
        and not sup.blocks_surface
    )


def _matched(districts, citywide: bool, status: str, sup: Suppressors) -> bool:
    """No district and no actionable status -> nothing structured to record."""
    return (
        (bool(districts) or citywide or status in ("clear", "destroyed"))
        and not sup.blocks_record
    )


def parse_message(text: str, matcher: DistrictMatcher) -> ParseResult:
    norm = normalize(text)
    target_type = _target_type(norm)
    status, conf = _status(text, norm)
    is_new = any(k in norm for k in _NEW_TARGET) or bool(_NEW_TARGET_COUNT_RE.search(norm))
    districts = matcher.find(norm)
    # Counted after the districts: the bare "3 на Славутич" form only counts when
    # a matched place follows the number.
    target_count = _target_count(norm, districts)
    # Unconditional modifier flags — computed regardless of matched/
    # suppression status, since a decoy/hypersonic mention is worth
    # accumulating onto the incident even on an otherwise-terse message.
    decoy = bool(_DECOY_RE.search(norm))
    hypersonic = bool(_HYPERSONIC_RE.search(norm))
    chatter = any(w in norm for w in (*_BUZZ_CHATTER, *_EXPLAINER))

    clear_scope = _clear_scope(status, target_type, norm)
    impact = _impact(districts, norm, status)
    aftermath = _aftermath(norm, status, impact)
    ad_action = _ad_action(norm, status, impact)
    negated = _negated(norm, status, impact)
    siren_only = _siren_only(target_type, status, districts, norm)
    civic_notice = _civic_notice(target_type, status, norm, impact)
    eppo_marks = _eppo_marks(target_type, status, norm, impact)
    day_recap = _day_recap(target_type, status, districts, norm)
    if day_recap:
        conf = min(conf, 0.35)
    political_quote = _political_quote(target_type, status, districts, norm)
    reportage = _reportage(norm, districts, status)
    lost_signal = _lost_signal(norm, districts, status)
    summary = _summary(norm, target_type, bool(districts))
    promo = _promo(norm, status, impact)
    sup = Suppressors(
        aftermath=aftermath,
        negated=negated,
        siren_only=siren_only,
        political_quote=political_quote,
        lost_signal=lost_signal,
        summary=summary,
        ad_action=ad_action,
        civic_notice=civic_notice,
        eppo_marks=eppo_marks,
        promo=promo,
        reportage=reportage,
        day_recap=day_recap,
    )
    citywide = _citywide(districts, status, norm, sup)
    target_pulse = _target_pulse(districts, citywide, status, norm, sup)
    origin = match_origin(norm)
    origin_present = _origin_present(origin, status, target_type, norm, sup)
    # Standalone directional: an origin with nothing else to localize on — the
    # primary "загроза з Брянська" class. When a raion/citywide IS also present,
    # origin still feeds a secondary axis but that branch handles the track/alert.
    directional = origin_present and not districts and not citywide
    notice_kind = _level_notice(target_type, districts, citywide, directional, status, norm,
                                target_count, sup)
    anticipated = notice_kind == "forecast" and _LEVEL_AHEAD_RE.search(norm) is not None
    matched = _matched(districts, citywide, status, sup)

    # Two distinct district lists, named rather than one variable reassigned
    # mid-function. Everything above consumes `districts` — every raion the
    # gazetteer matched, which is what those predicates ask about ("did this
    # message name a place at all?"). Everything below consumes the reported
    # set: suppressed messages report nowhere, and a raion merely put on
    # «готовність» is not a sighting. Reassigning one name meant the line a
    # predicate sat on silently decided which of the two it saw.
    reported_districts = [] if sup.clears_districts else _drop_standby_districts(districts, norm)
    multi_targets = not impact and _multi_targets(reported_districts, norm)
    # An impact is a point strike, never a trajectory — same rule the map holds
    # (threatVisual.ts), applied here so the flag can't contradict it.
    movement = not impact and _movement_path(reported_districts, norm)
    # Confidence drops when we can't localize the target.
    if not reported_districts and status not in ("clear",):
        conf = min(conf, 0.3)

    return ParseResult(
        target_type=target_type,
        status=status,
        is_new_target=is_new,
        districts=reported_districts,
        confidence=round(conf, 2),
        target_count=target_count,
        raw_text=text,
        matched=matched,
        aftermath=aftermath,
        promo=promo,
        ad_action=ad_action,
        impact=impact,
        negated=negated,
        siren_only=siren_only,
        civic_notice=civic_notice,
        eppo_marks=eppo_marks,
        day_recap=day_recap,
        chatter=chatter,
        political_quote=political_quote,
        reportage=reportage,
        lost_signal=lost_signal,
        clear_scope=clear_scope,
        citywide=citywide,
        summary=summary,
        target_pulse=target_pulse,
        anticipated=anticipated,
        notice_kind=notice_kind,
        decoy=decoy,
        hypersonic=hypersonic,
        directional=directional,
        origin_key=origin.key if origin_present and origin is not None else None,
        origin_sector=origin.sector if origin_present and origin is not None else None,
        multi_targets=multi_targets,
        movement=movement,
    )
