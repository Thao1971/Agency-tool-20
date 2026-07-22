"""Smoke tests — Sprint 5 Recommendation Intelligence Engine (first CONSUMER).

Validates frozen contract DR1..DR10: 5 fit dimensions, roles, multifactor confidence,
canonical actions reuse, composites/graph fields, memory+feedback, decoupled service API.
"""
import os
import subprocess
import requests
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
RI = "/api/v1/recommendation-intelligence"
SVC = {"X-API-Key": os.environ.get("ARROBA_SERVICE_API_KEY",
                                   "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk")}

pytestmark = pytest.mark.skipif(
    not os.path.isdir(SAMPLE_DIR), reason="Iberinform sample fixture not present")

_TARGET = {}


@pytest.fixture(scope="module", autouse=True)
def _setup():
    subprocess.run(["sudo", "supervisorctl", "stop", "data_layer_worker"], capture_output=True)

    async def go():
        from database import db
        from services.data_layer.ingestion.iberinform_ingest import ingest_directory
        from services.data_layer.master.master_builder import rebuild_master
        from services.engines.semantic import persistence as SP
        from services.engines.semantic.engine import build_profile
        from services.engines.recommendation import memory as MEM
        if await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}}) < 50:
            await ingest_directory(SAMPLE_DIR, source_version="20260519")
            await rebuild_master(scope="full")
        await SP.ensure_indexes()
        await MEM.ensure_indexes()
        await db.semantic_profiles.delete_many({})
        # build a semantic-profile pool so comparables/buyers/sellers have candidates
        from collections import Counter
        ids_by_section = {}
        async for d in db.master_companies.find(
                {"classification.cnae_section": {"$ne": None},
                 "financials.latest.revenue": {"$ne": None}},
                {"_id": 0, "master_id": 1, "classification.cnae_section": 1}).limit(150):
            sec = d["classification"]["cnae_section"]
            ids_by_section.setdefault(sec, []).append(d["master_id"])
        # choose the section with the most companies as target's section
        top_sec = max(ids_by_section, key=lambda s: len(ids_by_section[s]))
        pool = []
        for sec, ids in ids_by_section.items():
            pool += ids[:20]
        for mid in pool:
            await build_profile(mid)
        _TARGET["id"] = ids_by_section[top_sec][0]
    _run(go())
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


def _two_same_section():
    async def go():
        from database import db
        prof = await db.semantic_profiles.find_one({"embedding.vector": {"$exists": True}},
                                                   {"_id": 0, "master_id": 1, "cnae_section": 1})
        sec = prof["cnae_section"]
        ids = []
        async for d in db.semantic_profiles.find(
                {"cnae_section": sec, "embedding.vector": {"$exists": True}},
                {"_id": 0, "master_id": 1}).limit(2):
            ids.append(d["master_id"])
        return ids
    return _run(go())


def test_catalog_versions_and_dims():
    from services.engines.recommendation import scoring as S
    r = requests.get(f"{__base()}{RI}/catalog", headers=SVC, timeout=20).json()
    assert r["recommendation_method"] == "weighted-blend-v1"
    assert set(r["fit_dimensions"]) == {"strategic_fit", "financial_fit", "semantic_fit",
                                        "signal_fit", "execution_fit"}
    assert r["unavailable_types"]["investor"] == "source_not_available"
    assert r["unavailable_types"]["advisor"] == "source_not_available"
    # DR6: actions are EXACTLY the Signal engine canonical actions
    from services.engines.signal.actions import CANONICAL_ACTIONS
    assert r["canonical_actions"] == CANONICAL_ACTIONS


def __base():
    return os.environ.get("BASE_URL", "http://localhost:8001")


