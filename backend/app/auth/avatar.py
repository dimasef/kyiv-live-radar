"""Validation for a user-uploaded avatar.

The client sends the picture as a `data:` URL: it resizes to ~128px in a canvas
first, so what arrives is a few kilobytes of webp/jpeg/png rather than a phone
photo. That keeps the whole feature free of object storage, which matters here —
Railway's filesystem is ephemeral, so "write the file to a folder" would lose
every avatar on the next deploy (the same reason the Telegram session is a
string, see CLAUDE.md).

Nothing below trusts the client. The stored string ends up in an `<img src>` in
OTHER users' browsers, so it is checked three ways: the declared type must be one
we allow, the payload must decode, and its first bytes must actually look like
that format.
"""

from __future__ import annotations

import base64
import binascii

# Generous for a 128px square (~5 KB webp -> ~7 KB base64) and still bounded:
# the avatar rides along in every /me and /friends response, so an unbounded one
# would quietly inflate every payload the app makes.
MAX_AVATAR_CHARS = 48 * 1024

# Deliberately no SVG: it can carry script, and unlike a raster format it is not
# inert everywhere it might end up being opened.
_ALLOWED = {
    "image/webp": [b"RIFF"],  # RIFF....WEBP; the WEBP tag is checked separately
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}

_PREFIX = "data:"
_MARKER = ";base64,"


class AvatarError(ValueError):
    """Rejected avatar — the message is shown to the user, so keep it plain."""


def validate_avatar_data_url(value: str) -> str:
    """Return the value unchanged if it's an acceptable inline image, else raise.

    Only `data:` URLs are accepted — never a remote https one. A stored remote
    URL would be fetched by every contact's browser when they open their list,
    handing whoever controls it their IP addresses and a presence signal. The
    one exception already in the database (a Google profile picture set at
    sign-in) is written by the OAuth path, not by this one.
    """
    if len(value) > MAX_AVATAR_CHARS:
        raise AvatarError("Зображення завелике")
    if not value.startswith(_PREFIX) or _MARKER not in value:
        raise AvatarError("Очікується зображення у форматі data:base64")

    mime = value[len(_PREFIX) : value.index(_MARKER)]
    if mime not in _ALLOWED:
        raise AvatarError("Підтримуються лише WEBP, JPEG і PNG")

    payload = value[value.index(_MARKER) + len(_MARKER) :]
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AvatarError("Пошкоджене зображення") from exc
    if not raw:
        raise AvatarError("Порожнє зображення")

    if not any(raw.startswith(sig) for sig in _ALLOWED[mime]):
        raise AvatarError("Вміст не відповідає заявленому формату")
    # RIFF is also WAV/AVI — the container tag is what makes it a WebP.
    if mime == "image/webp" and raw[8:12] != b"WEBP":
        raise AvatarError("Вміст не відповідає заявленому формату")

    return value
