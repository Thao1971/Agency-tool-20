"""Tests for v2 new endpoints: rollup-thesis, control-synergy + regressions + auth negatives."""
import os
import pytest
import requests

BASE = "http://localhost:8001"
API_KEY = os.environ.get("ARROBA_SERVICE_API_KEY", "as_XwNq-0S9nQNhNd0wcXbpvQeYcwMKOi_x")
LOGIN_EMAIL = "daniel@wearebudadvisors.com"
LOGIN_PASSWORD = "Thao1971@"


@pytest.fixture(scope="module")
def jwt_token():
    r = requests.post(f"{BASE}/api/v1/auth/login",
                      json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token") or data.get("data", {}).get("access_token")
    assert token, f"no token in {data}"
    return token


@pytest.fixture(scope="module")
def jwt_headers(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


@pytest.fixture(scope="module")
def key_headers():
    return {"X-API-Key": API_KEY}


# --- Health ---
def test_health():
    r = requests.get(f"{BASE}/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert str(body).lower().find("healthy") >= 0 or body.get("status") in ("ok", "healthy")


# --- NEW EP1: rollup-thesis ---
class TestRollupThesis:
    URL = f"{BASE}/api/v1/investment-intelligence/rollup-thesis"

    def test_success(self, key_headers):
        r = requests.get(self.URL, params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers=key_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        for f in ["fragmentation", "rollup_viable", "viability_reasons",
                  "platform_candidate", "addon_targets_ranked"]:
            assert f in d, f"missing field {f} in {list(d.keys())}"
        assert isinstance(d["viability_reasons"], list)
        assert isinstance(d["addon_targets_ranked"], list)

    def test_missing_cnae_value(self, key_headers):
        r = requests.get(self.URL, params={"cnae_field": "cnae_code"}, headers=key_headers)
        assert r.status_code in (400, 422), f"expected 400/422 got {r.status_code}"

    def test_missing_api_key(self):
        r = requests.get(self.URL, params={"cnae_field": "cnae_code", "cnae_value": "4711"})
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_invalid_api_key(self):
        r = requests.get(self.URL, params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers={"X-API-Key": "bad-key"})
        assert r.status_code in (401, 403)


# --- NEW EP2: control-synergy ---
class TestControlSynergy:
    URL = f"{BASE}/api/v1/data-layer/control-synergy/mc_c6a1440c3ff8/mc_e7c308a8e883"

    def test_success(self, jwt_headers):
        r = requests.get(self.URL, headers=jwt_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "control" in d and "synergy" in d and "engine_version" in d
        c, s = d["control"], d["synergy"]
        for f in ["relationship", "control_level", "evidence"]:
            assert f in c, f"control missing {f}"
        for f in ["synergy_score", "evidence"]:
            assert f in s, f"synergy missing {f}"

    def test_missing_jwt(self):
        r = requests.get(self.URL)
        assert r.status_code in (401, 403)

    def test_invalid_jwt(self):
        r = requests.get(self.URL, headers={"Authorization": "Bearer invalid.jwt.token"})
        assert r.status_code in (401, 403)


# --- Regression ---
class TestRegression:
    def test_fragmentation(self, key_headers):
        r = requests.get(f"{BASE}/api/v1/investment-intelligence/fragmentation",
                         params={"cnae_field": "cnae_code", "cnae_value": "4711"},
                         headers=key_headers)
        assert r.status_code == 200, r.text

    def test_ratios_catalog(self, key_headers):
        r = requests.get(f"{BASE}/api/v1/financial-intelligence/ratios/catalog",
                         headers=key_headers)
        assert r.status_code == 200, r.text

    def test_watchlist_post_get(self, jwt_headers):
        payload = {"master_id": "mc_c6a1440c3ff8", "notes": "TEST_v2_regression"}
        r_post = requests.post(f"{BASE}/api/v1/watchlist", json=payload, headers=jwt_headers)
        assert r_post.status_code in (200, 201), f"POST watchlist: {r_post.status_code} {r_post.text}"
        r_get = requests.get(f"{BASE}/api/v1/watchlist", headers=jwt_headers)
        assert r_get.status_code == 200, r_get.text
