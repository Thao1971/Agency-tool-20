"""ARROBA Company Taxonomy Registry v1 — siembra idempotente, ids estables, lectura."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "taxonomy_test")
try:
    from mongomock_motor import AsyncMongoMockClient
    import database
    database.db = AsyncMongoMockClient()["taxonomy_test"]
except Exception:
    pass

import asyncio
from services.taxonomy import registry as REG

_loop = asyncio.get_event_loop()


def _run(c):
    return _loop.run_until_complete(c)


def test_seed_structure_and_stable_ids():
    nodes = REG.build_nodes()
    sectors = [n for n in nodes if n["level"] == "sector"]
    industries = [n for n in nodes if n["level"] == "industry"]
    categories = [n for n in nodes if n["level"] == "category"]
    assert len(sectors) == 11
    assert len(industries) > 100 and len(categories) > 300
    # ids únicos y estables
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids))
    assert REG.industry_id("S03", "AdTech") == "IND-S03-adtech"
    # jerarquía coherente: toda industria cuelga de un sector; toda categoría de una industria
    node_by_id = {n["id"]: n for n in nodes}
    for n in industries:
        assert n["parent_id"] in node_by_id and node_by_id[n["parent_id"]]["level"] == "sector"
    for n in categories:
        assert node_by_id[n["parent_id"]]["level"] == "industry"


def test_dimensions_present():
    dims = REG.build_dimensions()
    kinds = {d["dimension"] for d in dims}
    assert {"verticals", "business_models", "client_types", "technologies", "value_chain",
            "capabilities"} <= kinds


def test_seed_is_idempotent():
    r1 = _run(REG.build_registry_v1())
    r2 = _run(REG.build_registry_v1())
    assert r1["nodes"] == r2["nodes"] and r1["sectors"] == 11
    # no se duplican al re-sembrar
    from database import db
    total = _run(db.taxonomy_nodes.count_documents({}))
    assert total == r1["nodes"]


def test_tree_and_node_read():
    _run(REG.build_registry_v1())
    tree = _run(REG.get_tree())
    assert len(tree) == 11 and all(t["children"] for t in tree)  # cada sector tiene industrias
    s03 = next(t for t in tree if t["id"] == "S03")
    assert any(ch["label_es"] == "AdTech" for ch in s03["children"])
    node = _run(REG.get_node("S03"))
    assert node["label_es"] == "Medios, Marketing y Comunicación"


if __name__ == "__main__":
    for fn in (test_seed_structure_and_stable_ids, test_dimensions_present,
               test_seed_is_idempotent, test_tree_and_node_read):
        fn(); print("OK", fn.__name__)
