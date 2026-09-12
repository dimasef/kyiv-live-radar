"""Outbound transactional email (verification links, password resets) via Resend.

One HTTP call per message, no SDK: the API is a single POST. Without an API key
a laptop run logs the message body instead of sending, so the verification flow
can be walked locally by copying the link out of the log; a deployed host
without a key fails loudly (MailNotConfigured → 503 at the route).
"""

from __future__ import annotations

import logging

import httpx

from .config import settings

log = logging.getLogger("mail")

_RESEND_URL = "https://api.resend.com/emails"


class MailError(Exception):
    """The provider refused or failed to accept the message."""


class MailNotConfigured(MailError):
    """No RESEND_API_KEY on a non-development host."""


async def send_email(to: str, subject: str, text: str, html: str) -> None:
    if not settings.mail_configured:
        if settings.is_local_dev:
            log.warning("mail (not sent, no RESEND_API_KEY) to=%s subject=%r\n%s", to, subject, text)
            return
        raise MailNotConfigured("RESEND_API_KEY is not set")
    payload = {
        "from": settings.mail_from,
        "to": [to],
        "subject": subject,
        "text": text,
        "html": html,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.mail_timeout_s) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
    except httpx.HTTPError as exc:
        raise MailError(f"resend unreachable: {exc}") from exc
    if resp.status_code >= 300:
        raise MailError(f"resend {resp.status_code}: {resp.text[:200]}")
