"""Competitor graph (Q2 extension) — `competitor_of`, derived from REAL structural data only.

No new data source: same CNAE code + same revenue size_band (reusing
`services/engines/signal/baselines.py::size_band_for`, the same bands used for Q3's
contextual thresholds) + NOT already connected via the real ownership graph
(`ownership_graph.py`, same `ownership.group_id`). This is a heuristic proxy — same
activity + same scale is a plausible competitor signal, not a confirmed relationship —
so it's scored at a fixed, deliberately lower confidence (0.5) than the confirmed
ownership edges (0.95) `ownership_graph.py` writes.

Writes into the SAME `master_relationships` collection (`relationship_type=
"competitor_of"`, `origin="sector_size_heuristic"`), so `ownership_graph.relationships_for()`
returns the whole real graph (control + competitor) through one query, not two.

`supplier_candidate` / `acquisition_candidate` are deliberately NOT implemented here:
confirmed (by direct code inspection) that no connected source has any real supplier
relationship data, and acquisition candidacy belongs to Buyer Intelligence (G1/E1),
not to this structural "who competes with whom" graph.
"""

import itertools
from typing import Dict, List

from pymongo import UpdateOne

from database import db
from models import now_iso
from services.data_layer.master.ownership_graph import ensure_indexes
from services.engines.signal.baselines import size_band_for

RELATIONSHIP_TYPE = "competitor_of"
ORIGIN = "sector_size_heuristic"
MAX_PER_BUCKET = 30   # bound pairwise cost per (cnae_code, size_band) bucket (30 choose 2 = 435)
MIN_BUCKET_SIZE = 2
CONFIDENCE = 0.5      # heuristic proxy — deliberately lower than confirmed ownership edges (0.95)


async def rebuild_competitor_edges(limit_codes: int = 300) -> Dict:
    """Idempotent rebuild: replaces only the edges this function itself wrote
    (`origin=sector_size_heuristic`), never touches the real ownership edges."""
    await ensure_indexes()
    await db.master_relationships.delete_many({"relationship_type": RELATIONSHIP_TYPE, "origin": ORIGIN})

    codes = await db.master_companies.distinct(
        "classification.cnae_code",
        {"classification.cnae_code": {"$ne": None}, "financials.latest.revenue": {"$ne": None}})
    codes = codes[:limit_codes]

    now = now_iso()
    ops: List[UpdateOne] = []
    buckets_used = 0
    edges = 0
    skipped_same_group = 0

    for code in codes:
        companies = await db.master_companies.find(
            {"classification.cnae_code": code, "financials.latest.revenue": {"$ne": None}},
            {"_id": 0, "master_id": 1, "financials.latest.revenue": 1, "ownership.group_id": 1},
        ).to_list(MAX_PER_BUCKET * 3)

        by_band: Dict[str, List[Dict]] = {}
        for c in companies:
            band = size_band_for(((c.get("financials") or {}).get("latest") or {}).get("revenue"))
            if band:
                by_band.setdefault(band, []).append(c)

        for band, members in by_band.items():
            members = members[:MAX_PER_BUCKET]
            if len(members) < MIN_BUCKET_SIZE:
                continue
            buckets_used += 1
            for a, b in itertools.combinations(members, 2):
                gid_a = (a.get("ownership") or {}).get("group_id")
                gid_b = (b.get("ownership") or {}).get("group_id")
                if gid_a and gid_a == gid_b:
                    skipped_same_group += 1
                    continue  # same ownership group -> affiliate, not a competitor
                for src, dst in ((a["master_id"], b["master_id"]), (b["master_id"], a["master_id"])):
                    doc = {
                        "src_master_id": src, "dst_master_id": dst,
                        "relationship_type": RELATIONSHIP_TYPE, "year": None,
                        "basis": {"cnae_code": code, "size_band": band},
                        "source": "structural", "origin": ORIGIN,
                        "confidence": CONFIDENCE, "created_at": now,
                    }
                    ops.append(UpdateOne(
                        {"src_master_id": src, "dst_master_id": dst,
                         "relationship_type": RELATIONSHIP_TYPE, "year": None},
                        {"$set": doc}, upsert=True))
                    edges += 1
            if len(ops) >= 2000:
                await db.master_relationships.bulk_write(ops, ordered=False)
                ops = []

    if ops:
        await db.master_relationships.bulk_write(ops, ordered=False)

    return {"cnae_codes_scanned": len(codes), "buckets_used": buckets_used,
            "edges_written": edges, "skipped_same_group_pairs": skipped_same_group,
            "confidence": CONFIDENCE}
