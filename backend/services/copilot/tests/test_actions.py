"""Next Best Action + mini-card: sugerencias por nivel, caso no-resuelto, integración orchestrate."""

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
from services.copilot import actions as A
from services.copilot import orchestrate

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_L0_resolved_card_and_navigate():
    out = {"level": "L0", "fact": {"label": "EBITDA", "value": "10.000.000 €", "available": True},
           "answer": {}}
    nba = A.build(out, {"name": "ACME", "entity_id": "ACME", "resolved": True})
    kinds = [a["kind"] for a in nba["actions"]]
    assert "navigate" in kinds and "analyze" in kinds
    nav = next(a for a in nba["actions"] if a["kind"] == "navigate")
    assert nav["target"] == "/company/ACME"
    assert nba["card"]["type"] == "entity" and nba["card"]["kpis"][0]["label"] == "EBITDA"


def test_unresolved_offers_search_not_ficha():
    out = {"level": "L0", "fact": {"label": "EBITDA", "available": False}, "answer": {}}
    nba = A.build(out, {"name": "DESCONOCIDA", "entity_id": None, "resolved": False})
    kinds = {a["kind"] for a in nba["actions"]}
    assert kinds == {"search", "add_to_watchlist"} and nba["card"] is None


def test_L3_actions_and_conviction_chip():
    out = {"level": "L3", "decision": {"decision_id": "d1"},
           "answer": {"disclosure": {"conviction": "Convicción alta", "band": "PROCEED", "score": 94}}}
    nba = A.build(out, {"name": "ACME", "entity_id": "ACME", "resolved": True})
    kinds = [a["kind"] for a in nba["actions"]]
    assert "open_deliberation" in kinds and "generate_document" in kinds
    assert len(nba["actions"]) <= 3
    assert nba["card"]["conviction"] == "Convicción alta"      # chip cualitativo, no el 94


def test_L4_compare_actions():
    out = {"level": "L4", "capability": "compare", "answer": {"data": {"ranking": []}}}
    nba = A.build(out, {"name": "la compañía", "resolved": False,
                        "bias": ["−9% en sector retail: 3 descartes en 90 días"]})
    kinds = [a["kind"] for a in nba["actions"]]
    assert "navigate" in kinds and "explain_order" in kinds and nba["card"] is None


def test_orchestrate_attaches_actions():
    r = _run(orchestrate({"question": "¿cuál es el EBITDA?", "company_id": "ACME",
                          "opportunity_id": "ACME",
                          "inputs": {"identity": {"name": "ACME"}, "kpis": {"ebitda": 1e7},
                                     "evolution": {"points": []}, "financials": {}, "valuation": {},
                                     "comparables": {}, "assessment": {}, "sector_intelligence": {},
                                     "documents": {}, "fragmentation": {}},
                          "user": {"tenant_id": "ta", "user_id": "ua"}}))
    assert r.get("actions") and any(a["kind"] == "navigate" for a in r["actions"])
    assert r.get("ui", {}).get("card", {}).get("name") == "ACME"


def test_contract_covers_every_emitted_kind():
    # todas las acciones que build() puede emitir deben estar declaradas en el contrato
    emitted = set()
    for out, ctx in [
        ({"level": "L0", "fact": {"available": True, "label": "E", "value": "1"}, "answer": {}},
         {"name": "A", "entity_id": "A", "resolved": True}),
        ({"level": "L2", "answer": {"conflict": True}},
         {"name": "A", "entity_id": "A", "resolved": True}),
        ({"level": "L3", "decision": {"decision_id": "d"}, "answer": {}},
         {"name": "A", "entity_id": "A", "resolved": True}),
        ({"level": "L4", "capability": "compare", "answer": {"data": {"ranking": []}}},
         {"name": "x", "resolved": False, "bias": ["b"]}),
        ({"level": "L0", "fact": {"available": False, "label": "E"}, "answer": {}},
         {"name": "X", "entity_id": None, "resolved": False}),
    ]:
        for a in A.build(out, ctx)["actions"]:
            emitted.add(a["kind"])
    assert emitted and emitted <= set(A.CONTRACT["kinds"]), emitted


if __name__ == "__main__":
    for fn in (test_L0_resolved_card_and_navigate, test_unresolved_offers_search_not_ficha,
               test_L3_actions_and_conviction_chip, test_L4_compare_actions,
               test_orchestrate_attaches_actions, test_contract_covers_every_emitted_kind):
        fn(); print("OK", fn.__name__)
