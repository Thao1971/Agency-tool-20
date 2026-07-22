"""Smoke tests — REQ-005 Recommendation Engine skill (POST /api/v1/skills/recommend)."""
import requests

SEARCH = "/api/v1/skills/search"
RECOMMEND = "/api/v1/skills/recommend"
ALLOWED_LINEAGE = {"raw", "normalized", "inferred", "ai_generated"}
REC_KEYS = {"master_company_id", "name", "sector", "score", "reason", "type"}


def _browse_ids(base_url, n=10):
    r = requests.post(f"{base_url}{SEARCH}", json={"query": "", "pagination": {"page": 1, "page_size": n}}, timeout=20)
    return [x["master_company_id"] for x in r.json()["workspace"]["blocks"][0]["props"]["results"]]


def _recommend(base_url, body):
    return requests.post(f"{base_url}{RECOMMEND}", json=body, timeout=20)


def test_thesis_mode_contract(base_url):
    r = _recommend(base_url, {"query": "consult", "pagination": {"page_size": 5}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d.keys()) == {"recommendations", "confidence", "lineage"}
    assert isinstance(d["recommendations"], list)
    assert 0.0 <= d["confidence"] <= 1.0
    assert d["lineage"]["source"] in ALLOWED_LINEAGE
    for rec in d["recommendations"]:
        assert set(rec.keys()) == REC_KEYS
        assert rec["type"] == "similar"
        assert 0.0 <= rec["score"] <= 1.0


def test_thesis_ranked_descending(base_url):
    d = _recommend(base_url, {"query": "consult", "pagination": {"page_size": 20}}).json()
    scores = [r["score"] for r in d["recommendations"]]
    assert scores == sorted(scores, reverse=True)


def test_similar_mode_contract(base_url):
    """Find a seed that yields similar recommendations; assert reason + type + lineage."""
    found = None
    for mc_id in _browse_ids(base_url, 10):
        d = _recommend(base_url, {"master_company_id": mc_id, "pagination": {"page_size": 5}}).json()
        assert set(d.keys()) == {"recommendations", "confidence", "lineage"}
        assert d["lineage"]["source"] == "normalized"
        if d["recommendations"]:
            found = d
            break
    assert found, "no seed produced similar recommendations"
    for rec in found["recommendations"]:
        assert set(rec.keys()) == REC_KEYS
        assert rec["type"] == "similar"
        assert rec["reason"]


def test_404_unknown_seed(base_url):
    r = _recommend(base_url, {"master_company_id": "not-a-real-id"})
    assert r.status_code == 404


def test_lineage_is_normalized(base_url):
    d = _recommend(base_url, {"query": "software"}).json()
    assert d["lineage"]["source"] == "normalized"
