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
    _FPV,
    _GROUND_WAR,
    _HEDGE_MODAL_RE,
    _HYPERSONIC,
    _IMPACT,
    _JET,
    _JET_MODEL,
    _KAB,
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
    _MISSILE_WEAPON,
    _MOVEMENT_CUE,
    _NEGATION,
    _NEW_TARGET,
    _NEW_TARGET_COUNT_RE,
    _OWN_SCOPE_RE,
    _PATH_CONNECTIVE,
    _PATH_COUNT_BREAK,
    _PATH_FILLER,
    _PERSONAL_POST,
    _PHONE_RE,
    _POWER_OUTAGE,
    _PREPOSITION_BEFORE_DISTRICT,
    _PULSE_PREP_KNOWN,
    _PULSE_TARGET_PREP,
    _PULSE_WORD,
    _QUOTE_ATTRIBUTION_RE,
    _RAION_PHRASE_RE,
    _READINESS_RE,
    _RECON_ANALYSIS,
    _REPORTAGE,
    _RETROSPECTIVE,
    _SENTENCE_END_RE,
    _SIREN_WORD,
    _STANDDOWN_CLEAN_RE,
    _STANDDOWN_LIVE_THREAT,
    _SUMMARY,
    _SUMMARY_NO_DISTRICT,
    _THREAT_CONTEXT,
    _TOPONYM_WORD_RE,
    _UAV,
    _UNCONFIRMED,
    _UNSCOPED_CLEAR_WORD,
    count_value,
)


@dataclass
class LlmUsage:
    """Token usage + cost for one LLM call — recorded even when the call
    recovered nothing, since it still spent the budget."""

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
    # Gated by a weapon word, like the forecast rows, so it can't swallow a
    # terse real callout.
    if any(p in norm for p in _RECON_ANALYSIS) and any(w in norm for w in _THREAT_CONTEXT):
        return True
    # The relay phrases carry the advisory class on their own; the nominal
    # «підвищена загроза» and «ворога цікавлять» need a weapon word.
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
    target_type: str  # see models.TargetType
    status: str       # 'confirmed' | 'sighting' | 'unconfirmed' | 'destroyed' | 'clear'
    is_new_target: bool
    districts: list[DistrictHit]
    confidence: float
    target_count: int | None = None  # stated group size ("2х"), None if unstated
    raw_text: str = ""
    matched: bool = field(default=False)
    aftermath: bool = field(default=False)
    # The raions an AFTERMATH message named. `districts` above is empty for them
    # by design (`clears_districts`), so the aftermath layer needs its own field.
    aftermath_districts: list[DistrictHit] = field(default_factory=list)
    promo: bool = field(default=False)
    # Our air defence engaged — not an incoming target. Stored so ingest can keep
    # it out of the per-channel type context.
    ad_action: bool = field(default=False)
    # A localized confirmed strike — a terminal marker to place, NOT an active
    # inbound target. Keeps its district, unlike aftermath.
    impact: bool = field(default=False)
    negated: bool = field(default=False)
    siren_only: bool = field(default=False)
    civic_notice: bool = field(default=False)
    eppo_marks: bool = field(default=False)
    ground_war: bool = field(default=False)
    personal_post: bool = field(default=False)
    day_recap: bool = field(default=False)
    # Talk that NAMES a weapon without one being in the sky (buzz-slang,
    # explainer posts). Barely a suppressor — with no district it forms no track
    # either way — but it keeps the message out of type inheritance, which it
    # otherwise poisons ("реактивні бджілки" -> jet_drone), and out of the LLM.
    chatter: bool = field(default=False)
    political_quote: bool = field(default=False)
    reportage: bool = field(default=False)
    lost_signal: bool = field(default=False)
    # A city-level threat with no raion of its own — ingest raises ONE city-wide
    # alert instead of per-district tracks.
    citywide: bool = field(default=False)
    summary: bool = field(default=False)
    # A terse callout with no place — only acted on, as corroboration, when a
    # city-wide alert is already open.
    target_pulse: bool = field(default=False)
    # Speaks about a wave that has NOT arrived. Surfaces as a forecast notice but
    # must never set the channel's live target type: two such posts about a
    # possible NEXT ballistic wave relabelled the Kalibrs then in the air.
    anticipated: bool = field(default=False)
    # 'forecast' when a type's threat level is up, 'status' when it is quiet.
    # Never a live target and never an all-clear.
    notice_kind: str | None = field(default=None)
    # None = a genuine full clear, closing every open track. A target type = an
    # all-clear scoped to THAT type, which must not close unrelated tracks. Only
    # set when status == "clear".
    clear_scope: str | None = field(default=None)
    # Modifiers accumulated onto the incident (domain/attack.py), never a
    # replacement classification or a 6th target_type.
    decoy: bool = field(default=False)
    hypersonic: bool = field(default=False)
    # An origin callout with no Kyiv raion — ingest raises a directional AXIS,
    # not a track. origin_key/origin_sector are set only when this is True.
    directional: bool = field(default=False)
    origin_key: str | None = field(default=None)
    origin_sector: str | None = field(default=None)
    # 2+ districts as a bare enumeration = SIMULTANEOUS separate targets, one
    # track each. False for a movement frame, which is a route and stays one
    # track (the vector case).
    multi_targets: bool = field(default=False)
    # Runs of 2+ consecutive district indices joined by nothing but «/». Whether
    # a run is one target's sector or an enumeration is the channel's notation
    # (Source.sector_notation), decided at ingest, not here.
    slash_runs: list[list[int]] = field(default_factory=list)
    # A path was STATED between two named places, so the districts are waypoints
    # of one trajectory in text order. Display metadata only: it never changes
    # which track a sighting joins, it tells the map a single-timestamp track is
    # a real vector. Distinct from `multi_targets`, which is the NEGATIVE of the
    # same question and also False for a plain prepositional frame.
    movement: bool = field(default=False)


