"""Smoke tests — P2.1 Data Layer + Entity Resolution (rebuild-master + unified schema)."""
import requests

REBUILD = "/api/v1/data-layer/rebuild-master"
SEARCH = "/api/v1/skills/search"
VALUE = "/api/v1/skills/value"


def _rebuild(base_url, token):
    return requests.post(f"{base_url}{REBUILD}", headers={"Authorization": f"Bearer {token}"}, timeout=180)


def test_rebuild_requires_auth(base_url):
    r = requests.post(f"{base_url}{REBUILD}", timeout=30)
    assert r.status_code in (401, 403)


def test_rebuild_idempotent_and_enriches(base_url, auth_token):
    r1 = _rebuild(base_url, auth_token)
    assert r1.status_code == 200, r1.text
    s1 = r1.json()
    for k in ("total", "enriched", "with_classification", "with_financials", "dedupe"):
        assert k in s1
    assert s1["with_classification"] > 0 and s1["with_financials"] > 0
    assert s1["enriched"] == s1["total"]

    r2 = _rebuild(base_url, auth_token)
    s2 = r2.json()
    # idempotent: stable counts on re-run
    assert s2["total"] == s1["total"]
    assert s2["with_classification"] == s1["with_classification"]
    assert s2["with_financials"] == s1["with_financials"]


def test_classification_unlocks_value_comparables(base_url):
    """After unification, an Iberinform company resolves sector + real comparables."""
    ids = []
    for q in ("sa", "sl", "tecnolog"):
        r = requests.post(f"{base_url}{SEARCH}", json={
            "query": q, "filters": {"has_domain": False}, "pagination": {"page_size": 20}
        }, timeout=20)
        ids += [x["master_company_id"] for x in r.json()["workspace"]["blocks"][0]["props"]["results"]]

    unlocked = False
    for mc_id in ids[:30]:
        d = requests.post(f"{base_url}{VALUE}", json={"master_company_id": mc_id}, timeout=20).json()
        if d["lineage"].get("section") and d["comparables"]:
            for c in d["comparables"]:
                assert c["ebitda"] is not None or c["revenue"] is not None
            unlocked = True
            break
    assert unlocked, "expected at least one company with resolved section AND real comparables"
