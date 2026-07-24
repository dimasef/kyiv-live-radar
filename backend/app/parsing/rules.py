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

from ..domain.origins import Origin, match_origin, target_elsewhere
from .matcher import DistrictHit, DistrictMatcher, normalize


@dataclass
class LlmUsage:
    """Token usage + cost for one LLM fallback call — recorded regardless of
    whether the call recovered a usable district, since a call that found
    nothing still spent the budget. See parsing/llm.py::llm_extract."""

    input_tokens: int
    output_tokens: int
    cost_usd: float
from .vocab import (
    _AD_ACTION,
    _AD_RECRUIT,
    _ADVISORY_RELAY,
    _AFTERMATH,
    _BALLISTIC,
    _BUZZ_CHATTER,
    _CARD_NUMBER_RE,
    _CIVIC_NOTICE,
    _CITYWIDE_STRONG,
    _CITYWIDE_WEAK,
    _CLEAR,
    _CLEAR_ANTICIPATION,
    _CONDITIONAL_CONSEQUENCE,
    _CONDITIONAL_IDIOM_EXCLUDE,
    _CONDITIONAL_PHRASES,
    _CONFIRMED,
    _COUNT_NOUN_RE,
    _COUNT_RE,
    _DAY_RECAP_WORD,
    _DECOY,
    _DESTROYED,
    _EPPO_DISMISS,
    _EPPO_WORD,
    _FORECAST_TIMEFRAME,
    _FORECAST_VERB,
    _HEDGE_MODAL_RE,
    _HYPERSONIC,
    _IMPACT,
    _JET,
    _LINK_MARKERS,
    _LOST_WORD,
    _MASC_ONE_RE,
    _MISSILE,
    _MOVEMENT_CUE,
    _NEGATION,
    _NEW_TARGET,
    _NEW_TARGET_COUNT_RE,
    _POWER_OUTAGE,
    _PREPOSITION_BEFORE_DISTRICT,
    _PULSE_WORD,
    _QUOTE_ATTRIBUTION_RE,
    _RETROSPECTIVE,
    _SHAHED,
    _SIREN_WORD,
    _STANDDOWN_CLEAN_RE,
    _STANDDOWN_LIVE_THREAT,
    _SUMMARY,
    _SUMMARY_NO_DISTRICT,
    _THREAT_CONTEXT,
    _UNCONFIRMED,
    _UNSCOPED_CLEAR_WORD,
)


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
    # Advisory / relayed-opinion preview of which raions MIGHT be hit — see
    # _ADVISORY_RELAY. The relay/warning phrases carry the class on their own;
    # the nominal «підвищена загроза» and «ворога цікавлять» speculation need a
    # co-occurring weapon word (same gate as the forecast rows above).
    if any(p in norm for p in _ADVISORY_RELAY):
        return True
    if "підвищен" in norm and "загроз" in norm and any(w in norm for w in _THREAT_CONTEXT):
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
    # Spotter buzz-slang ("бджілки"/"бджоли" = drones) in casual reassurance
    # chatter — must not set/consume the per-channel live target-type context
    # (see ingest._note_and_inherit_type). Not a suppressor: with no district it
    # forms no track anyway; this flag exists purely to keep it out of type
    # inheritance, which it otherwise poisons ("реактивні бджілки" -> jet_drone).
    chatter: bool = field(default=False)
    political_quote: bool = field(default=False)
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
    return re.compile("|".join(parts))


_BALLISTIC_RE = _kw_regex(_BALLISTIC)
_MISSILE_RE = _kw_regex(_MISSILE)
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
    + "|".join(re.escape(w) for w in (*_BALLISTIC, *_MISSILE, *_JET, *_SHAHED))
    + r")[а-яіїєґ]*"
)


def _target_type(norm: str) -> str:
    norm = _NEGATED_TYPE_RE.sub(" ", norm)
    if _BALLISTIC_RE.search(norm):
        return "ballistic"
    if _MISSILE_RE.search(norm):
        return "missile"
    if _JET_RE.search(norm):
        return "jet_drone"
    if _SHAHED_RE.search(norm):
        return "shahed"
    if _MASC_ONE_RE.search(norm):
        return "shahed"
    return "unknown"


def _target_count(norm: str) -> int | None:
    """The largest sane group count stated in the text ("2х"->2, "3 ракети"->3)."""
    nums = [int(m.group(1)) for m in _COUNT_RE.finditer(norm)]
    nums += [int(m.group(1)) for m in _COUNT_NOUN_RE.finditer(norm)]
    nums = [n for n in nums if 1 <= n <= 50]  # ignore junk like "100х"/years
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
    """A message carrying a URL, a bare payment-card number, or a link-less
    channel-recruitment phrase (_AD_RECRUIT) is promo / donation / channel-boost
    / ad / meta, never a live target callout — a spotter's sighting never links
    out or advertises (validated against the real corpus: zero such sightings).
    Suppress it like aftermath: a real clear/destroyed keyword or a confirmed
    impact in the same message still wins."""
    return (
        (any(m in norm for m in _LINK_MARKERS) or bool(_CARD_NUMBER_RE.search(norm))
         or any(m in norm for m in _AD_RECRUIT))
        and status not in ("clear", "destroyed")
        and not impact
    )


