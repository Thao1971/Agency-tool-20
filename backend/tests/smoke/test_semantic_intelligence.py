"""Smoke tests — Sprint 4 Semantic Intelligence Engine.

Product = Company Semantic Profile (14 dims, explicit status, explainable). Embeddings/
similar/search are derived. Validates frozen contract D-S1..D-S6 + decoupled service API.
"""
import os
import subprocess
import requests
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
SE = "/api/v1/semantic-intelligence"
SVC = {"X-API-Key": os.environ.get("ARROBA_SERVICE_API_KEY",
                                   "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk")}

pytestmark = pytest.mark.skipif(
    not os.path.isdir(SAMPLE_DIR), reason="Iberinform sample fixture not present")


@pytest.fixture(scope="module", autouse=True)
def _setup():
    subprocess.run(["sudo", "supervisorctl", "stop", "data_layer_worker"], capture_output=True)

    async def go():
        from database import db
        from services.data_layer.ingestion.iberinform_ingest import ingest_directory
        from services.data_layer.master.master_builder import rebuild_master
        from services.engines.semantic import persistence as P
        from services.engines.semantic.engine import build_profile
        if await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}}) < 50:
            await ingest_directory(SAMPLE_DIR, source_version="20260519")
            await rebuild_master(scope="full")
        await P.ensure_indexes()
        # fresh start: drop any stale profiles from previous master rebuilds
        await db.semantic_profiles.delete_many({})
        # build a pool of profiles so /similar and /search have candidates
        ids = []
        async for d in db.master_companies.find(
                {"classification.cnae_section": {"$ne": None}}, {"_id": 0, "master_id": 1}).limit(60):
            ids.append(d["master_id"])
        for mid in ids:
            await build_profile(mid)
    _run(go())
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


def _a_master_id():
    async def go():
        from database import db
        # resolve from master_companies (current truth), then ensure its profile exists
        d = await db.master_companies.find_one(
            {"classification.cnae_section": {"$ne": None}}, {"_id": 0, "master_id": 1})
        return d["master_id"]
    return _run(go())


def test_profile_is_product_14_dims_with_status():
    from services.engines.semantic.engine import build_profile
    from services.engines.semantic.profile import DIMENSIONS
    p = _run(build_profile(_a_master_id()))
    assert p["profile_version"] == "semantic-profile-v1"
    sp = p["semantic_profile"]
    assert set(DIMENSIONS) <= set(sp.keys()) and len(DIMENSIONS) == 14
    # every dimension carries explicit status (D-S4)
    for f in DIMENSIONS:
        if f == "semantic_relationships":
            continue
        v = sp[f]
        items = v if isinstance(v, list) else [v]
        for it in items:
            assert it.get("status") in ("available", "partial", "unavailable")
            assert "method" in it and "evidence" in it and "confidence" in it
    assert {"score", "fields_total", "by_status"} <= set(p["coverage"].keys())
    assert p["coverage"]["fields_total"] == 14


def test_no_invention_without_evidence():
    """D-S1: customers/suppliers have no Master data -> explicit unavailable, no invented values."""
    from services.engines.semantic.engine import build_profile
    p = _run(build_profile(_a_master_id()))
    for f in ("customers", "suppliers"):
        for it in p["semantic_profile"][f]:
            assert it["status"] == "unavailable" and it["value"] is None


def test_embedding_is_derived_and_versioned():
    from services.engines.semantic.engine import build_profile
    p = _run(build_profile(_a_master_id()))
    emb = p["embedding"]
    assert emb and emb["embedding_version"] == "emb-v1"
    for k in ("provider", "model", "profile_checksum", "generated_at", "sources"):
        assert k in emb


def test_checksum_reproducible():
    from services.engines.semantic.engine import build_profile
    mid = _a_master_id()
    a = _run(build_profile(mid, persist=False))
    b = _run(build_profile(mid, persist=False))
    assert a["embedding"]["profile_checksum"] == b["embedding"]["profile_checksum"]


def test_similar_topk_blocked_by_sector():
    from services.engines.semantic.engine import similar
    r = _run(similar(_a_master_id(), limit=5))
    assert r["backend"] == "local-topk-v1"
    assert "cnae_section" in r["blocking"]
    for row in r["similar"]:
        assert "score" in row and "master_id" in row


# ── API contract (service-key auth, UI-agnostic) ──
def test_api_requires_service_key(base_url):
    r = requests.post(f"{base_url}{SE}/profile", json={"identifier": "x"}, timeout=20)
    assert r.status_code == 401


def test_api_endpoints(base_url):
    mid = _a_master_id()
    p = requests.post(f"{base_url}{SE}/profile", headers=SVC, json={"identifier": mid}, timeout=60)
    assert p.status_code == 200 and "semantic_profile" in p.json()

    e = requests.post(f"{base_url}{SE}/embedding", headers=SVC, json={"identifier": mid}, timeout=30)
    assert e.status_code == 200 and e.json()["embedding"]["embedding_version"] == "emb-v1"

    s = requests.post(f"{base_url}{SE}/similar", headers=SVC, json={"identifier": mid, "limit": 5}, timeout=30)
    assert s.status_code == 200 and "similar" in s.json()

    q = requests.post(f"{base_url}{SE}/search", headers=SVC, json={"query": "transporte logistica", "limit": 5}, timeout=30)
    assert q.status_code == 200 and "results" in q.json()

    sc = requests.get(f"{base_url}{SE}/profile/schema", headers=SVC, timeout=20)
    assert sc.status_code == 200 and sc.json()["dimension_count"] == 14

    c = requests.get(f"{base_url}{SE}/catalog", headers=SVC, timeout=20)
    cj = c.json()
    assert c.status_code == 200 and cj["profile_version"] == "semantic-profile-v1"
    assert cj["vector_search_backend"] == "local-topk-v1"

    nf = requests.post(f"{base_url}{SE}/profile", headers=SVC, json={"identifier": "nope"}, timeout=20)
    assert nf.status_code == 404
