"""One-time backfill: decode HTML entities in already-stored documents.

The ingestion pipeline now normalizes text on write (see services.text_normalize),
but historical documents remain HTML-encoded. This script sweeps every source
collection, decodes entities in string fields and updates ONLY the documents that
actually change. Idempotent and safe to re-run.

Run:  cd /app/backend && python -m scripts.backfill_html_unescape
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402
from services.text_normalize import normalize_strings  # noqa: E402

# Text-bearing source collections worth sweeping. Clean docs are skipped, so a
# collection with no entities costs only a scan.
COLLECTIONS = [
    "cnmv_entities",
    "public_procurement_contracts",
    "borme_events",
    "agency_results",
    "bme_companies",
    "companies_master",
    "iberinform_companies",
    "estadisticas_empleo",
    "estadisticas_territoriales",
    "economic_metrics",
    "datacomex_raw_data",
]

ENTITY_REGEX = {"$regex": "&[#a-zA-Z0-9]+;"}


async def backfill_collection(coll: str) -> dict:
    total = await db[coll].count_documents({})
    if total == 0:
        return {"collection": coll, "total": 0, "scanned": 0, "updated": 0}

    scanned = 0
    updated = 0
    cursor = db[coll].find({})
    async for doc in cursor:
        scanned += 1
        _id = doc.get("_id")
        payload = {k: v for k, v in doc.items() if k != "_id"}
        cleaned = normalize_strings(payload)
        changed = {k: cleaned[k] for k in cleaned if cleaned[k] != payload.get(k)}
        if changed:
            await db[coll].update_one({"_id": _id}, {"$set": changed})
            updated += 1
        if scanned % 20000 == 0:
            print(f"  [{coll}] scanned={scanned}/{total} updated={updated}", flush=True)

    return {"collection": coll, "total": total, "scanned": scanned, "updated": updated}


async def main():
    print("=== HTML-entity backfill starting ===", flush=True)
    grand_updated = 0
    for coll in COLLECTIONS:
        res = await backfill_collection(coll)
        grand_updated += res["updated"]
        print(f"DONE {res['collection']}: updated={res['updated']} / total={res['total']}", flush=True)
    print(f"=== Backfill complete. Total documents cleaned: {grand_updated} ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
