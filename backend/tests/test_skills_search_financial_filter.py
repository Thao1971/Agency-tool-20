"""REQ-004 — Financial/attribute screen in skills/search (pure-function unit tests).

No DB required: exercises _num_screen, _num_clauses, _build_candidate_query,
_passes_filters, _signal_badge, _row_summary. Run: pytest tests/test_skills_search_financial_filter.py
"""
import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")

from services import skills_search as s  # noqa: E402


def _doc(rev=None, eb=None, emp=None, hist=None, prov=None, margin=None):
    latest = {"revenue": rev, "ebitda": eb, "employees": emp}
    if margin is not None:
        latest["ebitda_margin"] = margin
    d = {"financials": {"latest": latest}}
    if hist is not None:
        d["financials"]["history"] = hist
    if prov:
        d["location"] = {"provincia": prov}
    return d


def test_num_screen_detection():
    assert s._num_screen({"revenue_min": 5}) is True
    assert s._num_screen({"province": "Madrid"}) is True
    assert s._num_screen({"category": ["x"]}) is False
    assert s._num_screen({}) is False


def test_num_clauses_dual_shape():
    cl = s._num_clauses({"revenue_min": 50_000_000})
    assert cl == [{"$or": [
        {"financials.latest.revenue": {"$gte": 50_000_000}},
        {"revenue_latest": {"$gte": 50_000_000}},
    ]}]
    cl2 = s._num_clauses({"ebitda_min": 1_000_000, "employees_min": 100, "province": "Valencia"})
    assert {"financials.latest.ebitda": {"$gte": 1_000_000}} in cl2
    assert any("location.provincia" in str(c) for c in cl2)


def test_build_candidate_query_screen_only():
    q = s._build_candidate_query("", has_domain=False, filters={"revenue_min": 50_000_000})
    assert "$and" in q and "$or" not in q and "domain" not in q


def test_build_candidate_query_lexical_plus_numeric():
    q = s._build_candidate_query("agencias", has_domain=True, filters={"revenue_min": 5_000_000})
    assert "$and" in q and len(q["$and"]) == 2
    assert q["domain"] == {"$nin": [None, ""]}


def test_passes_filters_revenue():
    web = {}
    assert s._passes_filters(_doc(rev=60_000_000), web, {"revenue_min": 50_000_000}) is True
    # the screenshot bug: 8k€ company must NOT pass a >50M filter
    assert s._passes_filters(_doc(rev=8_000), web, {"revenue_min": 50_000_000}) is False
    # unknown metric never passes a filter on that metric
    assert s._passes_filters(_doc(rev=None), web, {"revenue_min": 50_000_000}) is False


def test_passes_filters_ebitda_employees_province():
    web = {}
    assert s._passes_filters(_doc(eb=-1), web, {"ebitda_min": 0}) is False
    assert s._passes_filters(_doc(emp=250), web, {"employees_min": 100}) is True
    assert s._passes_filters(_doc(emp=50), web, {"employees_min": 100}) is False
    assert s._passes_filters(_doc(rev=1, prov="Valencia"), web, {"province": "valencia"}) is True
    assert s._passes_filters(_doc(rev=1, prov="Madrid"), web, {"province": "valencia"}) is False


def test_passes_filters_growth_from_history():
    web = {}
    d = _doc(rev=120, hist=[{"revenue": 120}, {"revenue": 100}])
    assert s._passes_filters(d, web, {"growth_min": 0.10}) is True
    assert s._passes_filters(d, web, {"growth_min": 0.30}) is False
    # no history + growth filter → excluded
    assert s._passes_filters(_doc(rev=100), web, {"growth_min": 0.10}) is False


def test_signal_badge():
    assert s._signal_badge(100, 10, 0.1, 0.30) == "alto_crecimiento"
    assert s._signal_badge(100, -5, -0.05, 0.0) == "riesgo"
    assert s._signal_badge(100, 10, 0.1, 0.05) is None


def test_row_summary_shape():
    rs = s._row_summary(_doc(rev=60_000_000, eb=6_000_000, emp=50))
    for k in ("revenue", "ebitda", "ebitda_margin", "growth_pct", "employees",
              "signal_score", "signal_badge", "city", "year"):
        assert k in rs
    assert rs["revenue"] == 60_000_000
    assert rs["ebitda_margin"] == 0.1
