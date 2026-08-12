"""Knowledge Graph — phase 1: STRUCTURAL relations derived from REAL ownership only.

No semantic similarity / embeddings / recommendations here (deferred). Maps the
norm_ownership edges (CIF↔CIF) onto permanent master_ids and materializes
`master_relationships`. Groups are computed via union-find (scalable, not O(n²)):
no pairwise same_group edges — a `group_id` label is assigned to each connected component.
"""

import logging
from typing import Dict, List, Optional

from pymongo import UpdateOne

from database import db
from models import now_iso
from borme.parser import normalize_company_name

logger = logging.getLogger(__name__)
BATCH = 1000

# norm_ownership.relationship_type → (canonical edge type, direction)
# direction "in": counterparty -> src ; "out": src -> counterparty
TYPE_MAP = {
    "shareholder": ("shareholder_of", "in"),
    "parent_co": ("parent_of", "in"),
    "ultimate_parent_co": ("ultimate_parent_of", "in"),
    "investee_co": ("investee_of", "out"),
}
GROUP_EDGE_TYPES = {"parent_of", "ultimate_parent_of"}


class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


async def _cif_to_master(cifs: List[str]) -> Dict[str, str]:
    out = {}
    async for m in db.master_companies.find({"cif_normalized": {"$in": cifs}},
                                            {"_id": 0, "cif_normalized": 1, "master_id": 1}):
        out[m["cif_normalized"]] = m["master_id"]
    return out


async def ensure_indexes() -> None:
    # Migration: the old unique key (src,dst,type,year) collapsed every EXTERNAL
    # counterparty (dst_master_id=None) of the same parent/year into a single row
    # (e.g. a holding with 34 unresolved investees showed only 1 in /connections).
    # The key now includes counterparty_key so each distinct counterparty gets its edge.
    try:
        await db.master_relationships.drop_index(
            "src_master_id_1_dst_master_id_1_relationship_type_1_year_1")
    except Exception:
        pass
    await db.master_relationships.create_index(
        [("src_master_id", 1), ("dst_master_id", 1), ("relationship_type", 1),
         ("year", 1), ("counterparty_key", 1)],
        unique=True, sparse=True, name="rel_unique_cpk")
    await db.master_relationships.create_index("src_master_id")
    await db.master_relationships.create_index("dst_master_id")
    await db.master_relationships.create_index("relationship_type")


async def rebuild_ownership_graph(heartbeat=None) -> Dict:
    """Materialize structural ownership edges + assign group_id via union-find."""
    await ensure_indexes()
    # Non-incremental phase-1 rebuild: replace structural edges from a single source.
    await db.master_relationships.delete_many({"source": "iberinform", "origin": "ownership"})

    uf = _UnionFind()
    stats = {"edges": 0, "resolved": 0, "external": 0, "by_type": {}}
    now = now_iso()
    buf: List[Dict] = []
    ops: List[UpdateOne] = []

    async def _flush(batch: List[Dict]):
        cifs = list({c for o in batch for c in (o.get("src_cif"), o.get("counterparty_cif")) if c})
        m = await _cif_to_master(cifs)
        local_ops = []
        for o in batch:
            mapping = TYPE_MAP.get(o.get("relationship_type"))
            if not mapping:
                continue
            etype, direction = mapping
            src_master = m.get(o["src_cif"])
            cp_cif = o.get("counterparty_cif")
            cp_master = m.get(cp_cif) if cp_cif else None
            if not src_master:
                continue
            # Disambiguate the counterparty even when it doesn't resolve to a master
            # (external): without this, N external investees of the same parent/year
            # collapse into one row on the unique index.
            cp_key = cp_cif or normalize_company_name(o.get("counterparty_name") or "")
            if not cp_key:
                continue
            if direction == "in":
                a, b = cp_master, src_master           # counterparty --etype--> src
            else:
                a, b = src_master, cp_master            # src --etype--> counterparty
            doc = {
                "src_master_id": a, "dst_master_id": b, "relationship_type": etype,
                "year": o.get("year"), "pct": o.get("pct"),
                "counterparty_name": o.get("counterparty_name"),
                "counterparty_key": cp_key,
                "counterparty_external": cp_master is None,
                "source": "iberinform", "origin": "ownership", "confidence": 0.95,
                "created_at": now,
            }
            stats["edges"] += 1
            stats["by_type"][etype] = stats["by_type"].get(etype, 0) + 1
            if cp_master is None:
                stats["external"] += 1
            else:
                stats["resolved"] += 1
                if etype in GROUP_EDGE_TYPES and a and b:
                    uf.union(a, b)
            local_ops.append(UpdateOne(
                {"src_master_id": a, "dst_master_id": b, "relationship_type": etype,
                 "year": o.get("year"), "counterparty_key": cp_key},
                {"$set": doc}, upsert=True))
        if local_ops:
            await db.master_relationships.bulk_write(local_ops, ordered=False)

    async for o in db.norm_ownership.find({}, {"_id": 0}):
        buf.append(o)
        if len(buf) >= BATCH:
            await _flush(buf)
            buf = []
    if buf:
        await _flush(buf)

    # Assign group_id (connected components over parent/ultimate-parent edges).
    groups: Dict[str, List[str]] = {}
    for node in list(uf.parent.keys()):
        groups.setdefault(uf.find(node), []).append(node)
    group_ops = []
    n_groups = 0
    # reset previous groups, then set new ones
    await db.master_companies.update_many({"ownership.group_id": {"$ne": None}},
                                          {"$set": {"ownership.group_id": None}})
    for root, members in groups.items():
        if len(members) < 2:
            continue
        n_groups += 1
        gid = f"grp_{root[3:]}" if root.startswith("mc_") else f"grp_{root}"
        for mid in members:
            group_ops.append(UpdateOne({"master_id": mid}, {"$set": {"ownership.group_id": gid}}))
    if group_ops:
        await db.master_companies.bulk_write(group_ops, ordered=False)
    stats["groups"] = n_groups
    return stats


