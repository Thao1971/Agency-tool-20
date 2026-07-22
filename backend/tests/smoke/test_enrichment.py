"""enrich_company() must complete with sources_consulted populated for the basic profile."""
import requests


def test_enrich_basic_returns_engine_block(base_url, known_master_with_scrape):
    mc_id = known_master_with_scrape["master_company_id"]
    r = requests.post(
        f"{base_url}/api/v1/intelligence/enrich",
        json={"master_company_id": mc_id, "profile": "basic"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d["master_company_id"] == mc_id
    assert d["profile"] == "basic"
    assert "fields" in d and isinstance(d["fields"], dict)
    assert isinstance(d["duration_ms"], int) and d["duration_ms"] >= 0

    # sources_consulted must list every source in the profile and report found bool
    assert isinstance(d["sources_consulted"], list) and len(d["sources_consulted"]) >= 1
    for s in d["sources_consulted"]:
        assert "source" in s and "found" in s


def test_enrich_unknown_master_returns_404(base_url):
    r = requests.post(
        f"{base_url}/api/v1/intelligence/enrich",
        json={"master_company_id": "mc_does_not_exist_xxxxx", "profile": "basic"},
        timeout=15,
    )
    assert r.status_code == 404


def test_enrich_invalid_profile_returns_400(base_url, known_master_with_scrape):
    mc_id = known_master_with_scrape["master_company_id"]
    r = requests.post(
        f"{base_url}/api/v1/intelligence/enrich",
        json={"master_company_id": mc_id, "profile": "nonexistent"},
        timeout=15,
    )
    assert r.status_code == 400