# Short keywords that are the head of an ordinary word — «каб» of «кабінет»,
# «реб» of «ребро», «шах» of «шахрай» — match as WHOLE words; everything else
# matches at a word start so inflected suffixes still hit (ракет→ракети). Every
# case form has to be listed explicitly, since a whole-word match carries no
# case tail of its own.
_WHOLE_WORD = {"каб", "каби", "кабів", "кабам", "кабами", "реб", "реби",
               "шах", "шаха", "шаху", "шахи", "шахів", "шахам", "шахами"}


def _kw_regex(words) -> re.Pattern:
    parts = []
    for w in words:
        esc = re.escape(w)
        if w in _WHOLE_WORD:
            parts.append(r"(?<![а-яіїєґ])" + esc + r"(?![а-яіїєґ])")
        else:
            parts.append(r"(?<![а-яіїєґ])" + esc)
    if not parts:
        # "|".join([]) matches at EVERY position, so an emptied keyword list
        # would label every message. Fail closed instead.
        return re.compile(r"(?!)")
    return re.compile("|".join(parts))


_BALLISTIC_RE = _kw_regex(_BALLISTIC)
_MISSILE_RE = _kw_regex(_MISSILE)
_KAB_RE = _kw_regex(_KAB)
_JET_MODEL_RE = _kw_regex(_JET_MODEL)
_JET_RE = _kw_regex(_JET)
_FPV_RE = _kw_regex(_FPV)
_UAV_RE = _kw_regex(_UAV)
_DECOY_RE = _kw_regex(_DECOY)
_HYPERSONIC_RE = _kw_regex(_HYPERSONIC)

# A type named only to DENY it ("це не БПЛА") must not type the message — the
# next callout would inherit that type from the channel context. Only the
# ADJACENT "не <type>" form is masked; a non-adjacent negation ("траєкторія не
# притаманна для «Іскандер-М»") still talks about that type for real.
_NEGATED_TYPE_RE = re.compile(
    r"(?<![а-яіїєґ])не\s+(?:"
    + "|".join(re.escape(w)
               for w in (*_BALLISTIC, *_MISSILE, *_KAB, *_JET_MODEL, *_JET, *_FPV, *_UAV))
    + r")[а-яіїєґ]*"
)


