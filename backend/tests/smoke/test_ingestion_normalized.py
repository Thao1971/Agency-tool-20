"""Smoke tests — P0.7+P0.1 Iberinform ingestion (raw CSV → Normalized layer).

Validates the real-sample data model end-to-end: streaming, EAV pivot to
(cif_normalized, year, basis), idempotent bulk upsert, derived metrics, ownership graph.
Skips if the fixture sample isn't present.
"""
import os
import asyncio
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
pytestmark = pytest.mark.skipif(
    not os.path.isdir(SAMPLE_DIR), reason="Iberinform sample fixture not present")


def test_ingest_sample_end_to_end():
    from services.data_layer.ingestion.iberinform_ingest import ingest_directory
    from database import db

    async def go():
        res = await ingest_directory(SAMPLE_DIR, source_version="20260519")
        comp = await db.norm_company.count_documents({})
        fin = await db.norm_financials.count_documents({})
        own = await db.norm_ownership.count_documents({})
        man = await db.raw_ingestion_manifest.count_documents({"ingestion_job_id": res["ingestion_job_id"]})
        # pivot: financial docs are per company-year, far fewer than EAV rows
        fin_file = next(f for f in res["files"] if f["file"] == "ES_Financial_Detail_Valu8.csv")
        return res, comp, fin, own, man, fin_file

    res, comp, fin, own, man, fin_file = _run(go())
    assert comp >= 900            # 1000 companies in sample
    assert fin_file["rows"] > 90000 and fin_file["queued"] < 2000   # EAV pivot collapsed rows→docs
    assert own > 100              # ownership edges materialized
    assert man == 8               # one manifest per CSV
    assert res["source_version"] == "20260519"


def test_derived_metrics_and_join():
    from database import db

    async def go():
        f = await db.norm_financials.find_one(
            {"revenue": {"$nin": [None, 0]}, "ebitda": {"$ne": None}}, {"_id": 0})
        comp = await db.norm_company.find_one({"cif_normalized": f["cif_normalized"]}, {"_id": 0})
        return f, comp

    f, comp = _run(go())
    assert f["revenue"] > 0
    assert f["ebitda"] is not None
    # EBITDA == operating_income + |depreciation| when both present
    if f.get("operating_income") is not None and f.get("depreciation") is not None:
        assert abs(f["ebitda"] - (f["operating_income"] + abs(f["depreciation"]))) < 1.0
    assert "accounts" in f and len(f["accounts"]) > 10   # full statement retained
    assert comp is not None and comp["cif_normalized"] == f["cif_normalized"]   # join by CIF


def test_ingest_is_idempotent():
    from services.data_layer.ingestion.iberinform_ingest import ingest_directory
    from database import db

    async def go():
        before = await db.norm_company.count_documents({})
        await ingest_directory(SAMPLE_DIR, source_version="20260519")
        after = await db.norm_company.count_documents({})
        return before, after

    before, after = _run(go())
    assert before == after   # re-running upserts, never duplicates


def test_ownership_graph_types_present():
    from database import db

    async def go():
        types = await db.norm_ownership.distinct("relationship_type")
        with_cif = await db.norm_ownership.count_documents({"counterparty_has_cif": True})
        with_pct = await db.norm_ownership.count_documents({"pct": {"$ne": None}})
        return set(types), with_cif, with_pct

    types, with_cif, with_pct = _run(go())
    assert {"shareholder", "parent_co", "ultimate_parent_co", "investee_co"} & types
    assert with_cif > 0 and with_pct > 0


def test_manifest_has_checksum_and_lineage():
    from database import db

    async def go():
        return await db.raw_ingestion_manifest.find_one({"target_collection": "norm_financials"}, {"_id": 0})

    m = _run(go())
    assert m and len(m["checksum"]) == 64        # sha256 hex
    assert m["bytes"] > 0 and m["status"] == "completed"
    assert m["lineage"]["layer"] == "raw->normalized"
