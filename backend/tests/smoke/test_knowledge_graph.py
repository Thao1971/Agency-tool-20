"""Smoke tests — P3 Knowledge Graph (company_relationships; transparent to contracts).

Only similar_to / same_cluster are materialized in this phase. ownership-type relations
(shareholder_of, subsidiary_of, same_group, ...) are reserved in the model, not populated.
"""
import requests

REBUILD_GRAPH = "/api/v1/data-layer/rebuild-graph"
REBUILD_EMB = "/api/v1/data-layer/rebuild-embeddings"
ENRICH = "/api/v1/enrich_company"
SEARCH = "/api/v1/skills/search"
RECOMMEND = "/api/v1/skills/recommend"
import os
SVC = {"X-API-Key": os.environ.get("ARROBA_SERVICE_API_KEY",
                                   "as_TGx2m4UaXc25lsYv_Ep5_w7niWJCA3q-SjU4I9mSmvk")}

MATERIALIZED_TYPES = {"similar_to", "same_cluster"}
REL_KEYS = {"target_master_company_id", "relationship_type", "score", "confidence"}


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def _some_master_ids(base_url, n=30):
    ids = []
    for q in ("sa", "sl", "consult", "tecnolog"):
        r = requests.post(f"{base_url}{SEARCH}", json={
            "query": q, "filters": {"has_domain": False}, "pagination": {"page_size": 20}}, timeout=20)
        ids += [x["master_company_id"] for x in r.json()["workspace"]["blocks"][0]["props"]["results"]]
    # dedupe preserving order
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out[:n]


def test_rebuild_graph_requires_auth(base_url):
    assert requests.post(f"{base_url}{REBUILD_GRAPH}", timeout=30).status_code in (401, 403)


def test_rebuild_graph_and_idempotent(base_url, auth_token):
    # ensure embeddings exist (graph depends on them)
    requests.post(f"{base_url}{REBUILD_EMB}", headers=_hdr(auth_token), timeout=180)
    r1 = requests.post(f"{base_url}{REBUILD_GRAPH}", headers=_hdr(auth_token), timeout=180)
    assert r1.status_code == 200, r1.text
    s1 = r1.json()
    assert s1["status"] == "ok"
    assert s1["companies"] > 100 and s1["relationships"] > 0
    assert set(s1["by_type"].keys()).issubset(MATERIALIZED_TYPES)
    assert "version" in s1
    # idempotent rebuild -> same count (deterministic infra)
    r2 = requests.post(f"{base_url}{REBUILD_GRAPH}", headers=_hdr(auth_token), timeout=180)
    s2 = r2.json()
    assert s2["relationships"] == s1["relationships"]


def test_relationships_shape_and_no_self_loops(base_url, auth_token):
    requests.post(f"{base_url}{REBUILD_GRAPH}", headers=_hdr(auth_token), timeout=180)
    found = None
    for mc_id in _some_master_ids(base_url, 30):
        d = requests.post(f"{base_url}{ENRICH}", json={
            "master_company_id": mc_id, "context": {"include_narrative": False}}, headers=SVC, timeout=30).json()
        rels = d.get("relationships") or []
        if rels:
            found = (mc_id, rels)
            break
    assert found, "expected at least one company with materialized relationships"
    seed_id, rels = found
    for rel in rels:
        assert set(rel.keys()) == REL_KEYS
        assert rel["relationship_type"] in MATERIALIZED_TYPES
        assert rel["target_master_company_id"] != seed_id  # no self-loop
        assert 0.0 <= rel["score"] <= 1.0
        assert 0.0 <= rel["confidence"] <= 1.0


def test_analyze_contract_has_relationships_block(base_url):
    ids = _some_master_ids(base_url, 5)
    d = requests.post(f"{base_url}{ENRICH}", json={
        "master_company_id": ids[0], "context": {"include_narrative": False}}, headers=SVC, timeout=30).json()
    # additive block present and ownership reserved (empty structure)
    assert "relationships" in d and isinstance(d["relationships"], list)
    assert "ownership" in d
    assert set(d["ownership"].keys()) == {"shareholders", "ultimate_parent", "group_name"}


def test_recommend_contract_unchanged_with_graph(base_url):
    ids = _some_master_ids(base_url, 5)
    d = requests.post(f"{base_url}{RECOMMEND}", json={"master_company_id": ids[0]}, timeout=20).json()
    assert set(d.keys()) == {"recommendations", "confidence", "lineage"}
    for r in d["recommendations"]:
        assert set(r.keys()) == {"master_company_id", "name", "sector", "score", "reason", "type"}


def test_search_cluster_id_filter_internal(base_url):
    # discover a cluster_id from a known company's master via Analyze is not exposed;
    # instead exercise the internal filter contract: results stay within shape and the
    # output contract is unchanged regardless of the (internal) cluster_id filter.
    r = requests.post(f"{base_url}{SEARCH}", json={
        "query": "", "filters": {"has_domain": False, "cluster_id": 0},
        "pagination": {"page_size": 10}}, timeout=20)
    assert r.status_code == 200
    b = r.json()["workspace"]["blocks"][0]
    assert b["type"] == "search_results"
    for x in b["props"]["results"]:
        assert set(x.keys()) == {"master_company_id", "name", "sector", "cif", "score"}
