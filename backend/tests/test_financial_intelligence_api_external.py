"""
End-to-end API contract verification for Sprint 2 — Financial Intelligence Engine.

Validates the two user-defined acceptance criteria against the EXTERNAL URL
(REACT_APP_BACKEND_URL): (1) engine is decoupled — auth via service key only,
(2) full explainability — every KPI/ratio/valuation exposes data, source, basis,
rules and confidence.
"""
import os
import pytest
import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "https://data-factory-hub.preview.emergentagent.com"
FI = "/api/v1/financial-intelligence"
API_KEY = "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk"
SVC = {"X-API-Key": API_KEY}
TIMEOUT = 45


# ── Helpers ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def master_id():
    """Fetch a real master_id with revenue from MongoDB."""
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from database import db

    async def go():
        d = await db.master_companies.find_one(
            {"financials.latest.revenue": {"$ne": None}},
            {"_id": 0, "master_id": 1},
        )
        return d["master_id"]

    return asyncio.get_event_loop().run_until_complete(go()) if False else asyncio.run(go())


# ── 1. Decoupling — service key required ──────────────────────────────────────
def test_analyze_without_key_returns_401():
    r = requests.post(f"{BASE_URL}{FI}/analyze", json={"identifier": "x"}, timeout=TIMEOUT)
    assert r.status_code == 401, f"expected 401 without key, got {r.status_code}: {r.text[:200]}"


def test_analyze_invalid_key_returns_401():
    r = requests.post(
        f"{BASE_URL}{FI}/analyze",
        headers={"X-API-Key": "as_invalid_key_xxx"},
        json={"identifier": "x"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 401, f"expected 401 with invalid key, got {r.status_code}: {r.text[:200]}"


# ── 2. Analyze contract ───────────────────────────────────────────────────────
def test_analyze_returns_complete_profile(master_id):
    r = requests.post(
        f"{BASE_URL}{FI}/analyze",
        headers=SVC,
        json={"identifier": master_id},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:400]}"
    d = r.json()
    required = {"statements", "kpis", "ratios", "evolution", "financial_quality",
                "comparables", "valuation", "assessment", "explainability"}
    missing = required - set(d.keys())
    assert not missing, f"missing keys in profile: {missing}"
    assert d.get("engine_version") == "financial-intelligence-v1", \
        f"engine_version={d.get('engine_version')}"


# ── 3. Explainability ─────────────────────────────────────────────────────────
def test_ratios_have_full_explainability(master_id):
    r = requests.post(f"{BASE_URL}{FI}/analyze", headers=SVC,
                      json={"identifier": master_id}, timeout=TIMEOUT)
    assert r.status_code == 200
    ratios = r.json()["ratios"]
    assert isinstance(ratios, dict) and len(ratios) > 0
    required_fields = {"value", "name", "formula", "explanation", "source", "available"}
    for key, ratio in ratios.items():
        missing = required_fields - set(ratio.keys())
        assert not missing, f"ratio '{key}' missing fields: {missing}"


def test_explainability_block(master_id):
    r = requests.post(f"{BASE_URL}{FI}/analyze", headers=SVC,
                      json={"identifier": master_id}, timeout=TIMEOUT)
    e = r.json()["explainability"]
    for k in ("data_source", "source_version", "basis", "year", "rules_applied"):
        assert k in e, f"explainability missing '{k}': {list(e.keys())}"
    assert e["ai_used"] is False


def test_financial_quality_rules_based(master_id):
    r = requests.post(f"{BASE_URL}{FI}/analyze", headers=SVC,
                      json={"identifier": master_id}, timeout=TIMEOUT)
    q = r.json()["financial_quality"]
    assert q["method"] == "rules_based"
    assert q["ai_used"] is False
    assert 0 <= q["score"] <= 100
    # score must equal sum of passed rules' points
    assert sum(rule["points"] for rule in q["rules"]) == q["score"], \
        f"score {q['score']} != sum(rules points)"


# ── 4. Valuation traceability ─────────────────────────────────────────────────
def test_valuation_traceable(master_id):
    r = requests.post(f"{BASE_URL}{FI}/analyze", headers=SVC,
                      json={"identifier": master_id}, timeout=TIMEOUT)
    v = r.json()["valuation"]
    for k in ("method", "hypotheses", "confidence", "lineage"):
        assert k in v, f"valuation missing '{k}': {list(v.keys())}"
    if v["method"] == "ev_ebitda":
        assert v.get("multiple_basis") == "inferred_reference", \
            f"multiple_basis={v.get('multiple_basis')}"


# ── 5. Comparables structural ─────────────────────────────────────────────────
def test_comparables_structural_no_embeddings(master_id):
    r = requests.post(f"{BASE_URL}{FI}/analyze", headers=SVC,
                      json={"identifier": master_id}, timeout=TIMEOUT)
    c = r.json()["comparables"]
    assert c["embeddings_used"] is False
    assert "cnae_section" in c["criteria"], f"criteria={c['criteria']}"


# ── 6. Valuation endpoint + ratios catalog ────────────────────────────────────
def test_valuation_endpoint(master_id):
    r = requests.post(f"{BASE_URL}{FI}/valuation", headers=SVC,
                      json={"identifier": master_id}, timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    assert "valuation" in r.json()


def test_ratios_catalog():
    r = requests.get(f"{BASE_URL}{FI}/ratios/catalog", headers=SVC, timeout=TIMEOUT)
    assert r.status_code == 200
    ratios = r.json()["ratios"]
    assert len(ratios) >= 10, f"expected >=10 ratios, got {len(ratios)}"
    # check structure of first ratio
    sample = ratios[0] if isinstance(ratios, list) else next(iter(ratios.values()))
    for k in ("formula", "explanation", "category"):
        assert k in sample, f"catalog ratio missing '{k}': {list(sample.keys())}"


# ── 7. Not found ──────────────────────────────────────────────────────────────
def test_nonexistent_identifier_returns_404():
    r = requests.post(f"{BASE_URL}{FI}/analyze", headers=SVC,
                      json={"identifier": "mc_does_not_exist_xxx"}, timeout=TIMEOUT)
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"
