"""Financial math helpers — Deterministic calculations, no AI.

Principle: Financial math calculates. Narrative Engine explains. Never reversed.

NOTE (Fase 2, DOCUMENT_STUDIO_UNIFICATION_PLAN): the pure math here (growth, margins,
percentiles, quartiles, positioning, similarity) is generic and kept. The two DATA
functions (`analyze_sector_benchmark`, `find_comparables`) were reconnected to the
MODERN master (`master_companies`) — they no longer read the legacy `iberinform_*`.
For a company's full financial profile + honest valuation, composers use the real
Financial Intelligence Engine via `docstudio/data_access.py`, not this module.

Capabilities:
  Growth: YoY, CAGR
  Profitability: Gross margin, EBITDA margin, Net margin
  Productivity: Revenue/employee, EBITDA/employee
  Benchmark: Percentiles, quartiles, sector ranking (modern master)
  Comparison: Gap vs market, gap vs category
"""

import math
from typing import Dict, List, Optional, Any


# ══════════════════════════════════════════
# GROWTH
# ══════════════════════════════════════════

def yoy_growth(current: float, previous: float) -> Optional[float]:
    """Year-over-year growth percentage."""
    if not previous or previous == 0:
        return None
    return round(((current - previous) / abs(previous)) * 100, 2)


def cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
    """Compound Annual Growth Rate."""
    if not start_value or start_value <= 0 or not end_value or end_value <= 0 or years <= 0:
        return None
    return round(((end_value / start_value) ** (1 / years) - 1) * 100, 2)


def growth_series(values: List[Dict]) -> List[Dict]:
    """Compute YoY growth for a time series [{period, value}]."""
    sorted_vals = sorted(values, key=lambda x: x.get("period", ""))
    result = []
    for i in range(1, len(sorted_vals)):
        prev = sorted_vals[i - 1]["value"]
        curr = sorted_vals[i]["value"]
        g = yoy_growth(curr, prev)
        result.append({
            "period": sorted_vals[i]["period"],
            "value": curr,
            "previous": prev,
            "yoy_pct": g,
        })
    return result


# ══════════════════════════════════════════
# PROFITABILITY
# ══════════════════════════════════════════

def gross_margin(revenue: float, cogs: float) -> Optional[float]:
    """Gross margin = (Revenue - COGS) / Revenue."""
    if not revenue or revenue == 0:
        return None
    return round(((revenue - cogs) / revenue) * 100, 2)


def ebitda_margin(ebitda: float, revenue: float) -> Optional[float]:
    """EBITDA margin = EBITDA / Revenue."""
    if not revenue or revenue == 0:
        return None
    return round((ebitda / revenue) * 100, 2)


def net_margin(net_income: float, revenue: float) -> Optional[float]:
    """Net margin = Net Income / Revenue."""
    if not revenue or revenue == 0:
        return None
    return round((net_income / revenue) * 100, 2)


# ══════════════════════════════════════════
# PRODUCTIVITY
# ══════════════════════════════════════════

def revenue_per_employee(revenue: float, employees: int) -> Optional[float]:
    """Revenue per employee."""
    if not employees or employees == 0:
        return None
    return round(revenue / employees, 2)


def ebitda_per_employee(ebitda: float, employees: int) -> Optional[float]:
    """EBITDA per employee."""
    if not employees or employees == 0:
        return None
    return round(ebitda / employees, 2)


# ══════════════════════════════════════════
# VALUATION MULTIPLES
# ══════════════════════════════════════════

def ev_revenue(enterprise_value: float, revenue: float) -> Optional[float]:
    """EV / Revenue multiple."""
    if not revenue or revenue == 0:
        return None
    return round(enterprise_value / revenue, 2)


def ev_ebitda(enterprise_value: float, ebitda: float) -> Optional[float]:
    """EV / EBITDA multiple."""
    if not ebitda or ebitda == 0:
        return None
    return round(enterprise_value / ebitda, 2)


def implied_ev_from_multiple(metric_value: float, multiple: float) -> Optional[float]:
    """Calculate implied EV from a metric and multiple."""
    if not metric_value or not multiple:
        return None
    return round(metric_value * multiple, 2)


# ══════════════════════════════════════════
# BENCHMARK (Percentiles, Quartiles, Ranking)
# ══════════════════════════════════════════

def percentile(values: List[float], p: float) -> Optional[float]:
    """Calculate p-th percentile (0-100)."""
    if not values:
        return None
    sorted_v = sorted(values)
    n = len(sorted_v)
    k = (p / 100) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_v[int(k)], 2)
    return round(sorted_v[f] * (c - k) + sorted_v[c] * (k - f), 2)


def quartiles(values: List[float]) -> Dict:
    """Calculate Q1, Q2 (median), Q3."""
    if not values:
        return {}
    return {
        "q1": percentile(values, 25),
        "median": percentile(values, 50),
        "q3": percentile(values, 75),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "count": len(values),
    }


