"""Fase 4 — feedback → sesgo de ranking acotado (90d, ±10%), solo surfacing, nunca score del comité."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_test"]
except Exception:
    pass

import asyncio
from services.copilot import feedback as FB
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_record_and_bias_reason():
    t, u = "tf", "uf"
    for _ in range(3):
        _run(FB.record(t, u, "dismiss", dimensions={"sector": "retail"}))
    _run(FB.record(t, u, "accept", dimensions={"sector": "pharma"}))
    bias = _run(FB.compute_bias(t, u))
    assert bias["sector:retail"]["bias"] < 0 and "descartes" in bias["sector:retail"]["reason"]
    assert bias["sector:pharma"]["bias"] > 0 and "aceptaciones" in bias["sector:pharma"]["reason"]


def test_bias_is_capped_at_10pct():
    t, u = "tc", "uc"
    for _ in range(6):                                   # 6 × -0.03 = -0.18 → recorta a -0.10
        _run(FB.record(t, u, "dismiss", dimensions={"sector": "retail"}))
    bias = _run(FB.compute_bias(t, u))
    assert bias["sector:retail"]["bias"] == -0.10
    assert "10%" in bias["sector:retail"]["reason"]


def test_rank_with_bias_reorders_without_touching_score():
    items = [{"opportunity_id": "R", "investment_score": 70},
             {"opportunity_id": "P", "investment_score": 70}]
    dims = {"R": {"sector": "retail"}, "P": {"sector": "pharma"}}
    bias = {"sector:retail": {"bias": -0.10, "reason": "x"},
            "sector:pharma": {"bias": 0.10, "reason": "y"}}
    ranked = FB.rank_with_bias(items, "opportunity_id", "investment_score", 100, dims, bias)
    assert ranked[0]["opportunity_id"] == "P"           # pharma sube en surfacing
    assert all(x["investment_score"] == 70 for x in ranked)   # score del comité intacto
    assert ranked[0]["surfacing_score"] > ranked[1]["surfacing_score"]


def _op(k, sector):
    return {"opportunity_id": k, "company_id": k,
            "inputs": {"identity": {"name": k, "cnae_section": sector},
                       "kpis": {"ebitda": 1e7, "revenue": 5e7, "ebitda_margin": 0.18,
                                "revenue_cagr": 0.09, "solvency": 0.55},
                       "valuation": {"enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
                       "comparables": {}, "assessment": {}, "sector_intelligence": {},
                       "documents": {}, "fragmentation": {"hhi": 1300},
                       "evolution": {"points": [{"year": 2024, "ebitda": 1e7}]}, "financials": {}}}


def test_orchestrate_L4_applies_bias_and_exposes_reason():
    user = {"tenant_id": "to4", "user_id": "uo4"}
    for _ in range(4):
        _run(FB.record("to4", "uo4", "dismiss", dimensions={"sector": "retail"}))
    r = _run(orchestrate({"question": "compara estas dos", "user": user,
                          "opportunities": [_op("R", "retail"), _op("P", "pharma")]}))
    assert r["level"] == "L4"
    assert r["personalization_applied"]["ranking_bias"]                 # explica el sesgo
    ranking = r["answer"]["data"]["ranking"]
    assert "surfacing_score" in ranking[0] and "bias_applied" in ranking[0]


if __name__ == "__main__":
    for fn in (test_record_and_bias_reason, test_bias_is_capped_at_10pct,
               test_rank_with_bias_reorders_without_touching_score,
               test_orchestrate_L4_applies_bias_and_exposes_reason):
        fn(); print("OK", fn.__name__)
