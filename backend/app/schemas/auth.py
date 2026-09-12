"""Registration/login/SSO/email-link inputs and the token pair they return."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..models import UserRole


class RegisterIn(BaseModel):
    """POST /auth/register — email+password signup."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


# What a user may type for themselves. Shorter than the column (and than what
# Google can hand us at sign-in) because this name is rendered inline in contact
# rows and map tooltips, where a long one just truncates. Existing longer names
# from OAuth are left alone — the cap only governs edits made here.
DISPLAY_NAME_MAX = 25


class MeUpdateIn(BaseModel):
    """PATCH /auth/me — edit your own profile.

    Both fields are tri-state: absent leaves the value alone, null clears it
    (removing an avatar falls back to the monogram), a value sets it. That's why
    `avatar_url` can't just be `str | None` with a default — the route inspects
    `model_fields_set` to tell "not mentioned" from "explicitly cleared".
    """

    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)
    # Validated in the route (app/auth/avatar.py): only inline data: images,
    # bounded in size, and their bytes must match the type they claim.
    avatar_url: str | None = None


class LoginIn(BaseModel):
    """POST /auth/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    """POST /auth/refresh — exchange a refresh token for a new token pair."""

    refresh: str


class LogoutIn(BaseModel):
    """POST /auth/logout — the refresh token to revoke. Optional so an old
    client that sends an empty body still logs out client-side."""

    refresh: str | None = None


class GoogleAuthIn(BaseModel):
    """POST /auth/google — the id_token from Google Identity Services."""

    credential: str


class VerifyEmailIn(BaseModel):
    """POST /auth/verify-email — the token from the link in the mail."""

    token: str = Field(min_length=1, max_length=128)


class EmailOnlyIn(BaseModel):
    """POST /auth/resend-verification and /auth/forgot-password."""

    email: EmailStr


class ResetPasswordIn(BaseModel):
    """POST /auth/reset-password — the token from the reset mail + new password."""

    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class RegisterOut(BaseModel):
    """POST /auth/register result: no tokens — the address has to be proven
    first (the mail with the link is on its way)."""

    status: Literal["verification_sent"] = "verification_sent"
    email: str


class OkOut(BaseModel):
    ok: bool = True


class UserOut(BaseModel):
    """The authenticated user's public profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    role: UserRole
    # Which sign-in methods are linked: 'password' + any of PROVIDERS.
    providers: list[str] = []
    # Account-bound opt-in gamification toggle (synced across the user's devices).
    gamification: bool = False
    # Whether accepted friends may see WHEN you were last active. On by default;
    # the online dot itself is not gated by this.
    share_presence: bool = True


class TokenPairOut(BaseModel):
    """Access + refresh tokens plus the user they belong to."""

    access: str
    refresh: str
    token_type: str = "bearer"
    user: UserOut


class AccessTokenOut(BaseModel):
    """POST /auth/refresh result. The refresh token rotates on every use: the
    one presented is dead, and `refresh` is its replacement — store it."""

    access: str
    refresh: str
    token_type: str = "bearer"
