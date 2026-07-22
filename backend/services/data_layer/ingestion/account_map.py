"""Canonical financial account map (Iberinform Valu8 EAV → normalized metrics).

The financial files are long EAV: ES_Account_number (code) → Amount_Eur. We extract a
small set of canonical metrics; raw accounts are still stored in full for auditability.
"""

from typing import Dict, Optional

# Iberinform Valu8 account codes (verified against the real sample).
ACCOUNT_MAP = {
    "40100": "revenue",            # 1. NET SALES
    "10000": "total_assets",       # TOTAL ASSETS
    "20000": "equity",             # A) NET WORTH
    "49100": "operating_income",   # A) OPERATING INCOME (EBIT-like)
    "40800": "depreciation",       # 8. DEPRECIATION OF FIXED ASSETS
    "49500": "net_income",         # D) RESULTS FOR THE FINANCIAL YEAR
}
RATIO_EBITDA_MARGIN = "REN007"     # provided "Ebitda / sales" ratio (sanity check)


def parse_amount(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace("\xa0", "")
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", ".") if s.count(",") and "." not in s else s.replace(",", "")
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


def derive_metrics(accounts: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Extract canonical metrics from an account_number→amount map for one company-year."""
    out: Dict[str, Optional[float]] = {v: accounts.get(k) for k, v in ACCOUNT_MAP.items()}
    revenue = out.get("revenue")
    op_income = out.get("operating_income")
    deprec = out.get("depreciation")
    # EBITDA = operating income + depreciation (depreciation stored as expense magnitude)
    ebitda = None
    if op_income is not None and deprec is not None:
        ebitda = round(op_income + abs(deprec), 2)
    elif revenue and accounts.get(RATIO_EBITDA_MARGIN) is not None:
        ebitda = round(revenue * accounts[RATIO_EBITDA_MARGIN], 2)
    out["ebitda"] = ebitda
    out["ebitda_margin"] = round(ebitda / revenue, 4) if (ebitda is not None and revenue) else None
    return out
