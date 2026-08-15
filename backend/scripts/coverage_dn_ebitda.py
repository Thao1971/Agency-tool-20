"""Read-only coverage count: how many companies can compute DN/EBITDA.

DN/EBITDA = deuda financiera neta / EBITDA, where the financial engine
(services/engines/financial/metrics.py) needs, in the newest year of
`norm_financials.accounts` (Iberinform Valu8 codes):
  - financial debt: 31200 (LP) and/or 32300 (CP)
  - cash / tesorería: 12700
  - EBITDA inputs: 49100 (operating income) AND 40800 (depreciation)

Reports the ceiling for the ratio (all three present) plus each component's
coverage, so we know if "no disponible" is data-absence (expected) vs a gap.

Read-only — no writes. Run: cd /app/backend && python -m scripts.coverage_dn_ebitda
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402

C_LT, C_ST, C_CASH, C_OP, C_DEP = "31200", "32300", "12700", "49100", "40800"


async def main() -> None:
    print("=== DN/EBITDA coverage (norm_financials, newest year per company) ===", flush=True)
    proj = {
        "_id": 0, "cif_normalized": 1, "year": 1,
        f"accounts.{C_LT}": 1, f"accounts.{C_ST}": 1, f"accounts.{C_CASH}": 1,
        f"accounts.{C_OP}": 1, f"accounts.{C_DEP}": 1,
    }
    newest: dict[str, dict] = {}
    scanned = 0
    async for f in db.norm_financials.find({}, proj):
        scanned += 1
        cif = f.get("cif_normalized")
        if not cif:
            continue
        y = f.get("year") or 0
        cur = newest.get(cif)
        if cur is None or y > (cur.get("year") or 0):
            newest[cif] = f

    companies = len(newest)
    has_debt = has_cash = has_ebitda = has_all = 0
    for f in newest.values():
        acc = f.get("accounts") or {}
        debt = acc.get(C_LT) is not None or acc.get(C_ST) is not None
        cash = acc.get(C_CASH) is not None
        ebitda = acc.get(C_OP) is not None and acc.get(C_DEP) is not None
        has_debt += debt
        has_cash += cash
        has_ebitda += ebitda
        has_all += (debt and cash and ebitda)

    def pct(n: int) -> str:
        return f"{(100 * n / companies):.1f}%" if companies else "—"

    print(f"docs scanned:            {scanned}", flush=True)
    print(f"companies (distinct):    {companies}", flush=True)
    print(f"con deuda financiera:    {has_debt} ({pct(has_debt)})", flush=True)
    print(f"con tesorería (caja):    {has_cash} ({pct(has_cash)})", flush=True)
    print(f"con EBITDA calculable:   {has_ebitda} ({pct(has_ebitda)})", flush=True)
    print(f"DN/EBITDA calculable:    {has_all} ({pct(has_all)})  <-- techo del ratio", flush=True)
    print("=== done ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
