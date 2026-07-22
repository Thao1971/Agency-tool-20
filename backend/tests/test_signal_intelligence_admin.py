"""Backend tests for signal-intelligence admin & data-layer rebuild endpoints."""
import os
import pytest
import requests

BASE_URL = "http://localhost:8001"
API_KEY = os.environ.get("ARROBA_SERVICE_API_KEY") or "as_XwNq-0S9nQNhNd0wcXbpvQeYcwMKOi_x"
LOGIN_EMAIL = "daniel@wearebudadvisors.com"
LOGIN_PASSWORD = "Thao1971@"


@pytest.fixture(scope="module")
def svc_headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def jwt_token():
    r = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


# --- STEP 1: borme-link-backfill ---
def test_step1_borme_link_backfill(svc_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/signal-intelligence/borme-link-backfill",
        headers=svc_headers,
        json={"limit_companies": 500},
        timeout=90,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    d = r.json()
    for k in ("companies_processed", "events_linked", "companies_remaining", "bridge_version"):
        assert k in d, f"missing {k} in {d}"
    assert d["companies_remaining"] == 0, f"expected 0 remaining, got {d['companies_remaining']}"
    print("STEP1:", d)


def test_step1_idempotent(svc_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/signal-intelligence/borme-link-backfill",
        headers=svc_headers,
        json={"limit_companies": 500},
        timeout=90,
    )
    assert r.status_code == 200
    assert r.json()["companies_remaining"] == 0


# --- STEP 2: baselines/compute ---
def test_step2_baselines_compute(svc_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/signal-intelligence/baselines/compute",
        headers=svc_headers,
        json={"limit_sectors": 50},
        timeout=120,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    d = r.json()
    print("STEP2:", d)
    assert d.get("sectors_processed", 0) > 0
    assert d.get("companies_sampled", 0) > 0
    assert d.get("buckets_written", 0) > 0


def test_step2b_baselines_status(svc_headers):
    r = requests.get(
        f"{BASE_URL}/api/v1/signal-intelligence/baselines/status",
        headers=svc_headers,
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    d = r.json()
    print("STEP2b:", d)
    assert d.get("total_buckets", 0) > 0
    by_metric = d.get("by_metric") or {}
    # Accept either dict or list layout
    keys = set(by_metric.keys()) if isinstance(by_metric, dict) else {
        (item.get("metric") or item.get("_id")) for item in by_metric
    }
    for m in ("ebitda_margin", "revenue_per_employee", "revenue_growth_yoy"):
        assert m in keys, f"metric {m} missing in by_metric={by_metric}"


# --- STEP 3: rebuild-competitor-graph (JWT) ---
def test_step3_rebuild_competitor_graph(jwt_token):
    r = requests.post(
        f"{BASE_URL}/api/v1/data-layer/rebuild-competitor-graph",
        params={"limit_codes": 300},
        headers={"Authorization": f"Bearer {jwt_token}"},
        timeout=180,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    d = r.json()
    print("STEP3:", d)
    assert d.get("edges_written", 0) > 0
    assert d.get("cnae_codes_scanned", 0) > 0
    assert d.get("buckets_used", 0) > 0


# --- AUTH negative checks ---
def test_signal_intel_rejects_missing_apikey():
    r = requests.post(
        f"{BASE_URL}/api/v1/signal-intelligence/borme-link-backfill",
        json={"limit_companies": 10},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


def test_signal_intel_rejects_bad_apikey():
    r = requests.get(
        f"{BASE_URL}/api/v1/signal-intelligence/baselines/status",
        headers={"X-API-Key": "wrong-key"},
        timeout=30,
    )
    assert r.status_code in (401, 403)


def test_rebuild_competitor_graph_rejects_no_jwt():
    r = requests.post(
        f"{BASE_URL}/api/v1/data-layer/rebuild-competitor-graph",
        params={"limit_codes": 10},
        timeout=30,
    )
    assert r.status_code in (401, 403)
