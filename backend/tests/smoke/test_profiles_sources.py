"""Profile size invariant: basic < valuo < arroba."""
import requests


def test_profiles_size_hierarchy(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/profiles", timeout=10)
    assert r.status_code == 200
    by_name = {p["name"]: p for p in r.json()["profiles"]}

    n_basic = len(by_name["basic"]["sources"])
    n_valuo = len(by_name["valuo"]["sources"])
    n_arroba = len(by_name["arroba"]["sources"])

    assert n_basic < n_valuo < n_arroba, (
        f"Profile hierarchy violated: basic={n_basic} valuo={n_valuo} arroba={n_arroba}"
    )


def test_valuo_includes_basic_sources(base_url):
    """Valuo profile must extend basic (basic.sources ⊆ valuo.sources)."""
    r = requests.get(f"{base_url}/api/v1/intelligence/profiles", timeout=10)
    by_name = {p["name"]: set(p["sources"]) for p in r.json()["profiles"]}
    assert by_name["basic"].issubset(by_name["valuo"])


def test_arroba_includes_valuo_sources(base_url):
    """Arroba profile must extend valuo (valuo.sources ⊆ arroba.sources)."""
    r = requests.get(f"{base_url}/api/v1/intelligence/profiles", timeout=10)
    by_name = {p["name"]: set(p["sources"]) for p in r.json()["profiles"]}
    assert by_name["valuo"].issubset(by_name["arroba"])
