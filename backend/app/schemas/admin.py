"""Admin console: moderation inputs, coverage gaps, corrections, reprocess."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..models import (
    AssignableRole,
    CorrectionKind,
    NoticeKind,
    RoleSource,
    TargetType,
    UserRole,
)
from .base import _as_utc
from .situation import AlertOut, IncidentOut
from .threats import ThreatOut


class RawNoticeIn(BaseModel):
    """POST /admin/raw_messages/{id}/notice — publish a message the parser left
    out as a feed notice (a forecast, an all-clear, a situation summary).

    `text` defaults to the message's own text: most of the time the spotter
    already said it well, and retyping it invites drift from the original."""

    kind: NoticeKind
    text: str | None = None


class ThreatTypeIn(BaseModel):
    """PATCH /admin/threats/{id} — admin retype of a track's target."""

    target_type: TargetType


class IncidentTypeIn(BaseModel):
    """PATCH /admin/incidents/{id}/type — the operator's verdict on what is in
    the air.

    A LIST, because a raid is not always one thing: naming two weapon families
    is how 'комбінована' is expressed, and attack.classify then derives that
    label itself rather than it having to be a magic value the TargetType enum
    does not contain.

    An empty list (or null) clears the override and hands the attack back to the
    derivation from its member tracks — which is why this can't reuse
    `ThreatTypeIn`: a track's type is one value and has no "auto" to return to.
    """

    target_types: list[TargetType] = []


class EventDistrictIn(BaseModel):
    """PATCH /admin/events/{id} — admin fixes a mislocated sighting."""

    district_id: int


class EventTrackIn(BaseModel):
    """PATCH /admin/events/{id}/threat — admin regroups a sighting.

    `threat_id` names the track to move it ONTO; None splits it out onto a track
    of its own. Both are the same operation from tracking's point of view — it
    grouped this sighting wrong, and the fix is to say where it belongs."""

    threat_id: int | None = None


class RegroupOut(BaseModel):
    """PATCH /admin/events/{id}/threat — BOTH tracks the move touched.

    A regroup always changes two tracks, and the admin view has to update both:
    returning only the destination left the source still advertising a sighting
    it no longer owns."""

    event_id: int
    # The track the sighting now lives on (newly created, when it was a split).
    threat: ThreatOut
    # The track it came from — still a row even when the move emptied and
    # dismissed it, so the caller can redraw or drop it.
    source_threat: ThreatOut


class DismissedOut(BaseModel):
    """GET /admin/dismissed — recently admin-cancelled entities, for the
    'Повернути' (restore) list in the admin panel."""

    threats: list[ThreatOut] = []
    incidents: list[IncidentOut] = []
    alerts: list[AlertOut] = []


class CoverageGapOut(BaseModel):
    """GET /admin/coverage_gaps — a message the parser couldn't localize that
    still names something (likely a missing gazetteer entry)."""

    raw_message_id: int
    text: str
    event_time: datetime
    source_name: str | None = None
    detected_target_type: TargetType
    detected_status: str
    # The unknown place-name words this row was admitted for — so the operator
    # sees WHICH word to look up, not just that the message failed.
    candidates: list[str] = []

    _tz_gap = field_validator("event_time", mode="before")(_as_utc)


class CoverageCandidateOut(BaseModel):
    """GET /admin/coverage_candidates — one unknown place-name, with how often
    it occurred in the scanned window. The ranked gazetteer work-list."""

    name: str
    count: int
    example_text: str
    example_raw_message_id: int


class ToponymDismissalIn(BaseModel):
    """POST /admin/coverage_candidates/dismiss — one candidate the operator
    judged not to be a place."""

    name: str = Field(min_length=2, max_length=60)


class CorrectionOut(BaseModel):
    """GET /admin/corrections — a harvested correction plus whether the CURRENT
    parser already agrees (so the admin sees which mistakes are retired)."""

    id: int
    raw_message_id: int | None = None
    text: str
    kind: CorrectionKind
    expected: dict = {}
    origin: str
    created_at: datetime
    resolved: bool  # current parser now matches the correction

    _tz_corr = field_validator("created_at", mode="before")(_as_utc)