def rank_in_sector(value: float, all_values: List[float], ascending: bool = False) -> Dict:
    """Rank a value within a set of sector values."""
    if not all_values:
        return {}
    sorted_v = sorted(all_values, reverse=not ascending)
    try:
        position = sorted_v.index(value) + 1
    except ValueError:
        # Find closest
        sorted_with_target = sorted(all_values + [value], reverse=not ascending)
        position = sorted_with_target.index(value) + 1

    total = len(all_values)
    pct = round((1 - (position - 1) / max(total - 1, 1)) * 100, 1)

    return {
        "rank": position,
        "total": total,
        "percentile": pct,
        "label": f"{position}/{total}",
    }


# ══════════════════════════════════════════
# COMPARISON (Gap analysis)
# ══════════════════════════════════════════

def gap_vs_benchmark(value: float, benchmark: float) -> Dict:
    """Calculate gap between a value and a benchmark."""
    if benchmark is None or benchmark == 0:
        return {"gap_absolute": None, "gap_pct": None}
    gap_abs = round(value - benchmark, 2)
    gap_pct = round(((value - benchmark) / abs(benchmark)) * 100, 2)
    return {
        "value": value,
        "benchmark": benchmark,
        "gap_absolute": gap_abs,
        "gap_pct": gap_pct,
        "position": "above" if gap_abs > 0 else "below" if gap_abs < 0 else "equal",
    }


def sector_comparison(company_metrics: Dict, sector_metrics: List[Dict]) -> Dict:
    """Compare a company against its sector peers across multiple metrics."""
    result = {}
    for metric_name, company_value in company_metrics.items():
        if company_value is None:
            continue
        peer_values = [p.get(metric_name) for p in sector_metrics if p.get(metric_name) is not None]
        if not peer_values:
            continue

        q = quartiles(peer_values)
        ranking = rank_in_sector(company_value, peer_values)
        gap_median = gap_vs_benchmark(company_value, q.get("median", 0))

        result[metric_name] = {
            "company_value": company_value,
            "sector_quartiles": q,
            "ranking": ranking,
            "gap_vs_median": gap_median,
        }
    return result


# ══════════════════════════════════════════
# FULL COMPANY ANALYSIS
# ══════════════════════════════════════════

def analyze_company_financials(financials: List[Dict]) -> Dict:
    """Run full financial analysis on a company's time series.
    
    Input: [{year, revenue, ebitda, net_income, employees, total_assets, equity}]
    Output: Complete analysis with all metrics.
    """
    if not financials:
        return {}

    sorted_fin = sorted(financials, key=lambda x: x.get("year", 0))
    latest = sorted_fin[-1]

    result = {"latest_year": latest.get("year")}

    # Growth
    if len(sorted_fin) >= 2:
        prev = sorted_fin[-2]
        result["revenue_yoy"] = yoy_growth(latest.get("revenue", 0), prev.get("revenue", 0))
        result["ebitda_yoy"] = yoy_growth(latest.get("ebitda", 0), prev.get("ebitda", 0))
        result["employee_yoy"] = yoy_growth(latest.get("employees", 0), prev.get("employees", 0))

    if len(sorted_fin) >= 4:
        first = sorted_fin[0]
        years = latest.get("year", 0) - first.get("year", 0)
        if years > 0:
            result["revenue_cagr"] = cagr(first.get("revenue", 0), latest.get("revenue", 0), years)

    # Profitability
    rev = latest.get("revenue", 0)
    result["ebitda_margin"] = ebitda_margin(latest.get("ebitda", 0), rev)
    result["net_margin"] = net_margin(latest.get("net_income", 0), rev)

    # Productivity
    emp = latest.get("employees", 0)
    result["revenue_per_employee"] = revenue_per_employee(rev, emp)
    result["ebitda_per_employee"] = ebitda_per_employee(latest.get("ebitda", 0), emp)

    # Revenue series
    result["revenue_series"] = growth_series([
        {"period": str(f.get("year", "")), "value": f.get("revenue", 0)}
        for f in sorted_fin if f.get("revenue")
    ])

    return result


async def analyze_sector_benchmark(cnae_code: str) -> Dict:
    """Sector-level benchmark over the MODERN master (`master_companies`).

    Fase 2: reads `master_companies` (classification.cnae_code + financials.latest +
    size), NOT the legacy `iberinform_companies`. Same return shape as before so
    consumers (composers + /financial/sector-benchmark route) are unaffected.
    """
    from database import db

    companies = []
    async for m in db.master_companies.find(
        {"classification.cnae_code": cnae_code},
        {"_id": 0, "financials.latest": 1, "size.employees_total": 1},
    ):
        fl = (m.get("financials") or {}).get("latest") or {}
        companies.append({
            "revenue": fl.get("revenue"),
            "ebitda": fl.get("ebitda"),
            "ebitda_margin": fl.get("ebitda_margin"),
            "employees": (m.get("size") or {}).get("employees_total"),
        })

    if not companies:
        return {"cnae_code": cnae_code, "peers": 0}

    revenues = [c["revenue"] for c in companies if c.get("revenue") and c["revenue"] > 0]
    ebitdas = [c["ebitda"] for c in companies if c.get("ebitda") and c["ebitda"] > 0]
    margins = [c["ebitda_margin"] for c in companies if c.get("ebitda_margin") is not None]
    emps = [c["employees"] for c in companies if c.get("employees") and c["employees"] > 0]
    rev_per_emp = [c["revenue"] / c["employees"] for c in companies
                   if c.get("revenue") and c.get("employees") and c["employees"] > 0]

    return {
        "cnae_code": cnae_code,
        "peers": len(companies),
        "revenue": quartiles(revenues),
        "ebitda": quartiles(ebitdas),
        "ebitda_margin": quartiles(margins),
        "employees": quartiles(emps),
        "revenue_per_employee": quartiles(rev_per_emp),
    }


