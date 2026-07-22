"""Health endpoint of the Valuo enrichment pipeline must be reachable and report counts."""
import requests


def test_health_endpoint_reachable(base_url):
    r = requests.get(f"{base_url}/api/v1/valuo/health", timeout=15)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"

    data = r.json()
    # Required keys
    for k in ("verdict", "by_status", "total", "timeline_last_hour", "duration_ms", "checked_at"):
        assert k in data, f"missing key {k} in {data.keys()}"

    # Verdict must be one of the known values
    assert data["verdict"] in {"healthy", "busy", "stuck", "degraded"}, data["verdict"]

    # by_status must contain all four states
    for s in ("pending", "processing", "completed", "failed"):
        assert s in data["by_status"], f"missing status {s}"
        assert isinstance(data["by_status"][s], int)

    # Timeline must have 12 buckets (last hour, 5-min bins)
    assert len(data["timeline_last_hour"]) == 12

    # Duration block exists
    assert "p50" in data["duration_ms"]
    assert "p95" in data["duration_ms"]


def test_health_not_stuck_after_deploy(base_url):
    """A freshly deployed engine should report healthy or busy (never stuck/degraded)."""
    r = requests.get(f"{base_url}/api/v1/valuo/health", timeout=15)
    data = r.json()
    assert data["verdict"] in {"healthy", "busy"}, (
        f"Pipeline reports {data['verdict']!r}: {data.get('oldest_stuck')} "
        f"(by_status={data['by_status']})"
    )
