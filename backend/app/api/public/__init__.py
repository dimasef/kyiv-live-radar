"""Public (unauthenticated) read endpoints, one module per domain area.

Split out of the former single 1129-line `api/routes.py`; the boundary that
matters is public-vs-admin, so the two packages are siblings and every admin
route lives in `api/admin/` behind `require_admin`.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    bugs,
    districts,
    journal,
    push,
    raw,
    regions,
    situation,
    sources,
    threats,
    zones,
)

router = APIRouter()
for _module in (districts, regions, sources, threats, situation, zones, journal, raw,
                push, bugs):
    router.include_router(_module.router)
