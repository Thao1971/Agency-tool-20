"""v3 backend regression: M&A ENGINE endpoints + auth negatives."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
# read API key from backend/.env
API_KEY = None
with open("/app/backend/.env") as f:
    for line in f:
        if line.startswith("ARROBA_SERVICE_API_KEY"):
            API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

LOGIN_EMAIL = "daniel@wearebudadvisors.com"
LOGIN_PASSWORD = "Thao1971@"

MASTER_A = "mc_c6a1440c3ff8"
MASTER_B = "mc_e7c308a8e883"


@pytest.fixture(scope="module")
def api_headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def jwt_token():
    r = requests.post(f"{BASE_URL}/api/v1/auth/login",
                      json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"No token in login response: {data}"
    return token


@pytest.fixture(scope="module")
def jwt_headers(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}


# ---------------- Health ----------------
def test_health():
    r = requests.get(f"{BASE_URL}/api/v1/health", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("status") in ("healthy", "ok")


# ---------------- X-API-Key endpoints ----------------
def test_fragmentation(api_headers):
    r = requests.get(f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
                     params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                     headers=api_headers, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "hhi" in d and "concentration_label" in d and "engine_version" in d


def test_ratios_catalog(api_headers):
    r = requests.get(f"{BASE_URL}/api/v1/financial-intelligence/ratios/catalog",
                     headers=api_headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    ratios = d.get("ratios") or d.get("items") or d
    assert isinstance(ratios, (list, dict)) and len(ratios) > 0


def test_borme_link_backfill(api_headers):
    r = requests.post(f"{BASE_URL}/api/v1/signal-intelligence/borme-link-backfill",
                      json={"limit_companies": 500}, headers=api_headers, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("companies_remaining") == 0


def test_baselines_compute_and_status(api_headers):
    r = requests.post(f"{BASE_URL}/api/v1/signal-intelligence/baselines/compute",
                      json={"limit_sectors": 50}, headers=api_headers, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("buckets_written", 0) > 0
    r2 = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/baselines/status",
                      headers=api_headers, timeout=30)
    assert r2.status_code == 200
    assert r2.json().get("total_buckets", 0) > 0


def test_rollup_thesis(api_headers):
    r = requests.get(f"{BASE_URL}/api/v1/investment-intelligence/rollup-thesis",
                     params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                     headers=api_headers, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("fragmentation", "rollup_viable", "platform_candidate", "addon_targets_ranked"):
        assert k in d, f"missing {k}"


# ---------------- JWT endpoints ----------------
def test_watchlist_post_get(jwt_headers):
    r = requests.post(f"{BASE_URL}/api/v1/watchlist",
                      json={"master_id": MASTER_A}, headers=jwt_headers, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("watch_id") or d.get("id")
    r2 = requests.get(f"{BASE_URL}/api/v1/watchlist", headers=jwt_headers, timeout=30)
    assert r2.status_code == 200
    body = r2.json()
    items = body if isinstance(body, list) else body.get("watches", body.get("items", body.get("watchlist", [])))
    assert any((it.get("master_id") == MASTER_A) for it in items), f"master_id not in list: {items}"


def test_rebuild_competitor_graph(jwt_headers):
    r = requests.post(f"{BASE_URL}/api/v1/data-layer/rebuild-competitor-graph",
                      params={"limit_codes": 300}, headers=jwt_headers, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("edges_written", 0) > 0


def test_graph_traverse(jwt_headers):
    r = requests.get(f"{BASE_URL}/api/v1/data-layer/graph/{MASTER_A}/traverse",
                     params={"max_hops": 2}, headers=jwt_headers, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d.get("nodes", [])) > 0
    assert len(d.get("edges", [])) > 0


def test_control_synergy(jwt_headers):
    r = requests.get(f"{BASE_URL}/api/v1/data-layer/control-synergy/{MASTER_A}/{MASTER_B}",
                     headers=jwt_headers, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "control" in d and "synergy" in d and "engine_version" in d


# ---------------- Auth negatives ----------------
def test_apikey_missing_rejected():
    r = requests.get(f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
                     params={"cnae_field": "cnae_code", "cnae_value": "4711"}, timeout=30)
    assert r.status_code in (401, 403)


def test_apikey_invalid_rejected():
    r = requests.get(f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
                     params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                     headers={"X-API-Key": "invalid_key_xxx"}, timeout=30)
    assert r.status_code in (401, 403)


def test_jwt_missing_rejected():
    r = requests.get(f"{BASE_URL}/api/v1/watchlist", timeout=30)
    assert r.status_code in (401, 403)
