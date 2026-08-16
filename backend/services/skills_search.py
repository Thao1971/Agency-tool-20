"""Skill: Search (REQ-003) — lexical company search over companies_master.

Agency Tool produces intelligence; arroba renders it. This returns a stable
`workspace.blocks` envelope with a single `search_results` block. No UX concepts here.

Current phase: lexical search. Embeddings/semantic search arrive in Fase C.
"""

import re
import logging
from typing import Dict, List, Optional

from database import db
from services.data_layer.accessors import (
    name_of, sector_of, financials_latest, financials_history,
    revenue_of, employees_of,
)

logger = logging.getLogger(__name__)

CANDIDATE_CAP = 500       # pre-rank pool for lexical/semantic search at current scale
SCREEN_CAP = 2000         # pre-rank pool for a pure financial screen (no lexical query)

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


# ---- Financial / attribute accessors (REQ-004) --------------------------------

def _ebitda_of(doc: Dict) -> Optional[float]:
    f = financials_latest(doc) or {}
    v = f.get("ebitda")
    return float(v) if isinstance(v, (int, float)) else None


def _margin_of(doc: Dict) -> Optional[float]:
    f = financials_latest(doc) or {}
    m = f.get("ebitda_margin")
    if isinstance(m, (int, float)):
        return float(m)
    rev, eb = f.get("revenue"), f.get("ebitda")
    if isinstance(rev, (int, float)) and rev not in (0, None) and isinstance(eb, (int, float)):
        return round(eb / rev, 4)
    return None


def _growth_of(doc: Dict) -> Optional[float]:
    """Revenue YoY growth as a fraction. Prefer a stored value; else compute from history."""
    f = financials_latest(doc) or {}
    for k in ("revenue_growth_yoy", "revenue_growth"):
        v = f.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    hist = financials_history(doc)
    if len(hist) >= 2:
        cur, prev = hist[0].get("revenue"), hist[1].get("revenue")
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)) and prev not in (0, None):
            return round((cur - prev) / abs(prev), 4)
    return None


def _city_of(doc: Dict) -> Optional[str]:
    loc = doc.get("location") or {}
    return (loc.get("municipio") or loc.get("provincia")
            or doc.get("province_name") or doc.get("municipio") or doc.get("provincia"))


def _num_screen(filters: Dict) -> bool:
    """True if any financial/attribute predicate is set (→ screen mode)."""
    return any(filters.get(k) is not None for k in (
        "revenue_min", "revenue_max", "ebitda_min", "ebitda_max",
        "ebitda_margin_min", "ebitda_margin_max",
        "employees_min", "employees_max", "growth_min", "province"))


def _signal_badge(revenue: Optional[float], ebitda: Optional[float],
                  margin: Optional[float], growth: Optional[float]) -> Optional[str]:
    """Snake_case ES token consumed by Beta's HARDENING-032 chips: 'alto_crecimiento' / 'riesgo'."""
    if (ebitda is not None and ebitda < 0) or (margin is not None and margin < 0) \
            or (growth is not None and growth <= -0.20):
        return "riesgo"
    if growth is not None and growth >= 0.20:
        return "alto_crecimiento"
    return None


def _row_summary(doc: Dict) -> Dict:
    """Enriched financial summary for a result row (matches Beta's RowSummary contract)."""
    f = financials_latest(doc) or {}
    revenue = revenue_of(doc)
    ebitda = _ebitda_of(doc)
    margin = _margin_of(doc)
    growth = _growth_of(doc)
    return {
        "revenue": revenue,
        "ebitda": ebitda,
        "ebitda_margin": margin,
        "growth_pct": growth,
        "employees": employees_of(doc),
        "year": f.get("year"),
        "signal_score": doc.get("signal_score"),
        "signal_badge": _signal_badge(revenue, ebitda, margin, growth),
        "city": _city_of(doc),
    }


def _num_clauses(filters: Dict) -> List[Dict]:
    """Push financial predicates down to Mongo. Each field lives either in
    `financials.latest.*` (modern) or a legacy top-level field → `$or` over both."""
    clauses: List[Dict] = []

    def rng(modern: str, legacy: Optional[str], lo, hi):
        cond: Dict = {}
        if lo is not None:
            cond["$gte"] = lo
        if hi is not None:
            cond["$lte"] = hi
        if not cond:
            return
        opts = [{modern: cond}]
        if legacy:
            opts.append({legacy: cond})
        clauses.append({"$or": opts} if len(opts) > 1 else opts[0])

    rng("financials.latest.revenue", "revenue_latest",
        filters.get("revenue_min"), filters.get("revenue_max"))
    rng("financials.latest.ebitda", None,
        filters.get("ebitda_min"), filters.get("ebitda_max"))
    rng("financials.latest.ebitda_margin", None,
        filters.get("ebitda_margin_min"), filters.get("ebitda_margin_max"))
    rng("financials.latest.employees", "employees_latest",
        filters.get("employees_min"), filters.get("employees_max"))
    prov = filters.get("province")
    if prov:
        rx = {"$regex": re.escape(str(prov)), "$options": "i"}
        clauses.append({"$or": [
            {"location.provincia": rx}, {"location.municipio": rx}, {"province_name": rx},
        ]})
    return clauses


