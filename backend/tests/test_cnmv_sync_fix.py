"""
Tests for CNMV browser recycling fix.
Verifies that the 'Target page, context or browser has been closed' error is gone
after implementing browser recycle every 30 navigations.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
EMAIL = "daniel@wearebudadvisors.com"
PASSWORD = "Thao1971@"

BROWSER_CLOSED_MARKER = "browser has been closed"


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _assert_no_browser_closed(errors):
    """Errors may include transient timeouts; only browser-closed is a failure."""
    for e in errors or []:
        s = str(e).lower()
        assert BROWSER_CLOSED_MARKER not in s, f"Browser-closed crash detected: {e}"


# ---- Health check (before) ----
def test_health_before(auth_headers):
    r = requests.get(f"{BASE_URL}/api/v1/health", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("healthy", "ok", "up") or "status" in body


# ---- CNMV sync fcr ----
def test_cnmv_sync_fcr_no_browser_closed(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/cnmv/sync",
        params={"types": "fcr", "max_pages": 60},
        headers=auth_headers,
        timeout=500,
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:500]}"
    body = r.json()
    assert body.get("status") in ("completed", "partial"), f"unexpected status: {body}"
    _assert_no_browser_closed(body.get("errors", []))
    print(f"fcr sync: status={body.get('status')} errors={body.get('errors')}")


# ---- CNMV sync scr ----
def test_cnmv_sync_scr_no_browser_closed(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/cnmv/sync",
        params={"types": "scr", "max_pages": 60},
        headers=auth_headers,
        timeout=500,
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:500]}"
    body = r.json()
    assert body.get("status") in ("completed", "partial"), f"unexpected status: {body}"
    _assert_no_browser_closed(body.get("errors", []))
    print(f"scr sync: status={body.get('status')} errors={body.get('errors')}")


# ---- Match companies ----
def test_cnmv_match_companies(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/cnmv/match-companies",
        headers=auth_headers,
        timeout=300,
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:500]}"
    body = r.json()
    assert body.get("status") == "completed", f"unexpected: {body}"
    assert isinstance(body.get("total_checked"), int)
    print(f"match: {body}")


# ---- Rebuild signals ----
def test_cnmv_rebuild_signals(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/v1/cnmv/rebuild-signals",
        headers=auth_headers,
        timeout=300,
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:500]}"
    body = r.json()
    assert body.get("status") == "completed", f"unexpected: {body}"
    assert isinstance(body.get("signals_generated"), int)
    assert isinstance(body.get("metrics_generated"), int)
    assert isinstance(body.get("total_entities"), int)
    assert body["total_entities"] > 0
    print(f"rebuild: {body}")


# ---- Health after (backend not killed) ----
def test_health_after(auth_headers):
    r = requests.get(f"{BASE_URL}/api/v1/health", timeout=15)
    assert r.status_code == 200
