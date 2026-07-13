import pytest

import app.domain.districts as districts
import app.pipeline.ingest as ingest


@pytest.fixture(autouse=True)
def _reset_ingest_globals():
    """Reset process-global ingest/tracking caches before every test.

    `_recent_type` (per-channel type inheritance) and the cached sentinel-
    district id (`domain.districts`) are process-global. Each test builds a
    FRESH DB, so a value cached from a prior test's DB would leak in — a
    spurious inherited type, or the wrong sentinel id. Live processes don't
    hit this (one long-lived DB, real-time progression).
    """
    ingest._recent_type.clear()
    districts.reset_cache()
    yield
    ingest._recent_type.clear()
    districts.reset_cache()
