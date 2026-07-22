"""Smoke tests — REQ-004 Valuation Engine skill (POST /api/v1/skills/value)."""
import requests

SEARCH = "/api/v1/skills/search"
VALUE = "/api/v1/skills/value"
ALLOWED_LINEAGE = {"raw", "normalized", "inferred", "ai_generated"}
CONTRACT_KEYS = {"master_company_id", "company_name", "valuation_range", "comparables",
                 "explanation", "confidence", "lineage"}


def _search_ids(base_url, query, has_domain):
    r = requests.post(f"{base_url}{SEARCH}", json={
        "query": query, "filters": {"has_domain": has_domain}, "pagination": {"page": 1, "page_size": 20}
    }, timeout=20)
    return [x["master_company_id"] for x in r.json()["workspace"]["blocks"][0]["props"]["results"]]


def _value(base_url, mc_id):
    return requests.post(f"{base_url}{VALUE}", json={"master_company_id": mc_id, "context": {}}, timeout=20)


def test_public_404_on_unknown(base_url):
    r = _value(base_url, "definitely-not-a-real-id")
    assert r.status_code == 404


def test_value_contract_shape(base_url):
    ids = _search_ids(base_url, "", True) or _search_ids(base_url, "sa", False)
    assert ids, "no companies to value"
    r = _value(base_url, ids[0])
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d.keys()) == CONTRACT_KEYS
    assert isinstance(d["valuation_range"], dict)
    assert isinstance(d["comparables"], list)
    assert isinstance(d["explanation"], str) and d["explanation"]
    assert 0.0 <= d["confidence"] <= 1.0
    assert d["lineage"]["source"] in ALLOWED_LINEAGE


def test_valuation_range_is_ordered_when_computable(base_url):
    """Find a company with financials and assert low <= base <= high + method present."""
    ids = _search_ids(base_url, "sa", False) + _search_ids(base_url, "tecnolog", False)
    computed = None
    for mc_id in ids[:25]:
        d = _value(base_url, mc_id).json()
        vr = d["valuation_range"]
        if vr:
            computed = vr
            break
    if not computed:
        import pytest
        pytest.skip("no company with financials reachable via public search in this env")
    assert computed["method"] in ("ev_ebitda", "ev_revenue", "book_value")
    assert computed["low"] <= computed["base"] <= computed["high"]
    assert computed["currency"] == "EUR"


def test_lineage_is_inferred_for_valuation(base_url):
    ids = _search_ids(base_url, "sa", False) or _search_ids(base_url, "", True)
    assert ids
    d = _value(base_url, ids[0]).json()
    # valuation is always a calculation → inferred lineage
    assert d["lineage"]["source"] == "inferred"
    assert "method" in d["lineage"]
