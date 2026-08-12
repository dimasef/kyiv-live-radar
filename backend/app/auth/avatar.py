"""Validation for a user-uploaded avatar.

The client sends the picture as a `data:` URL: it resizes to ~128px in a canvas
first, so what arrives is a few kilobytes of webp/jpeg/png rather than a phone
photo. The format checks live in app/images.py, shared with bug-report
screenshots; what's specific here is the size ceiling and the rule that a
remote URL is never accepted from this path.
"""

from __future__ import annotations

from ..images import ImageError, validate_inline_image

# Generous for a 128px square (~5 KB webp -> ~7 KB base64) and still bounded:
# the avatar rides along in every /me and /friends response, so an unbounded one
# would quietly inflate every payload the app makes.
MAX_AVATAR_CHARS = 48 * 1024

# Kept as the name the auth routes raise/catch; the shared validator's errors
# are already user-facing Ukrainian.
AvatarError = ImageError


def validate_avatar_data_url(value: str) -> str:
    """Return the value unchanged if it's an acceptable inline image, else raise.

    The one remote avatar URL in the database (a Google profile picture set at
    sign-in) is written by the OAuth path, not by this one.
    """
    return validate_inline_image(value, max_chars=MAX_AVATAR_CHARS)
