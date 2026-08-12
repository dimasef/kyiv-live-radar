"""Admin console endpoints. Every route here is gated by `require_admin`; the
gate stays on each individual route (not on this router) so the dependency is
visible at the endpoint that needs it and `tests/test_admin_gate.py` keeps
asserting it per route.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import bugs, learning, moderation, reprocess, sources

router = APIRouter()
for _module in (moderation, learning, reprocess, sources, bugs):
    router.include_router(_module.router)