def _target_type(norm: str) -> str:
    norm = _NEGATED_TYPE_RE.sub(" ", norm)
    if _BALLISTIC_RE.search(norm):
        return "ballistic"
    # A named model or КАБ beats the generic "ракет" the same way ballistic does:
    # it identifies the weapon, while "ракета" is what a spotter reaches for when
    # they can't ("10 ракет Бандероль" is one message, and it is a jet drone).
    if _JET_MODEL_RE.search(norm):
        return "jet_drone"
    if _KAB_RE.search(norm):
        return "kab"
    if _MISSILE_RE.search(norm):
        return "missile"
    if _JET_RE.search(norm):
        return "jet_drone"
    # Below the missile/jet lists so the more severe reading wins when both are
    # named, above the generic drone one so the specific statement beats it.
    if _FPV_RE.search(norm):
        return "fpv"
    if _UAV_RE.search(norm):
        return "shahed"
    if _MASC_ONE_RE.search(norm):
        return "shahed"
    return "unknown"


def _place_follows(end: int, districts) -> bool:
    """Whether a gazetteer-matched place starts right where a phrase ended.

    This is what makes the bare-number count form safe: the number only counts
    when a KNOWN place follows it. The slack absorbs a stray quote or space."""
    return any(0 <= h.position - end <= 2 for h in districts)


def _target_count(norm: str, districts) -> int | None:
    """The largest sane group count stated in the text ("2х"->2, "3 ракети"->3).

    The size of ONE group flying together, an annotation on the track — it never
    fabricates N tracks, and the enumeration path refuses to stamp it per
    district (see handlers.py)."""
    def inside_a_name(pos: int) -> bool:
        """Whether the number at `pos` is part of a matched place's own name —
        the two plants are numbered, so «Йде на ТЕЦ-6 реактивний» read as six."""
        return any(h.position <= pos < h.end for h in districts)

    nums = [int(m.group(1)) for m in _COUNT_RE.finditer(norm)
            if not inside_a_name(m.start(1))]
    # Every rule below accepts a numeral WORD as well as digits, so the value has
    # to be resolved rather than int()'d (vocab._NUM_WORDS).
    nums += [count_value(m.group(1)) for m in _COUNT_NOUN_RE.finditer(norm)
             if not inside_a_name(m.start(1))]
    nums += [
        count_value(m.group(1))
        for m in _COUNT_TO_PLACE_RE.finditer(norm)
        if _place_follows(m.end(), districts) and not inside_a_name(m.start(1))
    ]
    nums += [count_value(m.group(1)) for m in _COUNT_MOVING_RE.finditer(norm)
             if not inside_a_name(m.start(1))]
    # The place-adjacent form. Its anchor is a gazetteer hit rather than a word,
    # so the scan lives here, and it uses the hit's real END — which is also what
    # puts a name's own number inside the span above.
    for h in districts:
        after = _COUNT_AFTER_PLACE_RE.match(norm[h.end:])
        if after and not inside_a_name(h.end + after.start(1)):
            nums.append(count_value(after.group(1)))
        before = _COUNT_BEFORE_PLACE_RE.search(norm[:h.position])
        if before and not inside_a_name(before.start(1)):
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
# The dependency chain (impact feeds aftermath/ad_action; the suppressor flags
# feed citywide/target_pulse/matched; district-clearing happens once, after
# matched) is load-bearing — do not reorder without re-running the eval gate. ---


# Where the "відбій of WHAT" relation ends: a stand-down names its scope right
# next to the word, and a clause boundary separates that from a type the message
# merely mentions. Em dashes are deliberately absent — «Приємна новина — відбій
# по балістиці» is one statement, not two.
_CLAUSE_SPLIT_RE = re.compile(r"[,.;:!?\n]+")


