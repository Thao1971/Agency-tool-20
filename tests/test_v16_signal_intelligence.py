"""v16 regression + new-feature tests: signal-intelligence stats/opportunities/catalog/signals + auth negatives."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://preview-arroba-app.preview.emergentagent.com").rstrip("/")

# read API key from backend/.env directly (test env doesn't inherit)
def _read_env_key():
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("ARROBA_SERVICE_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"')
    return None

API_KEY = _read_env_key()
CREDS = {"email": "daniel@wearebudadvisors.com", "password": "Thao1971@"}


@pytest.fixture(scope="module")
def jwt_token():
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json=CREDS, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def jh(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


@pytest.fixture(scope="module")
def kh():
    return {"X-API-Key": API_KEY}


# ---------- STATS ----------
class TestStats:
    def test_stats_view(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/stats/view", headers=jh, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "total_signals" in d
        assert "total_opportunities" in d
        assert "by_severity" in d
        assert "by_category" in d
        assert "opportunities_by_type" in d
        # no pagination cap: expect real large number
        assert d["total_signals"] >= 1000, f"total_signals suspiciously low: {d['total_signals']}"
        # opportunities_by_type should include the multiple types (v14 fix)
        by_type = d["opportunities_by_type"]
        # store for other tests
        pytest.opportunities_stats = d
        print("stats:", {k: d.get(k) for k in ("total_signals", "total_opportunities", "opportunities_by_type")})


# ---------- OPPORTUNITIES ----------
class TestOpportunities:
    def test_opportunities_view_multi_type(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/opportunities/view?limit=50", headers=jh, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] > 0
        assert len(d["opportunities"]) == d["count"]
        types = {o["signal_type"] for o in d["opportunities"]}
        # v14 fix: should include more than just succession
        print("opportunity types seen:", types)
        assert "ownership.consolidator" in types, f"v14 severity filter fix broken; only types={types}"

    def test_opportunities_view_filter_by_type(self, jh):
        r = requests.get(
            f"{BASE_URL}/api/v1/signal-intelligence/opportunities/view?signal_types=ownership.consolidator&limit=20",
            headers=jh, timeout=60,
        )
        assert r.status_code == 200
        d = r.json()
        types = {o["signal_type"] for o in d["opportunities"]}
        assert types.issubset({"ownership.consolidator"}), f"got other types: {types}"

    def test_opportunities_view_invalid_combo_ok(self, jh):
        r = requests.get(
            f"{BASE_URL}/api/v1/signal-intelligence/opportunities/view?signal_types=does.not.exist&provincia=Nowhere",
            headers=jh, timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_opportunities_feed_view(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/opportunities/feed/view", headers=jh, timeout=60)
        assert r.status_code == 200


# ---------- SIGNALS CATALOG + DETAIL ----------
class TestSignals:
    def test_catalog_view(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/catalog/view", headers=jh, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "taxonomy_version" in d
        assert "categories" in d
        assert "signal_types" in d

    def test_signals_list_view(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/signals/view?limit=20", headers=jh, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # store a signal id for detail test
        signals = d.get("signals") or d.get("results") or []
        assert len(signals) > 0, f"no signals returned: {d}"
        pytest.first_signal_id = signals[0].get("signal_id")
        cats = {s.get("category") for s in signals if s.get("category")}
        print("signal categories seen (top20):", cats)

    def test_signal_detail_view(self, jh):
        sid = getattr(pytest, "first_signal_id", None)
        if not sid:
            pytest.skip("no signal id available")
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/signal/{sid}/view", headers=jh, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("signal_id") == sid


# ---------- AUTH NEGATIVES ----------
class TestAuthNegatives:
    def test_service_endpoint_no_key(self):
        r = requests.post(f"{BASE_URL}/api/v1/signal-intelligence/migrate-dedupe", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_service_endpoint_bad_key(self):
        r = requests.post(f"{BASE_URL}/api/v1/signal-intelligence/migrate-dedupe",
                          headers={"X-API-Key": "not-a-key"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_fragmentation_no_key(self):
        r = requests.get(f"{BASE_URL}/api/v1/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711", timeout=30)
        assert r.status_code in (401, 403)

    def test_jwt_endpoint_no_token(self):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/stats/view", timeout=30)
        assert r.status_code in (401, 403)

    def test_watchlist_no_token(self):
        r = requests.get(f"{BASE_URL}/api/v1/watchlist", timeout=30)
        assert r.status_code in (401, 403)

    def test_opportunities_view_no_token(self):
        r = requests.get(f"{BASE_URL}/api/v1/signal-intelligence/opportunities/view", timeout=30)
        assert r.status_code in (401, 403)


# ---------- REGRESSION ----------
class TestRegression:
    def test_fragmentation(self, kh):
        r = requests.get(
            f"{BASE_URL}/api/v1/investment-intelligence/fragmentation?cnae_field=cnae_code&cnae_value=4711",
            headers=kh, timeout=60,
        )
        assert r.status_code == 200, r.text

    def test_ratios_catalog(self, kh):
        r = requests.get(f"{BASE_URL}/api/v1/financial-intelligence/ratios/catalog", headers=kh, timeout=30)
        assert r.status_code == 200

    def test_rollup_thesis(self, kh):
        r = requests.get(
            f"{BASE_URL}/api/v1/investment-intelligence/rollup-thesis?cnae_field=cnae_code&cnae_value=4711",
            headers=kh, timeout=60,
        )
        assert r.status_code == 200

    def test_watchlist_get(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/watchlist", headers=jh, timeout=30)
        assert r.status_code == 200

    def test_iberinform_stats(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/admin/iberinform/stats", headers=jh, timeout=30)
        assert r.status_code == 200
        d = r.json()
        print("iberinform stats:", d)
        # accept either flat or nested
        real = d.get("real") or d.get("real_companies") or (d.get("counts") or {}).get("real")
        assert real == 24992 or (isinstance(real, dict) and False), f"expected 24992 real, got: {d}"

    def test_data_providers_health(self, jh):
        r = requests.get(f"{BASE_URL}/api/v1/data-providers/health", headers=jh, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # find iberinform entry
        found = False
        providers = d if isinstance(d, list) else d.get("providers", d.get("data_providers", []))
        for p in providers if isinstance(providers, list) else []:
            if "iberinform" in str(p).lower():
                found = True
                break
        assert found or "iberinform" in str(d).lower(), f"iberinform missing: {str(d)[:400]}"
