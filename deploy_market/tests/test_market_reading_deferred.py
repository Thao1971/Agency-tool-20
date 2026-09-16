import asyncio

import pytest

from services import company_summary as summary


class _Collection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query, projection=None):
        return self.docs.get((query["master_id"], query["ctx_hash"]))

    async def update_one(self, query, update, upsert=False):
        self.docs[(query["master_id"], query["ctx_hash"])] = update["$set"]


class _DB:
    def __init__(self):
        self.collection = _Collection()

    def __getitem__(self, name):
        assert name == "market_readings"
        return self.collection


def _market():
    return {
        "available": True,
        "sector": {"available": True, "cnae_label": "Servicios", "size_score": 55},
        "geo": {"available": False},
        "concentration": {"available": False},
        "position": {"available": False},
    }


@pytest.mark.asyncio
async def test_deferred_market_reading_pending_deduplicated_then_ready(monkeypatch):
    fake_db = _DB()
    release = asyncio.Event()
    calls = 0

    async def fake_generate(ctx, **kwargs):
        nonlocal calls
        calls += 1
        await release.wait()
        return {"executive_summary": "Lectura generada", "_model": "test-model"}

    monkeypatch.setattr(summary, "db", fake_db)
    monkeypatch.setattr(summary, "generate_summary", fake_generate)
    summary._MKT_INFLIGHT.clear()
    summary._MKT_FAILURE_UNTIL.clear()

    first = await summary.defer_market_reading("mc_test", _market())
    second = await summary.defer_market_reading("mc_test", _market())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert first == {"reading": None, "status": "pending"}
    assert second == {"reading": None, "status": "pending"}
    assert calls == 1

    release.set()
    await next(iter(summary._MKT_INFLIGHT.values()))
    ready = await summary.defer_market_reading("mc_test", _market())

    assert ready == {"reading": "Lectura generada", "status": "ready"}
    assert calls == 1


@pytest.mark.asyncio
async def test_deferred_market_reading_without_context_is_unavailable(monkeypatch):
    monkeypatch.setattr(summary, "db", _DB())
    summary._MKT_INFLIGHT.clear()
    summary._MKT_FAILURE_UNTIL.clear()

    result = await summary.defer_market_reading("mc_empty", {"available": False})

    assert result == {"reading": None, "status": "unavailable"}
    assert summary._MKT_INFLIGHT == {}