def _clear_scope(status: str, target_type: str, norm: str) -> str | None:
    """A clear/відбій is scoped to just the named type when the message states a
    missile-family type and doesn't ALSO say the siren itself ended — a ballistic
    stand-down must not close active cruise/shahed tracks, and vice versa.

    The type has to be the OBJECT of the stand-down, in the same clause as the
    word that made this a clear at all, not merely somewhere in the message. All
    29 real scoped stand-downs put it there; the two a looser rule also matched
    were saying the OPPOSITE («Поки відбій… балістика МОЖЕ ПОЛЕТІТИ в будь-який
    момент» ended a running attack and published a «Відбій» card while the city's
    alert was still open).

    Without a scope the message is an unscoped spotter відбій, which _dispatch
    deliberately treats as inert — so a hedged «поки відбій» closes nothing.
    """
    if status != "clear" or target_type not in ("ballistic", "missile"):
        return None
    if _UNSCOPED_CLEAR_WORD in norm:
        return None
    weapons = _BALLISTIC if target_type == "ballistic" else _MISSILE_WEAPON
    for clause in _CLAUSE_SPLIT_RE.split(norm):
        if any(c in clause for c in _CLEAR) and any(w in clause for w in weapons):
            return target_type
    return None


def _impact(districts, norm: str, status: str) -> bool:
    """A confirmed hit whose LOCATION we map as a terminal marker. Needs a
    district; a destroyed/clear keyword is a stronger, more specific status and
    wins. A power-outage notice also says "пошкодж" but that is grid damage —
    blocked unless an unambiguous strike word is present too, so it falls back to
    plain aftermath suppression."""
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
    """Consequence news mentions a district but is NOT a live target. Suppressed
    unless it is an all-clear (which legitimately closes tracks) or a localized
    impact (the strike location is the useful signal)."""
    return any(k in norm for k in _AFTERMATH) and status != "clear" and not impact


def _ad_action(norm: str, status: str, impact: bool) -> bool:
    """Air defence engaged over some districts — defensive action, not an
    incoming target. Suppressed so it never becomes a track, nor a bogus X→Y
    vector; a real strike keyword still wins via the impact carve-out."""
    return any(k in norm for k in _AD_ACTION) and status not in ("clear", "destroyed") and not impact


def _civic_notice(target_type: str, status: str, norm: str, impact: bool) -> bool:
    """A transport/utility notice naming a street or neighbourhood the gazetteer
    matches. Type-unknown only (a named threat is never a bus notice), with the
    aftermath carve-out, so a real strike report is never silenced by a
    coincidental transport word."""
    return (
        target_type == "unknown"
        and status not in ("clear", "destroyed")
        and not impact
        and any(k in norm for k in _CIVIC_NOTICE)
    )


def _eppo_marks(target_type: str, status: str, norm: str, impact: bool) -> bool:
    """єППО app marks the spotter RELAYS but DISMISSES as not seen on their own
    tracking — unverified, so the named districts must not become tracks.
    Requires BOTH an єППО mention AND a dismissal cue, so a genuine "єППО показує
    ціль на Троєщині, підтверджую" is untouched. Guarded like civic_notice."""
    return (
        target_type == "unknown"
        and status not in ("clear", "destroyed")
        and not impact
        and any(w in norm for w in _EPPO_WORD)
        and any(w in norm for w in _EPPO_DISMISS)
    )


def _negated(norm: str, status: str, impact: bool) -> bool:
    """Explicit denial ("Не йде на Оболонь") — a district named with the target
    NOT there. A conditional/speculative hedge gets the same treatment (see
    _has_conditional_hedge). The impact carve-out matters here: a confirmed
    strike report can use hedge words for an unrelated clause («під завалами
    можуть бути люди») and must not lose its real districts to that."""
    return (
        (any(k in norm for k in _NEGATION) or _has_conditional_hedge(norm))
        and status not in ("clear", "destroyed")
        and not impact
    )


