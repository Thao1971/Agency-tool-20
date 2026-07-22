"""Golden Contract Tests — Valuo Integration (/api/v1/valuo/*).

Consumer: Valuo.pro (PRODUCTION). 🔴 Legacy critical.
Freezes the observable contract of the Valuo enrichment pipeline.
"""
import requests
from conftest import (base, assert_json_200, assert_status, require_keys, assert_type)

V = "/api/v1/valuo"


# ── POST /request-update-from-valuo ──
def test_request_update_full_payload_contract(valuo_request):
    r = valuo_request["response"]
    body = assert_json_200(r)
    require_keys(body, ["agency_request_id", "master_company_id", "resolution_status",
                        "confidence_score", "candidates", "message"])
    assert isinstance(body["agency_request_id"], str) and body["agency_request_id"].startswith("vreq_")
    assert body["resolution_status"] in ("auto_merged", "conflict", "discovered")
    assert isinstance(body["confidence_score"], (int, float))
    assert isinstance(body["candidates"], list)
    assert isinstance(body["message"], str)
    for c in body["candidates"]:
        require_keys(c, ["master_company_id", "legal_name", "score", "method"])


def test_request_update_minimal_payload_still_resolves():
    """Edge: only the required valuo_company_id — must still return the full contract."""
    import time
    payload = {"valuo_company_id": f"golden_min_{int(time.time()*1000)}"}
    r = requests.post(f"{base()}{V}/request-update-from-valuo", json=payload, timeout=60)
    body = assert_json_200(r)
    require_keys(body, ["agency_request_id", "master_company_id", "resolution_status",
                        "confidence_score", "candidates", "message"])
    assert body["resolution_status"] in ("auto_merged", "conflict", "discovered")


def test_request_update_missing_required_field_422():
    """Error: missing valuo_company_id → FastAPI validation 422 (backward-compat)."""
    r = requests.post(f"{base()}{V}/request-update-from-valuo", json={}, timeout=30)
    assert_status(r, 422)


# ── GET /request-update-status/{id} ──
def test_request_update_status_contract(valuo_request):
    rid = valuo_request["response"].json()["agency_request_id"]
    r = requests.get(f"{base()}{V}/request-update-status/{rid}", timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["agency_request_id", "status", "master_company_id", "valuo_company_id",
                        "resolution_status", "enrichment_status", "merge_status",
                        "updated_fields", "completed_at", "error", "created_at"])
    assert body["agency_request_id"] == rid
    assert isinstance(body["updated_fields"], list)


def test_request_update_status_404():
    r = requests.get(f"{base()}{V}/request-update-status/vreq_doesnotexist", timeout=30)
    assert_status(r, 404)


# ── GET /request-status/{id} (Valuo polling) ──
def test_request_status_polling_contract(valuo_request):
    rid = valuo_request["response"].json()["agency_request_id"]
    r = requests.get(f"{base()}{V}/request-status/{rid}", timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["request_id", "status", "enrichment_status", "merge_status",
                        "master_company_id", "updated_fields", "fields_count", "enriched_data",
                        "enriched_company_url", "completed_at", "error", "created_at",
                        "updated_at", "enrichment_meta"])
    assert isinstance(body["fields_count"], int)
    assert isinstance(body["enriched_data"], dict)
    assert isinstance(body["enrichment_meta"], dict)
    require_keys(body["enrichment_meta"], ["sources_consulted", "sources_count",
                                           "fields_count", "duration_ms", "processed_at"])
    # enriched_company_url points to the canonical enriched endpoint when a master exists
    if body["master_company_id"]:
        assert "/api/v1/company/" in body["enriched_company_url"]


def test_request_status_404():
    r = requests.get(f"{base()}{V}/request-status/vreq_doesnotexist", timeout=30)
    assert_status(r, 404)


# ── GET /valuo-requests (admin, JWT) ──
def test_valuo_requests_requires_auth():
    r = requests.get(f"{base()}{V}/valuo-requests", timeout=30)
    assert r.status_code in (401, 403)


def test_valuo_requests_contract(auth_headers):
    r = requests.get(f"{base()}{V}/valuo-requests?limit=5", headers=auth_headers, timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["requests", "total"])
    assert isinstance(body["requests"], list)
    assert isinstance(body["total"], int)


# ── GET /health (public realtime health) ──
def test_health_contract():
    r = requests.get(f"{base()}{V}/health", timeout=30)
    body = assert_json_200(r)
    require_keys(body, ["verdict", "by_status", "total", "oldest_stuck",
                        "timeline_last_hour", "duration_ms", "checked_at"])
    assert body["verdict"] in ("healthy", "degraded", "stuck", "busy")
    require_keys(body["by_status"], ["pending", "processing", "completed", "failed"])
    for k in ("pending", "processing", "completed", "failed"):
        assert isinstance(body["by_status"][k], int)
    assert isinstance(body["total"], int)
    assert isinstance(body["timeline_last_hour"], list) and len(body["timeline_last_hour"]) == 12
    for bucket in body["timeline_last_hour"]:
        require_keys(bucket, ["from", "to", "label", "completed", "failed", "pending", "processing"])
    require_keys(body["duration_ms"], ["p50", "p95", "samples"])
    assert isinstance(body["duration_ms"]["samples"], int)
