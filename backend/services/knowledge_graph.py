"""Knowledge Graph (P3) — company relationship layer (separate from companies_master).

Boundary First, internal-only. Materializes relationships reusing existing infra:
embeddings/semantic_similarity + cluster_id (P2.2), signal_score (P3), classification/size (P2.1).
No new engines. companies_master stays the source of truth; relationships live independently.

Initially materialized: similar_to, same_cluster. Other types are reserved in the model.
"""

import logging
import uuid
from collections import defaultdict
from typing import Dict, List

import numpy as np

from database import db
from models import now_iso

logger = logging.getLogger(__name__)

SIMILAR_THRESHOLD = 0.35
TOP_SIMILAR = 8
TOP_SAME_CLUSTER = 8
GRAPH_VERSION = "kg-v1"

RELATIONSHIP_TYPES = [
    "similar_to", "same_cluster", "competitor_of", "same_group",
    "subsidiary_of", "shareholder_of", "supplier_candidate", "acquisition_candidate",
]


def _rel(source: str, target: str, rtype: str, score: float, confidence: float, basis: str) -> Dict:
    return {
        "relationship_id": str(uuid.uuid4()),
        "source_master_company_id": source,
        "target_master_company_id": target,
        "relationship_type": rtype,
        "score": round(float(score), 4),
        "confidence": round(float(confidence), 4),
        "lineage": {"source": "inferred", "basis": basis},
        "created_at": now_iso(),
    }


async def rebuild_graph() -> Dict:
    """Idempotent, non-destructive rebuild of company_relationships."""
    await db.company_relationships.create_index("source_master_company_id")
    await db.company_relationships.create_index("relationship_type")
    await db.company_relationships.create_index(
        [("source_master_company_id", 1), ("target_master_company_id", 1), ("relationship_type", 1)],
        unique=True,
    )

    rows = await db.company_embeddings.find(
        {}, {"_id": 0, "master_company_id": 1, "vector": 1, "cluster_id": 1}
    ).to_list(100000)
    if len(rows) < 3:
        return {"status": "skipped", "reason": "embedding index empty", "count": len(rows)}

    ids = [r["master_company_id"] for r in rows]
    clusters = [r.get("cluster_id") for r in rows]
    M = np.array([r["vector"] for r in rows], dtype=np.float32)  # unit vectors

    # signal_score lookup for same_cluster confidence
    score_rows = await db.companies_master.find(
        {"master_company_id": {"$in": ids}}, {"_id": 0, "master_company_id": 1, "signal_score": 1}
    ).to_list(100000)
    sig = {r["master_company_id"]: (r.get("signal_score") or 0) for r in score_rows}

    cluster_members = defaultdict(list)
    for i, cl in enumerate(clusters):
        if cl is not None:
            cluster_members[cl].append(i)

    sims = M @ M.T  # (n, n) cosine (unit vectors)
    n = len(ids)
    relationships: List[Dict] = []
    seen = set()  # (source, target, type)

    def _add(si, ti, rtype, score, conf, basis):
        key = (ids[si], ids[ti], rtype)
        if ids[si] == ids[ti] or key in seen:
            return
        seen.add(key)
        relationships.append(_rel(ids[si], ids[ti], rtype, score, conf, basis))

    for i in range(n):
        row = sims[i].copy()
        row[i] = -1.0
        # similar_to: global semantic neighbors
        k = min(TOP_SIMILAR, n - 1)
        top_idx = np.argpartition(row, -k)[-k:]
        for j in sorted(top_idx, key=lambda x: -row[x]):
            if row[j] >= SIMILAR_THRESHOLD:
                _add(i, int(j), "similar_to", row[j], row[j], "semantic_embedding")

        # same_cluster: top co-members by semantic sim within the cluster
        cl = clusters[i]
        if cl is not None:
            members = [m for m in cluster_members[cl] if m != i]
            members.sort(key=lambda m: -sims[i][m])
            for j in members[:TOP_SAME_CLUSTER]:
                proximity = 1 - abs(sig.get(ids[i], 0) - sig.get(ids[j], 0)) / 100.0
                _add(i, int(j), "same_cluster", float(sims[i][j]), round(proximity, 4), "cluster_id")

    await db.company_relationships.delete_many({})
    if relationships:
        # insert in batches
        for start in range(0, len(relationships), 5000):
            await db.company_relationships.insert_many(relationships[start:start + 5000])

    by_type = defaultdict(int)
    for r in relationships:
        by_type[r["relationship_type"]] += 1

    return {
        "status": "ok",
        "companies": n,
        "relationships": len(relationships),
        "by_type": dict(by_type),
        "version": GRAPH_VERSION,
    }


async def relationships_for(master_company_id: str, limit: int = 10) -> List[Dict]:
    """Top relationships for a company (consumed by Analyze)."""
    rels = await db.company_relationships.find(
        {"source_master_company_id": master_company_id}, {"_id": 0}
    ).sort("score", -1).limit(limit).to_list(limit)
    return [{
        "target_master_company_id": r["target_master_company_id"],
        "relationship_type": r["relationship_type"],
        "score": r["score"],
        "confidence": r["confidence"],
    } for r in rels]


async def neighbor_scores(master_company_id: str) -> Dict[str, float]:
    """Map target_master_company_id -> best graph score (similar_to/same_cluster).

    Internal-only signal for Recommend. Empty dict when the graph hasn't been built,
    so consumers fall back to their current logic transparently.
    """
    rels = await db.company_relationships.find(
        {"source_master_company_id": master_company_id,
         "relationship_type": {"$in": ["similar_to", "same_cluster"]}},
        {"_id": 0, "target_master_company_id": 1, "score": 1},
    ).to_list(2000)
    out: Dict[str, float] = {}
    for r in rels:
        tid = r["target_master_company_id"]
        s = float(r.get("score") or 0.0)
        if s > out.get(tid, 0.0):
            out[tid] = s
    return out