def _reportage(norm: str, districts, status: str) -> bool:
    """Relayed news of a destruction somewhere we don't track — not a stand-down
    for any of OUR tracks. Every other suppressor is powerless here: a
    "destroyed" message deliberately bypasses them (a real «мінус» must always be
    able to close a track), and with no district of its own the destroyed handler
    adopts whichever track is open and closes a live one as «знищено».

    Gated on no-district AND destroyed, the two things that make a relayed item
    dangerous rather than merely noisy — a first-hand callout always localizes."""
    return any(k in norm for k in _REPORTAGE) and not districts and status == "destroyed"


def _ground_war(target_type: str, status: str, norm: str, impact: bool) -> bool:
    """Ground-war / disinformation news. It names border villages the gazetteer
    matches, but it is about the LAND front or about a russian claim, not about
    anything flying — each such post raised phantom air tracks.

    Guarded exactly like civic_notice, so a real callout that happens to use one
    of these words keeps its districts."""
    return (
        target_type == "unknown"
        and status not in ("clear", "destroyed")
        and not impact
        and any(k in norm for k in _GROUND_WAR)
    )


def _personal_post(norm: str, status: str, impact: bool) -> bool:
    """Personal prose from the channel admin that names places in passing.

    Deliberately NOT gated on target_type, unlike _ground_war: a personal post is
    one by register, not by whether it happens to name a weapon (the birthday
    post in the corpus reads `missile` off "не думати щодня про ракети"). The
    aftermath carve-out still applies."""
    return (
        any(k in norm for k in _PERSONAL_POST)
        and status not in ("clear", "destroyed")
        and not impact
    )


def _siren_only(target_type: str, status: str, districts, norm: str) -> bool:
    """Siren-status echo: names a place, mentions "тривога", states no target
    type at all. An explicit clear/destroyed keyword is still a real signal.

    The place is either a gazetteer hit or a bare raion phrase
    (_RAION_PHRASE_RE) — whether the raion's adjective happens to have a stem
    decided, for no good reason, whether the echo was suppressed or sent to the
    LLM."""
    return (
        target_type == "unknown"
        and status in ("sighting", "confirmed")
        and (bool(districts) or bool(_RAION_PHRASE_RE.search(norm)))
        and _SIREN_WORD in norm
    )


def _day_recap(target_type: str, status: str, districts, norm: str) -> bool:
    """Day-summary commentary: the same shape as siren_only, but "сьогодні"
    alone is not a clean enough marker to drop the district, so this only softens
    confidence instead of suppressing."""
    return (
        target_type == "unknown"
        and status == "sighting"
        and bool(districts)
        and _DAY_RECAP_WORD in norm
    )


def _political_quote(target_type: str, status: str, districts, norm: str) -> bool:
    """A news repost of an official's statement naming a place, not a spotter
    sighting. Same shape-gate as siren_only; a stated target type still wins."""
    return (
        target_type == "unknown"
        and status in ("sighting", "confirmed")
        and bool(districts)
        and bool(_QUOTE_ATTRIBUTION_RE.search(norm))
    )


def _lost_signal(norm: str, districts, status: str) -> bool:
    """"Дорозвідка": ППО no longer sees targets of the stated type — a real
    stand-down handled by ingest (it closes matching tracks), not a suppression
    like the flags above. Gated on no-district (see _LOST_WORD). A
    clear/destroyed keyword in the SAME message is the stronger, more specific
    signal and must win: «Мінуснули, Дорозвідка» is ONE target destroyed, and
    reading it as lost would close every open track instead."""
    if districts or status in ("clear", "destroyed"):
        return False
    # A live-threat continuation clause outranks the stand-down half — leaving
    # lost_signal unset lets the directional/origin path handle it.
    if any(k in norm for k in _STANDDOWN_LIVE_THREAT):
        return False
    if _LOST_WORD in norm:
        return True
    # The shorthand, but only when the message isn't scoped to another oblast.
    return bool(_STANDDOWN_CLEAN_RE.search(norm)) and not target_elsewhere(norm, districts)


