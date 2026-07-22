"""Backend tests for review request: 4 endpoints + auth negatives."""
import os
import pytest
import requests

BASE_URL = "http://localhost:8001"
API_KEY = os.environ.get("ARROBA_SERVICE_API_KEY", "as_XwNq-0S9nQNhNd0wcXbpvQeYcwMKOi_x")
LOGIN_EMAIL = "daniel@wearebudadvisors.com"
LOGIN_PASSWORD = "Thao1971@"
MASTER_ID = "mc_c6a1440c3ff8"


@pytest.fixture(scope="module")
def jwt_token():
    r = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        # try form
        r = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
            timeout=30,
        )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token
    return token


# EP1
def test_ep1_fragmentation_ok():
    r = requests.get(
        f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
        params={"cnae_field": "cnae_code", "cnae_value": "4711"},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("total_companies_in_arroba_universe", "hhi", "concentration_label", "engine_version"):
        assert k in d, f"missing {k} in {d}"
    print("EP1:", d.get("total_companies_in_arroba_universe"), d.get("hhi"), d.get("concentration_label"))


def test_ep1_fragmentation_missing_key():
    r = requests.get(
        f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
        params={"cnae_field": "cnae_code", "cnae_value": "4711"},
        timeout=30,
    )
    assert r.status_code in (401, 403), r.status_code


def test_ep1_fragmentation_invalid_key():
    r = requests.get(
        f"{BASE_URL}/api/v1/investment-intelligence/fragmentation",
        params={"cnae_field": "cnae_code", "cnae_value": "4711"},
        headers={"X-API-Key": "bogus"},
        timeout=30,
    )
    assert r.status_code in (401, 403), r.status_code


# EP2
def test_ep2_ratios_catalog_ok():
    r = requests.get(
        f"{BASE_URL}/api/v1/financial-intelligence/ratios/catalog",
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert "ratios" in d
    assert isinstance(d["ratios"], list) and len(d["ratios"]) > 0
    print("EP2 ratios count:", len(d["ratios"]))


def test_ep2_ratios_catalog_missing_key():
    r = requests.get(f"{BASE_URL}/api/v1/financial-intelligence/ratios/catalog", timeout=30)
    assert r.status_code in (401, 403)


# EP3
def test_ep3_watchlist_add_and_list(jwt_token):
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = requests.post(
        f"{BASE_URL}/api/v1/watchlist",
        json={"master_id": MASTER_ID},
        headers=h,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert "watch_id" in d or "id" in d, d
    print("EP3 POST:", d)

    r2 = requests.get(f"{BASE_URL}/api/v1/watchlist", headers=h, timeout=30)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    items = d2 if isinstance(d2, list) else (d2.get("watches") or d2.get("items") or d2.get("watchlist") or [])
    master_ids = [it.get("master_id") for it in items if isinstance(it, dict)]
    assert MASTER_ID in master_ids, f"{MASTER_ID} not in {master_ids}"
    print("EP3 GET count:", len(items))


def test_ep3_watchlist_no_auth():
    r = requests.get(f"{BASE_URL}/api/v1/watchlist", timeout=30)
    assert r.status_code in (401, 403)
    r2 = requests.post(f"{BASE_URL}/api/v1/watchlist", json={"master_id": MASTER_ID}, timeout=30)
    assert r2.status_code in (401, 403)


# EP4
def test_ep4_traverse_ok(jwt_token):
    h = {"Authorization": f"Bearer {jwt_token}"}
    r = requests.get(
        f"{BASE_URL}/api/v1/data-layer/graph/{MASTER_ID}/traverse",
        params={"max_hops": 2},
        headers=h,
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("root_master_id") == MASTER_ID
    assert isinstance(d.get("nodes"), list) and len(d["nodes"]) > 0
    assert isinstance(d.get("edges"), list) and len(d["edges"]) > 0
    print("EP4 nodes:", len(d["nodes"]), "edges:", len(d["edges"]))


def test_ep4_traverse_no_auth():
    r = requests.get(
        f"{BASE_URL}/api/v1/data-layer/graph/{MASTER_ID}/traverse",
        params={"max_hops": 2},
        timeout=30,
    )
    assert r.status_code in (401, 403)
