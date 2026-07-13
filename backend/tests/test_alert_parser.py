"""Tests for app/alert_parser.py against the real captured sample
(tests/data/alert_channel_sample.jsonl — 27 messages from @KyivCityOfficial,
2026-07-10..12). Every message in the fixture is checked so a future edit to
the patterns can't silently regress a real example.
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
    # The remaining 24 messages are ordinary city news (transit, aftermath
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