def _summary(norm: str, target_type: str, has_district: bool) -> bool:
    """Retrospective summary of the whole attack — info, not a live target, so
    it blocks the city alert or track it would otherwise raise. Only meaningful
    on a threat-flavoured message.

    `_SUMMARY_NO_DISTRICT` markers count only when NO raion is named: "6
    балістичних вдарило по Києву" is a citywide recap, while a district-bearing
    "ракета вдарила по Троєщині" must stay a live impact."""
    if not (target_type != "unknown" or any(w in norm for w in _THREAT_CONTEXT)):
        return False
    if any(k in norm for k in _SUMMARY):
        return True
    if not has_district and any(k in norm for k in _SUMMARY_NO_DISTRICT):
        return True
    return False


def _promo(norm: str, status: str, impact: bool) -> bool:
    """A URL, a payment card, a phone number, a recruitment phrase or a donation
    frame makes a message promo/ad/meta, never a live callout — a spotter's
    sighting never links out or advertises. Aftermath carve-out applies."""
    return (
        (any(m in norm for m in _LINK_MARKERS) or bool(_CARD_NUMBER_RE.search(norm))
         or bool(_PHONE_RE.search(norm))
         or any(m in norm for m in _AD_RECRUIT) or any(m in norm for m in _ENGAGEMENT))
        and status not in ("clear", "destroyed")
        and not impact
    )


@dataclass(frozen=True)
class Suppressors:
    """Every message-level reason to hold something back, computed once.

    Passed whole rather than as positional bools, because each predicate used to
    re-list the subset it cared about and the lists drifted — `_target_pulse`
    dropped `promo`, so a recruitment line carrying a pulse word corroborated the
    live city-wide alert. The three subsets below are named once, here, next to
    the reason they differ.
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
    ground_war: bool
    personal_post: bool
    promo: bool
    reportage: bool
    day_recap: bool

    @property
    def blocks_surface(self) -> bool:
        """Reasons a message must not raise a live surface — a city-wide alert,
        a terse pulse, an origin axis or a level bulletin.

        `reportage` and `day_recap` are deliberately absent: one is a
        record-level judgement (see below), the other only softens confidence.
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
            or self.ground_war
            or self.personal_post
            or self.promo
        )

    @property
    def blocks_record(self) -> bool:
        """Reasons there is nothing structured to record at all (`matched`).

        Narrower than `blocks_surface`: `lost_signal` and `summary` are
        ACTIONABLE — `_dispatch` routes both to their own handlers before the
        matched check — so suppressing them here would drop a stand-down.
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
            or self.ground_war
            or self.personal_post
            or self.reportage
        )

    @property
    def clears_districts(self) -> bool:
        """Reasons the matched raions must be dropped from the result.

        `blocks_record` minus `reportage`: a news report still names a real
        place, and the hits stay for the gazetteer/eval tooling.
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
            or self.ground_war
            or self.personal_post
        )


def _level_notice(target_type: str, districts, citywide: bool, directional: bool, status: str,
                  norm: str, target_count: int | None, sup: Suppressors) -> str | None:
    """Threat-level bulletin about a target TYPE with nothing to localize —
    'forecast' (the level is up) or 'status' (that type is quiet, is somewhere in
    the oblast, or arrives as a bare count). Requires a named type: an untyped
    "поки тихо" is chatter, "по балістиці тихо" is the standing bulletin.

    Everything that localizes or supersedes wins first — a raion, a city-wide
    callout, an origin (by far the commonest shape of this sentence), a
    clear/destroyed, any suppressor — so this only fires where the message would
    otherwise have produced nothing. A pulse-shaped bulletin keeps BOTH flags:
    with a city alert open it corroborates as a pulse, and only the fall-through
    reaches the notice branch in _dispatch."""
    if (districts or citywide or directional or target_type == "unknown"
            or status in ("clear", "destroyed")):
        return None
    if sup.blocks_surface:
        return None
    # Someone else's bulletin. `target_not_kyiv`, not `target_elsewhere`: one
    # about the watched north is still not about Kyiv, which is what this card
    # claims to be — unless the message claims our scope outright, making the
    # foreign oblast the contrast half of "quiet here, busy there".
    if target_not_kyiv(norm, districts) and not _OWN_SCOPE_RE.search(norm):
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
    # A stated COUNT with nowhere to put it — during a salvo this number IS the
    # situation. Terse counts arriving while a city alert is open never get here:
    # _dispatch runs the pulse handler first.
    if target_count is not None:
        return "status"
    return None


