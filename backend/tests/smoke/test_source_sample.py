"""Smoke test: generic source data sample endpoint (Data Explorer).

`GET /api/v1/intelligence/sources/{source}/sample` must be 100% dynamic — the
collection comes from each module's META, sampling is gated by
`META['supports_sample']`, and there is NO per-source switch. A new source with a
collection becomes explorable automatically.
"""

import requests

from services.intelligence_engine import engine_info


def test_sample_returns_paginated_real_docs(base_url):
    """Pick the first sample-enabled source that has data and assert pagination."""
    target = None
    for name in engine_info.get_all_sources():
        meta = engine_info.get_source_meta(name)
        if not meta["supports_sample"]:
            continue
        r = requests.get(f"{base_url}/api/v1/intelligence/sources/{name}/sample?page=1&page_size=5", timeout=20)
        assert r.status_code == 200, f"{name} sample failed {r.status_code}: {r.text[:200]}"
        body = r.json()
        for field in ("source", "collection", "total_records", "current_page", "page_size", "items"):
            assert field in body, f"{name} sample missing '{field}'"
        assert body["current_page"] == 1
        assert body["page_size"] == 5
        if body["total_records"] > 0:
            target = (name, body)
            break
    assert target, "No sample-enabled source returned data — expected at least one populated collection"
    name, body = target
    assert len(body["items"]) <= 5
    assert all("_id" not in it for it in body["items"]), "Mongo _id must not leak into sample items"


def test_sample_pagination_advances(base_url):
    """page=2 returns different docs than page=1 for a large collection."""
    # procurement has ~180k records — safe for pagination assertions.
    p1 = requests.get(f"{base_url}/api/v1/intelligence/sources/procurement/sample?page=1&page_size=5", timeout=20).json()
    p2 = requests.get(f"{base_url}/api/v1/intelligence/sources/procurement/sample?page=2&page_size=5", timeout=20).json()
    assert p1["total_records"] == p2["total_records"]
    assert p1["current_page"] == 1 and p2["current_page"] == 2
    if p1["total_records"] > 10:
        assert p1["items"] != p2["items"], "Pagination did not advance (page 2 == page 1)"


def test_sample_rejects_unsupported_source(base_url):
    """OEPM legacy stub (collection=None, supports_sample=False) must 400."""
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/oepm/sample", timeout=15)
    assert r.status_code == 400, f"Expected 400 for oepm, got {r.status_code}"


def test_sample_unknown_source_404(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/not_a_real_source/sample", timeout=15)
    assert r.status_code == 404


def test_sample_flag_matches_meta(base_url):
    """sync-status `supports_sample` per source must mirror each module's META."""
    data = requests.get(f"{base_url}/api/v1/public/intelligence/sync-status", timeout=20).json()
    for name, row in (data.get("sources") or {}).items():
        expected = engine_info.get_source_meta(name)["supports_sample"]
        assert row.get("supports_sample") == expected, f"supports_sample mismatch for '{name}'"
