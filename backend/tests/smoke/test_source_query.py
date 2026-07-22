"""Smoke test: generic source query endpoint (Data inspection console).

`GET /api/v1/intelligence/sources/{source}/query` must be 100% dynamic — collection
from META, gated by `META['queryable']`, fields derived from real documents, NO
hardcoded field maps or switches. Numeric values match by equality, strings by
case-insensitive substring.
"""

import requests

from services.intelligence_engine import engine_info


def test_query_returns_fields_from_documents(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/territorial/query?page_size=3", timeout=20)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    for f in ("fields", "items", "total_records", "current_page", "total_pages"):
        assert f in body
    assert isinstance(body["fields"], list) and len(body["fields"]) > 0
    # fields derive from real docs (no hardcode)
    assert "province" in body["fields"] and "year" in body["fields"]


def test_query_numeric_equality_filter(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/territorial/query?field=year&value=2023&page_size=5", timeout=20)
    body = r.json()
    assert body["filter"] == {"field": "year", "value": "2023"}
    assert body["total_records"] > 0
    assert all(it.get("year") == 2023 for it in body["items"]), "Numeric filter returned wrong year"


def test_query_string_substring_filter(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/territorial/query?field=province&value=Barcelona&page_size=5", timeout=20)
    body = r.json()
    assert body["total_records"] > 0
    assert all("barcelona" in (it.get("province") or "").lower() for it in body["items"]), "String filter not case-insensitive substring"


def test_query_sort_order(base_url):
    desc = requests.get(f"{base_url}/api/v1/intelligence/sources/territorial/query?sort_by=average_income&sort_order=desc&page_size=5", timeout=20).json()
    incomes = [it["average_income"] for it in desc["items"] if it.get("average_income") is not None]
    assert incomes == sorted(incomes, reverse=True), "Descending sort not honored"


def test_query_rejects_non_queryable(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/oepm/query", timeout=15)
    assert r.status_code == 400


def test_query_unknown_source_404(base_url):
    r = requests.get(f"{base_url}/api/v1/intelligence/sources/nope/query", timeout=15)
    assert r.status_code == 404


def test_queryable_flag_matches_meta(base_url):
    data = requests.get(f"{base_url}/api/v1/public/intelligence/sync-status", timeout=20).json()
    for name, row in (data.get("sources") or {}).items():
        assert row.get("queryable") == engine_info.get_source_meta(name)["queryable"], f"queryable mismatch '{name}'"
