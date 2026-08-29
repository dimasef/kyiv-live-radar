"""The two rules every layer needs about target types: which ones are the same
kind of thing, and which of two labels for one target wins.

Both were written out three times over (fusion, axes, ingest.context), and the
axes copy's docstring said "Mirror ingest._upgrade_type" — an invitation for the
two to drift. They are one rule each, so they live once, here.
"""

from __future__ import annotations


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
