"""Backend tests for Intel batch (Daniel, 2026-09-09):
- PUNTO 1: deterministic tie-break in pagination (no dup/gaps)
- PUNTO 2: optional sort_by / sort_dir in skills/search and company-taxonomy/search
- PUNTO 3: new public predictive search GET /api/v1/companies/suggest
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api/v1"
API_KEY = os.environ["ARROBA_SERVICE_API_KEY"]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _extract_search_block(payload):
    for b in payload.get("workspace", {}).get("blocks", []):
        if b.get("type") == "search_results":
            return b.get("props", {})
    return {}


# ============================================================
# PUNTO 3 - GET /companies/suggest (público)
# ============================================================

def test_suggest_empty_query(session):
    r = session.get(f"{API}/companies/suggest", params={"q": ""}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json() == {"results": []}


def test_suggest_single_char(session):
    r = session.get(f"{API}/companies/suggest", params={"q": "b"}, timeout=30)
    assert r.status_code == 200
    assert r.json() == {"results": []}


def test_suggest_prefix_match_ba(session):
    r = session.get(f"{API}/companies/suggest", params={"q": "ba", "limit": 8}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "results" in data
    results = data["results"]
    assert len(results) > 0, "expected some results for prefix 'ba'"
    for item in results:
        # each item has required keys
        assert set(["master_company_id", "name", "cif", "sector"]).issubset(item.keys()), item
        # prefix match: name should start with 'ba' (case/diacritic insensitive)
        name_norm = item["name"].lower()
        # strip common diacritics
        import unicodedata
        name_norm = "".join(c for c in unicodedata.normalize("NFD", name_norm) if unicodedata.category(c) != "Mn")
        assert name_norm.startswith("ba"), f"Not a prefix match: {item['name']!r}"


def test_suggest_diacritic_insensitive(session):
    r1 = session.get(f"{API}/companies/suggest", params={"q": "telefon", "limit": 20}, timeout=30)
    r2 = session.get(f"{API}/companies/suggest", params={"q": "téléfon", "limit": 20}, timeout=30)
    assert r1.status_code == 200 and r2.status_code == 200
    names1 = [x["name"].upper() for x in r1.json()["results"]]
    names2 = [x["name"].upper() for x in r2.json()["results"]]
    print(f"telefon -> {names1[:5]}")
    print(f"téléfon -> {names2[:5]}")
    assert any("TELEFON" in n for n in names1), f"expected TELEFON* in {names1}"
    assert any("TELEFON" in n for n in names2), f"expected TELEFON* in {names2}"


def test_suggest_limit_caps_at_20(session):
    r = session.get(f"{API}/companies/suggest", params={"q": "a", "limit": 100}, timeout=30)
    # single char returns []; use 2-char prefix that is common
    if r.json().get("results") == []:
        r = session.get(f"{API}/companies/suggest", params={"q": "co", "limit": 100}, timeout=30)
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) <= 20, f"limit should cap at 20, got {len(results)}"


def test_suggest_order_by_revenue_desc(session):
    r = session.get(f"{API}/companies/suggest", params={"q": "te", "limit": 20}, timeout=30)
    assert r.status_code == 200
    results = r.json()["results"]
    # Can't directly assert revenue since not in payload, but at minimum order stability
    # Re-request and confirm same order (deterministic)
    r2 = session.get(f"{API}/companies/suggest", params={"q": "te", "limit": 20}, timeout=30)
    ids1 = [x["master_company_id"] for x in results]
    ids2 = [x["master_company_id"] for x in r2.json()["results"]]
    assert ids1 == ids2, "suggest order not deterministic"


# ============================================================
# PUNTO 2 - skills/search sort_by / sort_dir
# ============================================================

def _skills_search(session, sort_by=None, sort_dir=None, page=1, page_size=6):
    body = {
        "filters": {"has_domain": False},
        "pagination": {"page": page, "page_size": page_size},
    }
    if sort_by is not None:
        body["sort_by"] = sort_by
    if sort_dir is not None:
        body["sort_dir"] = sort_dir
    return session.post(f"{API}/skills/search", json=body, timeout=90)


def _names(results):
    out = []
    for r in results:
        n = r.get("name") or r.get("company_name") or r.get("summary", {}).get("name")
        out.append(n)
    return out


def _revenues(results):
    out = []
    for r in results:
        rev = None
        for path in [("summary", "revenue"), ("financials", "revenue"), ("revenue",)]:
            cur = r
            ok = True
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, (int, float)):
                rev = cur
                break
        out.append(rev)
    return out


def test_skills_sort_by_name_asc(session):
    r = _skills_search(session, sort_by="name", sort_dir="asc")
    assert r.status_code == 200, r.text[:400]
    props = _extract_search_block(r.json())
    results = props.get("results", [])
    assert len(results) > 0
    names = _names(results)
    names_norm = [n.lower() if n else "" for n in names]
    assert names_norm == sorted(names_norm), f"not sorted asc: {names_norm}"


def test_skills_sort_by_revenue_desc(session):
    r = _skills_search(session, sort_by="revenue", sort_dir="desc")
    assert r.status_code == 200, r.text[:400]
    props = _extract_search_block(r.json())
    results = props.get("results", [])
    assert len(results) > 0
    revs = _revenues(results)
    non_null = [r for r in revs if r is not None]
    print(f"revenues desc sample: {non_null[:10]}")
    assert non_null == sorted(non_null, reverse=True), f"not sorted desc: {non_null}"


def test_skills_sort_by_invalid_falls_back(session):
    r_bad = _skills_search(session, sort_by="DROP TABLE", sort_dir="asc")
    assert r_bad.status_code == 200, f"invalid sort should not 500: {r_bad.status_code} {r_bad.text[:300]}"
    r_bad2 = _skills_search(session, sort_by="foo", sort_dir="asc")
    assert r_bad2.status_code == 200
    # Compare to no-sort baseline
    r_base = _skills_search(session)
    assert r_base.status_code == 200
    ids_bad = [x.get("master_company_id") for x in _extract_search_block(r_bad.json()).get("results", [])]
    ids_base = [x.get("master_company_id") for x in _extract_search_block(r_base.json()).get("results", [])]
    assert ids_bad == ids_base, "invalid sort_by should fall back to relevance order"


def test_skills_no_sort_backwards_compatible(session):
    r = _skills_search(session)
    assert r.status_code == 200
    props = _extract_search_block(r.json())
    assert "results" in props and "total" in props


# ============================================================
# PUNTO 2 - company-taxonomy/search sort_by / sort_dir
# ============================================================

def _taxo_search(session, sort_by=None, sort_dir=None, offset=0, limit=5):
    params = {"node_id": "S09", "primary_only": "true", "offset": offset, "limit": limit}
    if sort_by:
        params["sort_by"] = sort_by
    if sort_dir:
        params["sort_dir"] = sort_dir
    return session.get(
        f"{API}/company-taxonomy/search",
        params=params,
        headers={"X-API-Key": API_KEY},
        timeout=90,
    )


def test_taxonomy_sort_by_name_asc(session):
    r = _taxo_search(session, sort_by="name", sort_dir="asc", limit=10)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    results = data.get("results") or data.get("items") or []
    assert len(results) > 0, f"no results: {data.keys()}"
    names = []
    for it in results:
        n = it.get("name") or it.get("company_name") or (it.get("master", {}) or {}).get("name")
        names.append((n or "").lower())
    print(f"taxonomy name asc sample: {names[:5]}")
    assert names == sorted(names), f"taxonomy name asc not sorted: {names}"
    # count should be large (~8458)
    count = data.get("count") or data.get("total")
    assert count and count > 1000, f"count too small: {count}"


def test_taxonomy_sort_by_revenue_desc(session):
    r = _taxo_search(session, sort_by="revenue", sort_dir="desc", limit=10)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    results = data.get("results") or data.get("items") or []
    assert len(results) > 0
    revs = []
    for it in results:
        r_val = None
        for path in [("revenue",), ("financials", "revenue"), ("master", "revenue"),
                     ("summary", "revenue"), ("financials", "latest", "revenue")]:
            cur = it
            ok = True
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, (int, float)):
                r_val = cur
                break
        revs.append(r_val)
    non_null = [x for x in revs if x is not None]
    print(f"taxonomy rev desc sample: {non_null[:10]}")
    assert non_null == sorted(non_null, reverse=True), f"not sorted desc: {non_null}"


def test_taxonomy_no_sort_backwards_compatible(session):
    r = _taxo_search(session, limit=5)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    count = data.get("count") or data.get("total")
    assert count and count > 1000, f"expected large S09 count, got {count}"


# ============================================================
# PUNTO 1 - deterministic pagination (no overlap, stable)
# ============================================================

def _get_ids(results):
    return [r.get("master_company_id") for r in results if r.get("master_company_id")]


def test_skills_pagination_no_overlap_sort_name(session):
    r1 = _skills_search(session, sort_by="name", sort_dir="asc", page=1, page_size=5)
    r2 = _skills_search(session, sort_by="name", sort_dir="asc", page=2, page_size=5)
    assert r1.status_code == 200 and r2.status_code == 200
    ids1 = _get_ids(_extract_search_block(r1.json()).get("results", []))
    ids2 = _get_ids(_extract_search_block(r2.json()).get("results", []))
    assert len(ids1) > 0 and len(ids2) > 0
    overlap = set(ids1) & set(ids2)
    assert not overlap, f"overlap between page1 and page2: {overlap}"
    # last of page1 <= first of page2 by name
    names1 = _names(_extract_search_block(r1.json()).get("results", []))
    names2 = _names(_extract_search_block(r2.json()).get("results", []))
    if names1 and names2 and names1[-1] and names2[0]:
        assert names1[-1].lower() <= names2[0].lower(), f"{names1[-1]} > {names2[0]}"


def test_skills_pagination_stable(session):
    r_a = _skills_search(session, sort_by="name", sort_dir="asc", page=1, page_size=5)
    r_b = _skills_search(session, sort_by="name", sort_dir="asc", page=1, page_size=5)
    ids_a = _get_ids(_extract_search_block(r_a.json()).get("results", []))
    ids_b = _get_ids(_extract_search_block(r_b.json()).get("results", []))
    assert ids_a == ids_b, f"unstable order: {ids_a} vs {ids_b}"


def _taxo_ids(data):
    results = data.get("results") or data.get("items") or []
    out = []
    for it in results:
        mid = it.get("master_company_id") or it.get("master_id") or (it.get("master") or {}).get("id")
        if mid:
            out.append(mid)
    return out


def test_taxonomy_pagination_no_overlap_sort_name(session):
    r1 = _taxo_search(session, sort_by="name", sort_dir="asc", offset=0, limit=5)
    r2 = _taxo_search(session, sort_by="name", sort_dir="asc", offset=5, limit=5)
    assert r1.status_code == 200 and r2.status_code == 200
    ids1 = _taxo_ids(r1.json())
    ids2 = _taxo_ids(r2.json())
    assert len(ids1) > 0 and len(ids2) > 0, f"no ids extracted: {ids1} / {ids2}"
    overlap = set(ids1) & set(ids2)
    assert not overlap, f"taxonomy overlap: {overlap}"


def test_taxonomy_pagination_stable(session):
    r_a = _taxo_search(session, sort_by="name", sort_dir="asc", offset=0, limit=5)
    r_b = _taxo_search(session, sort_by="name", sort_dir="asc", offset=0, limit=5)
    ids_a = _taxo_ids(r_a.json())
    ids_b = _taxo_ids(r_b.json())
    assert ids_a == ids_b, f"taxonomy unstable: {ids_a} vs {ids_b}"
