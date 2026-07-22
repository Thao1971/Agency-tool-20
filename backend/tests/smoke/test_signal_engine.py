"""Smoke tests — P3 Signal Engine (signals[] + signal_score; transparent to contracts)."""
import os
import requests

REBUILD_SIG = "/api/v1/data-layer/rebuild-signals"
ENRICH = "/api/v1/enrich_company"
SEARCH = "/api/v1/skills/search"
RECOMMEND = "/api/v1/skills/recommend"
SVC = {"X-API-Key": os.environ.get("ARROBA_SERVICE_API_KEY",
                                   "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk")}

SIGNAL_KEYS = {"signal_id", "signal_type", "title", "description", "severity",
               "score", "confidence", "created_at", "lineage"}


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def _iberinform_ids(base_url):
    ids = []
    for q in ("sa", "sl", "tecnolog"):
        r = requests.post(f"{base_url}{SEARCH}", json={
            "query": q, "filters": {"has_domain": False}, "pagination": {"page_size": 20}}, timeout=20)
        ids += [x["master_company_id"] for x in r.json()["workspace"]["blocks"][0]["props"]["results"]]
    return ids


def test_rebuild_signals_requires_auth(base_url):
    assert requests.post(f"{base_url}{REBUILD_SIG}", timeout=30).status_code in (401, 403)


def test_rebuild_signals(base_url, auth_token):
    r = requests.post(f"{base_url}{REBUILD_SIG}", headers=_hdr(auth_token), timeout=180)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "ok" and s["total"] > 100 and s["with_signals"] > 0


def test_analyze_signals_populated(base_url, auth_token):
    requests.post(f"{base_url}{REBUILD_SIG}", headers=_hdr(auth_token), timeout=180)
    enriched = None
    for mc_id in _iberinform_ids(base_url)[:25]:
        d = requests.post(f"{base_url}{ENRICH}", json={
            "master_company_id": mc_id, "context": {"include_narrative": False}}, headers=SVC, timeout=30).json()
        if d.get("signals"):
            enriched = d
            break
    assert enriched, "expected a company with computed signals"
    for sig in enriched["signals"]:
        assert set(sig.keys()) == SIGNAL_KEYS
        assert 0.0 <= sig["score"] <= 1.0 and 0.0 <= sig["confidence"] <= 1.0
        assert "." in sig["signal_type"]  # category.metric


def test_search_use_signals_transparent(base_url):
    r = requests.post(f"{base_url}{SEARCH}", json={
        "query": "consult", "context": {"use_signals": True}, "pagination": {"page_size": 5}}, timeout=20)
    assert r.status_code == 200
    b = r.json()["workspace"]["blocks"][0]
    assert b["type"] == "search_results"
    for x in b["props"]["results"]:
        assert set(x.keys()) == {"master_company_id", "name", "sector", "cif", "score"}


def test_recommend_contract_unchanged(base_url):
    d = requests.post(f"{base_url}{RECOMMEND}", json={"query": "software"}, timeout=20).json()
    assert set(d.keys()) == {"recommendations", "confidence", "lineage"}