def similarity_score(target: Dict, candidate: Dict) -> float:
    """Compute similarity score between two companies (0-100). Deterministic."""
    score = 0
    weights = {"revenue": 0.35, "ebitda": 0.25, "employees": 0.25, "ebitda_margin": 0.15}
    total_weight = 0

    for metric, weight in weights.items():
        t_val = target.get(metric)
        c_val = candidate.get(metric)
        if t_val is None or c_val is None or t_val == 0:
            continue

        # Ratio-based similarity: 1.0 = identical, 0.0 = very different
        ratio = min(t_val, c_val) / max(t_val, c_val) if max(t_val, c_val) > 0 else 0
        score += ratio * weight * 100
        total_weight += weight

    return round(score / total_weight, 1) if total_weight > 0 else 0


async def find_comparables(identifier: str, cnae_code: str, limit: int = 5) -> List[Dict]:
    """Most similar companies in the same CNAE, over the MODERN master. Deterministic.

    Fase 2: `identifier` is a master_id (or cif); peers come from `master_companies`
    (classification.cnae_code + financials.latest), NOT legacy iberinform. Same output
    shape (legal_name, province, revenue, ebitda, employees, ebitda_margin, similarity).
    """
    from database import db

    target_m = await db.master_companies.find_one(
        {"$or": [{"master_id": identifier}, {"cif_normalized": identifier}]},
        {"_id": 0, "master_id": 1, "financials.latest": 1, "size.employees_total": 1},
    )
    if not target_m:
        return []
    tfl = (target_m.get("financials") or {}).get("latest") or {}
    target = {
        "revenue": tfl.get("revenue") or 0,
        "ebitda": tfl.get("ebitda") or 0,
        "employees": (target_m.get("size") or {}).get("employees_total") or 0,
        "ebitda_margin": tfl.get("ebitda_margin") or 0,
    }
    target_id = target_m["master_id"]

    scored = []
    async for p in db.master_companies.find(
        {"classification.cnae_code": cnae_code, "master_id": {"$ne": target_id}},
        {"_id": 0, "master_id": 1, "identity.legal_name": 1, "location.provincia": 1,
         "financials.latest": 1, "size.employees_total": 1},
    ):
        fl = (p.get("financials") or {}).get("latest") or {}
        peer = {
            "revenue": fl.get("revenue"), "ebitda": fl.get("ebitda"),
            "ebitda_margin": fl.get("ebitda_margin"),
            "employees": (p.get("size") or {}).get("employees_total"),
        }
        sim = similarity_score(target, peer)
        if sim > 20:
            scored.append({
                "company_id": p["master_id"],
                "legal_name": (p.get("identity") or {}).get("legal_name", ""),
                "province": (p.get("location") or {}).get("provincia", ""),
                "revenue": peer["revenue"], "ebitda": peer["ebitda"],
                "employees": peer["employees"], "ebitda_margin": peer["ebitda_margin"],
                "similarity": sim,
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def compute_sector_positioning(company_metrics: Dict, benchmark: Dict) -> Dict:
    """Compute percentile positioning for a company vs sector. Deterministic."""
    positioning = {}

    for metric, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"),
                          ("employees", "Empleados"), ("ebitda_margin", "Margen EBITDA")]:
        comp_val = company_metrics.get(metric)
        q = benchmark.get(metric, {})
        if comp_val is None or not q or q.get("median") is None:
            continue

        median = q["median"]
        q1 = q.get("q1", median)
        q3 = q.get("q3", median)
        mn = q.get("min", q1)
        mx = q.get("max", q3)

        # Estimate percentile position
        if mx == mn:
            pct = 50
        elif comp_val <= mn:
            pct = 0
        elif comp_val >= mx:
            pct = 100
        elif comp_val <= q1:
            pct = 25 * (comp_val - mn) / max(q1 - mn, 1)
        elif comp_val <= median:
            pct = 25 + 25 * (comp_val - q1) / max(median - q1, 1)
        elif comp_val <= q3:
            pct = 50 + 25 * (comp_val - median) / max(q3 - median, 1)
        else:
            pct = 75 + 25 * (comp_val - q3) / max(mx - q3, 1)

        positioning[metric] = {
            "label": label,
            "value": comp_val,
            "percentile": round(pct, 1),
            "median": median,
            "q1": q1,
            "q3": q3,
            "gap_vs_median_pct": round(((comp_val - median) / abs(median)) * 100, 1) if median else None,
            "position": "top_quartile" if pct >= 75 else "above_median" if pct >= 50 else "below_median" if pct >= 25 else "bottom_quartile",
        }

    return positioning
