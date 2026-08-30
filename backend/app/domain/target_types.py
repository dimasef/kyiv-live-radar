"""The rules every layer needs about target types: which ones are the same kind
of thing, which of two labels for one target wins, and which types can reach a
given region at all.

The first two were written out three times over (fusion, axes, ingest.context),
and the axes copy's docstring said "Mirror ingest._upgrade_type" — an invitation
for the two to drift. They are one rule each, so they live once, here.
"""

from __future__ import annotations

# Weapons whose reach is short enough that the region decides whether they are
# possible at all. An FPV is an operator's copter with a ~20 km radius; a KAB is
# a glide bomb released from an aircraft that has to survive the approach, so
# both stay inside a belt along the front and the border.
#
# Measured over the whole stored corpus (13.9k messages), counting only types
# the RULES read out of a message's own text:
#
#   region      typed msgs    kab            fpv
#   kyiv           1814       1 (0.06%)*     0
#   chernihiv       195       0              0
#   sumy            178      50 (28.1%)     16 (9.0%)
#   kharkiv         127      19 (15.0%)      7 (5.5%)
#
#   * the single Kyiv "kab" is a fundraising post about the Запорізький
#     напрямок, i.e. not a Kyiv target at all.
#
# And in the live DB: of 2739 Kyiv+Chernihiv tracks, the only `kab` ones are the
# nine of 2026-08-30 06:54-07:10, where one classifier verdict over Ріпки
# propagated down the channel's inheritance chain. That is the entire history of
# these two types over the home regions — an error, and nothing else.
_REACH_LIMITED: dict[str, frozenset[str]] = {
    "kab": frozenset({"sumy", "kharkiv"}),
    "fpv": frozenset({"sumy", "kharkiv"}),
}


def type_plausible_in(target_type: str, region: str | None) -> bool:
    """Whether a target of this type can be over this region at all.

    Gates only what the pipeline INFERS — the classifier's verdict, the incident
    prior, a type inherited from an earlier message. A type the rules read out
    of a message's own words is first-hand testimony and is never overruled
    here: if a Чернігівщина spotter writes «КАБ по Семенівці», the map should say
    KAB, and that message is also how this table would learn it was wrong.

    An unknown region (a message that localized nowhere and whose channel has no
    binding) is permissive — the check exists to stop a wrong guess, not to add
    a new way to lose a type.
    """
    reachable = _REACH_LIMITED.get(target_type)
    return reachable is None or region is None or region in reachable


def family(target_type: str) -> str:
    """Collapse target types to a family.

    Ballistic is a specialization of missile, and jet_drone and fpv of a generic
    drone
    callout (a bare «БпЛА» parses as shahed, so «Реактивний БпЛА» + «БпЛА» about
    one target flagged a false conflict — track 274, 2026-07-18). Used for
    fusion's conflict detection, for axis matching (a ballistic wedge and a bare
    missile wedge on one bearing are the same inbound threat at different
    specificity) and by attack.py::classify.

    Trade-off: a genuine «Шахед!» vs «Реактивний!» disagreement no longer flags
    — no real case of that in the corpus, while the specificity mismatch is live.
    """
    if target_type in ("missile", "ballistic"):
        return "missile"
    if target_type in ("shahed", "jet_drone", "fpv"):
        return "drone"
    # `kab` is its OWN family, unlike the pairs above. It is not a specificity
    # step below «ракета» the way ballistic is: a cruise missile over Сумщина and
    # a glide bomb over Сумщина are two different things happening, and a feed
    # that says both about one target is disagreeing, not refining. Fusion should
    # surface that.
    return target_type


def upgrade_type(current: str, new: str) -> str:
    """The target type a track (or axis) should hold given a newly stated type.

    Upgrade `unknown` to any stated type; and within the missile family upgrade
    the generic `missile` to the more specific, more severe `ballistic` (a bare
    "8 ракет" followed by "8 балістичних С-400" is the SAME salvo, better
    identified). Never cross families (a shahed track stays shahed even if a
    missile event lands — that genuine disagreement is surfaced as a conflict by
    fusion, not silently overwritten).
    """
    if current == "unknown":
        return new
    if {current, new} == {"missile", "ballistic"}:
        return "ballistic"
    # Same shape one family over: the Сумщина feed opens with a bare «невідомий
    # БпЛа» (which types `shahed`) and names the FPV a callout or two later.
    if {current, new} == {"shahed", "fpv"}:
        return "fpv"
    return current
