"""Navigable Control Graph (T3 — Ownership & Control Intelligence, transformacional).

Q2 (`ownership_graph.py`) exposed the control graph as single-hop lookups:
`relationships_for()` (direct neighbors of one company) and `group_members()` (same
`ownership.group_id`, from union-find over parent/ultimate_parent edges only). Both are
real and correct, but neither lets a PE see the WHOLE map — the multi-hop, multi-type
subgraph the roadmap calls "grafo de control navegable" (T3), which E6 (roll-up thesis)
and the sector fragmentation view need.

This module adds two bounded traversals over the SAME `master_relationships`
collection Q2 already writes (real ownership edges + Q2's `competitor_of`) — no new
data source, no new relationship type:

1. `traverse()`: BFS outward from one company across ALL relationship types, both
   directions, capped by `max_hops` AND `max_nodes`. The cap is a real engineering
   necessity, not an arbitrary choice — an uncapped BFS through `competitor_of` edges
   alone (same CNAE + size band) can fan out to hundreds of nodes from one company.
2. `sector_consolidation_map()`: given a real CNAE filter (the same
   `master_companies.classification` fields Q5's drill-down already queries), returns
   the subgraph of relationships that exist ONLY between companies already identified
   as being in that sector — i.e. "what does this sector's ownership/competitive map
   actually look like", the concrete input a roll-up thesis needs.

Both return `{nodes, edges, truncated}`. `truncated=True` means the real graph is
larger than the requested cap — the caller should narrow scope (fewer hops, a tighter
CNAE filter, or a smaller `limit_companies`), this module never silently drops part of
a graph without saying so.
"""

from typing import Dict, List, Optional, Set

from database import db

DEFAULT_MAX_HOPS = 2
DEFAULT_MAX_NODES = 150
DEFAULT_LIMIT_COMPANIES = 200
CNAE_FIELDS = ("cnae_code", "cnae_division", "cnae_section")


def _node_label(m: Dict) -> Dict:
    return {
        "master_id": m["master_id"],
        "name": (m.get("identity") or {}).get("legal_name"),
        "cnae_code": (m.get("classification") or {}).get("cnae_code"),
        "revenue": (m.get("financials") or {}).get("latest", {}).get("revenue"),
        "group_id": (m.get("ownership") or {}).get("group_id"),
    }


async def _company_labels(master_ids: List[str]) -> Dict[str, Dict]:
    if not master_ids:
        return {}
    out = {}
    async for m in db.master_companies.find(
        {"master_id": {"$in": master_ids}},
        {"_id": 0, "master_id": 1, "identity.legal_name": 1, "classification.cnae_code": 1,
         "financials.latest.revenue": 1, "ownership.group_id": 1},
    ):
        out[m["master_id"]] = _node_label(m)
    return out


def _edge_row(r: Dict) -> Dict:
    return {"src_master_id": r["src_master_id"], "dst_master_id": r["dst_master_id"],
            "relationship_type": r["relationship_type"], "pct": r.get("pct"),
            "year": r.get("year"), "confidence": r.get("confidence")}


async def traverse(master_id: str, max_hops: int = DEFAULT_MAX_HOPS,
                    max_nodes: int = DEFAULT_MAX_NODES,
                    relationship_types: Optional[List[str]] = None) -> Dict:
    """BFS outward from `master_id` over `master_relationships`, both directions,
    across all relationship types by default (ownership edges + Q2's competitor_of).
    Bounded by `max_hops` and `max_nodes` — never returns an unbounded graph."""
    visited: Set[str] = {master_id}
    frontier = [master_id]
    edges: List[Dict] = []
    seen_edge_keys: Set[tuple] = set()
    truncated = False

    for _hop in range(max_hops):
        if not frontier or len(visited) >= max_nodes:
            break
        q: Dict = {"$or": [{"src_master_id": {"$in": frontier}}, {"dst_master_id": {"$in": frontier}}]}
        if relationship_types:
            q["relationship_type"] = {"$in": relationship_types}
        rows = await db.master_relationships.find(q, {"_id": 0}).to_list(2000)

        next_frontier = []
        for r in rows:
            key = (r["src_master_id"], r["dst_master_id"], r["relationship_type"], r.get("year"))
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                edges.append(_edge_row(r))
            for node in (r["src_master_id"], r["dst_master_id"]):
                if node not in visited:
                    if len(visited) >= max_nodes:
                        truncated = True
                        continue
                    visited.add(node)
                    next_frontier.append(node)
        frontier = next_frontier

    labels = await _company_labels(list(visited))
    nodes = [labels.get(mid, {"master_id": mid, "name": None}) for mid in visited]
    return {"root_master_id": master_id, "max_hops": max_hops, "max_nodes": max_nodes,
            "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges),
            "truncated": truncated}


async def sector_consolidation_map(cnae_field: str, cnae_value: str,
                                    limit_companies: int = DEFAULT_LIMIT_COMPANIES) -> Dict:
    """Real ownership + competitor map restricted to companies already identified as
    being in this CNAE sector (same classification fields Q5's drill-down already
    uses). Answers "what does this sector's consolidation map look like" — the
    concrete input a roll-up thesis (E6) needs, not an external estimate."""
    if cnae_field not in CNAE_FIELDS:
        raise ValueError(f"cnae_field must be one of {CNAE_FIELDS}")
    q = {"status": "active", f"classification.{cnae_field}": cnae_value}
    total = await db.master_companies.count_documents(q)
    rows = await db.master_companies.find(
        q, {"_id": 0, "master_id": 1, "identity.legal_name": 1, "classification.cnae_code": 1,
            "financials.latest.revenue": 1, "ownership.group_id": 1},
    ).limit(limit_companies).to_list(limit_companies)
    master_ids = [r["master_id"] for r in rows]

    edges = []
    if master_ids:
        async for r in db.master_relationships.find(
            {"src_master_id": {"$in": master_ids}, "dst_master_id": {"$in": master_ids}}, {"_id": 0},
        ):
            edges.append(_edge_row(r))

    nodes = [_node_label(r) for r in rows]
    return {"cnae_field": cnae_field, "cnae_value": cnae_value,
            "companies_in_arroba_universe": total, "companies_included": len(nodes),
            "nodes": nodes, "edges": edges, "edge_count": len(edges),
            "truncated": total > limit_companies}
