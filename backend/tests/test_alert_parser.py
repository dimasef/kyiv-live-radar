"""Tests for app/alert_parser.py against the real captured sample
(tests/data/alert_channel_sample.jsonl — 34 messages from @KyivCityOfficial:
27 from 2026-07-10..12, plus 7 from 2026-09-06..07 covering the differentiated
alerting introduced at 06:00 on 2026-09-06). Every message in the fixture is
checked so a future edit to the patterns can't silently regress a real example.

The four September explainer posts are the point of that second batch: 20351
prints the whole new taxonomy — «Дронова небезпека», «Ракетна загроза» and
«Повідомлення "Відбій" означає…» all in one message — and any parser that reads
past the headline turns it into a signal.
"""

import json
from pathlib import Path

from app.parsing.alert_parser import ParsedAlert, parse_alert_message

FIXTURE = Path(__file__).parent / "data" / "alert_channel_sample.jsonl"

# message_id -> expected ParsedAlert (or None) for every message in the real
# fixture that mentions "тривог"/"відбій"/"оголош" — the messages most likely
# to trip a naive keyword match. All other fixture rows (plain city news) are
# asserted None via the sweep test below.
EXPECTED = {
    19192: None,  # weekly recap: "...пролунали 13 повітряних тривог" — a stat, not a signal
    19193: ParsedAlert(scope="city", action="start"),  # real 2026-07-11 00:40 alert
    19200: ParsedAlert(scope="city", action="end"),  # real 2026-07-11 02:02 відбій
    # The differentiated announcements, live from 06.09.2026.
    20363: ParsedAlert(scope="city", action="start", level="yellow", threat="drone"),
    20368: ParsedAlert(scope="city", action="start", level="red", threat="missile"),
    20365: ParsedAlert(scope="city", action="end"),
    # …and the posts that merely TALK about them.
    20351: None,  # the taxonomy itself: names every level and «Відбій» in its body
    20356: None,  # metro timetable "під час жовтого та червоного рівня загрози"
    20359: None,  # "Про передачу сигналу «Повітряна тривога» за різними рівнями"
    20360: None,  # Кличко on what the city does "при жовтому рівні небезпеки"
}


def _load_fixture() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text("utf-8").splitlines() if line.strip()]


def test_fixture_has_the_expected_messages():
    ids = {m["message_id"] for m in _load_fixture()}
    assert set(EXPECTED) <= ids


def test_known_messages_parse_as_expected():
    by_id = {m["message_id"]: m["text"] for m in _load_fixture()}
    for message_id, expected in EXPECTED.items():
        assert parse_alert_message(by_id[message_id]) == expected, message_id


def test_every_other_fixture_message_is_none():
    # The remaining messages are ordinary city news (transit, aftermath
    # reports, moments of silence, weather warnings...) — none of them are a
    # тривога/відбій announcement.
    for m in _load_fixture():
        if m["message_id"] in EXPECTED:
            continue
        assert parse_alert_message(m["text"]) is None, m["message_id"]


# --- Direct unit checks (not fixture-dependent) ---

def test_start_announcement():
    r = parse_alert_message("‼️УВАГА! У Києві оголошена повітряна тривога!")
    assert r == ParsedAlert(scope="city", action="start")


def test_end_announcement():
    r = parse_alert_message("❕Відбій повітряної тривоги!")
    assert r == ParsedAlert(scope="city", action="end")


def test_oblast_scope():
    r = parse_alert_message("Увага! Оголошено повітряну тривогу в Київській області!")
    assert r == ParsedAlert(scope="oblast", action="start")


def test_end_with_conditional_clause_is_not_misread_as_start():
    # The real відбій message names "оголошення тривоги" in a conditional
    # ("у разі оголошення тривоги, повернутися до укриття") — must stay 'end'.
    r = parse_alert_message(
        "Відбій повітряної тривоги! Просимо уважно слідкувати за повідомленнями "
        "і, у разі оголошення тривоги, повернутися до укриття."
    )
    assert r == ParsedAlert(scope="city", action="end")


def test_recap_mentioning_alert_count_is_not_a_signal():
    r = parse_alert_message("Цього тижня у столиці пролунали 13 повітряних тривог.")
    assert r is None


def test_unrelated_city_news_is_none():
    r = parse_alert_message("Із 15 липня в Києві змінюється вартість проїзду в комунальному транспорті.")
    assert r is None


def test_english_start_announcement():
    r = parse_alert_message("ATTENTION! Air raid sirens in Kyiv")
    assert r == ParsedAlert(scope="city", action="start")


def test_english_end_announcement():
    r = parse_alert_message("Air siren all clear")
    assert r == ParsedAlert(scope="city", action="end")


# --- differentiated levels (from 06:00 on 2026-09-06) ---

def test_drone_danger_is_the_yellow_level():
    r = parse_alert_message("🟡 УВАГА! У Києві оголошена дронова небезпека!")
    assert r == ParsedAlert(scope="city", action="start", level="yellow", threat="drone")


def test_missile_threat_is_the_red_level():
    r = parse_alert_message("🔴 УВАГА! У Києві оголошена нова загроза — ракетна загроза!")
    assert r == ParsedAlert(scope="city", action="start", level="red", threat="missile")


def test_massed_drone_threat_is_the_red_level():
    r = parse_alert_message("🔴 УВАГА! У Києві оголошена масована дронова загроза!")
    assert r == ParsedAlert(scope="city", action="start", level="red", threat="massed_drone")


def test_missile_drone_threat_is_its_own_kind():
    # Must not be read as a plain missile threat — the ракетн* rule would match
    # it too if the combined one weren't checked first.
    r = parse_alert_message("🔴 УВАГА! У Києві оголошена ракетно-дронова загроза!")
    assert r == ParsedAlert(scope="city", action="start", level="red", threat="missile_drone")


def test_the_legacy_announcement_carries_no_level():
    """Still the wording every channel outside Kyiv uses, and every stored
    message from before 06.09 — 'unknown' is the honest reading, not a gap."""
    r = parse_alert_message("‼️УВАГА! У Києві оголошена повітряна тривога!")
    assert r.level == "unknown" and r.threat == "unspecified"


def test_the_taxonomy_explainer_is_not_a_signal():
    """The channel's own post announcing the new system names all four threats
    and «Відбій». Only the headline is read, which is why it stays None."""
    text = (
        "❗️🔉 Із 6:00 6 вересня 2026 року, за рішенням Уряду, в Києві "
        "запроваджено диференційоване оповіщення про повітряні загрози\n\n"
        "🟡 Жовтий рівень: \"Дронова небезпека\".\n"
        "🔴 Червоний рівень: \"Ракетна загроза\".\n"
        "🟢\"Відбій\" – загрози та небезпеки відсутні."
    )
    assert parse_alert_message(text) is None


def test_a_headline_naming_a_level_without_declaring_one_is_not_a_signal():
    r = parse_alert_message(
        "Про перевезення пасажирів відкритими ділянками Київського "
        "метрополітену під час жовтого та червоного рівня загрози."
    )
    assert r is None
