"""Web Source — cache hit/miss behavior and queue mechanics."""
import time
import requests


def test_cache_hit_for_known_master(base_url, known_master_with_scrape):
    """A master with a previously linked agency_result must return from cache (<100ms)."""
    mc_id = known_master_with_scrape["master_company_id"]

    r = requests.post(
        f"{base_url}/api/v1/intelligence/enrich",
        json={"master_company_id": mc_id, "profile": "basic"},
        timeout=15,
    )
    assert r.status_code == 200
    d = r.json()

    web_meta = next((s for s in d["sources_consulted"] if s["source"] == "web"), None)
    assert web_meta is not None
    assert web_meta.get("found") is True, f"Expected cache hit for {mc_id}, got {web_meta}"
    assert web_meta.get("from_cache") is True
    assert d["duration_ms"] < 500, f"Cache hit too slow: {d['duration_ms']}ms"

    # web.* fields must be present in the output
    web_fields = [k for k in d["fields"] if k.startswith("web.")]
    assert len(web_fields) > 0, f"No web.* fields returned: {list(d['fields'].keys())}"


def test_cache_miss_queues_scrape(base_url):
    """A fresh master with an unscraped domain must enqueue a scrape job."""
    # Create a brand-new master via the Valuo entrypoint with a unique domain
    unique = int(time.time() * 1000)
    payload = {
        "valuo_company_id": f"smoke_miss_{unique}",
        "legal_name": f"SMOKE MISS {unique} SL",
        "cif": f"B{unique % 100000000:08d}",
        "domain": f"smoketest-{unique}.example",
        "requested_by": "smoke_test",
    }
    r = requests.post(
        f"{base_url}/api/v1/valuo/request-update-from-valuo",
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200
    mc_id = r.json()["master_company_id"]

    # Now call enrich(basic) on this fresh master
    e = requests.post(
        f"{base_url}/api/v1/intelligence/enrich",
        json={"master_company_id": mc_id, "profile": "basic"},
        timeout=15,
    )
    assert e.status_code == 200
    d = e.json()

    web_meta = next((s for s in d["sources_consulted"] if s["source"] == "web"), None)
    assert web_meta is not None
    assert web_meta.get("found") is False
    assert web_meta.get("status") in ("scrape_queued", "scrape_already_queued"), web_meta
    assert web_meta.get("domain", "").startswith("smoketest-")


def test_scrape_queue_endpoint(base_url):
    """Scrape queue endpoint must report counts for the engine consumer."""
    r = requests.get(f"{base_url}/api/v1/intelligence/scrape-queue", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "counts" in d
    for s in ("pending", "claimed", "processing", "failed"):
        assert s in d["counts"]
        assert isinstance(d["counts"][s], int)
    assert "recent_jobs" in d and isinstance(d["recent_jobs"], list)