def test_comparables_five_dims_and_confidence():
    tid = _TARGET["id"]
    d = requests.post(f"{__base()}{RI}/comparables", headers=SVC,
                      json={"identifier": tid, "limit": 5}, timeout=60).json()
    assert d["status"] == "available"
    if d["count"] == 0:
        pytest.skip("no same-section candidates with embeddings in sample")
    r = d["recommendations"][0]
    assert set(r["fit_dimensions"].keys()) == {"strategic_fit", "financial_fit",
                                               "semantic_fit", "signal_fit", "execution_fit"}
    # score derived from dims, never opaque
    assert "score" in r and r["score_method"] == "derived_from_fit_dimensions"
    # DR5 multifactor confidence
    assert set(r["confidence"]["factors"].keys()) == {"coverage", "data_quality",
        "cross_engine_consistency", "recency", "profile_completeness"}
    # explainability + graph edge + versioning
    assert r["evidence"]["engines_used"] and r["graph_edges"]
    assert r["recommendation_version"] == "recommendation-intelligence-v1"
    assert set(r["evidence_version"].keys()) >= {"master", "financial", "signal", "semantic", "knowledge_graph"}


def test_buyers_roles_valid():
    from services.engines.recommendation.engine import ACTIONS_BY_ROLE
    d = requests.post(f"{__base()}{RI}/buyers", headers=SVC,
                      json={"identifier": _TARGET["id"], "limit": 5}, timeout=60).json()
    for r in d.get("recommendations", []):
        assert r["recommendation_role"] in ACTIONS_BY_ROLE
        assert all(a in __actions() for a in r["recommended_actions"])


def __actions():
    from services.engines.signal.actions import CANONICAL_ACTIONS
    return CANONICAL_ACTIONS


def test_investors_advisors_unavailable():
    for t in ("investors", "advisors"):
        d = requests.post(f"{__base()}{RI}/{t}", headers=SVC,
                          json={"identifier": _TARGET["id"]}, timeout=20).json()
        assert d["status"] == "unavailable" and d["reason"] == "source_not_available"
        assert d["recommendations"] == []


def test_matching_explains_not_just_percent():
    ids = _two_same_section()
    if len(ids) < 2:
        pytest.skip("need two profiled companies")
    d = requests.post(f"{__base()}{RI}/matching", headers=SVC,
                      json={"a": ids[0], "b": ids[1]}, timeout=60).json()
    m = d["match"]
    assert len(m["fit_dimensions"]) == 5 and m["explanation"]


def test_recommendation_id_deterministic():
    from services.engines.recommendation.engine import _rec_id
    assert _rec_id("a", "b", "comparable") == _rec_id("a", "b", "comparable")


def test_memory_and_feedback():
    """DR9/DR10: feedback recorded as evidence; memory tracks lifecycle."""
    d = requests.post(f"{__base()}{RI}/buyers", headers=SVC,
                      json={"identifier": _TARGET["id"], "limit": 3}, timeout=60).json()
    if not d.get("recommendations"):
        pytest.skip("no recommendations to give feedback on")
    rid = d["recommendations"][0]["recommendation_id"]
    fb = requests.post(f"{__base()}{RI}/feedback", headers=SVC,
                       json={"recommendation_id": rid, "event": "accepted"}, timeout=20).json()
    assert fb["recorded"] is True
    mem = requests.post(f"{__base()}{RI}/memory", headers=SVC,
                        json={"recommendation_id": rid}, timeout=20).json()
    assert mem["memory"] and mem["memory"][0]["state"] == "accepted"
    # invalid feedback event rejected
    bad = requests.post(f"{__base()}{RI}/feedback", headers=SVC,
                        json={"recommendation_id": rid, "event": "nope"}, timeout=20)
    assert bad.status_code == 400


def test_api_requires_service_key():
    r = requests.post(f"{__base()}{RI}/comparables", json={"identifier": "x"}, timeout=20)
    assert r.status_code == 401
    nf = requests.post(f"{__base()}{RI}/comparables", headers=SVC,
                       json={"identifier": "nope"}, timeout=20)
    assert nf.status_code == 404
