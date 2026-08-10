"""B6 — Web enrichment batch (background). For every company that has a website
(`contact.web`) but no `web_description` yet: scrape the homepage (httpx, best-effort),
cache the description, and re-run the taxonomy classification (improves fintech/biotech
labels). Idempotent & resumable: skips companies already enriched. No fabricated data.

Run:  nohup python -m scripts.web_enrichment_batch > /tmp/web_enrich.log 2>&1 &
"""
import asyncio
import json
import time
from collections import Counter

from database import db
from services.web_scraper import get_web_description
from services.taxonomy import batch as BATCH
from services.taxonomy import classify as CLS

CONCURRENCY = 8
TECH_PREFIXES = ("IND-S02", "IND-S08-fintech", "IND-S05-biotecnologia", "IND-S05-healthtech")


async def main():
    t0 = time.time()
    pending = []
    async for m in db.master_companies.find(
            {"contact.web": {"$nin": [None, ""]},
             "$or": [{"web_description": None}, {"web_description": {"$exists": False}}]},
            {"_id": 0, "master_id": 1}):
        pending.append(m["master_id"])
    total = len(pending)
    print(f"[web-enrich] pending={total} concurrency={CONCURRENCY}", flush=True)

    stats = Counter()
    sem = asyncio.Semaphore(CONCURRENCY)
    processed = 0
    lock = asyncio.Lock()

    async def _one(cid):
        nonlocal processed
        async with sem:
            ok = False
            try:
                desc = await get_web_description(cid)
                ok = bool(desc)
            except Exception:
                ok = False
            if ok:
                stats["scraped_ok"] += 1
                try:
                    doc = await db.master_companies.find_one({"master_id": cid}, {"_id": 0})
                    before = {c["taxonomy_id"] async for c in db.company_classifications.find(
                        {"company_id": cid}, {"_id": 0, "taxonomy_id": 1})}
                    await CLS.classify(BATCH.company_inputs(doc))
                    after = {c["taxonomy_id"] async for c in db.company_classifications.find(
                        {"company_id": cid}, {"_id": 0, "taxonomy_id": 1})}
                    if any(t.startswith(TECH_PREFIXES) for t in (after - before)):
                        stats["new_tech_tags"] += 1
                    stats["reclassified"] += 1
                except Exception:
                    stats["reclassify_error"] += 1
            else:
                stats["scraped_fail"] += 1
            async with lock:
                processed += 1
                if processed % 100 == 0:
                    print(f"[web-enrich] {processed}/{total} ok={stats['scraped_ok']} "
                          f"tech+={stats['new_tech_tags']} t={round(time.time()-t0)}s", flush=True)

    await asyncio.gather(*[_one(c) for c in pending])

    out = {"pending": total, **dict(stats), "elapsed_s": round(time.time() - t0, 1)}
    json.dump(out, open("/tmp/web_enrich_summary.json", "w"), ensure_ascii=False, indent=2)
    print("[web-enrich] DONE", json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
