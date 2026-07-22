"""Golden Contract Tests — Skills (/api/v1/skills/*).

Consumer: arroba.com (PUBLIC, no auth) — stable workspace.blocks / valuation / recommend
contracts. Frozen behavioral reference.
"""
import requests
from conftest import (base, assert_json_200, assert_status, require_keys)

S = "/api/v1/skills"


# ── POST /search ──
def test_search_workspace_blocks_contract():
    r = requests.post(f"{base()}{S}/search",
                      json={"query": "", "pagination": {"page": 1, "page_size": 5}}, timeout=60)
    body = assert_json_200(r)
    require_keys(body, ["workspace"])
    require_keys(body["workspace"], ["blocks"])
    blocks = body["workspace"]["blocks"]
    assert isinstance(blocks, list) and blocks
    sr = blocks[0]
    require_keys(sr, ["type", "props"])
    assert sr["type"] == "search_results"
    require_keys(sr["props"], ["query", "results"])
    assert isinstance(sr["props"]["results"], list)
    for item in sr["props"]["results"]:
        require_keys(item, ["master_company_id", "name", "sector", "cif", "score"])


def test_search_with_filters_contract():
    r = requests.post(f"{base()}{S}/search",
                      json={"query": "consulting", "filters": {"has_domain": True},
                            "pagination": {"page": 1, "page_size": 3}}, timeout=60)
    body = assert_json_200(r)
    assert body["workspace"]["blocks"][0]["type"] == "search_results"


def test_search_empty_defaults_contract():
    """Empty body: defaults apply (query='', page 1) and still returns the envelope."""
    r = requests.post(f"{base()}{S}/search", json={}, timeout=60)
    body = assert_json_200(r)
    require_keys(body["workspace"], ["blocks"])


# ── POST /value ──
def test_value_contract(any_master_id):
    r = requests.post(f"{base()}{S}/value", json={"master_company_id": any_master_id}, timeout=60)
    body = assert_json_200(r)
    require_keys(body, ["master_company_id", "company_name", "valuation_range",
                        "comparables", "explanation", "confidence", "lineage"])
    assert isinstance(body["comparables"], list)


def test_value_unknown_master_404():
    r = requests.post(f"{base()}{S}/value", json={"master_company_id": "mc_doesnotexist"}, timeout=60)
    assert_status(r, 404)


def test_value_missing_field_422():
    r = requests.post(f"{base()}{S}/value", json={}, timeout=30)
    assert_status(r, 422)


# ── POST /recommend ──
def test_recommend_similar_mode_contract(any_master_id):
    r = requests.post(f"{base()}{S}/recommend",
                      json={"master_company_id": any_master_id,
                            "pagination": {"page": 1, "page_size": 5}}, timeout=60)
    body = assert_json_200(r)
    require_keys(body, ["recommendations", "confidence", "lineage"])
    assert isinstance(body["recommendations"], list)
    for rec in body["recommendations"]:
        require_keys(rec, ["master_company_id", "name", "sector", "score", "reason", "type"])


def test_recommend_thesis_mode_by_query():
    """No master_company_id → 'thesis' mode by query; still returns the recommend contract."""
    r = requests.post(f"{base()}{S}/recommend",
                      json={"query": "software", "pagination": {"page": 1, "page_size": 5}}, timeout=60)
    body = assert_json_200(r)
    require_keys(body, ["recommendations", "confidence", "lineage"])


def test_recommend_unknown_master_404():
    r = requests.post(f"{base()}{S}/recommend",
                      json={"master_company_id": "mc_doesnotexist"}, timeout=60)
    assert_status(r, 404)
