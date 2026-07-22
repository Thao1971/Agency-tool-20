"""Smoke tests — REQ-003 Search Engine skill (POST /api/v1/skills/search)."""
import time
import requests

PATH = "/api/v1/skills/search"


def _post(base_url, body):
    return requests.post(f"{base_url}{PATH}", json=body, timeout=20)


def test_public_no_auth(base_url):
    r = _post(base_url, {"query": "consult"})
    assert r.status_code == 200, r.text


def test_workspace_blocks_contract(base_url):
    r = _post(base_url, {"query": "consult", "pagination": {"page": 1, "page_size": 5}})
    d = r.json()
    assert "workspace" in d and "blocks" in d["workspace"]
    blocks = d["workspace"]["blocks"]
    assert len(blocks) == 1
    b = blocks[0]
    assert b["type"] == "search_results"
    assert b["props"]["query"] == "consult"
    assert isinstance(b["props"]["results"], list)


def test_result_item_shape(base_url):
    r = _post(base_url, {"query": "consult", "pagination": {"page": 1, "page_size": 5}})
    results = r.json()["workspace"]["blocks"][0]["props"]["results"]
    assert results, "expected at least one result for 'consult'"
    for item in results:
        assert set(item.keys()) == {"master_company_id", "name", "sector", "cif", "score"}
        assert isinstance(item["score"], (int, float)) and 0.0 <= item["score"] <= 1.0
        assert item["master_company_id"]


def test_results_ranked_descending(base_url):
    results = _post(base_url, {"query": "consult", "pagination": {"page": 1, "page_size": 20}}).json()["workspace"]["blocks"][0]["props"]["results"]
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_pagination_page_size(base_url):
    results = _post(base_url, {"query": "", "pagination": {"page": 1, "page_size": 3}}).json()["workspace"]["blocks"][0]["props"]["results"]
    assert len(results) <= 3


def test_empty_query_browses(base_url):
    r = _post(base_url, {"query": ""})
    assert r.status_code == 200
    assert isinstance(r.json()["workspace"]["blocks"][0]["props"]["results"], list)


def test_defaults_when_minimal_body(base_url):
    """Filters/context/pagination are optional — contract must accept just {query}."""
    r = _post(base_url, {"query": "software"})
    assert r.status_code == 200


def test_sla_latency_origin():
    """Origin p95 must be well under the 400ms SLA."""
    times = []
    for q in ["consult", "software", "marca", "data", "agencia"] * 2:
        t0 = time.time()
        requests.post("http://localhost:8001" + PATH, json={"query": q}, timeout=10)
        times.append((time.time() - t0) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95) - 1]
    assert p95 < 400, f"p95={p95:.1f}ms exceeds SLA"
