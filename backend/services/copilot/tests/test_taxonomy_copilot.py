"""F5 — integración taxonomía↔Copilot: intención peers/taxo_search + orquestación L4 + narración."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_taxo_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["copilot_taxo_test"]
except Exception:
    pass

import asyncio
from services.copilot import intent as INTENT
from services.copilot import orchestrate
from services.taxonomy import classify as CLS

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_intent_peers_and_sector():
    assert INTENT.classify("comparables a Servier")["capability"] == "peers"
    assert INTENT.classify("empresas similares a esta")["capability"] == "peers"
    assert INTENT.classify("empresas del sector salud")["capability"] == "taxo_search"
    # 'compara estas dos' sigue siendo compare (no peers)
    assert INTENT.classify("compara estas dos")["capability"] == "compare"


def _seed():
    from database import db
    inp = {"cnae": "6201", "description": "Publicidad programática con inteligencia artificial. SaaS B2B."}
    _run(CLS.classify({"company_id": "P1", "inputs": {**inp, "name": "AdCo Uno"}}))
    _run(CLS.classify({"company_id": "P2", "inputs": {**inp, "name": "AdCo Dos"}}))
    _run(db.master_companies.insert_many([
        {"master_id": "P1", "financials": {"latest": {"revenue": 5e6}}, "location": {"provincia": "Madrid"}},
        {"master_id": "P2", "financials": {"latest": {"revenue": 6e6}}, "location": {"provincia": "Madrid"}},
    ]))


def test_orchestrate_peers():
    _seed()
    r = _run(orchestrate({"question": "enséñame comparables", "company_id": "P1",
                          "opportunity_id": "P1", "user": {"tenant_id": "t", "user_id": "u"}}))
    assert r["level"] == "L4" and r.get("capability") == "peers"
    ids = [p["company_id"] for p in r["answer"]["data"]["peers"]]
    assert "P2" in ids
    assert "comparables más cercanos" in r["answer"]["message"]


def test_orchestrate_sector_search():
    _seed()
    r = _run(orchestrate({"question": "empresas del sector tecnología", "user": {"tenant_id": "t", "user_id": "u"}}))
    assert r["level"] == "L4" and r.get("capability") == "taxo_search"
    # P1/P2 (software) deben salir bajo S02 Tecnología
    assert r["answer"]["data"]["company_ids"]
    assert "empresas en" in r["answer"]["message"].lower()


if __name__ == "__main__":
    for fn in (test_intent_peers_and_sector, test_orchestrate_peers, test_orchestrate_sector_search):
        fn(); print("OK", fn.__name__)
