"""REQ-004 backfill: copy EBITDA + financial history into the legacy
`companies_master` collection so the financial screen (skills/search) can
filter by ebitda / growth.

Why: `skills/search` reads `companies_master` (flat legacy, 24.992 rows) which
has `revenue_latest`/`employees_latest` but NO ebitda and NO history. The
canonical `master_companies` collection DOES have `financials.latest`
(revenue, ebitda, ebitda_margin, ...) and `financials.history`. This job copies
that `financials` block across, keyed by the shared `cif_normalized`.

Effect after run:
  - revenue / employees / province filters: unchanged (already worked).
  - ebitda_* and growth_min: start returning results where the data exists
    (~9.742 companies have ebitda; ~13.464 have history — the data ceiling).

Safety:
  - ADDITIVE only: `$set financials` on legacy docs that don't already have
    `financials.latest.ebitda`. Never deletes `revenue_latest`/`employees_latest`
    or anything else. Idempotent — safe to re-run (e.g. after each ingest).
  - Dry-run by default. Pass `--apply` to write.

Run (dry-run):  cd /app/backend && python -m scripts.backfill_financials_to_companies_master
Run (apply):    cd /app/backend && python -m scripts.backfill_financials_to_companies_master --apply
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402

try:
    from pymongo import UpdateOne  # noqa: E402
except Exception:  # pragma: no cover
    UpdateOne = None

BATCH = 1000


def _has_ebitda(fin: dict) -> bool:
    return bool(fin) and (fin.get("latest") or {}).get("ebitda") is not None


def _has_history(fin: dict) -> bool:
    return bool(fin) and bool(fin.get("history"))


async def main(apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== REQ-004 financials backfill ({mode}) ===", flush=True)

    # 1) Source map from the canonical collection: cif_normalized -> financials
    #    (only docs that actually add value: they carry ebitda or history).
    src: dict[str, dict] = {}
    q_src = {"$or": [
        {"financials.latest.ebitda": {"$ne": None}},
        {"financials.history.0": {"$exists": True}},
    ]}
    async for m in db.master_companies.find(
        q_src, {"_id": 0, "cif_normalized": 1, "financials": 1}
    ):
        cif = m.get("cif_normalized")
        fin = m.get("financials")
        if cif and fin and (_has_ebitda(fin) or _has_history(fin)):
            src[cif] = fin
    print(f"source master_companies with ebitda/history: {len(src)}", flush=True)

    # 2) Walk legacy docs; queue an additive $set where the target lacks ebitda.
    scanned = matched = would_update = 0
    ops: list = []
    cursor = db.companies_master.find(
        {"cif_normalized": {"$in": list(src.keys())}},
        {"_id": 1, "cif_normalized": 1, "financials": 1},
    )
    async for doc in cursor:
        scanned += 1
        cif = doc.get("cif_normalized")
        fin = src.get(cif)
        if not fin:
            continue
        matched += 1
        if _has_ebitda(doc.get("financials") or {}):
            continue  # already backfilled → idempotent skip
        would_update += 1
        if apply and UpdateOne is not None:
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"financials": fin}}))
            if len(ops) >= BATCH:
                await db.companies_master.bulk_write(ops, ordered=False)
                ops = []
    if apply and ops:
        await db.companies_master.bulk_write(ops, ordered=False)

    print(f"legacy scanned(matched by cif)={scanned} matched={matched} "
          f"{'updated' if apply else 'would_update'}={would_update}", flush=True)
    if not apply:
        print("Dry-run only. Re-run with --apply to write.", flush=True)
    print("=== done ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
