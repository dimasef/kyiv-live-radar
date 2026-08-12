"""Filing a bug from inside the app.

Signed-in only: a ticket nobody can be asked a follow-up question about is worth
much less than one with an author, and the rate limit has an account to hang
off instead of an IP.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.deps import get_current_user
from ...db import get_session
from ...domain.useragent import parse_user_agent
from ...images import ImageError, validate_inline_image
from ...models import BugReport, User, utcnow
from ...schemas import BugReportAckOut, BugReportIn

log = logging.getLogger("bugs")

router = APIRouter()

# A screenshot is resized to ~1600px and JPEG-encoded client-side
# (lib/screenshotImage.ts), which lands well under this. The ceiling is here so
# a hand-crafted request can't push a megabyte-per-row into the database.
MAX_SCREENSHOT_CHARS = 900 * 1024

# Enough for a real session of "found another one", far short of a flood.
RATE_LIMIT_PER_HOUR = 10


@router.post("/bug-reports", response_model=BugReportAckOut)
async def file_bug_report(
    body: BugReportIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    since = utcnow() - timedelta(hours=1)
    recent = await session.scalar(
        select(func.count())
        .select_from(BugReport)
        .where(BugReport.user_id == user.id, BugReport.created_at >= since)
    )
    if (recent or 0) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Забагато звітів — спробуйте пізніше")

    screenshot = body.screenshot or None
    if screenshot is not None:
        try:
            screenshot = validate_inline_image(screenshot, max_chars=MAX_SCREENSHOT_CHARS)
        except ImageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    ctx = body.context
    browser, os_name = parse_user_agent(ctx.user_agent)
    report = BugReport(
        user_id=user.id,
        description=body.description.strip(),
        screenshot=screenshot,
        app_version=ctx.app_version,
        browser=browser,
        os=os_name,
        user_agent=ctx.user_agent,
        # The parsed labels live in their own columns; everything else is kept
        # as sent, so a future field needs no migration to start being useful.
        context=ctx.model_dump(exclude={"user_agent", "app_version"}, exclude_none=True),
    )
    session.add(report)
    await session.commit()
    log.info(
        "bug report %s filed by user %s (%s / %s)", report.id, user.id, browser, os_name
    )
    return report
