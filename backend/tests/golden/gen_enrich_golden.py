"""One-shot generator for the frozen enrich golden dataset + snapshots (M2 prep).

Deterministic selection (sorted by master_company_id) of a diverse set:
  - rich + financials (Valuo-relevant), - with web, - sparse/discovered.
Run once: python -m tests.golden.gen_enrich_golden  (from /app/backend)
"""
import asyncio

from database import db
from services.intelligence_engine import enrich_company
from tests.golden.enrich_snapshot_util import normalize, save_snapshots, PROFILES


async def _pick(query, n, exclude, sort=None):
    ids = []
    sort_spec = (sort or []) + [("master_company_id", 1)]
    cur = db.companies_master.find(query, {"_id": 0, "master_company_id": 1}).sort(sort_spec)
    async for d in cur:
        mid = d["master_company_id"]
        if mid in exclude:
            continue
        ids.append(mid)
        if len(ids) >= n:
            break
    return ids


async def select_dataset():
    """Deterministic, edge-case-rich selection across real-world scenarios (M2 criterion 4).

    Excludes synthetic/test artifacts (records created/mutated by other suites, e.g. valuo
    request flow) so the frozen oracle is stable: requires a real legal_name and rejects
    test-named records.
    """
    seen = set()
    R = "financials.latest.revenue"
    # Base filter: only stable REAL companies (exclude synthetic test records).
    base = {
        "legal_name": {"$nin": [None, ""]},
        "normalized_name": {"$not": {"$regex": "golden|test|unknown", "$options": "i"}},
    }

    def q(extra):
        return {"$and": [base, extra]}

    buckets = [
        ("rich_financials", q({"sources.web": {"$exists": True}, "sources.iberinform": {"$exists": True}}), 2, None),
        ("microempresa", q({R: {"$gt": 0, "$lt": 2_000_000}}), 2, None),
        ("pyme", q({R: {"$gte": 2_000_000, "$lt": 50_000_000}}), 2, None),
        ("gran_empresa", q({R: {"$gte": 50_000_000, "$lt": 500_000_000}}), 2, None),
        ("muy_grande", q({R: {"$gte": 500_000_000}}), 2, [(R, -1)]),
        ("holding_grupo", q({"normalized_name": {"$regex": "holding|grupo", "$options": "i"}}), 2, None),
        ("financials_incompletos", q({"financials.latest": {"$exists": True}, R: None}), 2, None),
        ("sin_cuentas_recientes", q({"financials.latest.year": {"$lt": 2022}}), 2, None),
        ("multi_cnae", q({"cnae.1": {"$exists": True}}), 2, None),
        ("sin_web", q({"domain": None, "sources.web": {"$exists": False}}), 2, None),
        ("actividad_digital", q({"sources.web.present": True}), 2, None),
        ("baja_calidad", q({"confidence_score": {"$lt": 0.4}}), 2, None),
        ("discovered", q({"merge_status": "discovered"}), 2, None),
    ]
    out = []
    for label, query, n, sort in buckets:
        ids = await _pick(query, n, seen, sort=sort)
        for mid in ids:
            seen.add(mid)
            out.append((label, mid))
    return out


async def main():
    dataset = await select_dataset()
    payload = {"_meta": {"dataset_size": len(dataset),
                         "selection": "deterministic by master_company_id; buckets: rich_financials, with_web, sparse, discovered",
                         "profiles": PROFILES},
               "entries": {}}
    for label, mid in dataset:
        for profile in PROFILES:
            res = await enrich_company(mid, profile=profile)
            key = f"{mid}::{profile}"
            snap = normalize(res)
            snap["_bucket"] = label
            payload["entries"][key] = snap
    save_snapshots(payload)
    print(f"generated {len(payload['entries'])} snapshots for {len(dataset)} companies")
    for label, mid in dataset:
        print(f"  [{label}] {mid}")


if __name__ == "__main__":
    asyncio.run(main())
