"""The region registry and everything derived from it.

The point of these tests is that declaring a region must be inert until someone
flips `active` — the parser's behaviour on the live feed cannot move because a
name was added to a tuple.
"""

from app.domain import alert_zones, origins
from app.parsing import llm, vocab
from app.regions import (
    HOME_REGION,
    HOME_SPEC,
    REGION_SPECS,
    REGIONS,
    SPEC_BY_ID,
    active_regions,
    label,
    watched_regions,
)

# Copied verbatim from the source before the registry existed. A change here is
# a change to what the parser suppresses on the live feed — never update these
# to match new output, work out why the output moved.
#
# Updated once, deliberately: activating Сумщина (2026-08-28) moved its five
# stems from the first tuple to the second, which is the whole point of the
# split and what `test_activating_a_region_moves_its_stems_from_other_to_watched`
# rehearses. Everything else is still verbatim.
FROZEN_OTHER_OBLAST = (
    "брянщин", "курщин", "ростов", "воронеж", "воронєж",
    "дніпропетровщин", "дніпро", "запоріжж", "миколаївщин",
    "полтавщин", "харківщин", "харков", "білорус", "крим",
    "житомирщин", "вінницьк", "вінниччин", "вінничин",
    "черкащин", "одещин", "херсонщин",
    "черкас", "полтав", "житомирську обл",
    "житомирської обл", "жашків", "одес", "миколаїв",
    "львівщин", "дрогобич", "самбір", "стрий", "рівненщин", "волин",
    "тернопільщин", "тернопіл", "закарпат", "франківськ",
    "хмельниччин", "хмельницьк", "кіровоградщин", "донеччин",
    "луганщин", "чернівц", "буковин",
    "польщ", "люблін", "молдов", "румун",
    "пирятин", "кропивницьк",
)
FROZEN_WATCHED_OBLAST = ("чернігівщин", "чернігів", "ніжин", "прилук",
                         "сумщин", "суми", "сумах", "конотоп", "ромн")


def test_every_declared_region_has_a_spec():
    assert set(REGIONS) == {s.id for s in REGION_SPECS}
    assert len(SPEC_BY_ID) == len(REGION_SPECS)
    assert HOME_SPEC.id == HOME_REGION


def test_the_home_region_declares_no_threat_stems():
    """Kyiv is never 'elsewhere'. Empty here means no derivation can ever put
    the home region into a suppression list."""
    assert HOME_SPEC.threat_stems == ()
    assert HOME_SPEC not in watched_regions()


def test_no_two_regions_claim_the_same_oblast_name():
    names = [o for s in REGION_SPECS for o in s.oblasts]
    assert len(names) == len(set(names))


def test_the_suppression_lists_match_the_active_roster():
    assert origins._OTHER_OBLAST == FROZEN_OTHER_OBLAST
    assert origins._WATCHED_OBLAST == FROZEN_WATCHED_OBLAST


# What `_OTHER_OBLAST` held before Сумщина was activated — its five stems, back
# in the tuple they used to sit in. Kept so the split still has something real
# to be rehearsed against now that the live lists are on the far side of it.
PRE_SUMY_OTHER_OBLAST = FROZEN_OTHER_OBLAST + ("сумщин", "суми", "сумах",
                                               "конотоп", "ромн")


def test_activating_a_region_moves_its_stems_from_other_to_watched():
    """The whole activation, played out without flipping a flag."""
    other, watched = origins.split_oblast_stems(
        PRE_SUMY_OTHER_OBLAST, ("сумщин", "суми", "сумах", "конотоп", "ромн")
    )
    assert "сумщин" not in other and "конотоп" not in other and "ромн" not in other
    assert "сумщин" in watched
    # Everything else is untouched — activation is not a rewrite.
    assert "брянщин" in other and "полтав" in other
    assert len(other) == len(PRE_SUMY_OTHER_OBLAST) - 5


def test_activating_a_region_does_not_touch_stems_it_does_not_own():
    other, _ = origins.split_oblast_stems(PRE_SUMY_OTHER_OBLAST, ("харківщин", "харков"))
    assert "дніпро" in other and "суми" in other


