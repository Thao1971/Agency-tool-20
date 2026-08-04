"""F5 — búsqueda por taxonomía (doble modo) + resolución de etiqueta."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "taxonomy_search_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["taxonomy_search_test"]
except Exception:
    pass

import asyncio
from services.taxonomy import classify as CLS
from services.taxonomy import search as SEARCH

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_resolve_label():
    assert SEARCH.resolve_label("Tecnología")["id"] == "S02"
    assert SEARCH.resolve_label("salud")["id"] == "S05"
    adtech = SEARCH.resolve_label("adtech")
    assert adtech and adtech["kind"] in ("industry", "verticals")


def test_search_by_sector_dual_mode():
    _run(CLS.classify({"company_id": "A1", "inputs": {"cnae": "6201",
         "name": "AdCo", "description": "Publicidad programática con inteligencia artificial. SaaS."}}))
    _run(CLS.classify({"company_id": "A2", "inputs": {"cnae": "4121",
         "name": "Constructora", "description": "Construcción de edificios."}}))
    # S02 en cualquier clasificación vs solo principal
    any_s02 = _run(SEARCH.search_by_taxonomy(node_id="S02", primary_only=False))
    only_s02 = _run(SEARCH.search_by_taxonomy(node_id="S02", primary_only=True))
    assert "A1" in any_s02["company_ids"]
    assert only_s02["count"] <= any_s02["count"]
    # sector construcción (S06) contiene a A2
    s06 = _run(SEARCH.search_by_taxonomy(node_id="S06"))
    assert "A2" in s06["company_ids"]


def test_sector_counts_and_resolve_name():
    from database import db
    _run(CLS.classify({"company_id": "SC1", "inputs": {"cnae": "6201", "name": "AdCo",
         "description": "publicidad programatica con inteligencia artificial"}}))
    _run(db.master_companies.insert_one({"master_id": "SC1", "identity": {"legal_name": "AdCo Uno SL"}}))
    secs = _run(SEARCH.sector_counts())
    assert len(secs) == 11 and all("count" in s for s in secs)
    hit = _run(SEARCH.resolve_company_by_name("AdCo Uno"))
    assert hit and hit["company_id"] == "SC1"


if __name__ == "__main__":
    for fn in (test_resolve_label, test_search_by_sector_dual_mode, test_sector_counts_and_resolve_name):
        fn(); print("OK", fn.__name__)
