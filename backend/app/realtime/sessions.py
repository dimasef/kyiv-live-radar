"""Who is reading the radar right now — the accounts and everyone else.

`User.last_seen_at` (domain/presence.py) can only ever answer for accounts: it
is stamped on AUTHENTICATED requests, and most of this app's readers never sign
in at all. The live sockets know better — every open tab holds one — but a
socket carries no identity of its own, so two things are attached to it here:

* the DEVICE id the client mints once and keeps in localStorage, so one reader
  reloading the page stays one row instead of becoming a new stranger, and two
  tabs collapse into one row rather than reading as two people;
* the account behind that device, learned from the device's own authenticated
  HTTP requests (auth/deps notes it), because the socket itself never sees a
  token.

In memory and single-instance, exactly like the frame history next door: this
describes THIS process's sockets and is gone on restart. When the fan-out moves
to Redis (ws.py §2), this moves with it.

A device id is a client-supplied string: it is never trusted for authorization,
only for grouping rows in the admin console, and it is length-capped here
because it arrives in a header and a query param.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import utcnow
from ..timeutil import naive

# Long enough for a uuid4 with dashes, short enough that a header cannot be used
# to grow the maps below.
MAX_DEVICE_ID_CHARS = 64
# How long a device→account link outlives that device's last authenticated
# request. Generous: it only has to survive a reader who signs in, then browses
# for hours making anonymous reads.
ACCOUNT_LINK_TTL = timedelta(hours=12)
# Ceiling on the link map, so a flood of invented device ids cannot grow it
# without bound. Oldest links are dropped first.
MAX_ACCOUNT_LINKS = 5000


def clean_device_id(raw: str | None) -> str | None:
    """A device id we are willing to store, or None. Whitespace-only and
    over-long values are simply dropped — an unusable id is not an error, it
    just means this session stays an anonymous row of its own."""
    if raw is None:
        return None
    value = raw.strip()
    if not value or len(value) > MAX_DEVICE_ID_CHARS:
        return None
    return value


@dataclass(frozen=True)
class LiveSession:
    """One open socket, as much as the server can honestly say about it."""

    device_id: str | None
    connected_at: datetime
    user_agent: str | None
    ip: str | None


@dataclass(frozen=True)
class OnlineDevice:
    """One device holding at least one live socket — a row in the console.

    `tabs` is how many sockets that device has open. `since` is the oldest of
    them, which is when this reader actually arrived, not when they opened their
    most recent tab.
    """

    device_id: str | None
    tabs: int
    since: datetime
    user_agent: str | None
    ip: str | None
    user_id: int | None


class DeviceAccounts:
    """device id → the account that last used it, with a TTL.

    Deliberately last-write-wins: a shared device that two people sign into in
    turn belongs to whoever used it last, which is the only thing the sockets
    can support.
    """

    def __init__(self) -> None:
        self._links: dict[str, tuple[int, datetime]] = {}

    def note(self, device_id: str | None, user_id: int, now: datetime | None = None) -> None:
        device = clean_device_id(device_id)
        if device is None:
            return
        at = naive(now or utcnow())
        # Re-inserting moves the key to the end, which is what makes the
        # over-capacity eviction below drop the least recently seen link.
        self._links.pop(device, None)
        self._links[device] = (user_id, at)
        self._prune(at)

    def forget_user(self, user_id: int) -> None:
        """Drop every link to an account — its owner signed out, or was blocked
        or deleted, and the console must stop naming them behind a device that
        is still connected."""
        for device, (uid, _) in list(self._links.items()):
            if uid == user_id:
                del self._links[device]

    def user_for(self, device_id: str | None, now: datetime | None = None) -> int | None:
        device = clean_device_id(device_id)
        if device is None:
            return None
        link = self._links.get(device)
        if link is None:
            return None
        user_id, at = link
        if naive(now or utcnow()) - at > ACCOUNT_LINK_TTL:
            del self._links[device]
            return None
        return user_id

    def clear(self) -> None:
        self._links.clear()

    def _prune(self, now: datetime) -> None:
        for device, (_, at) in list(self._links.items()):
            if now - at > ACCOUNT_LINK_TTL:
                del self._links[device]
        while len(self._links) > MAX_ACCOUNT_LINKS:
            self._links.pop(next(iter(self._links)))


accounts = DeviceAccounts()


def client_ip(headers: dict[str, str] | None, peer: str | None) -> str | None:
    """The reader's address, seen through the deploy's proxy.

    Railway (and Vercel's rewrites in front of it) terminate the connection, so
    `ws.client` is the proxy, not the reader. The first entry of
    `X-Forwarded-For` is the original client — the rest are the proxies it
    passed through. Falls back to the peer when nothing forwarded it (local dev).
    """
    forwarded = (headers or {}).get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer


def describe(
    *, device_id: str | None, headers: dict[str, str] | None, peer: str | None
) -> LiveSession:
    """What a freshly accepted socket can say about its reader."""
    agent = (headers or {}).get("user-agent")
    return LiveSession(
        device_id=clean_device_id(device_id),
        connected_at=utcnow(),
        # Capped: it is shown in a table, and a header is whatever the client
        # chose to send.
        user_agent=agent[:200] if agent else None,
        ip=client_ip(headers, peer),
    )


def group_by_device(
    sessions: Iterable[LiveSession],
    resolve_user: Callable[[str | None], int | None],
) -> list[OnlineDevice]:
    """Live sockets → console rows, newest arrival first.

    Sockets with no device id are NOT merged with each other: without an id
    there is nothing to say they are the same reader, and collapsing them would
    invent a person. Each becomes its own row.
    """
    grouped: dict[str, list[LiveSession]] = {}
    loners: list[LiveSession] = []
    for s in sessions:
        if s.device_id is None:
            loners.append(s)
        else:
            grouped.setdefault(s.device_id, []).append(s)

    rows = [
        OnlineDevice(
            device_id=device,
            tabs=len(group),
            since=min(naive(s.connected_at) for s in group),
            # The newest socket's, not the oldest: a reader who switched from
            # the phone to the desktop should read as where they are now.
            user_agent=max(group, key=lambda s: naive(s.connected_at)).user_agent,
            ip=max(group, key=lambda s: naive(s.connected_at)).ip,
            user_id=resolve_user(device),
        )
        for device, group in grouped.items()
    ]
    rows.extend(
        OnlineDevice(
            device_id=None,
            tabs=1,
            since=naive(s.connected_at),
            user_agent=s.user_agent,
            ip=s.ip,
            user_id=None,
        )
        for s in loners
    )
    rows.sort(key=lambda r: r.since, reverse=True)
    return rows
