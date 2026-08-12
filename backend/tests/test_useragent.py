"""User-Agent -> (browser, OS) labels for the bug-report inbox."""
from __future__ import annotations

import pytest

from app.domain.useragent import parse_user_agent

CASES = [
    # The device from the 2026-08-12 report.
    (
        "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.7204.63 Mobile Safari/537.36",
        ("Chrome 138", "Android 14"),
    ),
    # Samsung Internet also says Chrome and Safari — it must win over both.
    (
        "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
        ("Samsung Internet 23", "Android 13"),
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Mobile/15E148 Safari/604.1",
        ("Safari 17.5", "iOS 17.5"),
    ),
    # Chrome on iOS is CriOS and is NOT Safari, whatever the rest of the string says.
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "CriOS/126.0.6478.54 Mobile/15E148 Safari/604.1",
        ("Chrome 126", "iOS 17.5"),
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36",
        ("Chrome 126", "macOS 10.15"),
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.68",
        ("Edge 126", "Windows 10"),
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        ("Firefox 127", "Windows 10"),
    ),
]


@pytest.mark.parametrize("ua,expected", CASES)
def test_parses_the_agents_this_app_actually_sees(ua, expected):
    assert parse_user_agent(ua) == expected


def test_an_absent_or_alien_agent_is_not_an_error():
    """A ticket from something unrecognised is still a ticket — the raw string
    is stored alongside, which is what a human re-reads."""
    assert parse_user_agent(None) == (None, None)
    assert parse_user_agent("") == (None, None)
    assert parse_user_agent("curl/8.4.0") == (None, None)
