"""End-to-end Valuo enrichment flow: request → pending → completed (no stuck)."""
import time
import requests
from .conftest import poll_until


def test_valuo_request_completes(base_url):
    payload = {
        "valuo_company_id": f"smoke_valuo_{int(time.time())}",
        "legal_name": "TELEFONICA SA",
        "cif": "A28015865",
        "domain": "telefonica.com",
        "requested_by": "smoke_test",
    }
    r = requests.post(
        f"{base_url}/api/v1/valuo/request-update-from-valuo",
        json=payload,
        timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    req_id = r.json()["agency_request_id"]

    def fetch_status():
        return requests.get(
            f"{base_url}/api/v1/valuo/request-status/{req_id}", timeout=10
        ).json()

    # Should complete within 10 seconds with BackgroundTasks (typical: <1s)
    status = poll_until(
        fetch_status,
        lambda d: d.get("enrichment_status") in ("completed", "failed"),
        timeout=10,
        interval=0.5,
    )

    assert status["enrichment_status"] == "completed", (
        f"Request {req_id} status={status.get('enrichment_status')} "
        f"error={status.get('error')}"
    )

    # Required response shape
    assert "enrichment_meta" in status
    meta = status["enrichment_meta"]
    assert isinstance(meta.get("sources_consulted"), list) and len(meta["sources_consulted"]) > 0
    assert isinstance(meta.get("duration_ms"), int) and meta["duration_ms"] >= 0
    assert meta["duration_ms"] < 10000, f"Enrichment too slow: {meta['duration_ms']}ms"


def test_no_stuck_requests_overall(base_url):
    """Globally there must be 0 requests stuck >5min on a healthy system."""
    r = requests.get(f"{base_url}/api/v1/valuo/health", timeout=10).json()
    assert r["oldest_stuck"] is None, f"Stuck request found: {r['oldest_stuck']}"