# ── Q2: read side (this graph was write-only until now — nothing ever queried it) ──

async def relationships_for(master_id: str, limit: int = 50) -> List[Dict]:
    """All real relationships involving this company, either as source or target,
    with the counterparty's name resolved for readability. This is the actual
    control-graph consumption point the roadmap's Q2 was missing."""
    rows = await db.master_relationships.find(
        {"$or": [{"src_master_id": master_id}, {"dst_master_id": master_id}]}, {"_id": 0},
    ).sort("confidence", -1).limit(limit).to_list(limit)

    counterparts = {r["dst_master_id"] if r["src_master_id"] == master_id else r["src_master_id"]
                    for r in rows}
    names = {}
    if counterparts:
        async for m in db.master_companies.find(
                {"master_id": {"$in": list(counterparts)}},
                {"_id": 0, "master_id": 1, "identity.legal_name": 1}):
            names[m["master_id"]] = (m.get("identity") or {}).get("legal_name")

    out = []
    for r in rows:
        as_source = r["src_master_id"] == master_id
        counterparty = r["dst_master_id"] if as_source else r["src_master_id"]
        out.append({
            "counterparty_master_id": counterparty,
            "counterparty_name": names.get(counterparty) or r.get("counterparty_name"),
            "relationship_type": r["relationship_type"],
            "direction": "as_source" if as_source else "as_target",
            "pct": r.get("pct"), "year": r.get("year"),
            "confidence": r.get("confidence"), "source": r.get("source"), "origin": r.get("origin"),
            "basis": r.get("basis"),
        })
    return out


async def group_members(master_id: str) -> Dict:
    """Every company sharing this company's `ownership.group_id` (union-find result).
    Cheaper/more direct than walking edges when all you need is 'who's in the same group'."""
    company = await db.master_companies.find_one({"master_id": master_id}, {"_id": 0, "ownership.group_id": 1})
    gid = (company or {}).get("ownership", {}).get("group_id")
    if not gid:
        return {"master_id": master_id, "group_id": None, "members": []}
    members = await db.master_companies.find(
        {"ownership.group_id": gid, "master_id": {"$ne": master_id}},
        {"_id": 0, "master_id": 1, "identity.legal_name": 1},
    ).to_list(200)
    return {"master_id": master_id, "group_id": gid,
            "members": [{"master_id": m["master_id"], "name": (m.get("identity") or {}).get("legal_name")}
                        for m in members]}
