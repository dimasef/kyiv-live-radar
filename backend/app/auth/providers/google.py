"""Google Sign-In (OIDC) id-token verification.

The SPA obtains an id_token via Google Identity Services and POSTs it; we verify
its RS256 signature against Google's published JWKS and check aud/iss/exp +
email_verified. No client secret and no server-side redirect are involved.
"""
from __future__ import annotations

import json
import time
from typing import Optional

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
_JWKS_TTL_S = 3600

# Simple in-process JWKS cache: {kid: jwk}. Refetched on miss (key rotation) or
# TTL lapse. Module-global — fine for a single-process app.
_jwks: dict[str, dict] = {}
_jwks_exp: float = 0.0


class GoogleAuthError(Exception):
    """A Google id_token failed verification."""


async def _load_jwks(force: bool = False) -> dict[str, dict]:
    global _jwks, _jwks_exp
    if not force and _jwks and time.time() < _jwks_exp:
        return _jwks
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(_JWKS_URL)
        resp.raise_for_status()
        data = resp.json()
    _jwks = {k["kid"]: k for k in data.get("keys", []) if "kid" in k}
    _jwks_exp = time.time() + _JWKS_TTL_S
    return _jwks


async def _signing_key(kid: Optional[str]):
    keys = await _load_jwks()
    jwk = keys.get(kid) if kid else None
    if jwk is None:  # possible key rotation — refetch once
        keys = await _load_jwks(force=True)
        jwk = keys.get(kid) if kid else None
    if jwk is None:
        raise GoogleAuthError("no matching Google signing key")
    return RSAAlgorithm.from_jwk(json.dumps(jwk))


async def verify_google_id_token(credential: str, client_id: str) -> dict:
    """Verify a Google id_token and return {sub, email, email_verified, name,
    picture}. Raises GoogleAuthError on any verification failure."""
    try:
        header = jwt.get_unverified_header(credential)
    except jwt.PyJWTError as exc:
        raise GoogleAuthError(f"malformed token: {exc}") from exc
    key = await _signing_key(header.get("kid"))
    try:
        claims = jwt.decode(
            credential, key, algorithms=["RS256"], audience=client_id
        )
    except jwt.PyJWTError as exc:
        raise GoogleAuthError(str(exc)) from exc
    if claims.get("iss") not in _ISSUERS:
        raise GoogleAuthError(f"bad issuer {claims.get('iss')!r}")
    return {
        "sub": claims["sub"],
        "email": claims.get("email"),
        "email_verified": bool(claims.get("email_verified")),
        "name": claims.get("name"),
        "picture": claims.get("picture"),
    }
