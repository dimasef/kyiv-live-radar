import pytest

import app.broadcast as broadcast
import app.ingest as ingest


@pytest.fixture(autouse=True)
def _reset_ingest_globals():
    """Reset process-global ingest/broadcast caches before every test.

    `_recent_type` (per-channel type inheritance) and the cached sentinel-
    district id (`ingest._citywide_district_id`, `broadcast._sentinel_district_id`)
    are process-global. Each test builds a FRESH DB, so a value cached from a
    prior test's DB would leak in — a spurious inherited type, or the wrong
    sentinel id. Live processes don't hit this (one long-lived DB, real-time
    progression).
    """
    ingest._recent_type.clear()
    ingest._citywide_district_id = None
    broadcast._sentinel_district_id = None
    yield
    ingest._recent_type.clear()
    ingest._citywide_district_id = None
    broadcast._sentinel_district_id = None
