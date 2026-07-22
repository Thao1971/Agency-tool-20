"""Smoke tests — Sprint 3 Signal Intelligence Engine.

Validates the frozen contract (D1-D8): taxonomy, parametrizable thresholds, 4 dimensions,
canonical actions, composites, persistence/history, decoupled service-key API.
"""
import os
import subprocess
import requests
import pytest
from smoke_loop import run_async as _run

SAMPLE_DIR = "/app/backend/tests/fixtures/iberinform_sample"
SI = "/api/v1/signal-intelligence"
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
        from services.engines.signal import thresholds as TH
        from services.engines.signal import persistence as P
        if await db.master_companies.count_documents({"financials.latest.revenue": {"$ne": None}}) < 50:
            await ingest_directory(SAMPLE_DIR, source_version="20260519")
            await rebuild_master(scope="full")
        await TH.ensure_thresholds()
        await P.ensure_indexes()
    _run(go())
    yield
    subprocess.run(["sudo", "supervisorctl", "start", "data_layer_worker"], capture_output=True)


def _master_ids(n=40):
    async def go():
        from database import db
        ids = []
        async for d in db.master_companies.find(
                {"financials.latest.revenue": {"$ne": None}}, {"_id": 0, "master_id": 1}).limit(n):
            ids.append(d["master_id"])
        return ids
    return _run(go())


def test_taxonomy_canonical_versioned():
    from services.engines.signal import taxonomy as T
    assert len(T.CATEGORIES) == 9
    assert set(T.CATEGORIES) == {"financial", "growth", "risk", "ownership", "corporate",
                                 "market", "opportunity", "transaction", "operational"}
    for st, meta in T.SIGNAL_TYPES.items():
        assert meta["category"] in T.CATEGORIES
        assert st.split(".")[0] == meta["category"] or meta["category"] in ("risk", "opportunity")


def test_actions_canonical_only():
    from services.engines.signal import actions as A
    assert A.validate(["analyze", "buy", "NOT_REAL"]) == ["analyze", "buy"]
    assert "consult_advisor" in A.CANONICAL_ACTIONS


def test_engine_signal_shape_and_explainability():
    from services.engines.signal.engine import analyze
    prof = None
    for mid in _master_ids():
        prof = _run(analyze(mid))
        if prof and prof["signals"]:
            break
    assert prof and prof["signals"]
    for s in prof["signals"]:
        assert {"signal_id", "master_id", "signal_type", "category", "severity",
                "dimensions", "confidence", "detected_at", "source", "evidence",
                "rule", "recommended_actions", "explanation"} <= set(s.keys())
        # D2: four independent dimensions always present
        assert set(s["dimensions"].keys()) == {"impact", "confidence", "urgency", "persistence"}
        # D1: threshold + origin recorded
        assert "threshold" in s["rule"] and "threshold_source" in s["rule"]
        assert s["rule"]["thresholds_version"] == "thr-v1"
        # D4: only canonical actions
        from services.engines.signal.actions import CANONICAL_ACTIONS
        assert all(a in CANONICAL_ACTIONS for a in s["recommended_actions"])
    assert prof["engine_version"] == "signal-intelligence-v1"
    assert prof["score"]["method"] == "derived_from_dimensions"


def test_signal_id_deterministic():
    from services.engines.signal.engine import analyze
    mid = _master_ids(1)[0]
    a = _run(analyze(mid, persist=False))
    b = _run(analyze(mid, persist=False))
    ta = {s["signal_type"]: s["signal_id"] for s in a["signals"]}
    tb = {s["signal_type"]: s["signal_id"] for s in b["signals"]}
    assert ta == tb   # reproducible


def test_composites_reuse_base_signals():
    from services.engines.signal.engine import analyze
    found = None
    for mid in _master_ids(40):
        prof = _run(analyze(mid))
        comp = [s for s in prof["signals"] if s.get("is_composite")]
        if comp:
            found = comp[0]
            break
    if found is None:
        pytest.skip("no composite triggered in sample")
    assert found["category"] == "opportunity"
    assert "components" in found["evidence"] and len(found["evidence"]["components"]) >= 2
    assert "requires" in found["rule"]


def test_persistence_history():
    from services.engines.signal.engine import analyze
    from services.engines.signal.persistence import get_history
    mid = _master_ids(1)[0]
    _run(analyze(mid))
    hist = _run(get_history(mid))
    assert isinstance(hist, list) and hist
    h = hist[0]
    assert {"first_detected_at", "last_seen_at", "occurrences", "trend", "status"} <= set(h.keys())


# ── API contract (own engine API, service-key auth, UI-agnostic) ──
def test_api_requires_service_key(base_url):
    r = requests.post(f"{base_url}{SI}/analyze", json={"identifier": "x"}, timeout=20)
    assert r.status_code == 401


def test_api_endpoints(base_url):
    mid = _master_ids(1)[0]
    a = requests.post(f"{base_url}{SI}/analyze", headers=SVC, json={"identifier": mid}, timeout=60)
    assert a.status_code == 200
    d = a.json()
    assert d["master_id"] == mid and "signals" in d and "score" in d

    c = requests.get(f"{base_url}{SI}/catalog", headers=SVC, timeout=20)
    assert c.status_code == 200
    cj = c.json()
    assert len(cj["categories"]) == 9 and cj["taxonomy_version"] == "tax-v1"
    assert cj["composites_version"] == "comp-v1"

    h = requests.post(f"{base_url}{SI}/history", headers=SVC, json={"identifier": mid}, timeout=30)
    assert h.status_code == 200 and "signals" in h.json()

    o = requests.post(f"{base_url}{SI}/opportunities", headers=SVC,
                      json={"sort_by_dimension": "impact", "limit": 5}, timeout=30)
    assert o.status_code == 200 and "opportunities" in o.json()

    nf = requests.post(f"{base_url}{SI}/analyze", headers=SVC, json={"identifier": "nope"}, timeout=20)
    assert nf.status_code == 404
