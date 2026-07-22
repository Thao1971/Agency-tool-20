"""Financial metrics extraction + normalized statements (from the Data Layer).

The engine is the boundary: it reads norm_financials (statement detail) + master_companies
(canonical summary). Consumers never read those directly. Verified Iberinform Valu8 codes.
"""

from typing import Dict, List, Optional

# Iberinform Valu8 account codes → canonical line.
CODES = {
    "revenue": "40100", "operating_income": "49100", "depreciation": "40800",
    "net_income": "49500", "supplies": "40400", "personnel_costs": "40600",
    "financial_expenses": "41500",
    "total_assets": "10000", "equity": "20000",
    "non_current_assets": "11000", "current_assets": "12000", "cash": "12700",
    "non_current_liabilities": "31000", "current_liabilities": "32000",
    "lt_debt": "31200", "st_debt": "32300",
}


def _g(acc: Dict, key: str) -> Optional[float]:
    return acc.get(CODES[key])


def _year_metrics(acc: Dict) -> Dict[str, Optional[float]]:
    """Canonical figures for one fiscal year from its account map."""
    op = _g(acc, "operating_income")
    dep = _g(acc, "depreciation")
    ebitda = round(op + abs(dep), 2) if (op is not None and dep is not None) else None
    lt, st = _g(acc, "lt_debt"), _g(acc, "st_debt")
    fin_debt = None
    if lt is not None or st is not None:
        fin_debt = round((lt or 0) + (st or 0), 2)
    eq, ta = _g(acc, "equity"), _g(acc, "total_assets")
    total_liabilities = round(ta - eq, 2) if (ta is not None and eq is not None) else None
    return {
        "revenue": _g(acc, "revenue"), "supplies": _g(acc, "supplies"),
        "personnel_costs": _g(acc, "personnel_costs"),
        "operating_income": op, "ebit": op, "depreciation": dep, "ebitda": ebitda,
        "financial_expenses": _g(acc, "financial_expenses"), "net_income": _g(acc, "net_income"),
        "total_assets": ta, "equity": eq,
        "non_current_assets": _g(acc, "non_current_assets"),
        "current_assets": _g(acc, "current_assets"), "cash": _g(acc, "cash"),
        "non_current_liabilities": _g(acc, "non_current_liabilities"),
        "current_liabilities": _g(acc, "current_liabilities"),
        "financial_debt": fin_debt, "total_liabilities": total_liabilities,
    }


def build_series(norm_fin_docs: List[Dict], basis: str = "individual") -> List[Dict]:
    """Per-year metrics, newest first. Prefers individual accounts, falls back to any."""
    docs = [f for f in norm_fin_docs if f.get("basis") == basis] or norm_fin_docs
    docs = sorted(docs, key=lambda f: (f.get("year") or 0), reverse=True)
    out = []
    for f in docs:
        m = _year_metrics(f.get("accounts") or {})
        m["year"] = f.get("year")
        m["basis"] = f.get("basis")
        m["fiscal_close_date"] = f.get("fiscal_close_date")
        out.append(m)
    return out


def statements(latest: Dict, employees: Optional[int]) -> Dict:
    """Structured income statement + balance sheet for the latest year. Cashflow N/A (individual)."""
    return {
        "year": latest.get("year"), "basis": latest.get("basis"),
        "income_statement": {k: latest.get(k) for k in
                             ("revenue", "supplies", "personnel_costs", "operating_income",
                              "depreciation", "ebitda", "ebit", "financial_expenses", "net_income")},
        "balance_sheet": {k: latest.get(k) for k in
                          ("non_current_assets", "current_assets", "cash", "total_assets",
                           "equity", "non_current_liabilities", "current_liabilities",
                           "financial_debt", "total_liabilities")},
        "cashflow": None,  # not provided in individual statements
        "employees": employees,
    }
