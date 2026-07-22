"""One-shot generator for the resolve_entity golden snapshot dataset (M3 safety net).

Snapshots the DETERMINISTIC output of the legacy `resolve_entity` over stable, real
identity inputs (exact CIF, exact domain, non-existent → discovered). This is the parity
oracle for M3: the canonical resolver behind the coexistence provider must reproduce it.

Run once: python -m tests.golden.gen_resolve_snapshots  (from /app/backend)
"""
import asyncio
import json
import os

from database import db
from services.entity_resolution import resolve_entity

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "resolve_golden_snapshots.json")


def normalize(r: dict) -> dict:
    return {"status": r["status"], "method": r["method"], "score": r["score"],
            "match_id": r["match_id"], "candidate_count": len(r.get("candidates") or [])}


async def _real_with(field_query, projection):
    return await db.companies_master.find_one(
        {**field_query, "legal_name": {"$nin": [None, ""]},
         "normalized_name": {"$not": {"$regex": "golden|test|unknown", "$options": "i"}}},
        {"_id": 0, **projection})


async def main():
    cases = []
    # exact CIF → auto_merged (stable real record)
    c = await _real_with({"cif_normalized": {"$ne": None}}, {"cif_normalized": 1, "legal_name": 1})
    if c:
        cases.append(("cif_exact", {"legal_name": c["legal_name"], "cif": c["cif_normalized"]}))
    # exact domain → domain_exact
    d = await _real_with({"domain": {"$ne": None}}, {"domain": 1, "legal_name": 1})
    if d:
        cases.append(("domain_exact", {"legal_name": d["legal_name"], "domain": d["domain"]}))
    # non-existent → discovered
    cases.append(("discovered_new", {"legal_name": "ZZZ NONEXISTENT GOLDEN CO", "cif": "B00000000"}))
    # name-only (no cif/domain) for a real record → whatever legacy decides (frozen)
    n = await _real_with({"cif_normalized": None, "domain": None}, {"legal_name": 1})
    if n and n.get("legal_name"):
        cases.append(("name_only", {"legal_name": n["legal_name"]}))

    payload = {"_meta": {"count": len(cases)}, "entries": {}}
    for label, inp in cases:
        r = await resolve_entity(**inp)
        payload["entries"][label] = {"input": inp, "snapshot": normalize(r)}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"generated {len(cases)} resolve snapshots")
    for label, _ in cases:
        print(f"  {label}: {payload['entries'][label]['snapshot']}")


if __name__ == "__main__":
    asyncio.run(main())
