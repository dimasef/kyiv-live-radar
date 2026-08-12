"""Validation for an inline (`data:` URL) image sent by a client.

Two features store pictures this way — avatars (`app/auth/avatar.py`) and
bug-report screenshots (`app/api/public/bugs.py`) — for the same reason:
Railway's filesystem is ephemeral, so "write the file to a folder" would lose
every picture on the next deploy (the same reason the Telegram session is a
string, see CLAUDE.md), and object storage is a dependency and a secret this
project doesn't otherwise need.

Nothing below trusts the client. A stored string ends up in an `<img src>` in
somebody else's browser, so it is checked three ways: the declared type must be
one we allow, the payload must decode, and its first bytes must actually look
like that format.
"""

from __future__ import annotations

import base64
import binascii

# Deliberately no SVG: it can carry script, and unlike a raster format it is not
# inert everywhere it might end up being opened.
_ALLOWED = {
    "image/webp": [b"RIFF"],  # RIFF....WEBP; the WEBP tag is checked separately
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}

_PREFIX = "data:"
_MARKER = ";base64,"


class ImageError(ValueError):
    """Rejected image — the message is shown to the user, so keep it plain."""


def validate_inline_image(value: str, *, max_chars: int) -> str:
    """Return the value unchanged if it's an acceptable inline image, else raise.

    Only `data:` URLs are accepted — never a remote https one. A stored remote
    URL would be fetched by every browser that renders it, handing whoever
    controls it their IP addresses and a presence signal.
    """
    if len(value) > max_chars:
        raise ImageError("Зображення завелике")
    if not value.startswith(_PREFIX) or _MARKER not in value:
        raise ImageError("Очікується зображення у форматі data:base64")

    mime = value[len(_PREFIX) : value.index(_MARKER)]
    if mime not in _ALLOWED:
        raise ImageError("Підтримуються лише WEBP, JPEG і PNG")

    payload = value[value.index(_MARKER) + len(_MARKER) :]
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("Пошкоджене зображення") from exc
    if not raw:
        raise ImageError("Порожнє зображення")

    if not any(raw.startswith(sig) for sig in _ALLOWED[mime]):
        raise ImageError("Вміст не відповідає заявленому формату")
    # RIFF is also WAV/AVI — the container tag is what makes it a WebP.
    if mime == "image/webp" and raw[8:12] != b"WEBP":
        raise ImageError("Вміст не відповідає заявленому формату")

    return value
