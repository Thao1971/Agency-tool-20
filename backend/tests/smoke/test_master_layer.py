"""Smoke tests — Sprint 1 Master Layer (master_companies, entity_xref, ER, merge, KG ownership).

Worker is paused so job handlers run deterministically via the runner. Setup ingests the
sample and builds the master once for the module.
"""
import os
import subprocess
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
JOBS = "/api/v1/data-layer/jobs"
STRUCTURAL_TYPES = {"shareholder_of", "parent_of", "ultimate_parent_of", "investee_of"}

pytestmark = pytest.mark.skipif(
    not os.path.isdir(SAMPLE_DIR), reason="Iberinform sample fixture not present")


@pytest.fixture(scope="module", autouse=True)
def _setup():
    subprocess.run(["sudo", "supervisorctl", "stop", "data_layer_worker"], capture_output=True)
    import services.jobs.handlers  # noqa: F401  (registers master handlers)

    async def go():
        from database import db
        from services.data_layer.ingestion.iberinform_ingest import ingest_directory
        from services.data_layer.master.master_builder import rebuild_master
        from services.data_layer.master.ownership_graph import rebuild_ownership_graph
        for c in ["norm_company", "norm_financials", "norm_ownership", "norm_officers",
                  "master_companies", "entity_xref", "master_relationships"]:
            await db[c].delete_many({})
        await ingest_directory(SAMPLE_DIR, source_version="20260519")
        await rebuild_master(scope="full")
        await rebuild_ownership_graph()
    _run(go())
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


def test_master_built_with_canonical_shape():
    from database import db

    async def go():
        n = await db.master_companies.count_documents({})
        d = await db.master_companies.find_one({"financials.latest.revenue": {"$ne": None}}, {"_id": 0})
        return n, d

    n, d = _run(go())
    assert n >= 900
    assert d["master_id"].startswith("mc_") and d["status"] == "active"
    for k in ("identity", "classification", "location", "contact", "financials", "ownership",
              "provenance", "sources", "pipeline_version", "source_hash"):
        assert k in d
    assert d["pipeline_version"] == "master-v1"
    assert d["financials"]["latest"]["ebitda"] is not None


def test_entity_xref_maps_and_sources_untouched():
    from database import db

    async def go():
        m = await db.master_companies.find_one({}, {"_id": 0})
        x = await db.entity_xref.find_one(
            {"id_type": "cif", "external_id": m["cif_normalized"]}, {"_id": 0})
        # original normalized source must remain intact (non-destructive)
        nc = await db.norm_company.find_one({"cif_normalized": m["cif_normalized"]}, {"_id": 0})
        cif_rows = await db.entity_xref.count_documents({"id_type": "cif"})
        n_master = await db.master_companies.count_documents({})
        return m, x, nc, cif_rows, n_master

    m, x, nc, cif_rows, n_master = _run(go())
    assert x and x["master_id"] == m["master_id"]
    assert nc is not None and nc.get("legal_name")     # source unchanged
    assert cif_rows == n_master                          # one cif xref per master


def test_rebuild_is_idempotent_and_id_permanent():
    from database import db
    from services.data_layer.master.master_builder import rebuild_master

    async def go():
        before = await db.master_companies.find_one({}, {"_id": 0, "cif_normalized": 1, "master_id": 1})
        stats = await rebuild_master(scope="full")
        after = await db.master_companies.find_one(
            {"cif_normalized": before["cif_normalized"]}, {"_id": 0, "master_id": 1})
        return stats, before, after

    stats, before, after = _run(go())
    assert stats["built"] == 0 and stats["skipped"] >= 900   # nothing changed → all skipped
    assert before["master_id"] == after["master_id"]          # permanent id


def test_incremental_scope_processes_only_dirty():
    from database import db
    from services.data_layer.master.master_builder import rebuild_master

    async def go():
        await db.norm_company.update_one({}, {"$set": {"dirty": True}})
        stats = await rebuild_master(scope="incremental")
        return stats

    stats = _run(go())
    assert (stats["built"] + stats["skipped"]) == 1   # only the single dirty record


def test_merge_provenance_non_destructive():
    from database import db

    async def go():
        return await db.master_companies.find_one({"identity.legal_name": {"$ne": None}}, {"_id": 0})

    d = _run(go())
    prov = d["provenance"]["legal_name"]
    assert isinstance(prov, list) and prov
    c = prov[0]
    assert {"source", "value", "observed_at", "confidence"} <= set(c.keys())
    assert d["identity"]["legal_name"] == c["value"]   # canonical matches retained candidate


def test_ownership_graph_structural_only():
    from database import db

    async def go():
        types = set(await db.master_relationships.distinct("relationship_type"))
        n = await db.master_relationships.count_documents({})
        grouped = await db.master_companies.count_documents({"ownership.group_id": {"$ne": None}})
        return types, n, grouped

    types, n, grouped = _run(go())
    assert n > 0
    assert types <= STRUCTURAL_TYPES                      # NO similarity/semantic edges
    assert "similar_to" not in types and "same_cluster" not in types


def test_rebuild_master_via_job_runner():
    from services.jobs import queue
    from services.jobs.runner import JobRunner
    from database import db

    async def go():
        await db.data_layer_jobs.delete_many({})
        jid = await queue.enqueue("rebuild_master", {"scope": "full"})
        await JobRunner("wMaster").process_one()
        return await queue.get(jid)

    doc = _run(go())
    assert doc["status"] == "completed"
    assert doc["result"]["total_master"] >= 900
