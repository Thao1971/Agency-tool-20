"""Golden Contract Tests — Master Layer admin + Valuo publication (/api/v1/master/*).

Consumers: Platform Console (JWT) + Valuo.pro (publish-to-valuo is the outbound contract).
🔴/🟡 Legacy critical. Freezes list/stats/detail + publish/unpublish behavior.
"""
import requests
from conftest import (base, assert_json_200, assert_status, require_keys)

M = "/api/v1/master"


# ── Auth gate ──
def test_master_list_requires_auth():
    r = requests.get(f"{base()}{M}", timeout=30)
    assert r.status_code in (401, 403)


def test_master_stats_requires_auth():
    r = requests.get(f"{base()}{M}/stats", timeout=30)
    assert r.status_code in (401, 403)


# ── GET /master (list) ──
def test_master_list_contract(auth_headers):
    r = requests.get(f"{base()}{M}?limit=5", headers=auth_headers, timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["companies", "total"])
    assert isinstance(body["companies"], list)
    assert isinstance(body["total"], int)


# ── GET /master/stats ──
def test_master_stats_contract(auth_headers):
    r = requests.get(f"{base()}{M}/stats", headers=auth_headers, timeout=30)
    body = assert_json_200(r)
    stat_keys = ["total", "discovered", "auto_merged", "verified", "conflict", "with_cif",
                 "with_domain", "published_to_valuo", "pending_publication", "valuo_requests",
                 "valuo_requests_pending", "audit_entries"]
    require_keys(body, stat_keys)
    for k in stat_keys:
        assert isinstance(body[k], int), f"stat '{k}' must be int"


# ── GET /master/{id} (detail) ──
def test_master_detail_contract(auth_headers, any_master_id):
    r = requests.get(f"{base()}{M}/{any_master_id}", headers=auth_headers, timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["master_company_id", "linked_agency_results", "audit_history"])
    assert body["master_company_id"] == any_master_id
    assert isinstance(body["linked_agency_results"], list)
    assert isinstance(body["audit_history"], list)


def test_master_detail_404(auth_headers):
    r = requests.get(f"{base()}{M}/mc_doesnotexist", headers=auth_headers, timeout=30)
    assert_status(r, 404)


# ── POST /master/{id}/publish-to-valuo ──
def test_publish_requires_auth(any_master_id):
    r = requests.post(f"{base()}{M}/{any_master_id}/publish-to-valuo", timeout=30)
    assert r.status_code in (401, 403)


def test_publish_unknown_404(auth_headers):
    r = requests.post(f"{base()}{M}/mc_doesnotexist/publish-to-valuo", headers=auth_headers, timeout=30)
    assert_status(r, 404)


def test_publish_non_publishable_400(auth_headers, discovered_master_id):
    """Guard: a 'discovered' company cannot be published (must be verified/auto_merged)."""
    if not discovered_master_id:
        import pytest
        pytest.skip("no 'discovered' master available")
    r = requests.post(f"{base()}{M}/{discovered_master_id}/publish-to-valuo",
                      headers=auth_headers, timeout=30)
    assert_status(r, 400)


def test_publish_then_unpublish_contract(auth_headers, publishable_master_id):
    """Happy path: publishable company → 200 {status: published_to_valuo}; then unpublish → 200."""
    if not publishable_master_id:
        import pytest
        pytest.skip("no verified/auto_merged master available")
    pub = requests.post(f"{base()}{M}/{publishable_master_id}/publish-to-valuo",
                        headers=auth_headers, timeout=30)
    body = assert_json_200(pub)
    require_keys(body, ["status"])
    assert body["status"] == "published_to_valuo"
    # unpublish (restores test state, also part of the contract)
    unp = requests.post(f"{base()}{M}/{publishable_master_id}/unpublish-from-valuo",
                        headers=auth_headers, timeout=30)
    ubody = assert_json_200(unp)
    assert ubody["status"] == "unpublished"


def test_unpublish_requires_auth(any_master_id):
    r = requests.post(f"{base()}{M}/{any_master_id}/unpublish-from-valuo", timeout=30)
    assert r.status_code in (401, 403)
