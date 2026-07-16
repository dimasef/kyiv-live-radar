import asyncio

import pytest

import app.domain.districts as districts
import app.pipeline.ingest as ingest
import app.pipeline.triage as triage
from app.parsing.rules import LlmUsage


@pytest.fixture(autouse=True)
def _reset_ingest_globals():
    """Reset process-global ingest/tracking caches before every test.

    `_recent_type` (per-channel type inheritance) and the cached sentinel-
    district id (`domain.districts`) are process-global. Each test builds a
    FRESH DB, so a value cached from a prior test's DB would leak in — a
    spurious inherited type, or the wrong sentinel id. Live processes don't
    hit this (one long-lived DB, real-time progression).

    The triage queue is bound to the event loop it was created on; pytest-asyncio
    builds a fresh loop per test, so a queue from a prior test would raise. Drop
    it (and the cost-guard cache) here too.
    """
    ingest._recent_type.clear()
    districts.reset_cache()
    triage.reset_queue()
    triage._invalidate_spend_cache()
    yield
    ingest._recent_type.clear()
    districts.reset_cache()
    triage.reset_queue()
    triage._invalidate_spend_cache()


def make_verdict(*, category="noise", surface=False, summary="", origin_place="none",
                 origin_sector="none", district_ids=None, target_type="unknown",
                 status="sighting", is_new_target=False, confidence=0.8):
    """Build a well-formed LLM triage verdict for tests (mirrors llm._normalize)."""
    return {
        "schema_version": 2, "category": category, "origin_place": origin_place,
        "origin_sector": origin_sector, "surface": surface, "summary": summary,
        "district_ids": district_ids or [], "target_type": target_type,
        "status": status, "is_new_target": is_new_target, "confidence": confidence,
    }


class _StubLlm:
    """Canned-verdict fake for llm_triage / llm_extract, keyed by text substring.
    No network ever. Records calls; supports injected latency for ordering tests."""

    def __init__(self):
        self._rules: list[tuple[str, dict]] = []
        self.default = make_verdict()
        self.latency = 0.0
        self.calls: list[str] = []

    def set(self, substring: str, verdict: dict):
        self._rules.append((substring, verdict))

    def verdict_for(self, text: str) -> dict:
        for sub, v in self._rules:
            if sub in text:
                return v
        return self.default

    async def _triage(self, text, matcher):
        self.calls.append(text)
        if self.latency:
            await asyncio.sleep(self.latency)
        return self.verdict_for(text), LlmUsage(10, 10, 0.0001)


@pytest.fixture
def stub_llm(monkeypatch):
    """Patch the LLM entry points with a canned fake and enable the triage path
    (real code reads settings.anthropic_api_key='' -> never calls the network;
    this makes that explicit AND lets llm_triage be driven from a fixture)."""
    from app.config import settings

    stub = _StubLlm()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "triage_enabled", True)
    monkeypatch.setattr("app.parsing.llm.llm_triage", stub._triage)
    return stub


async def drain_triage(stub_run_consumer=None):
    """Run the triage consumer until the queue is empty, then stop it — for
    end-to-end enqueue->route tests."""
    queue = triage.get_queue()
    task = asyncio.create_task(triage.run_triage_consumer())
    try:
        await asyncio.wait_for(queue.join(), timeout=5)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
