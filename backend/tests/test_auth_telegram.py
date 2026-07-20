"""Telegram Login Widget HMAC verification (app/auth/providers/telegram.py)."""
from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from app.auth.providers.telegram import TelegramAuthError, verify_telegram_login

BOT_TOKEN = "123456:FAKE-BOT-TOKEN"


def _sign(fields: dict, token: str = BOT_TOKEN) -> str:
    check = "\n".join(sorted(f"{k}={v}" for k, v in fields.items()))
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def test_valid_payload_accepts():
    fields = {"id": 123, "first_name": "Ann", "username": "ann", "auth_date": int(time.time())}
    verify_telegram_login(fields, _sign(fields), BOT_TOKEN)  # must not raise


def test_tampered_hash_rejected():
    fields = {"id": 123, "first_name": "Ann", "auth_date": int(time.time())}
    with pytest.raises(TelegramAuthError):
        verify_telegram_login(fields, "deadbeef" * 8, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    fields = {"id": 123, "first_name": "Ann", "auth_date": int(time.time())}
    good_hash = _sign(fields)
    with pytest.raises(TelegramAuthError):
        verify_telegram_login(fields, good_hash, "999:OTHER-TOKEN")


def test_stale_auth_date_rejected():
    fields = {"id": 123, "first_name": "Ann", "auth_date": int(time.time()) - 10 * 86400}
    with pytest.raises(TelegramAuthError):
        verify_telegram_login(fields, _sign(fields), BOT_TOKEN)
