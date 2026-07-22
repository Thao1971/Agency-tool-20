"""Profiles endpoint must return exactly the 3 known profiles."""
import requests


def test_profiles_endpoint(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/profiles", timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "profiles" in body
    names = {p["name"] for p in body["profiles"]}
    assert names == {"basic", "valuo", "arroba"}, f"Expected exactly basic/valuo/arroba, got {names}"


def test_profile_detail(base_url):
    """Each profile detail endpoint must return its full definition."""
    for name in ("basic", "valuo", "arroba"):
        r = requests.get(f"{base_url}/api/v1/intelligence/profile/{name}", timeout=10)
        assert r.status_code == 200, f"{name}: HTTP {r.status_code}"
        d = r.json()
        assert d["name"] == name
        assert isinstance(d["sources"], list) and len(d["sources"]) >= 1
        assert isinstance(d["description"], str) and len(d["description"]) > 0


def test_unknown_profile_returns_404(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/profile/nonexistent", timeout=10)
    assert r.status_code == 404
