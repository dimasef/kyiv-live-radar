"""Attack classification — derived from an Incident's accumulated member
data at serialization time, never stored itself (see models.Incident.
attack_types/decoy_mentions/has_hypersonic, accumulated in incidents.py).
"""

from __future__ import annotations

from dataclasses import dataclass

# Weapon families for classification. Deliberately NOT collapsed the way
# fusion.py collapses missile/ballistic for conflict-detection — a real
# combined raid of shaheds AND ballistic missiles together must read as
# "combined", not just "ballistic".
_FAMILIES: dict[str, set[str]] = {
    "drone": {"shahed", "jet_drone"},
    "cruise_missile": {"missile"},
    "ballistic": {"ballistic"},
}
_TYPE_TO_FAMILY = {t: fam for fam, types in _FAMILIES.items() for t in types}


@dataclass
class Classification:
    label: str  # 'drone' | 'cruise_missile' | 'ballistic' | 'combined' | 'unknown'
    decoy_suspected: bool
    has_hypersonic: bool


def classify(attack_types: list[str], decoy_mentions: int, has_hypersonic: bool) -> Classification:
    """`attack_types` is the incident's accumulated set of non-'unknown'
    member target_types (see incidents.py::attach_to_incident) — this just
    maps that set to a family label, ≥2 distinct families being 'combined'.

    Known limitation: attach_to_incident accumulates on every attach, so a
    single track upgraded mid-flight (missile -> ballistic, see ingest.py
    ::_upgrade_type) can leave BOTH the generic and specific type in
    attack_types, reading as a false 'combined'. Accepted for the MVP — the
    plan calls for a flat accumulated set, not per-track provenance.
    """
    families = {_TYPE_TO_FAMILY[t] for t in attack_types if t in _TYPE_TO_FAMILY}
    if not families:
        label = "unknown"
    elif len(families) >= 2:
        label = "combined"
    else:
        label = next(iter(families))
    return Classification(
        label=label, decoy_suspected=decoy_mentions > 0, has_hypersonic=has_hypersonic
    )
