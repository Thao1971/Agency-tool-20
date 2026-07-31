"""Golden snapshot (Fase 9). Congela la salida determinista de un caso fijo para detectar
regresiones en pesos/umbrales/lógica del comité. Si cambias la config a propósito, actualiza
el snapshot conscientemente."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ide_golden")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["ide_golden"]
except Exception:
    pass

import asyncio
from services.engines.investment_decision import analyze

FIXTURE = {
    "opportunity_id": "GOLD", "buyer_profile": {"type": "private_equity"},
    "inputs": {
        "identity": {"name": "GOLD", "cnae_section": "C"},
        "kpis": {"ebitda_margin": 0.18, "revenue_cagr": 0.09, "solvency": 0.55,
                 "ebitda": 1e7, "revenue_per_employee": 300000, "ebitda_growth_yoy": 0.05},
        "valuation": {"method": "ev_ebitda", "multiple_basis": "inferred_reference",
                      "enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
        "evolution": {"points": [{"year": 2024, "ebitda": 1e7, "net_financial_position": 4e6}]},
        "financials": {"x": 1}, "comparables": {"subject_ebitda_margin_percentile": 0.7},
        "assessment": {"strengths": ["A", "B"]}, "sector_intelligence": {"s": 1},
        "documents": {"d": 1}, "fragmentation": {"hhi": 1300, "standalone_targets_count": 40},
    },
}

GOLDEN = {
    "recommendation": "PROCEED", "investment_score": 78,
    "committee": {
        "cfo": "proceed", "valuation": "proceed_with_conditions", "strategy": "proceed",
        "market": "proceed", "commercial": "proceed", "operations": "proceed",
        "hr": "abstain", "legal": "abstain", "risk": "proceed", "investment_director": "proceed",
    },
}


def test_golden_snapshot():
    r = asyncio.get_event_loop().run_until_complete(analyze(FIXTURE))
    got = {"recommendation": r["recommendation"], "investment_score": r["investment_score"],
           "committee": {o["specialist"]: o["recommendation"] for o in r["committee"]}}
    assert got == GOLDEN, f"Regresión vs golden:\n GOT={got}\n EXP={GOLDEN}"


if __name__ == "__main__":
    test_golden_snapshot(); print("OK test_golden_snapshot")
