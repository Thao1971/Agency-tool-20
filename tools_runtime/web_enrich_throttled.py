"""Web enrichment THROTTLED + AISLADO (fuera de /app/backend para no disparar el
--reload de uvicorn). Sube `web_description` scrapeando homepages de empresas que ya
tienen `contact.web`. Procesa por lotes con baja concurrencia y pausas entre lotes
para NO saturar el pool de conexiones de Atlas (causa de la caída anterior de la API).

Uso:
  cd /app && PYTHONDONTWRITEBYTECODE=1 nohup python tools_runtime/web_enrich_throttled.py \
      > /tmp/web_enrich_throttled.log 2>&1 &

Env:
  ENRICH_CONCURRENCY  (def 4)   ops simultáneas por lote
  ENRICH_CHUNK        (def 40)   tamaño de lote
  ENRICH_SLEEP        (def 1.5)  pausa (s) entre lotes
  ENRICH_RECLASSIFY   (def 1)    reclasificar taxonomía tras scrapear (0 = más ligero)
"""
import asyncio
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import db
from services.web_scraper import get_web_description
from services.taxonomy import batch as BATCH
from services.taxonomy import classify as CLS

CONCURRENCY = int(os.environ.get("ENRICH_CONCURRENCY", "4"))
CHUNK = int(os.environ.get("ENRICH_CHUNK", "40"))
SLEEP = float(os.environ.get("ENRICH_SLEEP", "1.5"))
RECLASSIFY = os.environ.get("ENRICH_RECLASSIFY", "1") == "1"
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
    print(f"[web-enrich-throttled] pending={total} conc={CONCURRENCY} chunk={CHUNK} "
          f"sleep={SLEEP} reclassify={RECLASSIFY}", flush=True)

    stats = Counter()
    sem = asyncio.Semaphore(CONCURRENCY)
    processed = 0

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
                if RECLASSIFY:
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
            processed += 1

    # chunked: bound sustained load on Atlas + give the live API breathing room
    for i in range(0, total, CHUNK):
        batch = pending[i:i + CHUNK]
        await asyncio.gather(*[_one(c) for c in batch])
        print(f"[web-enrich-throttled] {processed}/{total} ok={stats['scraped_ok']} "
              f"fail={stats['scraped_fail']} tech+={stats['new_tech_tags']} "
              f"t={round(time.time()-t0)}s", flush=True)
        await asyncio.sleep(SLEEP)

    out = {"pending": total, **dict(stats), "elapsed_s": round(time.time() - t0, 1)}
    json.dump(out, open("/tmp/web_enrich_throttled_summary.json", "w"), ensure_ascii=False, indent=2)
    print("[web-enrich-throttled] DONE", json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
