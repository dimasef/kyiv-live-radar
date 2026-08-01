"""Assembles the app's HTTP routes from the `public` and `admin` packages.

This module used to hold all 43 endpoints inline (1160 lines). It stays as the
single import site — `main.py` and the tests still do `from .api.routes import
router` — so the split is invisible to everything downstream; the handlers now
live one module per domain area under `api/public/` and `api/admin/`.
"""

from __future__ import annotations

from fastapi import APIRouter

from .admin import router as admin_router
from .public import router as public_router

router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)