def test_a_stem_a_watched_region_never_had_still_ends_up_watched():
    """Чернігівщина's stems are not in the curated list at all — they were
    removed when the north was added — so the split has to pass them through."""
    _, watched = origins.split_oblast_stems(FROZEN_OTHER_OBLAST, ("чернігівщин", "чернігів"))
    assert watched == ("чернігівщин", "чернігів")


def test_the_oblast_city_stems_come_from_the_registry():
    assert vocab._OBLAST_CITY_STEMS == frozenset({"черніг"})
    assert vocab._OBLAST_CITY_STEMS == frozenset(
        s for spec in REGION_SPECS for s in spec.oblast_city_stems
    )


def test_every_zone_maps_to_a_declared_region():
    for zone in alert_zones.ZONES:
        assert alert_zones.region_of(zone) in REGIONS
    assert alert_zones.region_of(alert_zones.ZONES[0]) == "kyiv"


def test_watched_oblasts_stay_derived_from_the_zone_roster():
    """Not from the registry: a region declared without a raion roster must stay
    invisible to the siren provider instead of warning once per unknown raion."""
    assert alert_zones.WATCHED_OBLASTS == frozenset(z.oblast for z in alert_zones.ZONES)


def test_the_prompt_names_every_active_watched_region():
    system = llm._system(False)
    for spec in watched_regions():
        assert spec.name_uk in system
    assert f"other than the {llm.active_count_word()} watched ones" in system


def test_the_prompt_does_not_claim_an_inactive_region_is_watched():
    system = llm._system(False)
    for spec in REGION_SPECS:
        if not spec.active:
            assert f"AND over {spec.name_uk}" not in system


def test_label_falls_back_to_the_raw_id():
    assert label("kyiv") == "Київщина"
    assert label("atlantis") == "atlantis"


def test_active_regions_is_a_subset_of_declared_ones():
    assert {s.id for s in active_regions()} <= set(REGIONS)


# --- Per-type tables ---------------------------------------------------------
# `TargetType` is a Literal, so mypy/Pydantic check that every VALUE used is a
# valid type — but nothing checks the reverse, that every type has a row in the
# tables that decide how it behaves. Adding `fpv` (2026-08-28) touched eleven of
# them; this is what makes the twelfth fail loudly instead of silently falling
# back to a default meant for something else.

def test_every_target_type_has_a_row_in_every_per_type_table():
    from app.config import settings
    from app.domain import attack, incidents
    from app.models import TARGET_TYPES
    from app.parsing import type_llm
    from app.pipeline import home_push

    tables = {
        "stale_minutes_tracked": settings.stale_minutes_tracked,
        "stale_minutes_orphan": settings.stale_minutes_orphan,
        "incidents._SEVERITY": incidents._SEVERITY,
        "home_push._TYPE_LABEL": home_push._TYPE_LABEL,
    }
    for name, table in tables.items():
        assert set(table) == set(TARGET_TYPES), f"{name} is missing {set(TARGET_TYPES) - set(table)}"
    # The family maps deliberately EXCLUDE `unknown` — it is the absence of a
    # type, not a family of its own — so they are checked against the rest.
    typed = set(TARGET_TYPES) - {"unknown"}
    assert set(incidents._FAMILY) == typed
    assert set(attack._TYPE_TO_FAMILY) == typed
    # The LLM enum rail: a type the model is never offered is unreachable.
    assert set(type_llm.TYPES) == set(TARGET_TYPES)


def test_the_type_family_rule_covers_every_type():
    from app.domain.target_types import family
    from app.models import TARGET_TYPES

    assert {family(t) for t in TARGET_TYPES} == {"drone", "missile", "unknown"}


def test_the_push_label_matches_what_the_type_means():
    """`shahed` is the generic drone bucket, not the model — «дрон»/«бпла»/
    «баражуюч»/Ланцет/Італмас/Гербера all parse into it. The push title was the
    last surface naming the Shahed-136 specifically, so a bare «БпЛА» callout
    pushed as «Шахед»."""
    from app.pipeline.home_push import _TYPE_LABEL

    assert "Шахед" not in _TYPE_LABEL["shahed"]
    assert _TYPE_LABEL["shahed"] == "БпЛА"
