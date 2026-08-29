"""Alert-zone layer: parsing both providers, diffing, and failing honestly.

The fixtures in tests/data/ are REAL captured provider payloads (2026-08-19,
Сумська область appended from a 2026-08-28 capture and Харківська from a
2026-08-29 one), trimmed to the watched oblasts plus one unwatched, with a
handful of states flipped to true so the alerted path is covered — the shape,
key names and timestamp formats are untouched, which is the part that would
silently break. Сумщина's and Харківщина's rows are all quiet on purpose: the
alerted-path assertions name specific Kyiv/Chernihiv zones, and a new oblast
must not be able to satisfy them by accident.

Харківщина's capture keeps EIGHT district rows for seven raions — the provider
carries both names of the one renamed in 2024. That is not tidied up: the dead
«Берестинський» row is what exercises the unknown-zone path, and the day it
becomes the live one is the day this fixture stops matching the roster.

Nothing here touches the network: every test feeds a payload straight to the
pure parsers, or stubs the fetch.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.domain.alert_zones import ZONES
from app.feeds import alert_zones as az

DATA = Path(__file__).parent / "data"


def _skog() -> dict:
    return json.loads((DATA / "alert_zones_skog.json").read_text("utf-8"))


def _aiu() -> dict:
    return json.loads((DATA / "alert_zones_aiu.json").read_text("utf-8"))


def _skog_frozen() -> dict:
    return json.loads((DATA / "alert_zones_skog_frozen.json").read_text("utf-8"))


def _aiu_live() -> dict:
    return json.loads((DATA / "alert_zones_aiu_live.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def _clean_state():
    az.reset_state()
    yield
    az.reset_state()


# --- skog: the full snapshot ---

def test_skog_maps_every_watched_raion():
    states = az.parse_skog(_skog())
    assert set(states) == {z.id for z in ZONES}


def test_skog_reads_the_alerted_raions():
    states = az.parse_skog(_skog())
    alerted = {zid for zid, s in states.items() if s.alert}
    assert alerted == {"kyiv-city", "kyiv-obl-vyshhorodskyi", "chernihiv-obl-chernihivskyi"}


def test_skog_ignores_oblasts_we_do_not_watch():
    """The payload carries all 27 oblasts; only ours may reach the map."""
    states = az.parse_skog(_skog())
    assert not any("poltav" in zid for zid in states)


def test_kyiv_city_alerts_as_one_zone():
    """м. Київ has no raion split upstream — its oblast-level entry IS the zone."""
    state = az.parse_skog(_skog())["kyiv-city"]
    assert state.alert is True
    assert state.name_uk == "м. Київ"


def test_changed_at_is_read_as_kyiv_local_time():
    """The provider stamps local wall-clock with no offset. 16:09:23 Kyiv in
    August (UTC+3) is 13:09:23 UTC — reading it as UTC would put every siren
    three hours in the past."""
    state = az.parse_skog(_skog())["kyiv-obl-vyshhorodskyi"]
    assert state.changed_at == datetime(2026, 8, 19, 13, 9, 23, tzinfo=UTC)


def test_epoch_sentinel_means_never_observed():
    """1970-01-01 is the provider's "no transition on record" marker, not a
    siren that ended when Unix time began."""
    state = az.parse_skog(_skog())["chernihiv-obl-pryluckyi"]
    assert state.alert is False
    assert state.changed_at is None


# --- aiu: the active-only fallback ---

def test_aiu_reports_only_what_is_alerting():
    """It is an ACTIVE-alert source: a zone it doesn't list is merely unlisted,
    not evidence of an all-clear. Returning quiet zones from here once meant an
    empty/broken payload read as "everything is clear"."""
    states = az.parse_aiu(_aiu())
    assert set(states) == {"kyiv-city", "kyiv-obl-vyshhorodskyi", "chernihiv-obl-chernihivskyi"}
    assert all(s.alert for s in states.values())


def test_a_broken_active_payload_is_an_error_not_an_all_clear():
    with pytest.raises(ValueError):
        az.parse_aiu({})
    with pytest.raises(ValueError):
        az.parse_aiu({"raw": {}})


def test_aiu_ignores_non_air_raid_alerts():
    """Shelling and urban-fighting alerts exist upstream and say nothing about
    the air situation this map shows."""
    assert "chernihiv-obl-nizhynskyi" not in az.parse_aiu(_aiu())


def test_aiu_reads_iso_utc_timestamps():
    state = az.parse_aiu(_aiu())["chernihiv-obl-chernihivskyi"]
    assert state.changed_at == datetime(2026, 8, 19, 13, 9, 49, tzinfo=UTC)


# --- merging the two sources ---

def test_a_live_alert_the_roster_missed_still_shows():
    """The real disagreement this merge exists for.

    2026-08-19 23:06 Kyiv: alerts.in.ua had Вишгородський район under an air
    raid running for 14 minutes; the roster source reported відбій with its
    last transition six hours earlier — it had simply missed it. `stale` cannot
    catch that, because the provider was up and answering.
    """
    zone = "kyiv-obl-boryspilskyi"
    roster = az.parse_skog(_skog())
    assert roster[zone].alert is False  # the roster believes it is clear
    began = datetime(2026, 8, 19, 19, 52, 15, tzinfo=UTC)
    active = {zone: replace(roster[zone], alert=True, changed_at=began)}

    merged = az.merge_states(roster, active)
    assert merged[zone].alert is True
    # …dated by the source that actually knows when it started, not by the
    # clear the roster still believes in.
    assert merged[zone].changed_at == began


def test_the_merge_never_cancels_an_alert():
    """Only ever adds. A source that has NOT yet seen an alert must not be able
    to clear one the other is reporting."""
    roster = az.parse_skog(_skog())
    assert roster["kyiv-city"].alert is True
    assert az.merge_states(roster, {})["kyiv-city"].alert is True


# --- diffing ---

def test_only_changed_zones_are_published():
    first = az.parse_skog(_skog())
    assert len(az.changed_zones({}, first)) == len(ZONES)  # first poll: everything
    assert az.changed_zones(first, first) == []  # a quiet minute: nothing

    payload = _skog()
    for entry in payload["raw"].values():
        if entry["name"] == "Чернігівська область":
            for d in entry["districts"]:
                if d["name"] == "Ніжинський район":
                    d["alert"] = True
    changed = az.changed_zones(first, az.parse_skog(payload))
    assert [s.zone_id for s in changed] == ["chernihiv-obl-nizhynskyi"]


# --- failure behaviour ---

async def test_state_is_stale_until_the_first_successful_poll():
    assert az.is_stale() is True
    assert all(z.stale for z in az.zones_out())


async def test_a_successful_poll_publishes_a_fresh_layer(monkeypatch):
    monkeypatch.setattr(az, "_fetch", _stub_fetch(_skog()))
    changed = await az.poll_once()
    assert len(changed) == len(ZONES)
    assert az.is_stale() is False
    assert not any(z.stale for z in az.zones_out())


async def test_an_outage_goes_stale_instead_of_reading_as_an_all_clear(monkeypatch):
    """The failure mode worth engineering against: a dead provider must never
    look like every siren just stopped."""
    monkeypatch.setattr(az, "_fetch", _stub_fetch(_skog()))
    await az.poll_once()
    az._last_ok = datetime.now(UTC) - timedelta(
        seconds=settings.alert_zones_stale_after_s + 1
    )
    out = {z.zone_id: z for z in az.zones_out()}
    assert all(z.stale for z in out.values())
    # The last known states are still published — greyed out, not blanked.
    assert out["kyiv-obl-vyshhorodskyi"].alert is True


# --- the dev demo override ---

def test_demo_is_dormant_unless_configured():
    """It must stay off by default: a forced siren reaching prod would be the
    worst possible bug in this layer."""
    states = az.parse_skog(_skog())
    assert az.apply_demo(dict(states), {}) == states


def test_demo_forces_the_listed_zones_and_holds_their_start(monkeypatch):
    monkeypatch.setattr(settings, "alert_zones_demo", "chernihiv-obl-nizhynskyi")
    now = datetime(2026, 8, 19, 16, 0, tzinfo=UTC)
    first = az.apply_demo(az.parse_skog(_skog()), {}, now=now)
    assert first["chernihiv-obl-nizhynskyi"].alert is True
    assert first["chernihiv-obl-nizhynskyi"].changed_at == now
    # An untouched zone keeps whatever the provider said.
    assert first["kyiv-obl-boryspilskyi"].alert is False

    later = az.apply_demo(az.parse_skog(_skog()), first, now=now + timedelta(minutes=5))
    # The siren "began" when it was first forced — the tooltip counts up.
    assert later["chernihiv-obl-nizhynskyi"].changed_at == now


async def test_a_payload_without_a_single_watched_zone_is_a_failure(monkeypatch):
    """An upstream shape change that silently drops our oblasts must raise, not
    publish thirteen quiet zones."""
    monkeypatch.setattr(az, "_fetch", _stub_fetch({"raw": {}}))
    with pytest.raises(ValueError):
        await az.poll_once()


def _stub_fetch(payload: dict):
    async def _fetch(source: str) -> dict:
        return payload

    return _fetch


# --- a roster source that answers instantly with yesterday's state ---
#
# The `_frozen`/`_live` fixtures are the REAL 2026-08-29 23:50 incident: the
# roster source served a 07:55 snapshot in which Kyiv was still under a siren
# that had ended hours earlier, while answering in milliseconds with `cachedat`
# stamped the current second. Two other sources (alerts.in.ua and the official
# UkraineAlarm API) both had Kyiv clear.

def test_the_incident_payload_still_has_kyiv_under_alert():
    """Anchors what the fixture IS — if this ever stops holding, the tests
    below are measuring something else."""
    assert az.parse_skog(_skog_frozen())["kyiv-city"].alert is True


def test_a_frozen_roster_is_detected_by_the_gap_to_the_other_source():
    roster_newest = az.latest_transition(_skog_frozen())
    active_newest = az.latest_active_start(_aiu_live())
    assert roster_newest is not None and active_newest is not None
    # Sixteen hours, not minutes — the threshold has an enormous margin.
    assert (active_newest - roster_newest).total_seconds() > 12 * 3600
    assert az.roster_is_behind(roster_newest, active_newest) is True


def test_two_live_sources_are_never_judged_behind():
    """The normal case, and the one this must not break: both see the same
    transitions within seconds, so the gap is ~0 — including on a quiet night,
    when both simply report old news."""
    assert az.roster_is_behind(_dt("2026-08-29T07:55:00Z"), _dt("2026-08-29T07:55:04Z")) is False
    # A quiet night: nothing has changed anywhere for hours, in EITHER source.
    assert az.roster_is_behind(_dt("2026-08-28T02:00:00Z"), _dt("2026-08-28T02:00:00Z")) is False


def test_a_missing_source_is_never_judged():
    """An outage is not evidence about the other one."""
    assert az.roster_is_behind(None, _dt("2026-08-29T20:48:00Z")) is False
    assert az.roster_is_behind(_dt("2026-08-29T07:55:00Z"), None) is False


def test_the_check_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "alert_zones_max_source_lag_s", 0)
    assert az.roster_is_behind(_dt("2026-08-29T07:55:00Z"), _dt("2026-08-29T20:48:00Z")) is False


async def test_a_frozen_roster_stops_holding_kyiv_under_a_siren(monkeypatch):
    """End to end on the real payloads: the whole point of the fix.

    The stuck alert cannot be merged away — the merge only ever ADDS — so the
    roster has to be dropped for the zone to go quiet at all."""
    monkeypatch.setattr(settings, "alert_zones_source_gap_s", 0)
    monkeypatch.setattr(az, "_fetch", _stub_two(_skog_frozen(), _aiu_live()))

    await az.poll_once()
    out = {z.zone_id: z for z in az.zones_out()}
    assert out["kyiv-city"].alert is False
    # …and the zones the live source DOES report are still lit.
    assert out["kyiv-obl-brovarskyi"].alert is True
    # The clear is undated, not back-dated: an active-only source cannot say
    # when a zone went quiet, and inventing an instant would be a lie.
    assert out["kyiv-city"].changed_at is None


async def test_a_fresh_roster_is_still_trusted_for_its_clears(monkeypatch):
    """The check must not cost us dated відбій on a normal night."""
    monkeypatch.setattr(settings, "alert_zones_source_gap_s", 0)
    monkeypatch.setattr(az, "_fetch", _stub_two(_skog(), _aiu()))

    await az.poll_once()
    out = {z.zone_id: z for z in az.zones_out()}
    assert out["kyiv-obl-vyshhorodskyi"].changed_at is not None


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stub_two(roster_payload: dict, active_payload: dict):
    async def _fetch(source: str) -> dict:
        return roster_payload if source == settings.alert_zones_source else active_payload
    return _fetch
