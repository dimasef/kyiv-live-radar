"""User-filed bug reports: what was sent, and how a ticket reads in the admin."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from ..models import BugReportStatus
from .base import _as_utc


class BugContextIn(BaseModel):
    """The technical context the app collects for the reporter.

    Every field is optional: a browser that hides one of these (or a future one
    the client stops sending) must still be able to file a bug. `scale` is the
    page zoom — 0.25 there is the whole diagnosis of the 2026-08-12 Android
    report, so it is worth its own field rather than a line of prose.
    """

    app_version: str | None = Field(None, max_length=20)
    route: str | None = Field(None, max_length=200)
    user_agent: str | None = Field(None, max_length=1000)
    viewport_w: int | None = None
    viewport_h: int | None = None
    dpr: float | None = None
    scale: float | None = None
    standalone: bool | None = None
    language: str | None = Field(None, max_length=20)
    online: bool | None = None


class BugReportIn(BaseModel):
    """POST /bug-reports — the form a user submits.

    Either half is enough on its own: a screenshot of a mangled screen often
    says more than a sentence about it, and a description needs no picture. An
    empty report is the only thing rejected — it carries nothing to act on.
    """

    description: str = Field("", max_length=4000)
    # Inline data: URL, validated by app/images.py. None when none was attached.
    screenshot: str | None = None
    context: BugContextIn = BugContextIn()

    @model_validator(mode="after")
    def _carries_something(self) -> BugReportIn:
        if not self.description.strip() and not self.screenshot:
            raise ValueError("Опишіть проблему або додайте знімок екрана")
        return self


class BugReporterOut(BaseModel):
    """Who filed it — enough to reply to them, nothing more."""

    id: int
    email: str | None = None
    display_name: str | None = None


class BugReportOut(BaseModel):
    """One ticket in the admin console."""

    id: int
    status: BugReportStatus
    description: str
    screenshot: str | None = None
    app_version: str | None = None
    browser: str | None = None
    os: str | None = None
    user_agent: str | None = None
    context: dict = {}
    reporter: BugReporterOut | None = None
    created_at: datetime
    updated_at: datetime

    _tz_created = field_validator("created_at", mode="before")(_as_utc)
    _tz_updated = field_validator("updated_at", mode="before")(_as_utc)


class BugReportAckOut(BaseModel):
    """What the reporter gets back — deliberately just the receipt."""

    id: int
    status: BugReportStatus


class BugReportStatusIn(BaseModel):
    """PATCH /admin/bug-reports/{id} — move a ticket along."""

    status: BugReportStatus
