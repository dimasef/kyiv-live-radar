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

from .matcher import DistrictHit, DistrictMatcher, normalize
from .vocab import (
    _AD_ACTION,
    _AFTERMATH,
    _BALLISTIC,
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
    _HYPERSONIC,
    _IMPACT,
    _JET,
    _LOST_WORD,
    _MASC_ONE_RE,
    _MISSILE,
    _NEGATION,
    _NEW_TARGET,
    _NEW_TARGET_COUNT_RE,
    _PULSE_WORD,
    _QUOTE_ATTRIBUTION_RE,
    _RETROSPECTIVE,
    _SHAHED,
    _SIREN_WORD,
    _SUMMARY,
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
    # A localized confirmed strike ("влучання ... в Дніпровському районі") — a
    # terminal marker to place on the map, NOT an active inbound target. Keeps
    # its district (unlike aftermath, which suppresses).
    impact: bool = field(default=False)
    negated: bool = field(default=False)
    siren_only: bool = field(default=False)
    day_recap: bool = field(default=False)
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


def _target_type(norm: str) -> str:
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
    and wins over an impact reading."""
    return (
        bool(districts)
        and any(k in norm for k in _IMPACT)
        and status not in ("clear", "destroyed")
        and not any(k in norm for k in _RETROSPECTIVE)
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


def _negated(norm: str, status: str) -> bool:
    """Explicit denial ("Не йде на Оболонь") mentions a district but says the
    target is NOT there — suppress it, same carve-out as aftermath: an
    explicit clear/destroyed keyword elsewhere in the message still wins (its
    own keyword signal is stronger evidence than a coincidental negation word).
    A conditional/speculative hedge ("якщо піде…", "у разі оголошення
    тривоги…") gets the same treatment — see _has_conditional_hedge."""
    return (
        any(k in norm for k in _NEGATION) or _has_conditional_hedge(norm)
    ) and status not in ("clear", "destroyed")


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
    return _LOST_WORD in norm and not districts and status not in ("clear", "destroyed")


def _summary(norm: str, target_type: str) -> bool:
    """Retrospective summary of the whole attack (aggregate/past-frame count) —
    info, not a live target. Blocks the city-alert / track it would otherwise
    raise. Only meaningful on a threat-flavoured message."""
    return any(k in norm for k in _SUMMARY) and (
        target_type != "unknown" or any(w in norm for w in _THREAT_CONTEXT)
    )


def _citywide(districts, status: str, norm: str, aftermath: bool, negated: bool,
              siren_only: bool, political_quote: bool, lost_signal: bool,
              summary: bool, ad_action: bool) -> bool:
    """City-wide threat: a city-level phrase with NO raion of its own — a strong
    directional phrase on its own, or a weak one plus a threat-context word.
    Only when nothing else localizes or supersedes it: a real district, an
    all-clear/destroyed, aftermath/negation/siren/quote, or a retrospective
    summary all take precedence. ingest.py turns this into ONE city-level alert."""
    return (
        not districts
        and status not in ("clear", "destroyed")
        and not (aftermath or negated or siren_only or political_quote
                 or lost_signal or summary or ad_action)
        and (
            any(p in norm for p in _CITYWIDE_STRONG)
            or (any(p in norm for p in _CITYWIDE_WEAK)
                and any(w in norm for w in _THREAT_CONTEXT))
        )
    )


def _target_pulse(districts, citywide: bool, status: str, norm: str, aftermath: bool,
                   negated: bool, siren_only: bool, political_quote: bool,
                   lost_signal: bool, summary: bool, ad_action: bool) -> bool:
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
                 or lost_signal or summary or ad_action)
        and len(norm.split()) <= 3
        and any(any(p in w for p in _PULSE_WORD) for w in norm.split())
    )


def _matched(districts, citywide: bool, status: str, aftermath: bool, negated: bool,
             siren_only: bool, political_quote: bool, ad_action: bool) -> bool:
    """No district and no actionable status -> nothing structured to record."""
    return (
        (bool(districts) or citywide or status in ("clear", "destroyed"))
        and not aftermath
        and not negated
        and not siren_only
        and not political_quote
        and not ad_action
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

    clear_scope = _clear_scope(status, target_type, norm)
    impact = _impact(districts, norm, status)
    aftermath = _aftermath(norm, status, impact)
    ad_action = _ad_action(norm, status, impact)
    negated = _negated(norm, status)
    siren_only = _siren_only(target_type, status, districts, norm)
    day_recap = _day_recap(target_type, status, districts, norm)
    if day_recap:
        conf = min(conf, 0.35)
    political_quote = _political_quote(target_type, status, districts, norm)
    lost_signal = _lost_signal(norm, districts, status)
    summary = _summary(norm, target_type)
    citywide = _citywide(districts, status, norm, aftermath, negated, siren_only,
                         political_quote, lost_signal, summary, ad_action)
    target_pulse = _target_pulse(districts, citywide, status, norm, aftermath, negated,
                                 siren_only, political_quote, lost_signal, summary, ad_action)
    matched = _matched(districts, citywide, status, aftermath, negated, siren_only,
                       political_quote, ad_action)

    if aftermath or negated or siren_only or political_quote or ad_action:
        districts = []
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
        impact=impact,
        negated=negated,
        siren_only=siren_only,
        day_recap=day_recap,
        political_quote=political_quote,
        lost_signal=lost_signal,
        clear_scope=clear_scope,
        citywide=citywide,
        summary=summary,
        target_pulse=target_pulse,
        decoy=decoy,
        hypersonic=hypersonic,
    )
