"""Observabilidad: se registra una métrica por turno y el resumen agrega niveles/latencia/degradado."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_metrics_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_metrics_test"]
except Exception:
    pass

import asyncio
from services.copilot import metrics as M
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


_INPUTS = {"identity": {"name": "ACME"}, "kpis": {"ebitda": 1e7, "revenue": 5e7, "ebitda_margin": 0.18,
                                                  "revenue_cagr": 0.09, "solvency": 0.55},
           "valuation": {"enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
           "comparables": {}, "assessment": {}, "sector_intelligence": {}, "documents": {},
           "fragmentation": {"hhi": 1300}, "evolution": {"points": [{"year": 2024, "ebitda": 1e7}]},
           "financials": {}}


def test_turns_recorded_and_summary_aggregates():
    u = {"tenant_id": "tm2", "user_id": "um2"}
    _run(orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                      "opportunity_id": "ACME", "inputs": _INPUTS, "user": u}))
    _run(orchestrate({"question": "¿deberíamos comprarla?", "company_id": "ACME",
                      "opportunity_id": "ACME", "inputs": _INPUTS, "user": u}))
    s = _run(M.summary("tm2"))
    assert s["turns"] == 2
    assert s["by_level"].get("L0") == 1 and s["by_level"].get("L3") == 1
    assert s["latency_ms"]["avg"] is not None
    assert 0.0 <= s["degraded_rate"] <= 1.0 and 0.0 <= s["nba_rate"] <= 1.0


def test_summary_empty_is_safe():
    s = _run(M.summary("nadie"))
    assert s["turns"] == 0


if __name__ == "__main__":
    for fn in (test_turns_recorded_and_summary_aggregates, test_summary_empty_is_safe):
        fn(); print("OK", fn.__name__)