def _citywide(districts, status: str, norm: str, sup: Suppressors) -> bool:
    """A city-level phrase with NO raion of its own — a strong phrase alone, or a
    weak one plus a threat-context word. Only when nothing else localizes or
    supersedes it; ingest turns this into ONE city-level alert."""
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
    """A word in TARGET position after a place preposition that the gazetteer did
    NOT match ("Реактивний біля Пирятина").

    The message names somewhere we don't know, and pulsing it would credit the
    open KYIV city alert with that somewhere's sighting — one step past what
    `target_not_kyiv` can see, which knows oblast names rather than unrecognized
    settlements.

    Only the preposition form is caught: a bare trailing toponym ("Виліз
    реактивний Тростянка") reads like a target word to every rule we have and
    still pulses — a pre-existing limit of the pulse shape."""
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
    """A bare denial of the type ("Не реактивні") — the spotter is correcting
    what is in the sky, not calling a target in. `_negated` misses it: its
    vocabulary expects a verb, and two words don't give it one."""
    return any(prev == "не" and any(p in word for p in _PULSE_WORD)
               for prev, word in zip(words, words[1:], strict=False))


def _target_pulse(districts, citywide: bool, status: str, norm: str,
                  sup: Suppressors) -> bool:
    """A very short callout naming a target or launch but no place. The length
    cap keeps out longer status prose, and every suppressor flag is excluded so a
    negated/recap line never pulses. ingest only ACTS on this when a city-wide
    alert is already open — alone it is too terse to localize."""
    words = _pulse_tokens(norm)
    return (
        not districts
        and not citywide
        and status not in ("clear", "destroyed")
        and not sup.blocks_surface
        and len(norm.split()) <= 3
        and any(any(p in w for p in _PULSE_WORD) for w in norm.split())
        # A pulse corroborates the KYIV city-wide alert, so anything scoped to
        # another region — watched or not — must not pulse: «Ціль на Сумщині»
        # fits the shape exactly and once pushed a Kyiv card's confidence up.
        and not target_not_kyiv(norm, districts)
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
    target over — the raions governed by a «готовність».

    The marker governs forward to the end of its sentence, and backward only when
    it sits immediately after a raion with nothing but a space between. That
    tight backward window is what separates it from «Пухівка/Зазимʼя 🔴 та
    готовність Бровари», where the two before the marker are the sighting. A
    coordinated list right before the marker goes on standby whole."""
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
    sighting, so nothing is lost: it still surfaces where the target was seen.

    When EVERY raion is on standby the list is left alone: dropping it would
    delete the message from the feed entirely, and a heads-up the operator can
    see beats a track he has to discount. Representing that properly is a product
    decision, not a parser one."""
    if not districts:
        return districts
    standby = _standby_districts(districts, norm)
    if not standby or len(standby) == len(districts):
        return districts
    return [h for i, h in enumerate(districts) if i not in standby]


def _slash_runs(districts, norm: str) -> list[list[int]]:
    runs: list[list[int]] = []
    for i, h in enumerate(districts):
        if runs and i == runs[-1][-1] + 1:
            prev = districts[i - 1]
            gap = norm[(prev.end or prev.position + prev.stem_len):h.position]
            if gap.strip() and set(gap.strip()) <= {"/"}:
                runs[-1].append(i)
                continue
        runs.append([i])
    return [r for r in runs if len(r) > 1]


def _multi_targets(districts, norm: str) -> bool:
    """A bare enumeration of 2+ districts = simultaneous separate targets. Any
    movement cue, or any district in a prepositional phrase, reads as a
    located/route frame instead — one track."""
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
    hits («Мамекине [на] Смяч»), so the hits — already in text order — are
    waypoints of one trajectory. A bare enumeration has no connective in the gap
    and stays False.

    Positive-signal-only on purpose: `not multi_targets` would be far broader (it
    is also False for a located frame stating no path).

    The connective alone is far too weak, so three guards, each earned from a
    real false positive:
      * a sentence or line break ends the statement («повз Десну на південь. Ще
        один реактивний…» is two targets);
      * a count inside the gap makes it a distribution, not a path;
      * what follows the connective must be the destination, not a threat noun
        («через БпЛА»).
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
                    districts,
                    sup: Suppressors) -> bool:
    """A curated inbound origin in FROM-position on a threat-flavoured,
    non-suppressed message. Set whether or not the message ALSO localizes, so
    "Балістика на Київ з Брянщини" raises the city alert AND a NE wedge. The axis
    is raised from this; `directional` below marks the standalone case."""
    return (
        origin is not None
        and status not in ("clear", "destroyed")
        and (target_type != "unknown" or any(w in norm for w in _THREAT_CONTEXT))
        and not target_elsewhere(norm, districts)  # "з Чернігівщини курсом на Дніпро" -> not ours
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
    # Unconditional: a decoy/hypersonic mention is worth accumulating onto the
    # incident even on an otherwise-terse or suppressed message.
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
    ground_war = _ground_war(target_type, status, norm, impact)
    personal_post = _personal_post(norm, status, impact)
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
        ground_war=ground_war,
        personal_post=personal_post,
        promo=promo,
        reportage=reportage,
        day_recap=day_recap,
    )
    citywide = _citywide(districts, status, norm, sup)
    target_pulse = _target_pulse(districts, citywide, status, norm, sup)
    origin = match_origin(norm)
    origin_present = _origin_present(origin, status, target_type, norm, districts, sup)
    # An origin with nothing else to localize on. When a raion/citywide IS also
    # present, origin still feeds a secondary axis, but that branch owns the
    # track/alert.
    directional = origin_present and not districts and not citywide
    notice_kind = _level_notice(target_type, districts, citywide, directional, status, norm,
                                target_count, sup)
    anticipated = notice_kind == "forecast" and _LEVEL_AHEAD_RE.search(norm) is not None
    matched = _matched(districts, citywide, status, sup)

    # Two distinct district lists, named rather than one variable reassigned
    # mid-function — reassigning meant the LINE a predicate sat on silently
    # decided which of the two it saw. Everything above consumes `districts`
    # (every raion the gazetteer matched: "did this message name a place at
    # all?"); everything below consumes the reported set, because a suppressed
    # message reports nowhere and a «готовність» raion is not a sighting.
    reported_districts = [] if sup.clears_districts else _drop_standby_districts(districts, norm)
    # The third list, and the only one an aftermath message keeps: standby still
    # drops out, but `clears_districts` is skipped — which is the whole point.
    aftermath_districts = (
        _drop_standby_districts(districts, norm) if aftermath else []
    )
    multi_targets = not impact and _multi_targets(reported_districts, norm)
    # An impact is a point strike, never a trajectory — the same rule the map
    # holds, applied here so the flag can't contradict it.
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
        aftermath_districts=aftermath_districts,
        promo=promo,
        ad_action=ad_action,
        impact=impact,
        negated=negated,
        siren_only=siren_only,
        civic_notice=civic_notice,
        eppo_marks=eppo_marks,
        ground_war=ground_war,
        personal_post=personal_post,
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
        slash_runs=_slash_runs(reported_districts, norm) if multi_targets else [],
        movement=movement,
    )
