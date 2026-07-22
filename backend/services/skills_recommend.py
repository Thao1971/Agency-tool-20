"""Skill: Recommend (REQ-005) — structural company recommendations.

Agency Tool answers "which companies are interesting"; arroba decides how to show them.
Flat contract: {recommendations:[{master_company_id,name,sector,score,reason,type}], confidence, lineage}

Two modes:
  - similar  : {master_company_id, context}  → companies similar to the seed
  - thesis   : {query, filters, context}      → companies matching criteria

Current phase: structural similarity (sector/category + size + signals). Embeddings/graph
proximity arrive in Fase C — same endpoint, contract immutable.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from database import db
from services.skills_search import (
    _resolve_name, _resolve_sector, _build_candidate_query, _score, CANDIDATE_CAP,
)
from services.data_layer.accessors import financials_latest

logger = logging.getLogger(__name__)


def _size_proximity(seed_emp, seed_rev, fin: Optional[Dict]) -> Tuple[float, Optional[str]]:
    if not fin:
        return 0.0, None
    best = 0.0
    label = None
    emp = fin.get("employees")
    if seed_emp and emp and seed_emp > 0 and emp > 0:
        best = max(best, 1 - min(1.0, abs(seed_emp - emp) / max(seed_emp, emp)))
        label = f"~{emp} empl."
    rev = fin.get("revenue")
    if seed_rev and rev and seed_rev > 0 and rev > 0:
        prox_rev = 1 - min(1.0, abs(seed_rev - rev) / max(seed_rev, rev))
        if prox_rev > best:
            best = prox_rev
            label = f"~{rev/1e6:.1f}M€ ventas"
    return best, label


def _has_signals(doc: Dict) -> bool:
    return bool(doc.get("last_enriched_at")) or len(doc.get("sources") or {}) > 1


async def _recommend_similar(seed: Dict, limit: int) -> Tuple[List[Dict], float]:
    web = (seed.get("sources") or {}).get("web") or {}
    seed_cat = _resolve_sector(seed, web)
    seed_fin = financials_latest(seed)
    seed_emp = (seed_fin or {}).get("employees")
    seed_rev = (seed_fin or {}).get("revenue")

    # Candidate peers: same sector/category first; size-based fallback if no category.
    candidates: List[Dict] = []
    if seed_cat:
        rx = {"$regex": f"^{re.escape(seed_cat)}$", "$options": "i"}
        candidates = await db.companies_master.find(
            {"$and": [
                {"$or": [{"classification.category": rx}, {"classification.sector": rx},
                         {"category_name": rx}, {"sources.web.category": rx}]},
                {"master_company_id": {"$ne": seed.get("master_company_id")}},
                {"merge_status": {"$ne": "merged"}},
            ]}, {"_id": 0},
        ).limit(80).to_list(80)

    if not candidates and seed_emp:
        fins = await db.iberinform_financials.find(
            {"employees": {"$gte": seed_emp * 0.5, "$lte": seed_emp * 2}}, {"_id": 0, "cif": 1},
        ).limit(80).to_list(80)
        cifs = [f["cif"] for f in fins if f.get("cif") and f["cif"] != seed.get("cif")]
        if cifs:
            candidates = await db.companies_master.find(
                {"cif": {"$in": cifs}, "master_company_id": {"$ne": seed.get("master_company_id")}},
                {"_id": 0},
            ).limit(80).to_list(80)

    scored = []
    for c in candidates:
        cweb = (c.get("sources") or {}).get("web") or {}
        cat = _resolve_sector(c, cweb)
        cfin = financials_latest(c)
        reasons = []
        score = 0.0
        if seed_cat and cat and cat.lower() == seed_cat.lower():
            score += 0.55
            reasons.append(f"mismo sector ({cat})")
        prox, label = _size_proximity(seed_emp, seed_rev, cfin)
        score += 0.30 * prox
        if prox > 0.6 and label:
            reasons.append(f"tamaño similar ({label})")
        if _has_signals(c):
            score += 0.10
            reasons.append("con señales disponibles")
        score += 0.05 * float(c.get("confidence_score") or 0.0)
        if score <= 0:
            continue
        reason = ", ".join(reasons)
        reason = reason[0].upper() + reason[1:] if reason else "Compañía relacionada"
        scored.append([min(1.0, round(score, 4)), c, cweb, reason])

    # Hybrid: blend structural score with semantic affinity + signal similarity (transparent)
    from services.taxonomy_embeddings import is_ready, similar_by_vector
    from services.engines.signal.master_signals import signal_similarity
    from services.knowledge_graph import neighbor_scores
    if scored:
        seed_id = seed.get("master_company_id")
        sem = await similar_by_vector(seed_id, [row[1].get("master_company_id") for row in scored]) if is_ready() else {}
        graph = await neighbor_scores(seed_id)  # empty dict => no-op fallback
        for row in scored:
            cand = row[1]
            cid = cand.get("master_company_id")
            s = sem.get(cid, 0.0)
            sig = signal_similarity(seed, cand)
            row[0] = round(0.6 * row[0] + 0.25 * s + 0.15 * sig, 4)
            g = graph.get(cid, 0.0)
            if g > 0:
                row[0] = round(min(1.0, row[0] + 0.10 * g), 4)
                if g > 0.5 and "grafo" not in (row[3] or ""):
                    row[3] = (row[3] + ", vinculada en el grafo") if row[3] else "Vinculada en el grafo"
            if s > 0.5:
                row[3] = (row[3] + ", afinidad semántica") if row[3] else "Afinidad semántica"

    scored.sort(key=lambda x: -x[0])
    recs = [{
        "master_company_id": c.get("master_company_id"),
        "name": _resolve_name(c, cweb),
        "sector": _resolve_sector(c, cweb),
        "score": s,
        "reason": reason,
        "type": "similar",
    } for s, c, cweb, reason in scored[:limit]]

    confidence = round(0.8 if (seed_cat and recs) else (0.5 if recs else 0.3), 2)
    return recs, confidence


async def _recommend_thesis(query: str, filters: Dict, limit: int) -> Tuple[List[Dict], float]:
    mongo_q = _build_candidate_query(query, filters.get("has_domain", True))
    candidates = await db.companies_master.find(mongo_q, {"_id": 0}).sort(
        "confidence_score", -1
    ).limit(CANDIDATE_CAP).to_list(CANDIDATE_CAP)

    scored = []
    for c in candidates:
        cweb = (c.get("sources") or {}).get("web") or {}
        scored.append((_score(c, cweb, query), c, cweb))
    scored.sort(key=lambda x: -x[0])

    recs = [{
        "master_company_id": c.get("master_company_id"),
        "name": _resolve_name(c, cweb),
        "sector": _resolve_sector(c, cweb),
        "score": s,
        "reason": "Coincide con los criterios de búsqueda",
        "type": "similar",
    } for s, c, cweb in scored[:limit]]

    confidence = round(0.7 if recs else 0.4, 2)
    return recs, confidence


async def recommend(master_company_id: Optional[str], query: str, filters: Dict, limit: int) -> Optional[Dict]:
    if master_company_id:
        seed = await db.companies_master.find_one({"master_company_id": master_company_id}, {"_id": 0})
        if not seed:
            return None
        recs, confidence = await _recommend_similar(seed, limit)
    else:
        recs, confidence = await _recommend_thesis(query, filters, limit)

    return {
        "recommendations": recs,
        "confidence": confidence,
        "lineage": {"source": "normalized"},
    }
