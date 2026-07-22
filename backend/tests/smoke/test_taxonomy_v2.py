"""Smoke tests — Taxonomy Governance Engine v2 (weighted semantic mapping)."""
import requests

PREFIX = "/api/v1/taxonomy-intelligence"


def _auth(base_url, token, path, **kw):
    return requests.get(f"{base_url}{PREFIX}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30, **kw)


def test_resolve_is_public_and_weighted(base_url):
    """Public resolve returns weighted multi-mapping; weights sum to ~1.0."""
    r = requests.get(f"{base_url}{PREFIX}/resolve/taric/27", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["orphan"] is False
    assert len(data["mappings"]) >= 2  # TARIC 27 maps to multiple CNAEs
    for m in data["mappings"]:
        assert "weight" in m and "confidence_score" in m and "origin" in m
    wsum = sum(m["weight"] for m in data["mappings"])
    assert abs(wsum - 1.0) <= 0.02, f"weights must sum to 1.0, got {wsum}"


def test_resolve_never_returns_none_for_orphan(base_url):
    """Unknown code is explicitly flagged orphan, never None/error."""
    r = requests.get(f"{base_url}{PREFIX}/resolve/taric/ZZZ", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["orphan"] is True
    assert data["mappings"] == []


def test_health_verdict(base_url, auth_token):
    r = _auth(base_url, auth_token, "/health")
    assert r.status_code == 200, r.text
    h = r.json()
    assert h["verdict"] in ("healthy", "degraded", "critical")
    assert h["total_mappings"] > 0
    assert h["active"] > 0
    assert h["weight_integrity_pct"] >= 95  # weights normalized on startup
    # No human-approval statuses should leak
    assert "pending_review" not in str(h)
    assert "auto_approved" not in str(h)


def test_coverage_known_universe(base_url, auth_token):
    r = _auth(base_url, auth_token, "/coverage")
    assert r.status_code == 200, r.text
    cov = {c["taxonomy"]: c for c in r.json()["coverage"]}
    assert "taric" in cov and cov["taric"]["universe_known"] is True
    assert cov["taric"]["coverage_pct"] >= 90
    assert cov["taric"]["weight_integrity_pct"] >= 95


def test_orphans_no_data_loss(base_url, auth_token):
    """No TARIC code present in real trade data should be orphan (zero signal loss)."""
    r = _auth(base_url, auth_token, "/orphans", params={"limit": 1000})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "orphans" in data and "with_data_loss" in data
    assert data["with_data_loss"] == 0, f"signal loss detected: {data['with_data_loss']} codes"


def test_inconsistencies_structure(base_url, auth_token):
    r = _auth(base_url, auth_token, "/inconsistencies")
    assert r.status_code == 200, r.text
    d = r.json()
    for key in ("weight_breaches", "weak_mappings", "conflicts"):
        assert key in d and "total" in d[key] and "items" in d[key]
    assert d["weight_breaches"]["total"] == 0  # integrity holds after normalization


def test_mappings_use_v2_schema(base_url, auth_token):
    r = _auth(base_url, auth_token, "/all", params={"taxonomy": "taric", "limit": 50})
    assert r.status_code == 200, r.text
    items = r.json()["mappings"]
    assert items
    m = items[0]
    assert "confidence_score" in m and "weight" in m and "origin" in m
    assert m["status"] in ("active", "inactive")
    assert "confidence" not in m  # legacy field removed
