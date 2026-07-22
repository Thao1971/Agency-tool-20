"""Golden Contract Tests — Canonical Enriched Company (/api/v1/company/*/enriched).

Consumers: Valuo.pro (UI binding) + arroba.com. 🔴 Legacy critical.
Freezes the denormalized flat + nested-sources contract.
"""
import requests
from conftest import (base, assert_json_200, assert_status, require_keys)

C = "/api/v1/company"

# Flat top-level fields Valuo's UI binds to — must never disappear/rename.
FLAT_KEYS = [
    "master_company_id", "legal_name", "cif", "domain", "website", "commercial_names",
    "category_name", "description", "category", "subcategory", "tags", "main_clients",
    "has_awards", "awards", "email", "phone", "address", "logo_url", "logo_storage_path",
    "is_public_company", "isin", "market_cap", "market_segment", "ticker",
    "revenue_latest", "employees_latest", "ebitda_latest", "year_latest", "cnae_code",
    "borme_events_count", "cnmv_entity_type", "potential_buyers_count",
    "sector_trend", "sector_revenue",
]
ENVELOPE_KEYS = ["sources", "sources_present", "sources_count", "updated_fields",
                 "linked_valuo_ids", "last_enriched_at", "enrichment_source", "updated_at"]
CANONICAL_SOURCES = ["web", "bme", "borme", "cnmv", "iberinform",
                     "procurement", "datacomex", "economic_intel", "oepm"]


def _assert_enriched_contract(body):
    require_keys(body, FLAT_KEYS)
    require_keys(body, ENVELOPE_KEYS)
    assert isinstance(body["commercial_names"], list)
    assert isinstance(body["tags"], list)
    assert isinstance(body["address"], dict)
    assert isinstance(body["sources"], dict)
    assert isinstance(body["sources_present"], dict)
    assert isinstance(body["updated_fields"], list)
    assert isinstance(body["linked_valuo_ids"], list)
    assert isinstance(body["is_public_company"], bool)
    # presence map covers exactly the canonical sources
    assert set(body["sources_present"].keys()) == set(CANONICAL_SOURCES)
    # invariant: sources_count == number of present sources
    assert body["sources_count"] == sum(1 for v in body["sources_present"].values() if v)


# ── GET /{master_company_id}/enriched ──
def test_enriched_by_master_id_contract(any_master_id):
    r = requests.get(f"{base()}{C}/{any_master_id}/enriched", timeout=30)
    _assert_enriched_contract(assert_json_200(r))


def test_enriched_by_master_id_404():
    r = requests.get(f"{base()}{C}/mc_doesnotexist/enriched", timeout=30)
    assert_status(r, 404)


# ── GET /by-valuo-id/{valuo_company_id}/enriched ──
def test_enriched_by_valuo_id_contract(valuo_request):
    """After a Valuo request links the valuo_company_id, this lookup returns the same contract."""
    vid = valuo_request["payload"]["valuo_company_id"]
    r = requests.get(f"{base()}{C}/by-valuo-id/{vid}/enriched", timeout=30)
    # the master is created+linked synchronously in request-update-from-valuo
    body = assert_json_200(r)
    _assert_enriched_contract(body)
    assert vid in body["linked_valuo_ids"]


def test_enriched_by_valuo_id_404():
    r = requests.get(f"{base()}{C}/by-valuo-id/valuo_does_not_exist_xyz/enriched", timeout=30)
    assert_status(r, 404)


# ── Empty / partial data: a freshly discovered company has mostly-empty fields but full shape ──
def test_enriched_shape_stable_on_sparse_company(valuo_request):
    """Empty/partial response: a brand-new master still returns the full contract with
    empty (not missing) fields — backward compatibility for sparse data."""
    mc_id = valuo_request["response"].json()["master_company_id"]
    if not mc_id:
        return
    r = requests.get(f"{base()}{C}/{mc_id}/enriched", timeout=30)
    body = assert_json_200(r)
    _assert_enriched_contract(body)
    # sparse company: sources_count is an int >= 0, tags is a list (possibly empty)
    assert body["sources_count"] >= 0
    assert isinstance(body["tags"], list)
