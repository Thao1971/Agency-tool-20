"""Piloto de enriquecimiento web (~100 empresas de baja confianza con web).
Mide: sitios scrapeados OK, confianza antes/después, nº que superan 0,5, cambios de sector,
y nuevas etiquetas de industria tech/fintech/biotech. Best-effort, no inventa."""

import asyncio
import json
import time
from collections import Counter

from database import db
from services.web_scraper import get_web_description
from services.taxonomy import batch as BATCH
from services.taxonomy import classify as CLS

N = 100
CONCURRENCY = 8
TECH_PREFIXES = ("IND-S02", "IND-S08-fintech", "IND-S05-biotecnologia", "IND-S05-healthtech")


async def _classification_ids(cid):
    return [c["taxonomy_id"] async for c in db.company_classifications.find(
        {"company_id": cid}, {"_id": 0, "taxonomy_id": 1})]


async def main():
    t0 = time.time()
    low = [f async for f in db.company_fingerprint.find(
        {"overall_confidence": {"$lt": 0.5}}, {"_id": 0, "company_id": 1, "overall_confidence": 1, "primary_sector": 1})]
    low_ids = [f["company_id"] for f in low]
    # candidatos: baja confianza + con web
    cand = []
    async for m in db.master_companies.find(
            {"master_id": {"$in": low_ids}, "contact.web": {"$nin": [None, ""]}},
            {"_id": 0, "master_id": 1, "contact.web": 1}):
        cand.append(m["master_id"])
        if len(cand) >= N:
            break
    before = {f["company_id"]: f for f in low if f["company_id"] in set(cand)}
    before_ids = {cid: await _classification_ids(cid) for cid in cand}

    # ── scrape concurrente ──
    sem = asyncio.Semaphore(CONCURRENCY)
    scraped = {}

    async def _one(cid):
        async with sem:
            try:
                desc = await get_web_description(cid)
                scraped[cid] = bool(desc)
            except Exception:
                scraped[cid] = False
    await asyncio.gather(*[_one(c) for c in cand])
    scraped_ok = sum(1 for v in scraped.values() if v)

    # ── reclasificar cada una (lee web_description recién cacheada) ──
    reclassified = 0
    for cid in cand:
        doc = await db.master_companies.find_one({"master_id": cid}, {"_id": 0})
        req = BATCH.company_inputs(doc)
        try:
            await CLS.classify(req)
            reclassified += 1
        except Exception:
            pass

    # ── medir DESPUÉS ──
    improved = 0
    conf_b = conf_a = 0.0
    sector_changes = 0
    new_tech = []
    for cid in cand:
        fp = await db.company_fingerprint.find_one({"company_id": cid}, {"_id": 0})
        cb = before[cid].get("overall_confidence") or 0.0
        ca = (fp or {}).get("overall_confidence") or 0.0
        conf_b += cb
        conf_a += ca
        if cb < 0.5 <= ca:
            improved += 1
        if (before[cid].get("primary_sector")) != (fp or {}).get("primary_sector"):
            sector_changes += 1
        after_ids = set(await _classification_ids(cid))
        gained = [i for i in after_ids - set(before_ids[cid])
                  if any(i.startswith(p) for p in TECH_PREFIXES)]
        if gained:
            new_tech.append({"company_id": cid, "gained": gained})

    n = len(cand)
    out = {
        "cohort_size": n,
        "scraped_ok": scraped_ok,
        "scraped_failed": n - scraped_ok,
        "reclassified": reclassified,
        "avg_confidence_before": round(conf_b / n, 3) if n else 0,
        "avg_confidence_after": round(conf_a / n, 3) if n else 0,
        "improved_to_ge_0_5": improved,
        "sector_changes": sector_changes,
        "new_tech_tags_companies": len(new_tech),
        "new_tech_examples": new_tech[:15],
        "elapsed_s": round(time.time() - t0, 1),
    }
    json.dump(out, open("/tmp/pilot.json", "w"), ensure_ascii=False, indent=2)
    print("DONE", json.dumps({k: v for k, v in out.items() if k != "new_tech_examples"}, ensure_ascii=False))


asyncio.run(main())