class AdminUserOut(BaseModel):
    """GET /admin/users — one account in the «Юзери» tab.

    A superset of `UserOut`'s public profile plus the operator-only columns:
    whether the email was ever verified, when the account was created / last
    signed in / last did anything, whether it is blocked, and WHY its role holds
    the value it does (see models.RoleSource — `role` itself is read-only here,
    because role resolution recomputes it from the env allowlists on every
    login).

    `last_seen_at` is published regardless of the owner's `share_presence`: that
    flag gates peer-to-peer disclosure to accepted contacts, not the operator's
    view of their own database. Deliberately absent, as none of the operator's
    business: `gamification`, `share_presence`, `home_*`, `contact_prefs`.
    """

    id: int
    email: str | None = None
    email_verified: bool
    display_name: str | None = None
    avatar_url: str | None = None
    role: UserRole
    role_source: RoleSource
    # 'password' first (a native account), then the linked SSO providers sorted
    # — the exact order auth_routes._user_out builds, so the operator's view and
    # the user's own profile can never disagree about how they sign in.
    providers: list[str] = []
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    last_seen_at: datetime | None = None

    _tz_created = field_validator("created_at", mode="before")(_as_utc)
    _tz_login = field_validator("last_login_at", mode="before")(_as_utc)
    _tz_seen = field_validator("last_seen_at", mode="before")(_as_utc)


class AdminUserRoleIn(BaseModel):
    """PATCH /admin/users/{id}/role — grant or revoke console access.

    Only `AssignableRole` values: plain 'admin' is derived from the env
    allowlists on every login, so storing it would be a lie the next sign-in
    corrects. Durable admin is 'admin_g'."""

    role: AssignableRole


class AdminUserDeleteOut(BaseModel):
    """DELETE /admin/users/{id} — what the cascade actually removed.

    Reported rather than assumed because the deletion is done with explicit
    statements, not left to the DDL: SQLite (dev) does not enforce `ondelete`
    without PRAGMA foreign_keys, while Postgres (prod) does — so relying on the
    schema alone would mean two different behaviours."""

    deleted: int
    identities: int
    friendships: int
    analyses: int
    # Rows kept but disowned (their FKs are ON DELETE SET NULL): bug reports,
    # parser corrections, toponym dismissals, push subscriptions, sources added.
    orphaned: int


class ReprocessDayOut(BaseModel):
    date: str
    target_count: int
    track_count: int


class ReprocessSummaryOut(BaseModel):
    """Snapshot used to diff a reprocess: totals + recent per-day target counts
    (where the phantom-count inflation like the 23.07 '432 цілі' shows up)."""

    tracks: int
    events: int
    incidents: int
    days: list[ReprocessDayOut] = []


class ReprocessPreviewOut(BaseModel):
    """GET /admin/reprocess/preview — pre-flight scope, no mutation."""

    raw_messages: int  # everything stored, whatever the requested scope
    current: ReprocessSummaryOut
    attack_active: bool  # refuse-by-default guard: don't rebuild mid-attack
    # With `?last=N`: how many messages that tail ACTUALLY replays (N widened so
    # no track/alert is cut in half — see pipeline/reprocess.scope_cutoff) and
    # the instant it starts from. Both None when rebuilding everything.
    scope_messages: int | None = None
    scope_from: datetime | None = None


class ReprocessApplyIn(BaseModel):
    no_llm: bool = True  # match the boot path; True is fast + free
    force: bool = False  # override the mid-attack guard
    # Rebuild only the last N stored messages, keeping older history. None =
    # everything (the old behaviour).
    last: int | None = None


class ReprocessResultOut(BaseModel):
    """POST /admin/reprocess/apply — before/after diff + raw replay counts."""

    before: ReprocessSummaryOut
    after: ReprocessSummaryOut
    result: dict
