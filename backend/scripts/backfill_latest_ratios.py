"""Backfill financials.latest.ratios (+ free_cash_flow, cash_conversion) into
master_companies for docs built before the rich-ratios summary existed. Idempotent.
Enables sector percentiles for ALL ratios (incl. liquidity/working-capital).

Run: python -m scripts.backfill_latest_ratios
"""
import asyncio

from database import db
from services.engines.financial import metrics as M, ratios_library as R


async def main():
    cursor = db.master_companies.find(
        {"financials.latest": {"$ne": None}},
        {"_id": 0, "master_id": 1, "cif_normalized": 1})
    masters = await cursor.to_list(None)
    print(f"masters with financials.latest: {len(masters)}")

    updated = skipped = 0
    from pymongo import UpdateOne
    ops = []
    for m in masters:
        cif = m.get("cif_normalized")
        if not cif:
            skipped += 1
            continue
        norm = await db.norm_financials.find({"cif_normalized": cif}, {"_id": 0}).to_list(50)
        individual = [f for f in norm if f.get("basis") == "individual"]
        chosen = sorted(individual or norm, key=lambda f: (f.get("year") or 0), reverse=True)
        if not chosen:
            skipped += 1
            continue
        ym = M._year_metrics(chosen[0].get("accounts") or {})
        ratios = {k: v["value"] for k, v in R.compute_all(ym, None).items()
                  if v.get("value") is not None}
        setter = {"financials.latest.ratios": ratios}
        for extra in ("free_cash_flow", "cash_conversion"):
            if ym.get(extra) is not None:
                setter[f"financials.latest.{extra}"] = ym[extra]
        ops.append(UpdateOne({"master_id": m["master_id"]}, {"$set": setter}))
        if len(ops) >= 500:
            res = await db.master_companies.bulk_write(ops, ordered=False)
            updated += res.modified_count
            ops = []
            print(f"...updated so far: {updated}")
    if ops:
        res = await db.master_companies.bulk_write(ops, ordered=False)
        updated += res.modified_count
    print(f"DONE. updated={updated} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
