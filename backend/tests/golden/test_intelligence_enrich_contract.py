"""Golden Contract Tests — Intelligence Engine enrichment (/api/v1/intelligence/*).

Consumers: Valuo.pro (profile=valuo), arroba.com (profile=arroba), Console. 🔴 Legacy critical.
Freezes the unified enrichment contract and the profile catalog.
"""
import requests
from conftest import (base, assert_json_200, assert_status, require_keys)

I = "/api/v1/intelligence"
ENRICH_KEYS = ["master_company_id", "profile", "engine_version", "fields",
               "sources_consulted", "sources_with_data", "duration_ms",
               "started_at", "completed_at"]


def _assert_enrich_contract(body, expected_profile):
    require_keys(body, ENRICH_KEYS)
    assert body["profile"] == expected_profile
    assert isinstance(body["fields"], dict)
    assert isinstance(body["sources_consulted"], list)
    assert isinstance(body["sources_with_data"], list)
    assert isinstance(body["duration_ms"], int)
    assert isinstance(body["engine_version"], str)


# ── POST /enrich ── (profiles: basic | valuo | arroba)
def test_enrich_profile_valuo_contract(any_master_id):
    r = requests.post(f"{base()}{I}/enrich",
                      json={"master_company_id": any_master_id, "profile": "valuo"}, timeout=120)
    _assert_enrich_contract(assert_json_200(r), "valuo")


def test_enrich_profile_arroba_contract(any_master_id):
    r = requests.post(f"{base()}{I}/enrich",
                      json={"master_company_id": any_master_id, "profile": "arroba"}, timeout=120)
    _assert_enrich_contract(assert_json_200(r), "arroba")


def test_enrich_profile_basic_default(any_master_id):
    r = requests.post(f"{base()}{I}/enrich",
                      json={"master_company_id": any_master_id}, timeout=120)
    body = assert_json_200(r)
    _assert_enrich_contract(body, "basic")  # default profile is 'basic'


def test_enrich_unknown_master_404():
    r = requests.post(f"{base()}{I}/enrich",
                      json={"master_company_id": "mc_doesnotexist", "profile": "valuo"}, timeout=60)
    assert_status(r, 404)


def test_enrich_invalid_profile_400(any_master_id):
    r = requests.post(f"{base()}{I}/enrich",
                      json={"master_company_id": any_master_id, "profile": "nope_invalid"}, timeout=60)
    assert_status(r, 400)


def test_enrich_missing_master_id_422():
    r = requests.post(f"{base()}{I}/enrich", json={"profile": "valuo"}, timeout=30)
    assert_status(r, 422)


# ── GET /profiles ──
def test_profiles_catalog_contract():
    r = requests.get(f"{base()}{I}/profiles", timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["profiles"])
    assert isinstance(body["profiles"], list) and body["profiles"]
    names = set()
    for p in body["profiles"]:
        require_keys(p, ["name", "description", "sources"])
        assert isinstance(p["sources"], list)
        names.add(p["name"])
    # backward-compat: the three known products must remain present
    assert {"basic", "valuo", "arroba"}.issubset(names)


# ── GET /profile/{name} ──
def test_profile_detail_valuo():
    r = requests.get(f"{base()}{I}/profile/valuo", timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["name", "description", "sources"])
    assert body["name"] == "valuo"
    # valuo profile must keep its financial/market sources (backward-compat)
    assert {"identity", "web", "iberinform"}.issubset(set(body["sources"]))


def test_profile_detail_arroba_superset():
    r = requests.get(f"{base()}{I}/profile/arroba", timeout=30)
    body = assert_json_200(r)
    assert body["name"] == "arroba"
    assert {"identity", "web", "iberinform", "borme", "procurement"}.issubset(set(body["sources"]))


def test_profile_detail_unknown_404():
    r = requests.get(f"{base()}{I}/profile/nope_invalid", timeout=30)
    assert_status(r, 404)


# ── Canonical enriched company under /intelligence (intelligence_engine.py) ──
def test_intelligence_company_view_contract(any_master_id):
    r = requests.get(f"{base()}{I}/company/{any_master_id}", timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["master_company_id", "identity", "sources", "sources_present",
                        "sources_count", "logo_url", "linked_valuo_ids",
                        "last_enriched_at", "enrichment_source", "updated_at"])
    require_keys(body["identity"], ["legal_name", "cif", "domain", "website",
                                    "commercial_names", "aliases", "category_name",
                                    "cnae_primary", "country", "confidence_score", "merge_status"])
    # invariant: sources_count == number of present sources
    assert body["sources_count"] == sum(1 for v in body["sources_present"].values() if v)


def test_intelligence_company_view_404():
    r = requests.get(f"{base()}{I}/company/mc_doesnotexist", timeout=30)
    assert_status(r, 404)
