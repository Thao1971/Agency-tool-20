"""Smoke tests — REQ-001 Analyze Skill (POST /api/v1/enrich_company)."""
import os
import requests

ENRICH = "/api/v1/enrich_company"
SEARCH = "/api/v1/skills/search"
SVC = {"X-API-Key": os.environ.get("ARROBA_SERVICE_API_KEY",
                                   "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk")}

TOP_KEYS = {"master_company_id", "legal_name", "sector", "category", "cnae_code", "cnae_section",
            "financial_summary", "growth", "ratios", "peers", "ownership", "relationships",
            "signals", "narrative", "confidence", "lineage"}


def _enrich(base_url, mc_id, narrative=False):
    return requests.post(f"{base_url}{ENRICH}",
                         json={"master_company_id": mc_id, "context": {"include_narrative": narrative}},
                         headers=SVC, timeout=90)


def _iberinform_ids(base_url):
    ids = []
    for q in ("sa", "sl", "tecnolog"):
        r = requests.post(f"{base_url}{SEARCH}", json={
            "query": q, "filters": {"has_domain": False}, "pagination": {"page_size": 20}
        }, timeout=20)
        ids += [x["master_company_id"] for x in r.json()["workspace"]["blocks"][0]["props"]["results"]]
    return ids


def test_404_unknown(base_url):
    assert _enrich(base_url, "not-a-real-id").status_code == 404


def test_contract_shape(base_url):
    ids = _iberinform_ids(base_url) or ["x"]
    r = _enrich(base_url, ids[0])
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d.keys()) == TOP_KEYS
    assert set(d["narrative"].keys()) == {"summary", "key_points", "risks", "opportunities"}
    assert set(d["confidence"].keys()) == {"identity", "classification", "financials", "overall"}
    assert set(d["lineage"].keys()) == {"identity", "classification", "financials", "narrative"}
    assert set(d["ownership"].keys()) == {"shareholders", "ultimate_parent", "group_name"}
    assert isinstance(d["signals"], list)


def test_financials_growth_ratios_peers(base_url):
    """An Iberinform company must expose computed financial_summary + growth + ratios + peers."""
    enriched = None
    for mc_id in _iberinform_ids(base_url)[:25]:
        d = _enrich(base_url, mc_id).json()
        if d.get("financial_summary"):
            enriched = d
            break
    assert enriched, "no company with financials reachable"
    assert "revenue" in enriched["financial_summary"]
    assert set(enriched["growth"].keys()) == {"revenue_growth", "ebitda_growth"}
    assert set(enriched["ratios"].keys()) == {"ebitda_margin", "revenue_per_employee",
                                              "ebitda_per_employee", "debt_ratio"}
    for p in enriched["peers"]:
        assert set(p.keys()) == {"master_company_id", "legal_name", "sector", "score"}
        assert 0.0 <= p["score"] <= 1.0


def test_narrative_optional(base_url):
    ids = _iberinform_ids(base_url) or ["x"]
    d = _enrich(base_url, ids[0], narrative=False).json()
    assert d["narrative"]["summary"] == ""
    assert d["lineage"]["narrative"] == "none"


def test_narrative_via_claude(base_url):
    """Live Claude narrative generation (one call)."""
    ids = _iberinform_ids(base_url)
    assert ids
    d = _enrich(base_url, ids[0], narrative=True).json()
    n = d["narrative"]
    if n["summary"]:
        assert isinstance(n["key_points"], list)
        assert d["lineage"]["narrative"] == "ai_generated"
