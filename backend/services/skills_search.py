"""Skill: Search (REQ-003) — lexical company search over companies_master.

Agency Tool produces intelligence; arroba renders it. This returns a stable
`workspace.blocks` envelope with a single `search_results` block. No UX concepts here.

Current phase: lexical search. Embeddings/semantic search arrive in Fase C.
"""

import re
import logging
from typing import Dict, List, Optional

from database import db
from services.data_layer.accessors import name_of, sector_of

logger = logging.getLogger(__name__)

CANDIDATE_CAP = 500  # pre-rank pool; fine at current scale (Atlas Search planned for 3.3M)

_WORD_RE = re.compile(r"[^a-z0-9áéíóúñü]+")


def _tokens(text: str) -> set:
    return {t for t in _WORD_RE.split((text or "").lower()) if t}


def _resolve_name(doc: Dict, web: Dict) -> Optional[str]:
    return name_of(doc)


def _resolve_sector(doc: Dict, web: Dict) -> Optional[str]:
    return sector_of(doc)


def _resolve_tags(web: Dict) -> List[str]:
    t = web.get("tags") or []
    return t if isinstance(t, list) else [t]


def _build_candidate_query(query: str, has_domain: bool, cluster_id=None) -> Dict:
    q: Dict = {"merge_status": {"$ne": "merged"}}
    if has_domain:
        q["domain"] = {"$nin": [None, ""]}
    if cluster_id is not None:
        q["classification.cluster_id"] = cluster_id
    if query.strip():
        rx = {"$regex": re.escape(query.strip()), "$options": "i"}
        q["$or"] = [
            {"legal_name": rx},
            {"normalized_name": rx},
            {"commercial_names": rx},
            {"aliases": rx},
            {"domain": rx},
            {"category_name": rx},
            {"sector": rx},
            {"classification.sector": rx},
            {"classification.cnae_label": rx},
            {"sources.web.company_name": rx},
            {"sources.web.category": rx},
            {"sources.web.tags": rx},
            {"sources.web.description": rx},
        ]
    return q


def _score(doc: Dict, web: Dict, query: str) -> float:
    confidence = float(doc.get("confidence_score") or 0.0)
    if not query.strip():
        return round(min(1.0, 0.5 + 0.5 * confidence), 4)

    q = query.strip().lower()
    name = (_resolve_name(doc, web) or "").lower()
    domain = (doc.get("domain") or "").lower()
    desc = (web.get("description") or "").lower()
    tags = " ".join(_resolve_tags(web)).lower()

    if name == q:
        base = 1.0
    elif name.startswith(q):
        base = 0.92
    elif q in name:
        base = 0.8
    else:
        nt, qt = _tokens(name), _tokens(q)
        overlap = len(nt & qt) / len(qt) if qt else 0.0
        base = 0.4 + 0.4 * overlap

    if q in domain:
        base = max(base, 0.7)
    if q in desc or q in tags:
        base = max(base, 0.55)

    return round(min(1.0, 0.85 * base + 0.15 * confidence), 4)


def _passes_filters(doc: Dict, web: Dict, filters: Dict) -> bool:
    cluster_id = filters.get("cluster_id")
    if cluster_id is not None:
        if (doc.get("classification") or {}).get("cluster_id") != cluster_id:
            return False
    cats = [c.lower() for c in (filters.get("category") or [])]
    if cats:
        sector = (_resolve_sector(doc, web) or "").lower()
        if not any(c in sector for c in cats):
            return False
    want_tags = [t.lower() for t in (filters.get("tags") or [])]
    if want_tags:
        have = {t.lower() for t in _resolve_tags(web)}
        if not any(t in h for t in want_tags for h in have):
            return False
    cnaes = [str(c) for c in (filters.get("cnae") or [])]
    if cnaes:
        doc_cnae = str(doc.get("cnae") or "")
        if doc_cnae not in cnaes:
            return False
    return True


async def search_companies(query: str, filters: Dict, page: int, page_size: int,
                           context: Optional[Dict] = None) -> Dict:
    from services.taxonomy_embeddings import is_ready, semantic_top

    context = context or {}
    use_signals = bool(context.get("use_signals"))
    has_domain = filters.get("has_domain", True)
    cluster_id = filters.get("cluster_id")
    mongo_q = _build_candidate_query(query, has_domain, cluster_id)
    candidates = await db.companies_master.find(mongo_q, {"_id": 0}).sort(
        "confidence_score", -1
    ).limit(CANDIDATE_CAP).to_list(CANDIDATE_CAP)
    pool = {d["master_company_id"]: d for d in candidates}

    q = query.strip()
    sem_ready = bool(q) and is_ready()
    sem: Dict[str, float] = {}
    if sem_ready:
        top = await semantic_top(q, 80)
        sem = dict(top)
        missing = [mid for mid, _ in top if mid not in pool]
        if missing:
            extra = await db.companies_master.find(
                {"master_company_id": {"$in": missing}, "merge_status": {"$ne": "merged"}},
                {"_id": 0},
            ).to_list(len(missing))
            for d in extra:
                if not has_domain or (d.get("domain") not in (None, "")):
                    pool[d["master_company_id"]] = d

    scored = []
    for mid, doc in pool.items():
        web = (doc.get("sources") or {}).get("web") or {}
        if not _passes_filters(doc, web, filters):
            continue
        lex = _score(doc, web, query)
        final = round(0.6 * lex + 0.4 * sem.get(mid, 0.0), 4) if sem_ready else lex
        if use_signals:
            final = round(0.9 * final + 0.1 * ((doc.get("signal_score") or 0) / 100.0), 4)
        scored.append((final, doc, web))

    scored.sort(key=lambda x: -x[0])

    start = (page - 1) * page_size
    page_items = scored[start:start + page_size]

    results = [{
        "master_company_id": doc.get("master_company_id"),
        "name": _resolve_name(doc, web),
        "sector": _resolve_sector(doc, web),
        "cif": doc.get("cif"),
        "score": score,
    } for score, doc, web in page_items]

    return {
        "workspace": {
            "blocks": [
                {"type": "search_results", "props": {"query": query, "results": results}}
            ]
        }
    }
