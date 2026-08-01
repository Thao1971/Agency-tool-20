"""F4 — Peer Universe Resolver + similitud de fingerprint (fixture, mongomock)."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "taxonomy_sim_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["taxonomy_sim_test"]
except Exception:
    pass

import asyncio
from services.taxonomy import classify as CLS
from services.taxonomy import similarity as SIM

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_fingerprint_cosine():
    a = {"sector": 90, "industry": 80, "vertical": 70, "capabilities": 0, "business_model": 60,
         "client": 50, "technology": 60}
    assert SIM.fingerprint_cosine(a, a) == 1.0
    assert SIM.fingerprint_cosine(a, {}) == 0.0
    b = {"sector": 10, "industry": 0, "vertical": 0, "capabilities": 90, "business_model": 0,
         "client": 0, "technology": 0}
    assert SIM.fingerprint_cosine(a, b) < 0.5


def _seed():
    from database import db
    # dos empresas AdTech/IA parecidas + una constructora distinta
    inputs = {"cnae": "6201", "description": "Plataforma de publicidad programática con inteligencia artificial. SaaS B2B."}
    _run(CLS.classify({"company_id": "P1", "inputs": {**inputs, "name": "AdCo Uno"}}))
    _run(CLS.classify({"company_id": "P2", "inputs": {**inputs, "name": "AdCo Dos"}}))
    _run(CLS.classify({"company_id": "C1", "inputs": {"cnae": "4121", "name": "Constructora",
                                                      "description": "Construcción de edificios."}}))
    _run(db.master_companies.insert_many([
        {"master_id": "P1", "financials": {"latest": {"revenue": 5_000_000}}, "location": {"provincia": "Madrid"}},
        {"master_id": "P2", "financials": {"latest": {"revenue": 6_000_000}}, "location": {"provincia": "Madrid"}},
        {"master_id": "C1", "financials": {"latest": {"revenue": 40_000_000}}, "location": {"provincia": "Sevilla"}},
    ]))


def test_peers_ranks_similar_first():
    _seed()
    res = _run(SIM.peers("P1", k=5))
    ids = [p["company_id"] for p in res["peers"]]
    assert "P2" in ids                      # la AdTech gemela aparece
    assert res["peers"][0]["company_id"] == "P2"   # y como primer comparable
    assert res["peers"][0]["why"]           # explica por qué (industria/vertical/tamaño/geo)
    # la constructora, si aparece, va por detrás
    if "C1" in ids:
        assert ids.index("C1") > ids.index("P2")


def test_peers_unclassified_is_safe():
    res = _run(SIM.peers("NO-EXISTE"))
    assert res["peers"] == [] and "note" in res


if __name__ == "__main__":
    for fn in (test_fingerprint_cosine, test_peers_ranks_similar_first, test_peers_unclassified_is_safe):
        fn(); print("OK", fn.__name__)
