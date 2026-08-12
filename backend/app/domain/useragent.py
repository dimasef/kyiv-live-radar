"""Browser and OS from a User-Agent string.

A hand-written table rather than a parsing library, in the same spirit as the
rule parser: the whole job is turning one string into two labels for an admin
list, and a dependency that ships a monthly-updated regex database would be more
machinery than the problem deserves.

It WILL be wrong sometimes — UA strings lie by design (every browser claims to
be Mozilla, Chrome and Safari at once). That's why the raw string is stored
alongside the parsed labels: a wrong guess stays re-readable by a human.
Ordering matters below: the impostors are checked before the browsers they
impersonate.
"""

from __future__ import annotations

import re

# (label, pattern) — first match wins, so derivatives come before their base.
_BROWSERS: tuple[tuple[str, str], ...] = (
    ("Samsung Internet", r"SamsungBrowser/([\d.]+)"),
    ("Edge", r"Edg(?:A|iOS)?/([\d.]+)"),
    ("Opera", r"OPR/([\d.]+)"),
    ("Firefox", r"(?:FxiOS|Firefox)/([\d.]+)"),
    # Chrome on iOS is CriOS; on Android/desktop it's Chrome. Both are "Chrome".
    ("Chrome", r"(?:CriOS|Chrome)/([\d.]+)"),
    ("Safari", r"Version/([\d.]+).*Safari/"),
)

_OS: tuple[tuple[str, str], ...] = (
    ("Android", r"Android ([\d.]+)"),
    ("iOS", r"(?:iPhone |CPU )OS ([\d_]+)"),
    ("iPadOS", r"iPad.*OS ([\d_]+)"),
    ("Windows", r"Windows NT ([\d.]+)"),
    ("macOS", r"Mac OS X ([\d_.]+)"),
    ("Linux", r"(Linux)"),
)

# Only the leading numbers are useful in a list: "138.0.7204.63" is noise, and a
# Chromium minor is always 0 — so "Chrome 138", but "Safari 17.5".
def _short(version: str) -> str:
    short = ".".join(version.replace("_", ".").split(".")[:2]).strip(".")
    return short[:-2] if short.endswith(".0") else short


def _first_match(ua: str, table: tuple[tuple[str, str], ...]) -> str | None:
    for label, pattern in table:
        m = re.search(pattern, ua)
        if not m:
            continue
        version = _short(m.group(1))
        # The Linux row captures the word itself, not a version.
        return label if version == "Linux" or not version else f"{label} {version}"
    return None


def parse_user_agent(ua: str | None) -> tuple[str | None, str | None]:
    """(browser, os) as short display labels, either being None when unknown."""
    if not ua:
        return None, None
    return _first_match(ua, _BROWSERS), _first_match(ua, _OS)
