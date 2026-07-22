"""Smoke tests — P2.2 Taxonomy Fase C (embeddings / semantic similarity / clustering)."""
import requests

REBUILD_EMB = "/api/v1/data-layer/rebuild-embeddings"
SEARCH = "/api/v1/skills/search"
RECOMMEND = "/api/v1/skills/recommend"


def test_rebuild_embeddings_requires_auth(base_url):
    r = requests.post(f"{base_url}{REBUILD_EMB}", timeout=30)
    assert r.status_code in (401, 403)


def test_rebuild_embeddings_builds_index(base_url, auth_token):
    r = requests.post(f"{base_url}{REBUILD_EMB}", headers={"Authorization": f"Bearer {auth_token}"}, timeout=180)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "ok"
    assert s["count"] > 100 and s["dim"] >= 2 and s["clusters"] >= 2


def test_hybrid_search_semantic_relevance(base_url):
    """A multi-word semantic query returns sector-coherent results (hybrid ranking)."""
    r = requests.post(f"{base_url}{SEARCH}", json={
        "query": "publicidad y marketing", "pagination": {"page_size": 8}
    }, timeout=20)
    assert r.status_code == 200, r.text
    results = r.json()["workspace"]["blocks"][0]["props"]["results"]
    assert results
    # contract unchanged + ranked desc
    scores = [x["score"] for x in results]
    assert scores == sorted(scores, reverse=True)
    for x in results:
        assert set(x.keys()) == {"master_company_id", "name", "sector", "cif", "score"}


def test_search_contract_unchanged_under_hybrid(base_url):
    r = requests.post(f"{base_url}{SEARCH}", json={"query": "consult"}, timeout=20)
    b = r.json()["workspace"]["blocks"][0]
    assert b["type"] == "search_results" and "results" in b["props"]


def test_recommend_still_works_with_semantic_blend(base_url):
    r = requests.post(f"{base_url}{RECOMMEND}", json={"query": "software", "pagination": {"page_size": 5}}, timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert set(d.keys()) == {"recommendations", "confidence", "lineage"}
