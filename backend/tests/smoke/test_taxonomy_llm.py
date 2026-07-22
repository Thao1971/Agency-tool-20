"""Smoke tests — Semantic Mapping Engine v2, Fase B (LLM Assisted Mapping).

Deterministic MetaScore/threshold logic is tested via direct imports; endpoint wiring
and the auto-learn invariants are tested over HTTP. The live GPT call is only triggered
when no suggestions exist yet (keeps the suite fast/cheap and avoids flakiness).
"""
import requests
from services.taxonomy_llm import (
    _metascore, _semantic_similarity,
    W_SEMANTIC, W_FREQUENCY, W_HISTORICAL, W_SECTOR, W_GPT,
    AUTO_ACCEPT_METASCORE, CANDIDATE_METASCORE,
)

PREFIX = "/api/v1/taxonomy-intelligence"


def _auth(base_url, token, path, **kw):
    return requests.get(f"{base_url}{PREFIX}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=60, **kw)


# ── Deterministic MetaScore logic ───────────────────────────────────────────

def test_metascore_weights_sum_to_one():
    assert abs((W_SEMANTIC + W_FREQUENCY + W_HISTORICAL + W_SECTOR + W_GPT) - 1.0) < 1e-9


def test_metascore_math_and_gpt_is_minority():
    assert _metascore(1, 1, 1, 1, 1) == 1.0
    assert _metascore(0, 0, 0, 0, 0) == 0.0
    # GPT alone contributes only its 10% weight (LLM is never the source of truth)
    assert abs(_metascore(0, 0, 0, 0, 1.0) - W_GPT) < 1e-6
    # exact blend
    assert abs(_metascore(0.5, 0.4, 1.0, 0.8, 0.9)
               - (0.40 * 0.5 + 0.25 * 0.4 + 0.15 * 1.0 + 0.10 * 0.8 + 0.10 * 0.9)) < 1e-6


def test_threshold_bands():
    assert AUTO_ACCEPT_METASCORE == 0.90
    assert CANDIDATE_METASCORE == 0.70
    # a perfect mapping auto-accepts; a mediocre one is rejected
    assert _metascore(1, 1, 1, 1, 1) >= AUTO_ACCEPT_METASCORE
    assert _metascore(0.1, 0.1, 0.5, 0.2, 0.3) < CANDIDATE_METASCORE


def test_semantic_similarity_prefers_related():
    related = _semantic_similarity("Pescados, crustaceos, moluscos", "Pesca y acuicultura")
    unrelated = _semantic_similarity("Pescados, crustaceos, moluscos", "Telecomunicaciones")
    assert related > unrelated
    assert 0.0 <= related <= 1.0


# ── Endpoint wiring ──────────────────────────────────────────────────────────

def test_suggest_loop_end_to_end(base_url, auth_token):
    """Trigger the loop only if no suggestions exist yet; validate the summary invariant."""
    stats = _auth(base_url, auth_token, "/suggestions/stats").json()
    if (stats["auto_accepted"] + stats["pending_candidates"] + stats.get("rejected", 0)) == 0:
        r = requests.post(
            f"{base_url}{PREFIX}/suggest?scope=orphans&limit=1",
            headers={"Authorization": f"Bearer {auth_token}"}, timeout=180,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("scope", "codes_processed", "suggestions_generated", "auto_accepted", "candidates", "rejected"):
            assert k in d
        assert d["suggestions_generated"] == d["auto_accepted"] + d["candidates"] + d["rejected"]


def test_suggestions_endpoints_structure(base_url, auth_token):
    for path in ("/suggestions", "/suggestions/weak", "/suggestions/orphans"):
        r = _auth(base_url, auth_token, path)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "suggestions" in body and "count" in body
        for s in body["suggestions"][:3]:
            assert "metascore" in s and "suggested_cnae" in s and s["origin"] == "llm"
            assert s["status"] in ("candidate", "accepted", "rejected")
            assert "semantic_similarity" in s and "gpt_confidence_score" in s


def test_suggestions_stats_shape(base_url, auth_token):
    r = _auth(base_url, auth_token, "/suggestions/stats")
    assert r.status_code == 200
    d = r.json()
    for k in ("llm_candidates", "auto_accepted", "pending_candidates", "average_metascore"):
        assert k in d


def test_health_includes_llm_signals(base_url, auth_token):
    r = _auth(base_url, auth_token, "/health")
    assert r.status_code == 200
    d = r.json()
    for k in ("llm_candidates", "auto_accepted", "pending_candidates", "average_metascore"):
        assert k in d


def test_no_signal_loss_preserved(base_url):
    """Fase B must not break the Fase A no-None guarantee."""
    r = requests.get(f"{base_url}{PREFIX}/resolve/taric/ZZZ", timeout=20)
    assert r.status_code == 200
    assert r.json()["orphan"] is True


def test_auto_accepted_suggestions_become_active_llm_mappings(base_url, auth_token):
    """Any accepted suggestion must have produced an active mapping with origin=llm."""
    stats = _auth(base_url, auth_token, "/suggestions/stats").json()
    if stats["auto_accepted"] > 0:
        accepted = _auth(base_url, auth_token, "/suggestions", params={"status": "accepted"}).json()["suggestions"]
        allm = _auth(base_url, auth_token, "/all", params={"limit": 2000}).json()["mappings"]
        llm_pairs = {(m["source_taxonomy"], m["source_code"], m["cnae_code"])
                     for m in allm if m.get("origin") == "llm" and m["status"] == "active"}
        for s in accepted:
            assert (s["source_taxonomy"], s["source_code"], s["suggested_cnae"]) in llm_pairs
