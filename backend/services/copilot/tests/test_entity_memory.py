"""Fase 3 — memoria de entidad: histórico por compañía + diff ('mejoró desde…')."""

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
from services.copilot import entity_memory as ENTITY
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def _dec(band, score, did):
    return {"recommendation": band, "investment_score": score, "decision_id": did, "confidence": 0.7}


def test_first_then_improvement():
    t, u, c = "te", "ue", "CO1"
    r1 = _run(ENTITY.record_decision(t, u, c, _dec("EXPLORE", 62, "d1")))
    assert r1["delta"]["first"] is True and "Primer análisis" in r1["narrative"]
    r2 = _run(ENTITY.record_decision(t, u, c, _dec("PROCEED", 78, "d2")))
    d = r2["delta"]
    assert d["direction"] == "improved" and d["band_changed"] is True
    assert d["score_delta"] == 16 and "ha mejorado" in r2["narrative"]


def test_worsened_and_stable():
    t, u, c = "te", "ue", "CO2"
    _run(ENTITY.record_decision(t, u, c, _dec("PROCEED", 80, "a")))
    worse = _run(ENTITY.record_decision(t, u, c, _dec("EXPLORE", 55, "b")))
    assert worse["delta"]["direction"] == "worsened" and "ha empeorado" in worse["narrative"]
    same = _run(ENTITY.record_decision(t, u, c, _dec("EXPLORE", 55, "b")))
    assert same["delta"]["direction"] == "stable" and "se mantiene" in same["narrative"]


def test_latest_and_history():
    t, u, c = "th", "uh", "CO3"
    _run(ENTITY.record_decision(t, u, c, _dec("PASS", 40, "x")))
    _run(ENTITY.record_decision(t, u, c, _dec("EXPLORE", 50, "y")))
    last = _run(ENTITY.latest(t, u, c))
    assert last["recommendation"] == "EXPLORE" and last["score"] == 50
    hist = _run(ENTITY.history(t, u, c))
    assert len(hist) == 2 and hist[0]["decision_id"] == "y"      # más reciente primero
    # aislamiento por usuario
    assert _run(ENTITY.latest(t, "otro", c)) is None


_INPUTS = {"identity": {"name": "ACME", "cnae_section": "C"},
           "kpis": {"ebitda": 1e7, "revenue": 5e7, "ebitda_margin": 0.18, "revenue_cagr": 0.09,
                    "solvency": 0.55, "revenue_per_employee": 3e5},
           "valuation": {"enterprise_value": 6e7, "range": {"low": 5e7, "high": 7e7}},
           "comparables": {"subject_ebitda_margin_percentile": 0.7}, "assessment": {"strengths": ["A"]},
           "sector_intelligence": {"s": 1}, "documents": {"d": 1}, "fragmentation": {"hhi": 1300},
           "evolution": {"points": [{"year": 2024, "ebitda": 1e7}]}, "financials": {}}


def test_orchestrate_records_on_L3_and_shows_on_L0():
    user = {"tenant_id": "to", "user_id": "uo"}
    r3 = _run(orchestrate({"question": "¿deberíamos comprarla?", "company_id": "ACME",
                           "opportunity_id": "ACME", "inputs": _INPUTS, "user": user}))
    assert r3["level"] == "L3" and "entity_history" in r3
    assert r3["entity_history"]["current"]["recommendation"] == r3["decision"]["recommendation"]
    # consulta posterior distinta nivel: adjunta el último análisis
    r0 = _run(orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                           "opportunity_id": "ACME", "inputs": _INPUTS, "user": user}))
    assert r0["entity_history"]["narrative"].startswith("Último análisis registrado")


if __name__ == "__main__":
    for fn in (test_first_then_improvement, test_worsened_and_stable, test_latest_and_history,
               test_orchestrate_records_on_L3_and_shows_on_L0):
        fn(); print("OK", fn.__name__)
