"""Canonical enriched-company contract — what Valuo and arroba consume after
an enrichment completes. Public, no JWT required.

Endpoint: GET /api/v1/company/{master_company_id}/enriched
"""
import requests


REQUIRED_TOP_KEYS = {
    "master_company_id", "legal_name", "cif", "domain",
    "description", "category", "subcategory", "tags",
    "logo_url", "logo_storage_path",
    "email", "phone", "address", "main_clients", "awards", "has_awards",
    "is_public_company", "isin", "market_cap",
    "revenue_latest", "employees_latest",
    "sources", "sources_present", "sources_count",
    "updated_fields", "linked_valuo_ids",
    "last_enriched_at", "enrichment_source",
}

CANONICAL_SOURCES = {"web", "bme", "borme", "cnmv", "iberinform",
                     "procurement", "datacomex", "economic_intel", "oepm"}


def test_enriched_company_returns_flat_and_nested(base_url, known_master_with_scrape):
    mc_id = known_master_with_scrape["master_company_id"]
    r = requests.get(f"{base_url}/api/v1/company/{mc_id}/enriched", timeout=10)
    assert r.status_code == 200, r.text[:200]
    d = r.json()

    missing = REQUIRED_TOP_KEYS - set(d.keys())
    assert not missing, f"Missing top-level keys: {missing}"

    assert d["master_company_id"] == mc_id

    # sources_present must include every canonical source as a boolean
    assert set(d["sources_present"].keys()) == CANONICAL_SOURCES

    # A master picked because it has web with description/tags MUST report web True
    assert d["sources_present"]["web"] is True
    assert d["description"], "Top-level description must be present from web source"
    assert isinstance(d["tags"], list) and len(d["tags"]) > 0

    # updated_fields lists ONLY top-level keys that have data
    assert isinstance(d["updated_fields"], list)
    assert "description" in d["updated_fields"]
    assert "tags" in d["updated_fields"]


def test_enriched_company_unknown_returns_404(base_url):
    r = requests.get(
        f"{base_url}/api/v1/company/mc_does_not_exist_xxxxx/enriched", timeout=10,
    )
    assert r.status_code == 404


def test_enriched_company_by_valuo_id(base_url, known_master_with_scrape):
    mc_id = known_master_with_scrape["master_company_id"]
    full = requests.get(f"{base_url}/api/v1/company/{mc_id}/enriched", timeout=10).json()
    valuo_ids = full.get("linked_valuo_ids") or []
    if not valuo_ids:
        return
    r = requests.get(
        f"{base_url}/api/v1/company/by-valuo-id/{valuo_ids[0]}/enriched", timeout=10,
    )
    assert r.status_code == 200, r.text[:200]
    assert r.json()["master_company_id"] == mc_id


def test_request_status_exposes_enriched_company_url(base_url):
    """request-status → status==completed → enriched_company_url is dereferenceable."""
    import time
    payload = {
        "valuo_company_id": f"smoke_contract_{int(time.time()*1000)}",
        "legal_name": "TELEFONICA SA",
        "cif": "A28015865",
        "domain": "telefonica.com",
        "requested_by": "smoke_contract",
    }
    r = requests.post(
        f"{base_url}/api/v1/valuo/request-update-from-valuo",
        json=payload, timeout=15,
    )
    assert r.status_code == 200
    req_id = r.json()["agency_request_id"]

    time.sleep(1)
    status = requests.get(
        f"{base_url}/api/v1/valuo/request-status/{req_id}", timeout=10,
    ).json()
    assert status["enrichment_status"] == "completed"

    url = status.get("enriched_company_url")
    assert url and "/api/v1/company/" in url and "/enriched" in url, status

    dereferenced = requests.get(url, timeout=10)
    assert dereferenced.status_code == 200
    d = dereferenced.json()
    assert d["master_company_id"] == status["master_company_id"]
    # Top-level flat fields are present and the consumer can render the card
    for k in ("description", "tags", "logo_url", "sources", "updated_fields"):
        assert k in d, f"Missing flat field {k}"


def test_logo_url_resolves_to_binary(base_url, known_master_with_scrape):
    """logo_url, when present, must be a fetchable image."""
    mc_id = known_master_with_scrape["master_company_id"]
    d = requests.get(f"{base_url}/api/v1/company/{mc_id}/enriched", timeout=10).json()
    logo = d.get("logo_url")
    if not logo:
        return  # Skip if the picked master has no logo
    r = requests.get(logo, timeout=15, allow_redirects=True)
    assert r.status_code == 200, f"Logo URL {logo} returned {r.status_code}"
    ctype = r.headers.get("content-type", "")
    assert ctype.startswith("image/"), f"Expected image content-type, got {ctype!r}"
