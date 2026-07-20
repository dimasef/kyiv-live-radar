"""Telegram Login Widget verification.

The widget hands the browser a signed payload {id, first_name, ..., auth_date,
hash}; we re-derive the HMAC to prove it came from Telegram and isn't replayed.
Algorithm (https://core.telegram.org/widgets/login#checking-authorization):

    secret_key = SHA256(bot_token)
    data_check_string = "\n".join(sorted "key=value" for every field except hash)
    hmac_sha256(secret_key, data_check_string) == hash
"""
from __future__ import annotations

import hashlib
import hmac
import time


class TelegramAuthError(Exception):
    """The Telegram login payload failed HMAC or freshness verification."""


def verify_telegram_login(
    fields: dict, received_hash: str, bot_token: str, *, max_age_s: int = 86400
) -> None:
    """Raise TelegramAuthError if `fields` (the widget payload WITHOUT `hash`)
    doesn't verify against `bot_token`, or `auth_date` is older than max_age_s."""
    if not received_hash:
        raise TelegramAuthError("missing hash")
    check_string = "\n".join(sorted(f"{k}={v}" for k, v in fields.items() if v is not None))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise TelegramAuthError("bad hash")
    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError):
        raise TelegramAuthError("missing/invalid auth_date")
    if time.time() - auth_date > max_age_s:
        raise TelegramAuthError("stale auth_date (possible replay)")
