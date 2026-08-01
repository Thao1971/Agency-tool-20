"""Smoke del Orquestador del Copilot: clasificación de intención + enrutado L0–L4 (determinista,
con evidencia inyectada; el comité y las capacidades ya están testeados aparte)."""

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
from services.copilot import orchestrate
from services.copilot import intent as INTENT

INPUTS = {
    "identity": {"name": "TESTCO", "cnae_section": "C"},
    "kpis": {"ebitda_margin": 0.18, "revenue_cagr": 0.09, "solvency": 0.55, "ebitda": 1e7,
             "revenue": 5e7, "revenue_per_employee": 300000},
    "valuation": {"method": "ev_ebitda", "multiple_basis": "inferred_reference",
                  "enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
    "evolution": {"points": [{"year": 2024, "ebitda": 1e7, "net_financial_position": 4e6}]},
    "financials": {"x": 1}, "comparables": {"subject_ebitda_margin_percentile": 0.7},
    "assessment": {"strengths": ["A", "B"]}, "sector_intelligence": {"s": 1},
    "documents": {"d": 1}, "fragmentation": {"hhi": 1300, "standalone_targets_count": 40},
}


def _ask(q, **kw):
    req = {"question": q, "opportunity_id": "T", "buyer_profile": {"type": "private_equity"}, "inputs": INPUTS}
    req.update(kw)
    return asyncio.get_event_loop().run_until_complete(orchestrate(req))


def test_intent_levels():
    assert INTENT.classify("¿cuál es el EBITDA?")["level"] == "L0"
    assert INTENT.classify("¿cuánto vale la empresa?")["level"] == "L1"
    assert INTENT.classify("¿qué riesgos legales tiene?")["level"] == "L2"
    assert INTENT.classify("¿deberíamos comprarla?")["level"] == "L3"
    assert INTENT.classify("compara estas dos")["level"] == "L4"


def test_L0_fact():
    r = _ask("¿cuál es el EBITDA?")
    assert r["level"] == "L0" and "EBITDA" in r["answer"]["headline"]


def test_L1_specialist():
    r = _ask("¿cuánto vale?")
    assert r["level"] == "L1" and r["answer"]["detail"]


def test_L3_committee_single_voice():
    r = _ask("¿deberíamos comprarla?")
    assert r["level"] == "L3" and r["answer"].get("message")   # voz única, natural
    assert r["decision"]["recommendation"] in ("PROCEED", "PROCEED_WITH_CONDITIONS", "EXPLORE",
                                               "PASS", "REJECT")
    assert "committee" in r and len(r["committee"]) == 10   # comité completo (interno)


def test_L4_compare():
    r = _ask("compara estas dos", opportunities=[{"opportunity_id": "A", "inputs": INPUTS},
                                                 {"opportunity_id": "B", "inputs": INPUTS}])
    assert r["level"] == "L4" and r["answer"]["data"]["ranking"]


def test_degraded_never_500():
    import services.copilot.orchestrator as O

    async def _boom(req, sink=None):
        raise RuntimeError("motor caído")

    orig = O._route
    O._route = _boom
    try:
        r = asyncio.get_event_loop().run_until_complete(
            O.orchestrate({"question": "¿deberíamos comprarla?", "opportunity_id": "X",
                           "buyer_profile": {"type": "private_equity"}, "inputs": INPUTS}))
    finally:
        O._route = orig
    assert r.get("degraded") is True
    assert "No he podido completar" in r["answer"]["message"]
    assert r.get("session_id")                     # la conversación sigue viva


if __name__ == "__main__":
    for fn in (test_intent_levels, test_L0_fact, test_L1_specialist,
               test_L3_committee_single_voice, test_L4_compare, test_degraded_never_500):
        fn(); print("OK", fn.__name__)
