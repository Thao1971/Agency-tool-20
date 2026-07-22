"""Engine identity & capabilities endpoints.

Used by Valuo/arroba for audit, smoke tests for post-deploy verification,
and support to answer 'what version is in production?'.
"""
import requests


REQUIRED_VERSION_KEYS = {
    "engine_name", "engine_version", "build_timestamp", "git_commit",
    "environment", "profiles", "sources", "health",
}

REQUIRED_PROFILES = {"basic", "valuo", "arroba"}
REQUIRED_MODULES = {"lineage", "cache", "queue", "enrichment", "matching"}


def test_engine_version_endpoint(base_url):
    r = requests.get(f"{base_url}/api/v1/engine/version", timeout=10)
    assert r.status_code == 200, r.text[:200]
    d = r.json()

    missing = REQUIRED_VERSION_KEYS - set(d.keys())
    assert not missing, f"Missing version keys: {missing}"

    assert d["engine_name"] == "Intelligence Engine"
    assert isinstance(d["engine_version"], str) and len(d["engine_version"]) > 0
    assert isinstance(d["git_commit"], str) and len(d["git_commit"]) > 0
    assert isinstance(d["build_timestamp"], str) and "T" in d["build_timestamp"]
    assert d["environment"] in {"production", "preview", "staging", "development"}
    assert set(d["profiles"]) == REQUIRED_PROFILES
    assert isinstance(d["sources"], list) and len(d["sources"]) >= 5
    assert d["health"] in {"healthy", "busy", "degraded", "unknown"}


def test_engine_capabilities_endpoint(base_url):
    r = requests.get(f"{base_url}/api/v1/engine/capabilities", timeout=10)
    assert r.status_code == 200, r.text[:200]
    d = r.json()

    assert set(d["profiles"]) == REQUIRED_PROFILES
    assert isinstance(d["sources"], list) and len(d["sources"]) >= 5
    # Modules must include the 5 canonical transversal capabilities
    assert REQUIRED_MODULES.issubset(set(d["modules"])), (
        f"Missing modules: {REQUIRED_MODULES - set(d['modules'])}"
    )
