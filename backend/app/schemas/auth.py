"""Registration/login/SSO inputs and the token pair they return."""

from __future__ import annotations

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
    """POST /auth/refresh — exchange a refresh token for a new access token."""

    refresh: str


class GoogleAuthIn(BaseModel):
    """POST /auth/google — the id_token from Google Identity Services."""

    credential: str


class TelegramAuthIn(BaseModel):
    """POST /auth/telegram — the Telegram Login Widget payload. extra='allow'
    so any future widget field is preserved for the HMAC data-check-string
    (which must include EXACTLY the fields Telegram signed)."""

    model_config = ConfigDict(extra="allow")

    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


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
    """POST /auth/refresh result — a fresh access token only."""

    access: str
    token_type: str = "bearer"