def _citywide(districts, status: str, norm: str, aftermath: bool, negated: bool,
              siren_only: bool, political_quote: bool, lost_signal: bool,
              summary: bool, ad_action: bool, civic_notice: bool,
              eppo_marks: bool) -> bool:
    """City-wide threat: a city-level phrase with NO raion of its own — a strong
    directional phrase on its own, or a weak one plus a threat-context word.
    Only when nothing else localizes or supersedes it: a real district, an
    all-clear/destroyed, aftermath/negation/siren/quote, a civic notice, or a
    retrospective summary all take precedence. ingest.py turns this into ONE
    city-level alert."""
    return (
        not districts
        and status not in ("clear", "destroyed")
        and not (aftermath or negated or siren_only or political_quote
                 or lost_signal or summary or ad_action or civic_notice
                 or eppo_marks)
        and (
            any(p in norm for p in _CITYWIDE_STRONG)
            or (any(p in norm for p in _CITYWIDE_WEAK)
                and any(w in norm for w in _THREAT_CONTEXT))
        )
    )


def _target_pulse(districts, citywide: bool, status: str, norm: str, aftermath: bool,
                   negated: bool, siren_only: bool, political_quote: bool,
                   lost_signal: bool, summary: bool, ad_action: bool,
                   civic_notice: bool, eppo_marks: bool) -> bool:
    """Terse target/launch pulse: a very short callout ("Ціль!", "Ще вихід",
    "Групова ціль", "3 ракети") naming a target/launch but no place. The
    length cap keeps out longer sentences (which are usually status prose,
    e.g. "Наразі повторні цілі відсутні…"), and all the suppressor flags are
    excluded so a negated/recap line never pulses. ingest.py only ACTS on this
    when a city-wide alert is already open — alone it's too terse to localize."""
    return (
        not districts
        and not citywide
        and status not in ("clear", "destroyed")
        and not (aftermath or negated or siren_only or political_quote
                 or lost_signal or summary or ad_action or civic_notice
                 or eppo_marks)
        and len(norm.split()) <= 3
        and any(any(p in w for p in _PULSE_WORD) for w in norm.split())
    )


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


def _origin_present(origin: Origin | None, status: str, target_type: str, norm: str,
                    aftermath: bool, negated: bool, siren_only: bool,
                    political_quote: bool, lost_signal: bool, summary: bool,
                    ad_action: bool, civic_notice: bool, eppo_marks: bool,
                    promo: bool) -> bool:
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
        and not (aftermath or negated or siren_only or political_quote
                 or lost_signal or summary or ad_action or civic_notice
                 or eppo_marks or promo)
    )


def _matched(districts, citywide: bool, status: str, aftermath: bool, negated: bool,
             siren_only: bool, political_quote: bool, ad_action: bool, promo: bool,
             civic_notice: bool, eppo_marks: bool) -> bool:
    """No district and no actionable status -> nothing structured to record."""
    return (
        (bool(districts) or citywide or status in ("clear", "destroyed"))
        and not aftermath
        and not negated
        and not siren_only
        and not political_quote
        and not ad_action
        and not promo
        and not eppo_marks
        and not civic_notice
    )


def parse_message(text: str, matcher: DistrictMatcher) -> ParseResult:
    norm = normalize(text)
    target_type = _target_type(norm)
    status, conf = _status(text, norm)
    is_new = any(k in norm for k in _NEW_TARGET) or bool(_NEW_TARGET_COUNT_RE.search(norm))
    target_count = _target_count(norm)
    districts = matcher.find(norm)
    # Unconditional modifier flags — computed regardless of matched/
    # suppression status, since a decoy/hypersonic mention is worth
    # accumulating onto the incident even on an otherwise-terse message.
    decoy = bool(_DECOY_RE.search(norm))
    hypersonic = bool(_HYPERSONIC_RE.search(norm))
    chatter = any(w in norm for w in _BUZZ_CHATTER)

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
    lost_signal = _lost_signal(norm, districts, status)
    summary = _summary(norm, target_type, bool(districts))
    promo = _promo(norm, status, impact)
    citywide = _citywide(districts, status, norm, aftermath, negated, siren_only,
                         political_quote, lost_signal, summary, ad_action, civic_notice,
                         eppo_marks)
    target_pulse = _target_pulse(districts, citywide, status, norm, aftermath, negated,
                                 siren_only, political_quote, lost_signal, summary,
                                 ad_action, civic_notice, eppo_marks)
    origin = match_origin(norm)
    origin_present = _origin_present(origin, status, target_type, norm, aftermath, negated,
                                     siren_only, political_quote, lost_signal, summary,
                                     ad_action, civic_notice, eppo_marks, promo)
    # Standalone directional: an origin with nothing else to localize on — the
    # primary "загроза з Брянська" class. When a raion/citywide IS also present,
    # origin still feeds a secondary axis but that branch handles the track/alert.
    directional = origin_present and not districts and not citywide
    matched = _matched(districts, citywide, status, aftermath, negated, siren_only,
                       political_quote, ad_action, promo, civic_notice, eppo_marks)

    if (aftermath or negated or siren_only or political_quote or ad_action or promo
            or civic_notice or eppo_marks):
        districts = []
    multi_targets = not impact and _multi_targets(districts, norm)
    # Confidence drops when we can't localize the target.
    if not districts and status not in ("clear",):
        conf = min(conf, 0.3)

    return ParseResult(
        target_type=target_type,
        status=status,
        is_new_target=is_new,
        districts=districts,
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
        lost_signal=lost_signal,
        clear_scope=clear_scope,
        citywide=citywide,
        summary=summary,
        target_pulse=target_pulse,
        decoy=decoy,
        hypersonic=hypersonic,
        directional=directional,
        origin_key=origin.key if origin_present and origin is not None else None,
        origin_sector=origin.sector if origin_present and origin is not None else None,
        multi_targets=multi_targets,
    )
