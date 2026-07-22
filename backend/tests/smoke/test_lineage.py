"""Lineage invariant: enriched masters carry master.sources.<origin> namespaces."""
import requests


REQUIRED_LINEAGE_KEYS = {"web", "bme", "borme", "cnmv", "iberinform"}


def test_lineage_namespaces_present_in_engine_output(base_url, known_master_with_scrape):
    """At least one of the canonical lineage namespaces must appear in fields."""
    mc_id = known_master_with_scrape["master_company_id"]
    r = requests.post(
        f"{base_url}/api/v1/intelligence/enrich",
        json={"master_company_id": mc_id, "profile": "arroba"},
        timeout=30,
    )
    assert r.status_code == 200
    d = r.json()

    namespaces = {k.split(".", 1)[0] for k in d["fields"].keys() if "." in k}
    # At least one canonical source must have contributed data on a real master
    intersection = namespaces & REQUIRED_LINEAGE_KEYS
    assert len(intersection) > 0, (
        f"No canonical source contributed lineage. Namespaces seen: {namespaces}"
    )


def test_lineage_block_present_in_master(base_url, auth_token, known_master_with_scrape):
    """Master record must expose sources.* nested namespaces post-Phase-2 migration."""
    mc_id = known_master_with_scrape["master_company_id"]
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = requests.get(f"{base_url}/api/v1/master/{mc_id}", headers=headers, timeout=15)
    assert r.status_code == 200, r.text[:200]
    company = r.json()
    if "company" in company and isinstance(company["company"], dict):
        company = company["company"]

    sources_block = company.get("sources") or {}
    assert "web" in sources_block, (
        f"Expected master.sources.web on a migrated master, got keys: {list(sources_block.keys())}"
    )
    # Web block must carry at least one of the canonical fields
    web = sources_block["web"]
    assert any(k in web for k in ("description", "tags", "category", "company_name")), web