def _build_candidate_query(query: str, has_domain: bool, cluster_id=None,
                           filters: Optional[Dict] = None) -> Dict:
    filters = filters or {}
    q: Dict = {"merge_status": {"$ne": "merged"}}
    if has_domain:
        q["domain"] = {"$nin": [None, ""]}
    if cluster_id is not None:
        q["classification.cluster_id"] = cluster_id

    # Sector scoping (REQ-004b): restrict to a pre-resolved id set.
    ids = filters.get("master_company_ids") or []
    if ids:
        q["master_company_id"] = {"$in": list(ids)}

    and_clauses: List[Dict] = list(_num_clauses(filters))
    if query.strip():
        rx = {"$regex": re.escape(query.strip()), "$options": "i"}
        lexical = {"$or": [
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
        ]}
        and_clauses.append(lexical)

    if and_clauses:
        q["$and"] = and_clauses
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

    # --- Financial / attribute guards (REQ-004) — authoritative correctness gate.
    # A doc with the metric unknown does NOT pass a filter on that metric.
    def _fail_range(value, lo, hi) -> bool:
        if lo is None and hi is None:
            return False
        if value is None:
            return True
        if lo is not None and value < lo:
            return True
        if hi is not None and value > hi:
            return True
        return False

    if _fail_range(revenue_of(doc), filters.get("revenue_min"), filters.get("revenue_max")):
        return False
    if _fail_range(_ebitda_of(doc), filters.get("ebitda_min"), filters.get("ebitda_max")):
        return False
    if _fail_range(_margin_of(doc), filters.get("ebitda_margin_min"), filters.get("ebitda_margin_max")):
        return False
    if _fail_range(employees_of(doc), filters.get("employees_min"), filters.get("employees_max")):
        return False
    gmin = filters.get("growth_min")
    if gmin is not None:
        g = _growth_of(doc)
        if g is None or g < gmin:
            return False
    prov = filters.get("province")
    if prov:
        city = (_city_of(doc) or "").lower()
        if prov.lower() not in city:
            return False
    return True


async def search_companies(query: str, filters: Dict, page: int, page_size: int,
                           context: Optional[Dict] = None) -> Dict:
    from services.taxonomy_embeddings import is_ready, semantic_top

    context = context or {}
    use_signals = bool(context.get("use_signals"))
    has_domain = filters.get("has_domain", True)
    cluster_id = filters.get("cluster_id")
    is_screen = _num_screen(filters)
    # REQ-004b id bridge: taxonomy returns canonical master_id (mc_...), but this screener
    # reads the legacy `companies_master` keyed by UUID `master_company_id`. Translate
    # mc_* → UUID via cif_normalized so the {$in} sector scope actually intersects.
    raw_scope = filters.get("master_company_ids") or []
    if raw_scope:
        canon = [i for i in raw_scope if isinstance(i, str) and i.startswith("mc_")]
        legacy = [i for i in raw_scope if not (isinstance(i, str) and i.startswith("mc_"))]
        uuids: List[str] = []
        if canon:
            cifs: List[str] = []
            async for m in db.master_companies.find(
                    {"master_id": {"$in": canon}}, {"_id": 0, "cif_normalized": 1}):
                if m.get("cif_normalized"):
                    cifs.append(m["cif_normalized"])
            if cifs:
                async for d in db.companies_master.find(
                        {"cif_normalized": {"$in": cifs}}, {"_id": 0, "master_company_id": 1}):
                    if d.get("master_company_id"):
                        uuids.append(d["master_company_id"])
        resolved = uuids + legacy
        # non-empty request that resolves to nothing → scope to impossible (return empty, not all)
        filters = {**filters, "master_company_ids": resolved or ["__no_match__"]}
    mongo_q = _build_candidate_query(query, has_domain, cluster_id, filters)
    # A pure financial screen (no lexical query) sorts by revenue desc and scans a
    # bigger pool; lexical/semantic search keeps the confidence-ranked candidate pool.
    screen_only = is_screen and not query.strip()
    cap = SCREEN_CAP if is_screen else CANDIDATE_CAP
    sort_field = "financials.latest.revenue" if screen_only else "confidence_score"
    candidates = await db.companies_master.find(mongo_q, {"_id": 0}).sort(
        sort_field, -1
    ).limit(cap).to_list(cap)
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
        if screen_only:
            # rank by revenue desc; keep score in [0,1] for the UI (relative to top revenue)
            final = revenue_of(doc) or 0.0
        else:
            lex = _score(doc, web, query)
            final = round(0.6 * lex + 0.4 * sem.get(mid, 0.0), 4) if sem_ready else lex
            if use_signals:
                final = round(0.9 * final + 0.1 * ((doc.get("signal_score") or 0) / 100.0), 4)
        scored.append((final, doc, web))

    scored.sort(key=lambda x: -x[0])
    total = len(scored)

    start = (page - 1) * page_size
    page_items = scored[start:start + page_size]

    results = [{
        "master_company_id": doc.get("master_company_id"),
        "name": _resolve_name(doc, web),
        "sector": _resolve_sector(doc, web),
        "cif": doc.get("cif"),
        "score": (1.0 if screen_only else score),
        "summary": _row_summary(doc),
    } for score, doc, web in page_items]

    return {
        "workspace": {
            "blocks": [
                {"type": "search_results", "props": {
                    "query": query, "results": results,
                    "total": total, "page": page, "page_size": page_size,
                }}
            ]
        }
    }
